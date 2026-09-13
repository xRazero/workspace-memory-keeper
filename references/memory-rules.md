# Memory Rules — Detailed Reference

Companion to `SKILL.md`. Evidence and patterns for the layered memory
architecture.

## 0. Cross-platform budget profiles (verified 2026-09-13)

The "silent truncation" risk is **universal across agent platforms** — every
platform injects memory with a finite budget; only the number and the unit
differ. The `scripts/check_memory_budget.py` checker is platform-aware
(`--platform` / `--list`). Use the same layered architecture everywhere; only the
numeric budget and the file path change.

| Platform | Memory / rule file | Unit | Hard limit | Silent truncation? | Source |
|---|---|---|---|---|---|
| **WorkBuddy** | `.workbuddy/memory/MEMORY.md` (ws) + `~/.workbuddy/MEMORY.md` (user) | chars (code points) | ws 3000 / user 4000 | ✅ yes | system prompt injection budget |
| **Claude Code** | `~/.claude/projects/<hash>/memory/MEMORY.md` | bytes **OR** lines | 25 KB **or** 200 lines (first wins); `CLAUDE.md` ≤ 4 MiB | ✅ yes | Anthropic docs (memory) |
| **OpenAI Codex** | `AGENTS.md` (+ `AGENTS.override.md`) | bytes | 64 KiB (current; older 32 KiB) via `project_doc_max_bytes` | ✅ yes | Codex config docs |
| **Windsurf** | `.windsurfrules` (+ `.windsurf/rules/*.md`) | chars | 6000/file, **12000 total** | ✅ yes | Windsurf rules docs |
| **Cursor** | `.cursor/rules/*.mdc` | lines | no hard cap; soft **<500 lines** (alwaysApply ≈ 2000–3000 tok) | ❌ no (attention decays) | Cursor rules guide 2026 |

Notes:
- **Units are not interchangeable**: WorkBuddy counts *code points* (Python
  `len()`); Claude/Codex count *bytes* (UTF-8); Cursor counts *lines*. A 6000-char
  Windsurf file ≠ a 6000-byte Codex file.
- **Claude `MEMORY.md`** is truncated at *whichever* threshold hits first (25 KB
  or 200 lines). `CLAUDE.md` is a separate, larger budget (4 MiB full load, skip
  if larger).
- **Codex** silently truncates beyond `project_doc_max_bytes`; the checker warns
  at 60 KiB (buffer under 64 KiB).
- The **overflow rule (MOVE, never compress)** in §4 applies identically on every
  platform — only the head that must stay small changes.

## 1. Read / injection mechanism (verified 2026-09-13)

```
Session start (platform auto-injects, hard-truncated at budget)
  ├─ Cloud profile  Layer1A  <memory> block            (server-generated, RO)
  ├─ User MEMORY.md ~/.workbuddy/MEMORY.md             ≤ 4000 chars
  └─ WS   MEMORY.md <ws>/.workbuddy/memory/MEMORY.md   ≤ 3000 chars
        → injected head only; tail silently dropped if over budget

On-demand (NOT injected; no budget cost; agent pulls as needed)
  ── ordered by relevance to current project/session (see §8) ──
  ├─ Daily logs   <ws>/.workbuddy/memory/YYYY-MM-DD.md  (append-only, newest first)
  ├─ docs/*.md                                              (Grep / Read)
  ├─ 资料库 (Library) node                                   (full-text search)
  └─ conversation_search                                    (cross-session, last resort)
```

