---
name: workspace-memory-keeper
description: "This skill should be used when writing or updating project memory files (.workbuddy/memory/MEMORY.md) or any agent memory/rule file, when memory approaches the injection budget, or when auditing memory hygiene. It enforces a layered memory architecture so the auto-injected memory stays a small, stable index while volatile detail lives in append-only daily logs and on-demand docs or knowledge base, preventing silent truncation and information loss. Budget-aware across platforms: WorkBuddy (3000/4000 chars), Claude Code (25KB or 200 lines), OpenAI Codex (64 KiB AGENTS.md), Windsurf (6000 chars/file, 12000 total), Cursor (no hard cap, soft <500 lines) — all verified 2026-09-13."
agent_created: true
---

# Workspace Memory Keeper

Enforce a layered memory architecture. The goal is to never lose information to
the platform's auto-injection character budget, and to never churn `MEMORY.md`
by re-compressing it.

## When to use

- About to create or edit `.workbuddy/memory/MEMORY.md` (workspace) or
  `~/.workbuddy/MEMORY.md` (user-level, cross-project).
- After substantive work, deciding what to persist and where.
- Auditing memory hygiene (e.g. when `MEMORY.md` feels large or was truncated).
- After updating a `docs/*.md` that is mirrored to a 知识库 (run the project's
  sync script if one exists).

## Read mechanism (facts — verified 2026-09-13)

At session start the platform auto-injects memory into context:

- Cloud profile (server-generated, read-only) inside `<memory>`.
- `~/.workbuddy/MEMORY.md` — user-level, **≤4000 chars**.
- `<workspace>/.workbuddy/memory/MEMORY.md` — workspace, **≤3000 chars**.
- Content beyond the budget is **silently truncated** (injected head only; tail
  lost). The file on disk may be larger (observed 15 KB), but only the head
  reaches context.

NOT auto-injected (retrieved on demand, no budget cost):

- Daily logs `<workspace>/.workbuddy/memory/YYYY-MM-DD.md` (append-only).
- `docs/*.md` and the 资料库 (Library) — pulled via Read / Grep / 资料库 search.
- `conversation_search` for cross-session history.

**Conclusion:** the safe "expansion" channels are daily logs + docs/资料库. The
injected `MEMORY.md` head must stay small and stable.

## On-demand retrieval — relevance-first

When a fact is not in the injected context, pull on-demand sources in
**relevance order**: the more relevant to the CURRENT project/session, the
higher the priority. Scope beats cost — workspace-scoped always outranks
cross-project; injected (already in context) always wins. Full table + rules:
`references/memory-rules.md` §8.

## The 3000/4000 limit is HARD and non-extensible (verified)

No user-facing setting extends it. Checked and found absent:

- `~/.workbuddy/settings.json` — only plugins / claw / sandbox.
- `~/.workbuddy/app/app-config.json` — only `{"locale":"zh-CN"}`.
- No `3000` / `memory.limit` / `context.limit` / `char.limit` / `inject` key in
  either config. (The lone `3000` in the tree is `gc_config.json`
  `"maxSizeMb": 3000` — session-cache GC in MB, unrelated.)
- Public docs (workbuddy.cn/docs) have no memory-settings page.

Do not try to expand the budget. Design around it.

## MEMORY.md content rules — only these 4 types

1. **Project identity & directory** — stable, rarely changes.
2. **Source-of-truth map** — "where to find X" pointers to `docs/`, 资料库,
   daily logs. Stable.
3. **Permanent red-lines** — hard rules that must be in every context (e.g.
   "browser automation = opencli only", "secrets in .env"). List project-specific
   red-lines here as stable one-liners; do NOT embed spec dumps or code references.
4. **Current sync status** — tiny, stable (e.g. 资料库 nodeId + sync state).

NEVER put in MEMORY.md: dated changelog lines ("2026-09-13 did X"), E1–E9-style
spec dumps, volatile task details, raw data, or anything that changes per task.

## Budget control

- Measure with **Python `len()` (Unicode code points), NOT bytes, NOT `wc -m`.**
  `wc -m` can over-count combining characters in some environments; the platform's
  injection budget uses code-point count. Keep workspace MEMORY.md ≤ 2800 chars
  (buffer under 3000); user-level ≤ 3800.
- Use `scripts/check_memory_budget.py` to check any workspace quickly.

## Cross-platform budget support (verified 2026-09-13)

The "silent truncation" problem is **not unique to WorkBuddy** — every agent
platform injects memory with a finite budget, only the number and the unit differ.
This skill's checker is platform-aware so the same discipline applies everywhere:

| Platform | File | Unit | Limit | Silent truncation? |
|---|---|---|---|---|
| **WorkBuddy** | `MEMORY.md` | chars | ws 3000 / user 4000 | ✅ |
| **Claude Code** | `MEMORY.md` | bytes | 25 KB **OR** 200 lines (first wins); `CLAUDE.md` ≤ 4 MiB | ✅ |
| **OpenAI Codex** | `AGENTS.md` | bytes | 64 KiB (current; 32 KiB older) | ✅ |
| **Windsurf** | `.windsurfrules` | chars | 6000/file, 12000 total | ✅ |
| **Cursor** | `.cursor/rules/*.mdc` | lines | no hard cap; soft <500 lines | ❌ (attention decays) |

The underlying fix is identical on every platform: keep the **injected head** a
small stable index; push growth to **budget-free** channels (daily logs, `docs/`,
knowledge base). Only the budget number/unit changes.

Run the checker against any platform:

