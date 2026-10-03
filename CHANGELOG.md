# CHANGELOG

All notable changes to `workspace-memory-keeper`. SemVer: MAJOR.MINOR.PATCH.

## [1.1.1] — 2026-10-03

### Added — marketplace (WorkBuddy 开放平台) readiness
- `author: xRazero` and `category: 办公效率` added to SKILL.md frontmatter — the
  two fields the 开放平台 upload parser requires beyond the 1.1.0 set. The full
  required set is now present: `name / display_name / display_name_en /
  description / description_zh / description_en / category / version / author`.
- `assets/icon.png` — 512×512 PNG marketplace avatar (≤500 KB), generated
  programmatically (no external assets).
- YAML frontmatter re-validated with a real parser (PyYAML safe_load) to rule out
  the well-known "colon without a space / Chinese quotes" upload failures.

### Note
No functional change to the skill logic — this release only makes the packaged
skill submittable to the official WorkBuddy marketplace (open.workbuddy.cn).

## [1.1.0] — 2026-09-28

### Added
- **AUTO-EXECUTE rule for budget overflow** — when the checker reports `[OVER]`
  the refactor now runs in the same turn. No "do you want me to tidy this up?"
  prompt. Permission is required only for destructive actions (deleting originals
  without backup, writing outside the memory directory, 资料库 upload).
  (User directive 2026-09-28: this case was designed for; asking was the defect.)
- **Mandatory backup step** — step 0 of overflow handling: copy the original to
  `docs/_MEMORY_备份_<YYYY-MM-DD>.md` (workspace) or `~/.workbuddy/memory-backups/`
  (user-level) before touching `MEMORY.md`.
- **Mandatory re-verify step** — step 4: re-run `check_memory_budget.py` and
  report before/after char counts; target ≤2800 (workspace) / ≤3800 (user).
- **Documented expected outcome** of a healthy refactor: index-only `MEMORY.md`
  (~1500–2000 chars) holding project identity, permanent red-lines, pointer table
  and sync status; zero information loss.

### Changed
- Overflow handling now spells out the practical workspace layout actually used:
  `<memory>/docs/<topic>.md` + a `## 详细笔记` pointer table in `MEMORY.md`.
- Bootstrap init flow item 1: "PROPOSE a refactor" → **auto-execute**
  (back up → MOVE → pointer table → re-check). Same change in the
  "Install & first-run notes" item 4 shown to users on first activation.

### Note
Also verified: local background HTTP services (e.g. detached dashboard servers)
do not survive the turn boundary in the sandbox — do not rely on them for
cross-turn previews. Recorded in project docs, not a skill change.

## [1.0.0] — 2026-09-13

- Initial release: layered memory architecture (index + MOVE overflow +
  budget-free channels), anti-loss rule (never re-compress in place),
  cross-platform budget checker (WorkBuddy / Claude Code / OpenAI Codex /
  Windsurf / Cursor), optional 资料库 sync via a project-local `sync_memory.py`
  generated from `templates/sync_memory.py.tmpl`, marketplace frontmatter
  (version / display_name / description_zh / description_en).
