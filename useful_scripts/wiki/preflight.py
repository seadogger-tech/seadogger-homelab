#!/usr/bin/env python3
"""Stage the exact public wiki payload and compare it with the live wiki."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from check_publication import check


CORE = Path(__file__).resolve().parents[2]
WIKI_URL = "https://github.com/seadogger-tech/seadogger-homelab.wiki.git"
IMAGE_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".svg"})


def included_file(relative):
    if relative.name == ".DS_Store" or relative.parts[0] == "tools":
        return False
    if relative == Path("images/Logo.key"):
        return False  # Editable artwork source, not a rendered wiki image.
    if len(relative.parts) == 1 and relative.suffix == ".md":
        return True
    if relative.parts[0] == "memory_bank" and relative.suffix == ".md":
        return True
    if relative.parts[0] == "images" and relative.suffix.lower() in IMAGE_SUFFIXES:
        return True
    raise ValueError(f"Unexpected wiki source file: {relative}")


def stage(source, destination):
    if not source.is_dir():
        raise ValueError(f"Missing wiki source directory: {source}")
    files = []
    for path in source.rglob("*"):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(source)
        if included_file(relative):
            if path.is_symlink():
                raise ValueError(f"Wiki payload must not contain a symlink: {relative}")
            files.append(relative)
    destination.mkdir(parents=True, exist_ok=False)
    for relative in sorted(files):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=CORE / "docs/wiki")
    parser.add_argument("--published", type=Path, help="existing clone of the live wiki master branch")
    parser.add_argument("--payload", type=Path, help="new directory to keep the reviewed payload for syncing")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="wiki-preflight-") as temporary:
        temporary = Path(temporary)
        published = args.published or temporary / "published"
        if args.published is None:
            subprocess.run(
                ["git", "clone", "--quiet", WIKI_URL, str(published)],
                check=True,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        if not published.is_dir():
            parser.error(f"Missing published wiki directory: {published}")

        payload = args.payload or temporary / "payload"
        count = stage(args.source, payload)
        exceptions_path = Path(__file__).with_name("publication-exceptions.json")
        exceptions = json.loads(exceptions_path.read_text())
        errors = check(payload, published, exceptions)
        if errors:
            for error in errors:
                print(error)
            raise SystemExit(1)
        print(f"Wiki preflight passed: {count} reviewed files staged.")


if __name__ == "__main__":
    main()