```bash
python scripts/check_memory_budget.py --list                 # show all profiles
python scripts/check_memory_budget.py <ws>                   # workbuddy (default, back-compat)
python scripts/check_memory_budget.py -p codex <ws>          # Codex AGENTS.md (bytes)
python scripts/check_memory_budget.py -p windsurf <ws>       # Windsurf (chars, 6000/12000)
python scripts/check_memory_budget.py -p claude <ws>         # Claude MEMORY.md (glob ~/.claude/projects)
python scripts/check_memory_budget.py -p cursor <ws>         # Cursor .mdc (lines, soft)
python scripts/check_memory_budget.py -p codex --file ./AGENTS.md   # check one explicit file
```

When `--platform` is a non-WorkBuddy value, the layered *architecture* (index +
MOVE overflow + budget-free channels) still applies; only the numeric budget and
the file path differ. The overflow-handling rule in the next section is universal.

## Overflow handling — MOVE, do not compress (anti-loss rule)

When MEMORY.md would exceed budget, **never compress in place** (that drops
information). Instead:

1. Identify the overflow content. If it is "what happened", append it to the
   dated daily log `YYYY-MM-DD.md` (append-only, no budget).
2. If it is structured knowledge, move it to `docs/<topic>.md`; if the project
   mirrors docs to a 资料库, run the project's sync script (e.g.
   `.workbuddy/memory/sync_memory.py` with `check`/`push`/`init`).
3. Leave a **one-line pointer** in MEMORY.md (the source-of-truth map).

This keeps MEMORY.md a stable index and pushes growth to budget-free channels.

## Stability discipline

MEMORY.md changes ONLY when project fundamentals shift (new red-line, new
pointer, directory move). Per-task detail goes to the daily log, never to
MEMORY.md. A healthy MEMORY.md is edited rarely and stays under budget without
re-compression.

## Quick checklist (apply before writing memory)

- [ ] Is this a stable fact or a permanent rule? → MEMORY.md.
- [ ] Is this "what I did today"? → daily log `YYYY-MM-DD.md`.
- [ ] Is this structured knowledge / specs? → `docs/*.md` (+ 资料库 sync).
- [ ] Would MEMORY.md exceed ~2800 chars after the edit? → MOVE overflow out,
      leave pointer. Do not compress.
- [ ] Confirm char count with `python scripts/check_memory_budget.py <ws>` (Python
      `len()`口径, not `wc -c`/not `wc -m`).

## Bootstrap a new project (init flow)

When this skill is first activated in a project with no layered memory yet,
ensure the skeleton exists (do NOT silently overwrite existing content):

1. If `<ws>/.workbuddy/memory/MEMORY.md` is absent → generate a minimal index
   template: project identity + directory, a source-of-truth pointer block, and a
   red-lines placeholder. If it EXISTS but is a large blob, PROPOSE a refactor
   (MOVE overflow to daily log / docs, keep a pointer) — do not rewrite in place.
2. If `<ws>/.workbuddy/memory/sync_state.json` is absent AND the project mirrors
   `docs/*.md` to a 资料库 → copy `templates/sync_memory.py.tmpl` to
   `<ws>/.workbuddy/memory/sync_memory.py` (single source; no per-project edits
   needed) and create a `sync_state.json` with at least `{"namespace": "...",
   "files": {}}`. Tell the user to fill `files` (or run `init --path ...`).
3. If user-level `~/.workbuddy/MEMORY.md` lacks the discipline block → offer to
   APPEND it (idempotent, never overwrite/delete existing content; respects the
   4000-char cap). User may decline; the skill still works.
4. Register the project's namespace under `/memory-hub/projects/<name>/` in the
   资料库 (only when the user opts into 资料库 mirroring).

The sync script is fully generic — the file manifest lives in `sync_state.json`,
so copied verbatim it works in any project.

## Install & first-run notes (what the user is told)

Installing this skill copies `SKILL.md` (+ references/scripts/templates) into
`~/.workbuddy/skills/`. It makes ZERO changes to any memory file at install time.
On first activation, the user is informed (6 points):

1. **What it does**: enforces a layered memory discipline — the auto-injected
   `MEMORY.md` stays a small stable index (WorkBuddy: workspace ≤3000 / user ≤4000
   chars; other platforms have their own budgets — see "Cross-platform budget
   support"); volatile or dated content overflows to daily logs and `docs/`/资料库,
   avoiding silent truncation; overflow uses MOVE, never in-place compression. The
   same discipline transfers to Claude/Codex/Windsurf/Cursor memory files.
2. **Hard limit is non-extensible**: 3000/4000 is a platform injection cap, not
   locally configurable; this skill works AROUND it, not through it.
3. **Effect on user-level `MEMORY.md`**: zero change at install; first use may
   APPEND a discipline block (idempotent, never overwrites/deletes your content,
   capped at 4000). Already present → skipped. User may decline.
4. **Effect on workspace `MEMORY.md`**: first use in a project ensures the layered
   skeleton; if your existing `MEMORY.md` is a big blob, the skill PROPOSES a
   refactor (MOVE + pointer), never a silent rewrite.
5. **资料库 / sync (optional)**: if the project mirrors `docs` to a 资料库, the
   skill generates a project-local `sync_memory.py` + `sync_state.json` and an
   independent namespace; needs 资料库 connect permission; each project keeps its
   own nodes.
6. **Safety**: reads/writes no secrets; 资料库 uploads only after explicit consent;
   touches no other files.

## References

Detailed rules, the verification evidence, architecture tables, and the
project sync protocol: `references/memory-rules.md`.
