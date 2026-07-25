#!/usr/bin/env python3
"""Resolve known, expected cherry-pick conflicts when adopting unmerged
aws-samples/bedrock-access-gateway PRs on top of upstream main.

Used by .github/workflows/upstream-rebuild.yaml. Run from inside the
`upstream` checkout, after `git cherry-pick` has stopped on a conflict in
src/api/models/bedrock.py. Takes the PR number as its only argument so it
knows which known conflict pattern to apply.

Usage: python3 resolve_bedrock_gateway_conflicts.py <239|198>

Both conflicts are between PRs that each append an independent
if/elif branch (or a shared log line) in the same function. Neither
conflict reflects any real logic disagreement — they are pure adjacency
conflicts from two additive patches landing near each other. If a future
upstream change touches the same region of bedrock.py, the patterns below
may stop matching; the script raises SystemExit with a clear message
rather than silently doing nothing, so the workflow step fails loudly.
"""

import re
import sys

BEDROCK_PY = "src/api/models/bedrock.py"


def resolve_239():
    """PR #239 vs #255: both add a branch right after toolConfig handling
    in _parse_request. #255 (response_format) always applies first in our
    cherry-pick order, so #239's `elif` needs to become a standalone `if`
    guarded on toolConfig not already being set."""
    with open(BEDROCK_PY) as f:
        content = f.read()

    pattern = re.compile(
        r"<<<<<<< HEAD\n(.*?)\n=======\n"
        r"        elif self\._messages_contain_tool_blocks\(messages\):",
        re.DOTALL,
    )
    if not pattern.search(content):
        raise SystemExit(
            "resolve_239: expected conflict pattern not found in "
            f"{BEDROCK_PY} — upstream code may have changed near the "
            "toolConfig/response_format branch. Manual rebase needed."
        )

    content = pattern.sub(
        r'\1\n\n        if "toolConfig" not in args and '
        r"self._messages_contain_tool_blocks(messages):",
        content,
    )
    content = re.sub(
        r"\n>>>>>>> [0-9a-f]+ "
        r"\(fix: allow messages with tool blocks when tools array is omitted\)",
        "",
        content,
    )
    _write_and_verify(content, "239")


def resolve_198():
    """PR #198 vs #239: both touch the same "unknown tag in message
    content" logger.warning call. Keep #198's more detailed version,
    which includes finish_reason in the message."""
    with open(BEDROCK_PY) as f:
        content = f.read()

    pattern = re.compile(
        r"<<<<<<< HEAD\n.*?\n=======\n"
        r'(                    logger\.warning\(\n'
        r'                        "Unknown tag in message content " \+ ",".join\(c\.keys\(\)\) '
        r'\+ ". finish_reason is: " \+ finish_reason\n'
        r"                    \)\n)"
        r">>>>>>> [0-9a-f]+ "
        r'\(Return `tool_calls` when `finish_reason` is `"max_tokens"`\.\)',
        re.DOTALL,
    )
    if not pattern.search(content):
        raise SystemExit(
            "resolve_198: expected conflict pattern not found in "
            f"{BEDROCK_PY} — upstream code may have changed near the "
            "'unknown tag' warning. Manual rebase needed."
        )

    content = pattern.sub(r"\1", content)
    _write_and_verify(content, "198")


def _write_and_verify(content, pr):
    # Only check the actual git conflict markers (<<<<<<< / >>>>>>>), not a
    # bare "=======" - that 7-char run is common in code/docstrings as a
    # plain divider and produces false positives here.
    if "<<<<<<<" in content or ">>>>>>>" in content:
        raise SystemExit(
            f"resolve_{pr}: conflict markers remain after patch — "
            "manual rebase needed."
        )
    with open(BEDROCK_PY, "w") as f:
        f.write(content)
    print(f"Resolved PR #{pr}'s conflict in {BEDROCK_PY}")


RESOLVERS = {"239": resolve_239, "198": resolve_198}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in RESOLVERS:
        raise SystemExit(f"Usage: {sys.argv[0]} <{'|'.join(RESOLVERS)}>")
    RESOLVERS[sys.argv[1]]()
