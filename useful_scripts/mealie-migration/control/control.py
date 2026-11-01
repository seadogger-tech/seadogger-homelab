#!/usr/bin/env python3
"""Explicit entrypoints; default invocation never initializes or runs a target."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

from adapter import SocketAdapter, verified
from contract import BODY_LIMIT, Binding, Denied, require, verify_image_bytes
from controller import Controller
from ledger import Ledger


def bounded_file(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(BODY_LIMIT + 1)
    require(len(raw) <= BODY_LIMIT, "ARTIFACT_LIMIT")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Check packet shape only; grants no execution authority")
    validate.add_argument("packet", type=Path)
    image = commands.add_parser("image-identity", help="Verify previously authorized raw E1 bytes; no fetching")
    for name in ("index", "manifest", "config"):
        image.add_argument(name, type=Path)
    image.add_argument("--config-digest", required=True)
    initialize = commands.add_parser("initialize-ledger", help="Separately authorized host installation; refuses an existing ledger")
    initialize.add_argument("directory", type=Path)
    run = commands.add_parser("supervise", help="Explicit authorized runtime only, using an enforcing Operations broker")
    run.add_argument("--packet", required=True, type=Path)
    run.add_argument("--ledger-directory", required=True, type=Path)
    run.add_argument("--broker-socket", required=True, type=Path)
    run.add_argument("--execute-authorized-run", required=True, action="store_true")
    args = parser.parse_args()
    controller = None
    ledger = None
    try:
        if args.command == "validate":
            binding = Binding.parse(bounded_file(args.packet))
            result = {"shape": "VALID", "bindingHash": binding.hash, "authority": "NOT_VERIFIED", "ready": False}
        elif args.command == "image-identity":
            result = verify_image_bytes(bounded_file(args.index), bounded_file(args.manifest),
                                        bounded_file(args.config), args.config_digest)
        elif args.command == "initialize-ledger":
            Ledger.initialize(args.directory)
            result = {"ledger": "INITIALIZED", "runtime": "CLOSED", "durability": "REQUIRES_HOST_VERIFICATION"}
        else:
            binding = Binding.parse(bounded_file(args.packet))
            adapter = SocketAdapter(args.broker_socket)
            ledger = Ledger(args.ledger_directory)
            controller = Controller(ledger, adapter, binding)

            def stop(signum, frame):
                raise KeyboardInterrupt

            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            controller.prepare()
            controller.launch()
            while not controller.stop_event.is_set():
                state = controller.status()
                receipt = adapter.call("next_request", binding, state["sequence"])
                verified(receipt, "channelBound")
                handle = receipt.get("handle")
                if handle is not None:
                    controller.handle(handle)
                else:
                    controller.stop_event.wait(0.05)
            state = controller.status()
            result = {"phase": state["phase"], "inspectionAllowed": False,
                      "applicationConsistency": "UNPROVEN"}
        print(json.dumps(result, sort_keys=True))
        if args.command == "supervise":
            return 0 if result["phase"] == "QUIESCENT_RETAINED" else 2
        return 0
    except (Denied, OSError, ValueError, TypeError, KeyError, AttributeError, KeyboardInterrupt):
        if controller is not None:
            controller.close("ENTRYPOINT_FAILURE")
        # Do not leak raw receipts, credentials, targets, paths or exception strings.
        print(json.dumps({"outcome": "CLOSED", "reason": "INPUT_OR_CONTROL_FAILURE", "ready": False}))
        return 2
    finally:
        if controller is not None and controller.timer is not None:
            controller.stop_event.set()
            controller.timer.join(timeout=1)
        if ledger is not None:
            ledger.close()


if __name__ == "__main__":
    sys.exit(main())