Key fact: a memory FILE on disk can exceed the budget (observed 15 KB for a
cloud session's memory file). The limit bites at **injection**, not storage.
Therefore: keep the injected head (first ~3000 chars) as the stable index; push
everything else to budget-free channels.

## 2. Limit is hard & non-extensible — evidence

| Check | Result |
|---|---|
| `~/.workbuddy/settings.json` | plugins / claw / sandbox only — no memory key |
| `~/.workbuddy/app/app-config.json` | `{"locale":"zh-CN"}` only |
| grep `3000\|memory.limit\|context.limit\|char.limit\|inject` in both | no hits |
| `gc_config.json "maxSizeMb": 3000` | session-cache GC (MB), unrelated to memory chars |
| workbuddy.cn/docs Overview reading order | no memory-settings page |

**Do not attempt to raise the budget.** Design around it: small stable index +
budget-free daily logs / docs / 资料库.

## 3. MEMORY.md — allowed vs forbidden

**Allowed (stable, 4 types):**
- Project identity & absolute directory.
- Source-of-truth map (pointers to docs/, 资料库, daily logs).
- Permanent red-lines (rules that must be in every context).
- Tiny sync status (nodeId + state).

**Forbidden (causes churn / overflow):**
- Dated changelog: `2026-09-13: did X`.
- Spec dumps (E1–E9 details, field tables, word lists).
- Per-task volatile detail, raw data, metrics.

If a forbidden item is already in MEMORY.md, relocate it (see §4) and replace
with a pointer.

## 4. Overflow procedure (MOVE, never compress)

1. Overflow is "what happened" → append to `YYYY-MM-DD.md` (append-only).
2. Overflow is knowledge → `docs/<topic>.md`; if mirrored to 资料库, run the
   project sync script.
3. Leave a 1-line pointer in MEMORY.md.

Compression-in-place is explicitly forbidden: it silently drops information and
must be re-done every time detail is added, creating the exact loss risk this
skill prevents.

## 5. Budget measurement

- Always count **Unicode code points with Python `len()`** (matches the platform's
  injection budget). `wc -m` can over-count combining characters in some
  environments; `wc -c` measures bytes and is wrong for CJK.
- Targets: workspace MEMORY.md ≤ 2800 chars; user MEMORY.md ≤ 3800 chars.
- Helper: `scripts/check_memory_budget.py <workspace_dir>`.

## 6. Project sync protocol (generic, template-driven)

For projects mirroring `docs/*.md` → 资料库 (Library) nodes, use a local-primary,
hash-gated, MULTI-FILE sync script (`.workbuddy/memory/sync_memory.py`):

- `init --path <p> --node-id <id>` — register one file's nodeId + local hash as synced.
- `check [--path <p>]` — offline-safe; per-file hash compare → synced / dirty / pending_offline.
- `push [--path <p>] --token-stdin` — hash-gated re-send (only if dirty); missing --path = ALL files.
- `list` — show all file→node mappings.

The file manifest lives entirely in `sync_state.json` (`files` key: path →
{node_id, url, hash, status, ...}); adding a file = one entry there — **no code
edit and no MEMORY.md edit**. The copied `sync_memory.py` is generic and identical
across projects, sourced from a single template
(`workspace-memory-keeper/templates/sync_memory.py.tmpl`) to avoid N-project drift.

KEY: MEMORY.md holds NO node URLs. The mapping (path→node_id/url/hash/status) lives
entirely in `sync_state.json` (machine-readable, zero injection budget). MEMORY.md
keeps one stable line: "资料库节点映射见 .workbuddy/memory/sync_state.json". Adding any
number of files only touches sync_state.json → eliminates the 3000-char leak that per-
node pointer lines would cause.

Offline / reconnect handling:
- Offline: `push` without token → per-file state `pending_offline`; local stays
  authoritative, zero loss.
- Reconnect: next `push` detects hash change → re-sends (new nodeId auto-written to
  sync_state.json, URL derived). No MEMORY.md rewrite needed.
- Constraint: 资料库 edit API returns no blockId, so updates are full re-sends
  (old node becomes orphan; clean up in UI). Acceptable for rarely-updated knowledge.
- Token: obtained by the agent via `connect_open_platform` (skill_id=library);
  the sync script never self-fetches.
- Library skill location: set `LIBRARY_SKILL_DIR` env, or the script auto-detects
  common install paths on Windows/macOS/Linux.

## 7. Red-line examples (illustrative — replace with your own)

These are the author's project red-lines, shown only as **style examples**. Your
MEMORY.md should list YOUR permanent red-lines, one stable line each:

- 浏览器自动化一律 opencli（抖音/TikTok/1688）。
- 密钥必须放 `.env`，不放配置文件/代码。
- 配置三层优先级：系统env > `.env` > 配置默认 > 脚本 `_DEFAULTS`。

Rule: red-lines are stable one-liners. Never embed spec dumps or code references
here — keep MEMORY.md a small index.

## 8. On-demand retrieval priority — relevance-first

**Primary sort key = relevance to the CURRENT project/session. More relevant =
higher priority.** Cost is only a tiebreaker. Workspace-scoped sources always
outrank cross-project ones; injected (already in context) always wins.

| Tier | Source | Relevance ranking rationale | Use when |
|---|---|---|---|
| P0 | Injected MEMORY.md (workspace + user) | already in context, directly about this project/you — zero pull, max relevance | identity, pointers, red-lines — answer without fetching |
| P1 | Workspace daily logs (newest date first) | same project, time-ordered, highest "this-project recency" relevance | "what we did on X day", recent state |
| P2 | Project `docs/*.md` + 资料库 node | same project, dense stable specs | spec details, field tables, word lists |
| P3 | `conversation_search` | cross-session, global — inherently lowest relevance by default | "that old discussion, forgot which project/day" |

Relevance sorting rules:
1. **Scope first.** Workspace-scoped (P1–P2) before cross-project (P3). Never
   jump to P3 while P1/P2 can answer.
2. **Recency within scope.** Among daily logs, read newest-first; stop once the
   fact is found.
3. **Injected beats pulled.** If P0 already answers, do NOT trigger P1–P3 —
   saves calls and avoids drift.
4. **Cross-project is last resort.** Only use `conversation_search` when local
   workspace sources are exhausted or the fact's location is unknown.
5. **Combine when incomplete.** If a daily log is thin, pair it with P2 docs;
   platform explicitly allows using sources together.

Anti-patterns (do NOT):
- Pulling `conversation_search` first "just in case" — it is global and
  low-relevance; wastes a server round-trip and can surface irrelevant sessions.
- Re-reading MEMORY.md from disk when it is already injected (it is in context;
  the disk read is redundant).
- Letting cost drive the order — a cheaper but less relevant source must NOT
  outrank a more relevant one.
