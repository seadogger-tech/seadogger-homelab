#!/usr/bin/env python3
"""Pre-run guard. Usage: guard.py '<ansible-playbook arguments>' (run in the playbook working directory).

Collects every -e/--extra-vars from the run arguments, then evaluates guard.yml with config.yml plus
those overrides, so the decision uses effective variable values, not the argument text.
Fails closed: any parse problem or guard failure exits non-zero.
"""
import os
import shlex
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
try:
    args = shlex.split(sys.argv[1])
except (IndexError, ValueError) as exc:
    sys.exit(f"refused: cannot parse arguments ({exc})")

extras = []
i = 0
while i < len(args):
    a = args[i]
    if a in ("-e", "--extra-vars"):
        if i + 1 >= len(args):
            sys.exit("refused: dangling -e")
        extras.append(args[i + 1])
        i += 2
        continue
    if a.startswith("--extra-vars="):
        extras.append(a.split("=", 1)[1])
    elif a.startswith("-e") and not a.startswith("--") and len(a) > 2:
        extras.append(a[2:])
    i += 1

cmd = ["ansible-playbook", "-i", "localhost,", "-c", "local", os.path.join(here, "guard.yml"), "-e", "@config.yml"]
for e in extras:
    cmd += ["-e", e]
sys.exit(subprocess.call(cmd))
