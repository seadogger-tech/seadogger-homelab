#!/usr/bin/env python3
"""
fetch_hdhomerun_guide.py

A small utility that:

1. Retrieves the HDHomeRun device discovery JSON from a configurable URL.
2. Extracts the ``DeviceAuth`` token from the discovery payload.
3. Calls the HDHomeRun public XMLTV guide API using that token or Email+DeviceIDs.
4. Stores the resulting XMLTV guide locally (either in the current directory or at a user‑specified path).

The script is fully configurable via command‑line arguments and includes a helpful ``--help`` output.

Updated to use the official /api/xmltv endpoint (supports 14-day guide data with HDHomeRun DVR subscription).
"""

import argparse
import gzip
import json
import pathlib
import sys
import urllib.error
import urllib.request

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------


def fetch_url(url: str, accept_gzip: bool = False) -> bytes:
    """Fetch raw bytes from a URL, raising a clear exception on failure.

    Args:
        url: The URL to fetch
        accept_gzip: If True, add Accept-Encoding: gzip header and decompress response
                     If False, explicitly request uncompressed with Accept-Encoding: identity
    """
    try:
        req = urllib.request.Request(url)
        if accept_gzip:
            req.add_header('Accept-Encoding', 'gzip')
        else:
            # Explicitly request uncompressed content (important for compatibility)
            req.add_header('Accept-Encoding', 'identity')

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()

            # Decompress if response is gzipped
            if accept_gzip and resp.headers.get('Content-Encoding') == 'gzip':
                data = gzip.decompress(data)

            return data
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
        description="Fetch HDHomeRun XMLTV guide and store it locally."
    )
    parser.add_argument(
        "--discover-url",
        default="http://192.168.1.70/discover.json",
        help="URL to the HDHomeRun discover.json endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--email",
        help="Email address for HDHomeRun DVR account (recommended method for accessing guide)",
    )
    parser.add_argument(
        "--device-ids",
        help="Comma-separated list of HDHomeRun Device IDs (use with --email)",
    )
    parser.add_argument(
        "--target",
        required=False,
        default=None,
        help=(
            "Filesystem path where the XMLTV guide should be saved. "
            "If omitted, the guide is saved as ``xmltv.xml`` in the current working directory."
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Determine which authentication method to use
    if args.email and args.device_ids:
        # Use Email + DeviceIDs method (recommended, added Oct 2025)
        print("Using Email + DeviceIDs authentication method")
        guide_url = f"https://api.hdhomerun.com/api/xmltv?Email={args.email}&DeviceIDs={args.device_ids}"
        # Request uncompressed XML for compatibility with Jellyfin
        guide_xml = fetch_url(guide_url, accept_gzip=False)
    else:
        # Use legacy DeviceAuth method
        print("Using legacy DeviceAuth method (fetching from discover.json)")

        # 1️⃣ Retrieve discover.json
        discover_bytes = fetch_url(args.discover_url)

        # 2️⃣ Extract DeviceAuth token
        device_auth = get_device_auth(discover_bytes)

        # 3️⃣ Request the guide XMLTV (uncompressed for compatibility)
        guide_url = f"https://api.hdhomerun.com/api/xmltv?DeviceAuth={device_auth}"
        guide_xml = fetch_url(guide_url, accept_gzip=False)

    # 4️⃣ Store the XMLTV
    if args.target is None:
        # No target supplied – save to current directory as xmltv.xml
        default_path = pathlib.Path.cwd() / "xmltv.xml"
        write_local(default_path, guide_xml)
        print(f"XMLTV guide saved to default location: {default_path}")
    else:
        # Save to user‑specified path
        write_local(pathlib.Path(args.target), guide_xml)
        print(f"XMLTV guide successfully saved to: {args.target}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
