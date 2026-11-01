"""Authenticated local transport to the separately implemented Operations broker.

No shell commands, Kubernetes clients, arbitrary URLs, process names or fallback
executables are accepted. The broker must itself enforce every operation against
the protected target map, host tombstones and independent watchdog.
"""

from __future__ import annotations

import socket
import stat
import struct
import time
import uuid
from pathlib import Path

from contract import Binding, Denied, decode, encode, require


OPERATIONS = frozenset({"inspect_binding", "claim_writer", "arm_once", "read_run_state", "close_and_stop",
                        "force_fence", "observe_quiescence", "describe_retained_set", "capture_request",
                        "forward_once", "release_response", "deny_request", "next_request"})


def boottime_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME)


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()


class SocketAdapter:
    """One request per connection, peer authenticated, bounded, without retries."""

    def __init__(self, path: Path, expected_uid: int = 0):
        require(path.is_absolute() and path.resolve() == path, "ADAPTER_PATH")
        self.path = path
        self.expected_uid = expected_uid
        for parent in path.parents:
            info = parent.stat()
            require(info.st_uid == 0 and not info.st_mode & 0o022, "ADAPTER_PARENT")
        info = path.stat()
        require(stat.S_ISSOCK(info.st_mode) and info.st_uid == expected_uid
                and not info.st_mode & 0o007, "ADAPTER_SOCKET")
        self.identity = info.st_dev, info.st_ino

    def call(self, operation: str, binding: Binding, sequence: int, payload: dict | None = None,
             timeout: float = 0.2) -> dict:
        require(operation in OPERATIONS, "ADAPTER_OPERATION")
        require(0 < timeout <= 295, "ADAPTER_TIMEOUT")
        value = binding.value
        require(boot_id() == value["hostBootId"], "BOOT_CHANGED")
        info = self.path.stat()
        require((info.st_dev, info.st_ino) == self.identity, "ADAPTER_REPLACED")
        request_id = uuid.uuid4().hex
        request = {"version": "OCE63-ADAPTER-1", "operation": operation, "requestId": request_id,
                   "bindingHash": binding.hash, "runId": value["runId"], "epoch": value["epoch"],
                   "hostBootId": value["hostBootId"], "targetBootId": value["targetBootId"],
                   "configDigest": value["configDigest"], "sequence": sequence, "payload": payload or {}}
        sent = boottime_ns()
        deadline = sent + int(timeout * 1e9)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.settimeout(timeout)
                channel.connect(str(self.path))
                _, uid, _ = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                require(uid == self.expected_uid, "ADAPTER_PEER")
                message = encode(request)
                require(len(message) <= 4_194_304, "ADAPTER_REQUEST_LIMIT")
                self._remaining(channel, deadline)
                channel.sendall(len(message).to_bytes(4, "big") + message)
                size = int.from_bytes(self._read(channel, 4, deadline), "big")
                require(0 < size <= 4_194_304, "ADAPTER_RESPONSE_LIMIT")
                response = decode(self._read(channel, size, deadline), 4_194_304)
        except (OSError, ValueError, TypeError, KeyError):
            raise Denied("ADAPTER_UNCERTAIN") from None
        require(isinstance(response, dict), "ADAPTER_RECEIPT")
        for key in ("version", "operation", "requestId", "bindingHash", "runId", "epoch", "hostBootId",
                    "targetBootId", "configDigest", "sequence"):
            require(response.get(key) == request[key], "ADAPTER_RECEIPT_BINDING")
        require(response.get("producerDigest") == value["components"]["adapter"], "ADAPTER_VERSION")
        observed = response.get("observedNs")
        require(type(observed) is int and sent <= observed <= boottime_ns(), "ADAPTER_STALE")
        require(response.get("outcome") in ("VERIFIED", "ACKNOWLEDGED", "REJECTED", "UNKNOWN"), "ADAPTER_OUTCOME")
        require(isinstance(response.get("observations"), dict), "ADAPTER_OBSERVATIONS")
        return response

    @staticmethod
    def _remaining(channel: socket.socket, deadline: int) -> None:
        remaining = (deadline - boottime_ns()) / 1e9
        require(remaining > 0, "ADAPTER_TIMEOUT")
        channel.settimeout(remaining)

    @staticmethod
    def _read(channel: socket.socket, size: int, deadline: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            SocketAdapter._remaining(channel, deadline)
            part = channel.recv(size - len(chunks))
            require(bool(part), "ADAPTER_DISCONNECTED")
            chunks.extend(part)
        return bytes(chunks)


def verified(receipt: dict, *observations: str) -> dict:
    require(receipt["outcome"] == "VERIFIED", "ADAPTER_NOT_VERIFIED")
    values = receipt["observations"]
    require(all(values.get(name) == "VERIFIED_TRUE" for name in observations), "ADAPTER_GAP")
    return values
