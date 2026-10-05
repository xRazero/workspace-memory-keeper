#!/usr/bin/env python3
"""Install / uninstall the memory-budget guard hook into WorkBuddy settings.

Idempotent. Backs up settings.json before every write. Merges rather than
overwrites: unrelated keys and any pre-existing hooks are preserved.

    python install_hooks.py            # install (default)
    python install_hooks.py --status   # report only
    python install_hooks.py --uninstall
"""
import argparse
import datetime
import io
import json
import os
import shutil
import sys

SETTINGS = os.path.join(os.path.expanduser("~"), ".workbuddy", "settings.json")
HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "hook_memory_guard.py").replace("\\", "/")
PY = sys.executable.replace("\\", "/")
if not PY:
    PY = "python"
MATCHER = "Write|Edit"
COMMAND = '"%s" "%s"' % (PY, GUARD)
MARKER = "hook_memory_guard.py"


def backup(path):
    if not os.path.exists(path):
        return None
    dst = "%s.bak-%s" % (path, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, dst)
    return dst


def load(path):
    if not os.path.exists(path):
        return {}
    return json.load(io.open(path, encoding="utf-8"))


def save(path, data):
    io.open(path, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))


def has_guard(hooks):
    for _evt, groups in (hooks or {}).items():
        for g in groups or []:
            for h in g.get("hooks", []) or []:
                if MARKER in (h.get("command") or ""):
                    return True
    return False


def install(data):
    hooks = data.setdefault("hooks", {})
    changed = False
    for evt in ("PreToolUse", "PostToolUse"):
        groups = hooks.setdefault(evt, [])
        if not isinstance(groups, list):
            continue
        found = None
        for g in groups:
            if g.get("matcher") == MATCHER:
                found = g
                break
        entry = {"type": "command", "command": COMMAND, "timeout": 10}
        if found is None:
            groups.append({"matcher": MATCHER, "hooks": [entry]})
            changed = True
        elif not any(MARKER in (h.get("command") or "") for h in found.get("hooks", [])):
            found.setdefault("hooks", []).append(entry)
            changed = True
    return changed


def uninstall(data):
    hooks = data.get("hooks") or {}
    changed = False
    for evt, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        kept = []
        for g in groups or []:
            hs = [h for h in (g.get("hooks") or []) if MARKER not in (h.get("command") or "")]
            if len(hs) != len(g.get("hooks") or []):
                changed = True
            if hs:
                g["hooks"] = hs
                kept.append(g)
            else:
                changed = True
        if kept:
            hooks[evt] = kept
        else:
            hooks.pop(evt, None)
            changed = True
    if not hooks:
        data.pop("hooks", None)
    return changed


def main():
    ap = argparse.ArgumentParser(description="Install the memory-budget guard hook.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--settings", default=SETTINGS)
    args = ap.parse_args()

    path = args.settings
    if not os.path.exists(path):
        print("settings not found: %s" % path)
        return 1
    if not os.path.exists(GUARD):
        print("guard script missing: %s" % GUARD)
        return 1

    data = load(path)
    if args.status:
        print("settings : %s" % path)
        print("guard    : %s" % GUARD)
        print("installed: %s" % has_guard(data.get("hooks")))
        print("events   : %s" % ", ".join(sorted((data.get("hooks") or {}).keys())) or "-")
        return 0

    before = set(data.keys())
    changed = uninstall(data) if args.uninstall else install(data)
    if not changed:
        print("no change (already %s)" % ("absent" if args.uninstall else "installed"))
        return 0

    dst = backup(path)
    save(path, data)
    v = load(path)
    lost = [k for k in before if k not in v]
    print("%s hook %s" % ("Removed" if args.uninstall else "Installed",
                          "from" if args.uninstall else "into"))
    print("  settings : %s" % path)
    if dst:
        print("  backup   : %s" % dst)
    print("  lost keys: %s" % (lost or "none"))
    print("  installed: %s" % has_guard(v.get("hooks")))
    if lost:
        print("  WARNING: keys lost during merge — restore from backup!")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
