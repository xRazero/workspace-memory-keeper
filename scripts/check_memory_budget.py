#!/usr/bin/env python3
"""Check AI-agent memory / rule files against the platform auto-injection budget.

Different agent platforms inject memory with DIFFERENT limits and DIFFERENT
measurement units. This script is platform-aware: pick a profile with
--platform, and it measures the right files with the right unit.

Supported profiles (verified 2026-09-13 from official docs / spec):

  workbuddy  MEMORY.md         chars   ws 3000 / user 4000           silent truncation
  claude     MEMORY.md         bytes   25 KB OR 200 lines (first wins); CLAUDE.md 4 MiB
  codex      AGENTS.md         bytes   64 KiB (current; 32 KiB older)  silent truncation
  windsurf   .windsurfrules    chars   6000/file, 12000 total         truncation
  cursor     .cursor/rules/*   lines   no hard cap; soft <500 lines / ~2-3k tokens

Default platform = workbuddy (backward compatible with the old single-platform
script: `python check_memory_budget.py <workspace_dir>`).

Usage:
    python check_memory_budget.py [--platform P] [--list] [--file PATH ...] [workspace_dir]
"""
import argparse
import glob
import os
import sys

KILO = 1024


# ----- discovery helpers --------------------------------------------------
def _discover_workbuddy(ws):
    return [
        ("workspace MEMORY.md", os.path.join(ws, ".workbuddy", "memory", "MEMORY.md")),
        ("user      MEMORY.md", os.path.expanduser("~/.workbuddy/MEMORY.md")),
    ]


def _discover_claude(ws):
    # Claude auto-memory lives at ~/.claude/projects/<hash>/memory/MEMORY.md.
    # The hash is not worth computing; glob all of them (usually one per project).
    return [
        ("MEMORY.md", p)
        for p in sorted(glob.glob(os.path.expanduser("~/.claude/projects/*/memory/MEMORY.md")))
    ]


def _discover_codex(ws):
    return [
        ("AGENTS.md", os.path.join(ws, "AGENTS.md")),
        ("AGENTS.override.md", os.path.join(ws, "AGENTS.override.md")),
    ]


def _discover_windsurf(ws):
    out = [(".windsurfrules", os.path.join(ws, ".windsurfrules"))]
    rd = os.path.join(ws, ".windsurf", "rules")
    if os.path.isdir(rd):
        for f in sorted(os.listdir(rd)):
            if f.endswith(".md"):
                out.append((".windsurf/rules/" + f, os.path.join(rd, f)))
    return out


def _discover_cursor(ws):
    rd = os.path.join(ws, ".cursor", "rules")
    if not os.path.isdir(rd):
        return []
    return [
        (".cursor/rules/" + f, os.path.join(rd, f))
        for f in sorted(os.listdir(rd))
        if f.endswith(".mdc")
    ]


# ----- platform profiles --------------------------------------------------
# unit: "chars" | "bytes" | "lines"
# limits: label -> (hard_limit, warn_buffer); "_soft" is the soft cap for
#         platforms/files whose label is not explicitly listed.
# truncate: does exceeding the cap silently drop content?
# total_cap: optional aggregate cap across all discovered files.
# line_cap: optional secondary line cap (claude MEMORY.md).
PROFILES = {
    "workbuddy": {
        "unit": "chars",
        "truncate": True,
        "desc": "WorkBuddy MEMORY.md — 注入预算，超限静默砍尾",
        "note": "工作区 ≤3000 / 用户级 ≤4000 字符（Python len 码点）。本地无配置可放大。",
        "discover": _discover_workbuddy,
        "limits": {
            "workspace MEMORY.md": (3000, 2800),
            "user      MEMORY.md": (4000, 3800),
        },
    },
    "claude": {
        "unit": "bytes",
        "truncate": True,
        "desc": "Claude Code MEMORY.md — 前 200 行或 25 KB 先到为准；CLAUDE.md ≤ 4 MiB",
        "note": "25KB 与 200 行任一触及即截断；CLAUDE.md 完整加载上限 4 MiB，超过跳过。推荐 ≤200 行 / ≤40000 字符。",
        "discover": _discover_claude,
        "limits": {
            "MEMORY.md": (25 * KILO, 25 * KILO),
        },
        "line_cap": 200,
    },
    "codex": {
        "unit": "bytes",
        "truncate": True,
        "desc": "OpenAI Codex AGENTS.md — 64 KiB 默认上限，超限静默截断",
        "note": "project_doc_max_bytes 默认 64 KiB（旧版本 32 KiB），超出部分静默截断。",
        "discover": _discover_codex,
        "limits": {
            "AGENTS.md": (64 * KILO, 60 * KILO),
            "AGENTS.override.md": (64 * KILO, 60 * KILO),
        },
    },
    "windsurf": {
        "unit": "chars",
        "truncate": True,
        "desc": "Windsurf .windsurfrules — 6000 字符/文件，合计 ≤12000 字符",
        "note": "单文件硬上限 6000 字符，所有规则文件合计 ≤12000 字符。",
        "discover": _discover_windsurf,
        "limits": {
            ".windsurfrules": (6000, 6000),
        },
        "total_cap": 12000,
    },
    "cursor": {
        "unit": "lines",
        "truncate": False,
        "desc": "Cursor .cursor/rules/*.mdc — 无硬上限，软建议单文件 <500 行",
        "note": "无硬上限；建议单文件 <500 行，alwaysApply 合计 <~2000–3000 tokens，过长注意力衰减。",
        "discover": _discover_cursor,
        "limits": {
            "_soft": (500, 500),
        },
    },
}


