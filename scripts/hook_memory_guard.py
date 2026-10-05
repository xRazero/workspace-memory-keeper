#!/usr/bin/env python3
"""Memory-budget guard hook (WorkBuddy / Claude Code hooks spec).

Why this exists
---------------
`workspace-memory-keeper` documents the 3000 (workspace) / 4000 (user-level)
char injection budget, but a SKILL.md is only honoured when the model happens
to load it. On 2026-10-05 the project MEMORY.md was written to 4213 chars and
silently truncated. A hook cannot be forgotten: it runs on every tool call.

Behaviour
---------
* PreToolUse  (Write|Edit)  -> blocks writes that would exceed the HARD cap.
* PostToolUse (Write|Edit)  -> re-checks the real file; warns at the SOFT
 警戒线 (soft watermark) so overflow is MOVEd out *before* hitting the cap.
* Only MEMORY.md files are inspected; everything else is a no-op.
* Fail-safe: any exception -> exit 0 with {"continue": true}. A broken guard
  must never block the user's work.

Output: JSON on stdout (hooks spec). Exit code 0 always; blocking is expressed
via `permissionDecision: "deny"` on PreToolUse.
"""
import io
import json
import os
import sys

# Hard caps = platform injection budget (verified 2026-09-13, non-extensible).
WS_LIMIT = 3000
USER_LIMIT = 4000
# Soft watermark: warn early so there is room to MOVE instead of compress.
WS_WARN = 2400
USER_WARN = 3200

TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _norm(p):
    try:
        return os.path.normpath(os.path.expanduser(p or "")).replace("\\", "/").lower()
    except Exception:
        return ""


def classify(path):
    """Return (kind, hard_limit, warn_at) or None if not a MEMORY.md."""
    low = _norm(path)
    if not low.endswith("memory.md"):
        return None
    if low.endswith("/memory/memory.md"):
        return ("workspace MEMORY.md", WS_LIMIT, WS_WARN)
    # user-level: ~/.workbuddy/MEMORY.md and the real layout
    # ~/.workbuddy/user-<hash>-personal/MEMORY.md
    if "/.workbuddy/" in low or "/.claude/" in low or "/.codebuddy/" in low:
        return ("user MEMORY.md", USER_LIMIT, USER_WARN)
    return None


def read_len(path):
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            return len(f.read())
    except Exception:
        return 0


def allow(msg=None):
    out = {"continue": True, "suppressOutput": True,
           "hookSpecificOutput": {"hookEventName": "", "permissionDecision": "allow"}}
    if msg:
        out["hookSpecificOutput"]["permissionDecisionReason"] = msg
        out["hookSpecificOutput"]["additionalContext"] = msg
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)


def deny(reason):
    print(json.dumps({
        "continue": False,
        "suppressOutput": False,
        "systemMessage": reason,
        "stopReason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }, ensure_ascii=False))
    sys.exit(0)


def guard(kind, limit, warn_at, cur_len):
    if cur_len > limit:
        return ("HARD", (
            "BLOCKED: %s is %d chars, over the %d-char injection budget — tail would be "
            "SILENTLY TRUNCATED. Do NOT compress. MOVE the volatile/dated detail out to "
            ".workbuddy/memory/YYYY-MM-DD.md (append-only) or docs/*.md, and leave only a "
            "one-line pointer in MEMORY.md. Then rewrite MEMORY.md under the cap."
            % (kind, cur_len, limit)))
    if cur_len > warn_at:
        return ("WARN", (
            "%s is %d chars (cap %d, watermark %d) — only %d chars of headroom. "
            "Next write risks silent truncation. MOVE dated/volatile detail to the daily log "
            "or docs/ now, keep MEMORY.md as a pointer-only index."
            % (kind, cur_len, limit, warn_at, limit - cur_len)))
    return ("OK", None)


def main():
    try:
        raw = sys.stdin.read()
        evt = json.loads(raw) if raw.strip() else {}
    except Exception:
        return allow()

    event = evt.get("hook_event_name", "")
    tool = evt.get("tool_name", "")
    ti = evt.get("tool_input") or {}
    if tool not in TOOLS:
        return allow()

    path = ti.get("file_path") or ti.get("path") or ""
    c = classify(path)
    if not c:
        return allow()
    kind, limit, warn_at = c

    try:
        if event == "PreToolUse":
            if tool == "Write":
                cur = len(ti.get("content") or "")
            else:
                # Edit: estimate from the delta against the current file.
                base = read_len(path)
                new = ti.get("new_string")
                old = ti.get("old_string")
                if isinstance(new, str) and isinstance(old, str):
                    cur = base + (len(new) - len(old))
                elif isinstance(new, str):
                    cur = base + len(new)
                else:
                    cur = base
            level, msg = guard(kind, limit, warn_at, cur)
            if level == "HARD":
                return deny(msg)
            if level == "WARN":
                return allow(msg)
            return allow()

        if event == "PostToolUse":
            level, msg = guard(kind, limit, warn_at, read_len(path))
            if msg:
                return allow(msg)
            return allow()
    except Exception:
        return allow()

    return allow()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"continue": True, "suppressOutput": True}))
    sys.exit(0)
