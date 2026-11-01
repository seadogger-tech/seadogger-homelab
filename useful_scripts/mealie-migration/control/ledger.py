"""Host-owned, bounded SQLite journal. Never placed on the application volume.

Filesystem/fsync behavior, anti-rollback host tombstones and quotas are deployment
prerequisites. SQLite cannot establish those properties from a filename.
"""

from __future__ import annotations

import fcntl
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

from contract import Binding, Denied, SLUG, decode, encode, exact_keys, require


ACTIVE = ("PREPARED", "RUNNING_UNUSED", "SPENT", "STOPPING")
TERMINAL = ("QUIESCENT_RETAINED", "FAILED_UNCERTAIN_RETAINED")


def checked_state(raw: bytes) -> dict:
    state = decode(raw)
    exact_keys(state, {"phase", "sequence", "launchConsumed", "importSpent", "readSpent", "slug",
                       "attempt", "reason", "inspectionAllowed"})
    require(state["phase"] in ACTIVE + TERMINAL and type(state["sequence"]) is int
            and state["sequence"] >= 0 and state["inspectionAllowed"] is False, "LEDGER_CORRUPT")
    require(all(type(state[key]) is bool for key in ("launchConsumed", "importSpent", "readSpent")), "LEDGER_CORRUPT")
    require(state["slug"] is None or (isinstance(state["slug"], str) and 0 < len(state["slug"]) <= 250
                                     and bool(SLUG.fullmatch(state["slug"]))), "LEDGER_CORRUPT")
    require(state["attempt"] is None or (isinstance(state["attempt"], str) and len(state["attempt"]) == 32
                                        and all(c in "0123456789abcdef" for c in state["attempt"])), "LEDGER_CORRUPT")
    require(not state["importSpent"] or (state["launchConsumed"] and state["attempt"] is not None), "LEDGER_CORRUPT")
    require(not state["readSpent"] or (state["importSpent"] and state["slug"] is not None), "LEDGER_CORRUPT")
    require(state["slug"] is None or state["importSpent"], "LEDGER_CORRUPT")
    require(state["phase"] not in ("RUNNING_UNUSED", "SPENT") or state["launchConsumed"], "LEDGER_CORRUPT")
    require(state["phase"] != "RUNNING_UNUSED" or not state["importSpent"], "LEDGER_CORRUPT")
    require(state["phase"] != "SPENT" or state["importSpent"], "LEDGER_CORRUPT")
    require(state["reason"] is None or (isinstance(state["reason"], str) and len(state["reason"]) <= 64
                                       and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_" for c in state["reason"])), "LEDGER_CORRUPT")
    return state


def protected_directory(path: Path) -> None:
    require(path.is_absolute() and path.resolve() == path, "UNSAFE_LEDGER_PATH")
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "UNSAFE_LEDGER_DIRECTORY")
    for parent in path.parents:
        info = parent.stat()
        require(not (info.st_mode & 0o022) and info.st_uid in (0, os.geteuid()), "UNSAFE_LEDGER_PARENT")


class Ledger:
    """One process owns the journal; every transition commits before returning."""

    @classmethod
    def initialize(cls, directory: Path) -> None:
        """Separate authorized installation step; refuses existing files/records."""
        protected_directory(directory)
        path = directory / "runs.sqlite"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=EXTRA")
            connection.execute("PRAGMA page_size=4096")
            connection.execute("PRAGMA max_page_count=6144")  # 24MiB DB + rollback journal within 64MiB host quota.
            connection.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, epoch TEXT UNIQUE NOT NULL, "
                               "binding BLOB NOT NULL, state BLOB NOT NULL)")
            connection.execute("PRAGMA user_version=1")
            connection.commit()
        finally:
            connection.close()
        fd = os.open(directory, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def __init__(self, directory: Path):
        protected_directory(directory)
        path = directory / "runs.sqlite"
        self.fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600, "UNSAFE_LEDGER_FILE")
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.connection = sqlite3.connect(f"file:{path}?mode=rw", uri=True, isolation_level=None,
                                          check_same_thread=False, timeout=0.2)
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.execute("PRAGMA synchronous=EXTRA")
        self.connection.execute("PRAGMA max_page_count=6144")
        require(self.connection.execute("PRAGMA user_version").fetchone() == (1,), "LEDGER_VERSION")
        require(self.connection.execute("PRAGMA quick_check").fetchall() == [("ok",)], "LEDGER_CORRUPT")
        self.poisoned = False

    @contextmanager
    def transaction(self):
        require(not self.poisoned, "LEDGER_UNAVAILABLE")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield
            self.connection.execute("COMMIT")
        except sqlite3.Error:
            self.poisoned = True
            try:
                self.connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise Denied("LEDGER_UNAVAILABLE") from None
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def recover(self) -> list[tuple[Binding, dict]]:
        """Any daemon restart burns active runs, including an unused import."""
        interrupted = []
        with self.transaction():
            for run_id, epoch, raw_binding, raw_state in self.connection.execute("SELECT run_id,epoch,binding,state FROM runs"):
                binding = Binding.parse(raw_binding)
                require(binding.value["runId"] == run_id and binding.value["epoch"] == epoch, "LEDGER_CORRUPT")
                state = checked_state(raw_state)
                if state["phase"] in ACTIVE:
                    state.update(phase="FAILED_UNCERTAIN_RETAINED", reason="CONTROLLER_RESTART",
                                 sequence=state["sequence"] + 1)
                    self.connection.execute("UPDATE runs SET state=? WHERE run_id=?", (encode(state), run_id))
                    interrupted.append((binding, state))
        return interrupted

    def create(self, binding: Binding) -> dict:
        value = binding.value
        state = {"phase": "PREPARED", "sequence": 0, "launchConsumed": False,
                 "importSpent": False, "readSpent": False, "slug": None, "attempt": None,
                 "reason": None, "inspectionAllowed": False}
        with self.transaction():
            require(self.connection.execute("SELECT 1 FROM runs WHERE run_id=? OR epoch=?",
                                            (value["runId"], value["epoch"])).fetchone() is None, "RUN_REUSED")
            self.connection.execute("INSERT INTO runs VALUES (?,?,?,?)",
                                    (value["runId"], value["epoch"], binding.raw, encode(state)))
        return state

    def read(self, binding: Binding) -> dict:
        require(not self.poisoned, "LEDGER_UNAVAILABLE")
        try:
            row = self.connection.execute("SELECT binding,state FROM runs WHERE run_id=?",
                                          (binding.value["runId"],)).fetchone()
        except sqlite3.Error:
            self.poisoned = True
            raise Denied("LEDGER_UNAVAILABLE") from None
        require(row is not None and row[0] == binding.raw, "BINDING_MISMATCH")
        return checked_state(row[1])

    def change(self, binding: Binding, expected: dict, **updates) -> dict:
        with self.transaction():
            state = self.read(binding)
            require(state == expected, "STATE_CHANGED")
            state.update(updates, sequence=state["sequence"] + 1)
            checked_state(encode(state))
            self.connection.execute("UPDATE runs SET state=? WHERE run_id=?",
                                    (encode(state), binding.value["runId"]))
        return state

    def close(self) -> None:
        self.connection.close()
        os.close(self.fd)
