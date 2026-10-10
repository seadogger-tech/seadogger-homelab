#!/usr/bin/env python3
"""Check the delta that a Core wiki sync would publish."""

import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path


MIN_LARGE_PAGE_LINES = 100
MAX_REDUCTION = 0.5
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
EVIDENCE_PATTERNS = (
    ("personal checkout path", re.compile(r"/Users/[A-Za-z0-9._-]+/")),
    ("account-bearing S3 bucket", re.compile(r"s3://[a-z0-9.-]*\d{12}[a-z0-9.-]*/", re.I)),
    ("dated operational evidence heading", re.compile(
        r"^#{1,6}\s+.*\b(?:staging|production|incident|validation)\s+evidence\b.*\b20\d{2}-\d{2}-\d{2}\b", re.I
    )),
    ("operational result table", re.compile(r"^\|\s*Check\s*\|\s*Observed result\s*\|", re.I)),
)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_unclosed_fence(text):
    opened = None
    for line in text.splitlines():
        match = FENCE.match(line)
        if not match:
            continue
        marker = match.group(1)
        if opened is None:
            opened = marker
        elif marker[0] == opened[0] and len(marker) >= len(opened):
            opened = None
    return opened is not None


def added_lines(previous, source):
    before = previous.splitlines() if previous is not None else []
    after = source.splitlines()
    for operation, _, _, start, end in difflib.SequenceMatcher(
        None, before, after, autojunk=False
    ).get_opcodes():
        if operation in ("insert", "replace"):
            for index in range(start, end):
                yield index + 1, after[index]


def reduction_allowed(name, previous, source, exceptions):
    entry = exceptions.get(name)
    return (
        isinstance(entry, dict)
        and bool(entry.get("reason"))
        and entry.get("published_sha256") == digest(previous)
        and entry.get("source_sha256") == (digest(source) if source is not None else None)
    )


def check(source_dir, published_dir, exceptions):
    errors = []
    paths = {path.relative_to(source_dir) for path in source_dir.rglob("*.md")}
    paths.update(path.relative_to(published_dir) for path in published_dir.rglob("*.md"))

    for relative in sorted(paths):
        source_path = source_dir / relative
        published_path = published_dir / relative
        source = source_path.read_text() if source_path.exists() else None
        previous = published_path.read_text() if published_path.exists() else None
        name = relative.as_posix()

        if source is not None and has_unclosed_fence(source):
            errors.append(f"{name}: unclosed Markdown fence")

        if source == previous:
            continue

        if previous is not None and len(previous.splitlines()) >= MIN_LARGE_PAGE_LINES:
            new_size = len(source.splitlines()) if source is not None else 0
            if new_size < len(previous.splitlines()) * MAX_REDUCTION:
                if not reduction_allowed(name, previous, source, exceptions):
                    errors.append(
                        f"{name}: large reduction ({len(previous.splitlines())} to {new_size} lines); "
                        "record an exact-hash exception with a reason if intentional"
                    )

        if source is None:
            continue

        for line_number, line in added_lines(previous, source):
            for description, pattern in EVIDENCE_PATTERNS:
                if pattern.search(line):
                    errors.append(
                        f"{name}:{line_number}: {description}; use a public placeholder "
                        "and keep live receipts private"
                    )

    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Core docs/wiki source directory")
    parser.add_argument("published", type=Path, help="cloned default-branch wiki directory")
    parser.add_argument(
        "--exceptions",
        type=Path,
        default=Path(__file__).with_name("publication-exceptions.json"),
    )
    args = parser.parse_args()
    if not args.source.is_dir() or not args.published.is_dir():
        parser.error("source and published must both be directories")
    exceptions = json.loads(args.exceptions.read_text()) if args.exceptions.exists() else {}
    errors = check(args.source, args.published, exceptions)
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("Wiki publication preflight passed.")


if __name__ == "__main__":
    main()
