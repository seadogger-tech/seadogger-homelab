#!/usr/bin/env python3
"""Pre-run guard and launcher. Usage: guard.py '<ansible-playbook arguments>' (run in the playbook working directory).

Parses the argument string ONCE with shlex. Rejects ambiguous option spellings, collects every
-e/--extra-vars, evaluates guard.yml with config.yml plus those overrides, and only if that passes
execs ansible-playbook with the same parsed list. So the guard and the real run see identical arguments.
Fails closed: any parse problem or guard failure exits non-zero and nothing runs.
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
    if a == "--":
        sys.exit("refused: '--' is not allowed")
    if a in ("-e", "--extra-vars"):
        if i + 1 >= len(args):
            sys.exit("refused: dangling -e")
        extras.append(args[i + 1])
        i += 2
        continue
    if a.startswith("--extra-vars="):
        extras.append(a.split("=", 1)[1])
    elif a.startswith("--e"):
        # optparse accepts unique prefixes (--extra, --extra-v); only the exact spelling is allowed
        sys.exit(f"refused: ambiguous long option {a!r}; use --extra-vars")
    elif a.startswith("-e="):
        sys.exit("refused: use '-e value' or '-evalue', not '-e='")
    elif a.startswith("-e") and not a.startswith("--") and len(a) > 2:
        extras.append(a[2:])
    elif a.startswith("-") and not a.startswith("--") and "e" in a[1:]:
        sys.exit(f"refused: combined short options {a!r} contain 'e'; pass -e separately")
    i += 1

cmd = ["ansible-playbook", "-i", "localhost,", "-c", "local", os.path.join(here, "guard.yml"), "-e", "@config.yml"]
for e in extras:
    cmd += ["-e", e]
rc = subprocess.call(cmd)
if rc != 0:
    sys.exit(rc)
os.execvp("ansible-playbook", ["ansible-playbook"] + args)
