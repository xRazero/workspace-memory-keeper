#!/usr/bin/env python3
"""Check WorkBuddy memory files against the auto-injection character budget.

The platform injects only the first ~N chars of MEMORY.md at session start
(workspace <=3000, user <=4000); content beyond that is silently truncated.
This script measures character counts (NOT bytes) so CJK-heavy files are
judged correctly, and flags files that risk truncation.

Usage:
    python check_memory_budget.py [workspace_dir]

If workspace_dir is omitted, the current directory is used. The user-level
~/.workbuddy/MEMORY.md is always checked.
"""
import os
import sys

WS_LIMIT = 2800      # warn buffer under the 3000 hard cap
USER_LIMIT = 3800    # warn buffer under the 4000 hard cap


def char_count(path):
    """Return (chars, exists). Counts Unicode code points (Python len())."""
    if not os.path.isfile(path):
        return 0, False
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception as exc:  # noqa: BLE001
        return -1, True
    # len(text) counts Unicode code points = Python len() = the platform's injection
    # budget口径 (NOT wc -m, which over-counts combining characters in some environments).
    return len(text.rstrip("\n")), True


def report(label, path, limit):
    n, exists = char_count(path)
    if not exists:
        print(f"  [absent] {label}: {path}")
        return
    if n < 0:
        print(f"  [ERROR ] {label}: cannot read {path}")
        return
    flag = "OK " if n <= limit else "WARN"
    print(f"  [{flag}] {label}: {n} chars (limit {limit})  {path}")
    if n > limit:
        print(f"         -> exceeds buffer; MOVE overflow to daily log / docs, keep pointer.")


def main():
    ws_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    ws_mem = os.path.join(ws_dir, ".workbuddy", "memory", "MEMORY.md")
    user_mem = os.path.expanduser("~/.workbuddy/MEMORY.md")

    print("=== WorkBuddy memory budget check ===")
    print(f"workspace: {ws_dir}")
    report("workspace MEMORY.md", ws_mem, WS_LIMIT)
    report("user      MEMORY.md", user_mem, USER_LIMIT)

    # Informational: daily logs (append-only, no injection budget)
    log_dir = os.path.join(ws_dir, ".workbuddy", "memory")
    if os.path.isdir(log_dir):
        logs = sorted(f for f in os.listdir(log_dir) if f[:4].isdigit() and f.endswith(".md"))
        if logs:
            print(f"  [info ] daily logs ({len(logs)}): append-only, no injection budget.")
    print("=== done ===")


if __name__ == "__main__":
    main()
