#!/usr/bin/env python3
"""
fetch_hdhomerun_guide.py

A small utility that:

1. Retrieves the HDHomeRun device discovery JSON from a configurable URL.
2. Extracts the ``DeviceAuth`` token from the discovery payload.
3. Calls the HDHomeRun public guide API using that token.
4. Stores the resulting XML guide locally (either in the current directory or at a user‑specified path).

The script is fully configurable via command‑line arguments and includes a helpful ``--help`` output.
"""

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------


def fetch_url(url: str) -> bytes:
    """Fetch raw bytes from a URL, raising a clear exception on failure."""
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to fetch {url!r}: {e.reason}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error while fetching {url!r}: {e}") from e


def get_device_auth(discover_json: bytes) -> str:
    """Parse the discover JSON and return the DeviceAuth token."""
    try:
        data = json.loads(discover_json.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from discover endpoint: {e}") from e

    if "DeviceAuth" not in data:
        raise RuntimeError("DeviceAuth field not found in discover JSON")
    return data["DeviceAuth"]


def write_local(path: pathlib.Path, content: bytes):
    """Write content to a local file, creating parent directories as needed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    except Exception as e:
        raise RuntimeError(f"Unable to write XML to {path}: {e}") from e


# ----------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch HDHomeRun guide XML and store it locally."
    )
    parser.add_argument(
        "--discover-url",
        default="http://192.168.1.70/discover.json",
        help="URL to the HDHomeRun discover.json endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--target",
        required=False,
        default=None,
        help=(
            "Filesystem path where the XML guide should be saved. "
            "If omitted, the guide is saved as ``xmltv.xml`` in the current working directory."
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 1️⃣ Retrieve discover.json
    discover_bytes = fetch_url(args.discover_url)

    # 2️⃣ Extract DeviceAuth token
    device_auth = get_device_auth(discover_bytes)

    # 3️⃣ Request the guide XML
    guide_url = f"https://api.hdhomerun.com/api/guide?DeviceAuth={device_auth}"
    guide_xml = fetch_url(guide_url)

    # 4️⃣ Store the XML
    if args.target is None:
        # No target supplied – save to current directory as xmltv.xml
        default_path = pathlib.Path.cwd() / "xmltv.xml"
        write_local(default_path, guide_xml)
        print(f"Guide saved to default location: {default_path}")
    else:
        # Save to user‑specified path
        write_local(pathlib.Path(args.target), guide_xml)
        print(f"Guide successfully saved to: {args.target}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
