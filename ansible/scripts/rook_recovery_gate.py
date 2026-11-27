#!/usr/bin/env python3
"""Allow only the B3 Ceph rollback states; read one health/OSD JSON fixture on stdin."""
import json
import sys

ALLOWED_CODES = {
    "MDS_CACHE_OVERSIZED",
    "MDS_SLOW_REQUEST",
    "MDS_SLOW_METADATA_IO",
    "MDS_TRIM",
    "SLOW_OPS",
    "MDS_INSUFFICIENT_STANDBY",
    "FS_DEGRADED",
    "OSD_DOWN",
    "PG_DEGRADED",
    "RECENT_CRASH",
}


def recovery_refusal(document):
    health = document.get("health", {})
    osd = document.get("osd", {})
    status = health.get("status")
    checks = health.get("checks", {})
    if not isinstance(checks, dict):
        return "health checks must be a JSON object"
    codes = sorted(checks)
    try:
        num_osds = int(osd["num_osds"])
        num_up_osds = int(osd["num_up_osds"])
    except (KeyError, TypeError, ValueError):
        return f"invalid OSD stat JSON; raised codes: {', '.join(codes) or '(none)'}"
    down = num_osds - num_up_osds
    reasons = []
    if status == "HEALTH_ERR":
        reasons.append("status is HEALTH_ERR")
    unknown = sorted(set(codes) - ALLOWED_CODES)
    if unknown:
        reasons.append(f"unlisted check codes: {', '.join(unknown)}")
    if down < 0:
        reasons.append(f"invalid OSD count ({num_up_osds} up of {num_osds})")
    elif down > 1:
        reasons.append(f"{down} OSDs are down (maximum one)")
    if reasons:
        return f"{'; '.join(reasons)}; raised codes: {', '.join(codes) or '(none)'}"
    return None


def main():
    try:
        document = json.load(sys.stdin)
        if not isinstance(document, dict):
            raise ValueError("fixture root must be an object")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"refused: invalid recovery fixture JSON ({exc})", file=sys.stderr)
        return 2
    refusal = recovery_refusal(document)
    if refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