def measure(path, unit):
    """Return (count, exists, error)."""
    if not os.path.isfile(path):
        return 0, False, None
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:  # noqa: BLE001
        return -1, True, "read error"
    if unit == "chars":
        return len(text.rstrip("\n")), True, None
    if unit == "bytes":
        return len(text.encode("utf-8")), True, None
    if unit == "lines":
        return (text.count("\n") + (1 if text and not text.endswith("\n") else 0)), True, None
    return -1, True, "unknown unit"


def fmt_count(n, unit):
    if unit == "chars":
        return f"{n} chars"
    if unit == "bytes":
        return f"{n} bytes ({n / KILO:.1f} KiB)"
    if unit == "lines":
        return f"{n} lines"
    return str(n)


def report(profile, label, path, limit, warn):
    unit = profile["unit"]
    n, exists, err = measure(path, unit)
    if not exists:
        print(f"  [absent] {label}: {path}")
        return 0
    if n < 0:
        print(f"  [ERROR ] {label}: {err} — {path}")
        return 0
    over = n > limit
    flag = "OK " if not over else ("WARN" if not profile.get("truncate") else "OVER")
    print(f"  [{flag}] {label}: {fmt_count(n, unit)} (limit {fmt_count(limit, unit)})  {path}")
    if over:
        if profile.get("truncate"):
            print("         -> exceeds cap; content beyond is SILENTLY DROPPED. MOVE overflow out, keep pointer.")
        else:
            print("         -> over soft guidance; attention may degrade. Consider splitting.")
    return n


def cmd_list():
    print("=== Platform budget profiles ===")
    for name, p in PROFILES.items():
        print(f"\n* {name}  [{p['unit']}]  truncate={p.get('truncate')}")
        print(f"    {p['desc']}")
        print(f"    {p['note']}")
        for lbl, (hard, _warn) in p["limits"].items():
            if lbl == "_soft":
                continue
            print(f"    limit {lbl}: {fmt_count(hard, p['unit'])}")
        if "line_cap" in p:
            print(f"    line_cap: {p['line_cap']} lines")
        if "total_cap" in p:
            print(f"    total_cap: {fmt_count(p['total_cap'], p['unit'])}")
    print("\nDefault platform: workbuddy (backward compatible).")


def main():
    ap = argparse.ArgumentParser(
        description="Check AI-agent memory / rule files against the platform budget."
    )
    ap.add_argument("workspace_dir", nargs="?", default=os.getcwd())
    ap.add_argument("--platform", "-p", default="workbuddy", choices=list(PROFILES.keys()))
    ap.add_argument("--file", action="append", default=[],
                    help="explicit file(s) to check with the chosen platform's unit/limit")
    ap.add_argument("--limit", type=int, help="override per-file hard limit")
    ap.add_argument("--list", action="store_true", help="list platform profiles and exit")
    args = ap.parse_args()

    if args.list:
        cmd_list()
        return

    prof = PROFILES[args.platform]
    unit = prof["unit"]
    print(f"=== memory budget check | platform={args.platform} | unit={unit} ===")
    print(f"workspace: {args.workspace_dir}")

    targets = []
    if args.file:
        for fp in args.file:
            lbl = os.path.basename(fp)
            if args.limit is not None:
                hard = warn = args.limit
            elif lbl in prof["limits"]:
                hard, warn = prof["limits"][lbl]
            elif "_soft" in prof["limits"]:
                hard = warn = prof["limits"]["_soft"][0]
            else:
                hard = warn = 10 ** 9  # no known cap -> informational only
            targets.append((lbl, fp, hard, warn))
    else:
        for lbl, fp in prof["discover"](args.workspace_dir):
            if lbl in prof["limits"]:
                hard, warn = prof["limits"][lbl]
            else:
                hard = warn = prof["limits"].get("_soft", (10 ** 9, 10 ** 9))[0]
            targets.append((lbl, fp, hard, warn))

    total = 0
    for lbl, fp, hard, warn in targets:
        n = report(prof, lbl, fp, hard, warn)
        if n > 0 and prof.get("total_cap"):
            total += n

    # aggregate caps (e.g. windsurf 12000 chars across all rule files)
    if prof.get("total_cap"):
        cap = prof["total_cap"]
        print(f"  [info ] combined total: {fmt_count(total, unit)} (cap {fmt_count(cap, unit)})")
        if total > cap:
            print("         -> OVER combined cap; split rules across files.")

    # secondary line cap (claude MEMORY.md: 200 lines)
    if "line_cap" in prof and not args.file:
        for lbl, fp in prof["discover"](args.workspace_dir):
            ln, exists, _ = measure(fp, "lines")
            if exists and ln > prof["line_cap"]:
                print(f"  [OVER ] {lbl}: {ln} lines exceeds {prof['line_cap']}-line cap (truncation).")

    # informational: daily logs are budget-free for workbuddy
    if args.platform == "workbuddy" and not args.file:
        log_dir = os.path.join(args.workspace_dir, ".workbuddy", "memory")
        if os.path.isdir(log_dir):
            logs = sorted(f for f in os.listdir(log_dir)
                          if f[:4].isdigit() and f.endswith(".md"))
            if logs:
                print(f"  [info ] daily logs ({len(logs)}): append-only, no injection budget.")

    print("=== done ===")


if __name__ == "__main__":
    main()
