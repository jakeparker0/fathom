# ruff: noqa: INP001  # standalone hook script run by Claude Code, not a package
"""PreToolUse hook: stop Claude Code editing Tier A (hand-written) code. See ADR-011.

Blocks Edit/Write/MultiEdit/NotebookEdit on any path matched by
.claude/hand-write-paths.txt, and Bash commands that look like they write to one
(redirects, sed -i, mv, cp, rm, ...) or generate a migration. Exit code 2 blocks the
tool call and shows the reason to Claude. This is a speed bump, not a sandbox.
"""

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WRITE_HINTS = re.compile(
    r"(>|\btee\b|\bsed\s+-i|\bperl\s+-i|\bmv\b|\bcp\b|\brm\b|\btouch\b"
    r"|\bgit\s+(checkout|restore|apply)\b|\bpatch\b|open\(|write_text)"
)
MIGRATION_GEN = re.compile(r"\balembic\s+revision\b")
MESSAGE = (
    "Blocked by the hand-write guard (ADR-011): {target} is Tier A, so Jake writes it. "
    "Don't write or paste the implementation. Use the hint ladder in AGENTS.md: "
    "ask a question, explain the concept, point to where to look, or sketch pseudocode."
)


def block(reason: str) -> None:
    sys.stderr.write(reason + "\n")


def load_patterns(root: Path) -> list[str]:
    path = root / ".claude" / "hand-write-paths.txt"
    if not path.exists():
        return []
    lines = (line.strip() for line in path.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def protected(rel_path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in patterns)


def literal_prefix(pattern: str) -> str:
    return pattern.split("*", 1)[0]


def main() -> int:
    event = json.load(sys.stdin)
    root_dir = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or "."
    root = Path(root_dir).resolve()
    patterns = load_patterns(root)
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    if tool in WRITE_TOOLS:
        raw = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        target = Path(raw)
        if not target.is_absolute():
            target = root / target
        try:
            rel = target.resolve().relative_to(root).as_posix()
        except ValueError:
            return 0
        if protected(rel, patterns):
            block(MESSAGE.format(target=rel))
            return 2

    if tool == "Bash":
        command = tool_input.get("command", "")
        if MIGRATION_GEN.search(command):
            block(MESSAGE.format(target="Generating a migration"))
            return 2
        if WRITE_HINTS.search(command):
            for pattern in patterns:
                prefix = literal_prefix(pattern)
                if prefix and prefix in command:
                    block(MESSAGE.format(target=prefix))
                    return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
