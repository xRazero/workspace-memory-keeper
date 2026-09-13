# Workspace Memory Keeper

> 一套「分层记忆」技能，让 WorkBuddy 的自动注入 `MEMORY.md` 永远只做小而稳的索引，
> 彻底避免被 3000 / 4000 字符预算**静默砍尾丢信息**；溢出内容用 MOVE 而非就地压缩，
> 杜绝反复压缩造成的信息损失。

[English summary](#english-summary) · MIT License

---

## 痛点：你的记忆正在被悄悄截断

WorkBuddy 在每次会话开始时，会把 `MEMORY.md` **自动注入**到上下文，但只注入文件头部约：

- 工作区 `<ws>/.workbuddy/memory/MEMORY.md`：**≤ 3000 字符**
- 用户级 `~/.workbuddy/MEMORY.md`：**≤ 4000 字符**

**超出部分被平台静默丢弃**（只注入头部，尾部丢失），且本地磁盘上的文件可以很大（实测曾达 15 KB）——你以为记下了，模型其实没看到。很多人「压缩一下 MEMORY.md」来腾空间，结果每次压缩都丢一点信息，越压越碎。

本技能就是为了解决这个问题：建立一套结构，让注入区永远小而稳，把增长推向**零预算**的渠道（每日日志、本地 `docs/`、资料库）。

---

## 核心机制

### 三层记忆

| 层 | 位置 | 作用 | 预算 |
|---|---|---|---|
| L0 全局中枢 | 用户级 `~/.workbuddy/MEMORY.md`（≤4000） | 跨项目永久红线 + 机制指针 | 注入 |
| L1 项目工作区 | `<ws>/.workbuddy/memory/`（`MEMORY.md` 索引 ≤3000、每日日志、`docs/`） | 本项目细节 | 仅索引注入；日志/docs 按需拉取，**无预算** |
| L2 共享知识中枢（可选） | 资料库(Library) 节点 + `/memory-hub/projects/<name>/` 命名空间 | 跨项目可检索的结构化知识 | 无预算 |

### 四条铁律

1. **MEMORY.md 只做索引**：身份/目录、真相地图（去哪找 X）、永久红线、tiny 同步状态。绝不放日期流水、规格大块、易变细节。
2. **溢出 MOVE 不压缩**：超预算就把「发生了什么」追加到 `YYYY-MM-DD.md`、把结构化知识移到 `docs/<topic>.md`，在 MEMORY.md 留一行指针。
3. **硬上限不可扩**：3000/4000 是平台注入硬上限，本地无配置项可放大（已核查 settings/app-config/文档均无相关键）。本技能是「绕开」而非「突破」。
4. **按需检索按相关性优先**：注入区(P0) > 工作区日志(P1) > 项目 docs/资料库(P2) > 跨会话搜索(P3)；范围优先于成本，注入内容已在上下文就别再读盘。

---

## 安装

把本技能目录放到 WorkBuddy 的用户级技能目录即可：

```bash
# 方式 A：直接拷贝
cp -r workspace-memory-keeper ~/.workbuddy/skills/

# 方式 B：作为 git 仓库
git clone <your-repo> ~/.workbuddy/skills/workspace-memory-keeper
```

**安装瞬间零改动**：只拷贝 `SKILL.md` + `references/` + `scripts/` + `templates/`，
**不会动你任何记忆文件**。首次激活时技能会提示你并（在你同意后）追加一段纪律说明，
该追加幂等、不覆盖/不删除你已有内容、受 4000 上限约束，也可拒绝。

---

## 快速使用

### 1. 写记忆前自检（清单）

- 稳定事实 / 永久规则？→ `MEMORY.md`
- 「今天干了啥」？→ 每日日志 `YYYY-MM-DD.md`
- 结构化知识 / 规格？→ `docs/*.md`（+ 资料库同步）
- 编辑后 MEMORY.md 会超过 ~2800 字符？→ 把溢出 MOVE 出去，留指针，**不要压缩**

### 2. 检查预算（脚本，任意项目可用）

```bash
python ~/.workbuddy/skills/workspace-memory-keeper/scripts/check_memory_budget.py <你的项目目录>
```

输出工作区与用户级 MEMORY.md 的字符数（Python `len()` 口径，非字节非 `wc -m`）及是否超出缓冲。

### 3. 新项目引导（bootstrap）

首次在某项目激活技能时，技能会确保分层骨架存在（不静默覆盖你现有内容）：
- 缺 `MEMORY.md` → 生成最小索引模板；已有但是大杂烩 → **提议重构**（MOVE+指针），不原地重写。
- 项目要镜像 `docs/` 到资料库 → 从模板复制 `sync_memory.py` + 生成 `sync_state.json`，注册独立命名空间。
- 用户级 MEMORY.md 缺纪律段 → 提议幂等追加（可拒）。

---

## 可选：资料库同步（跨项目共享知识）

适合「把 `docs/*.md` 镜像到资料库(Library) 长期沉淀、跨项目检索」的项目。

**准备**（每项目一次，脚本完全通用，无需改代码）：

```bash
# 1) 从单源模板复制薄启动器到项目内
cp ~/.workbuddy/skills/workspace-memory-keeper/templates/sync_memory.py.tmpl \
   <ws>/.workbuddy/memory/sync_memory.py

# 2) 生成状态文件（namespace 改成你的项目名）
cat > <ws>/.workbuddy/memory/sync_state.json <<'JSON'
{
  "namespace": "/memory-hub/projects/<your-project>",
  "files": {}
}
JSON
```

**日常命令**：

```bash
# 离线安全检查（不触网）：逐文件比对哈希 → synced / dirty / pending_offline
python <ws>/.workbuddy/memory/sync_memory.py check

# 列出全部文件↔节点映射
python <ws>/.workbuddy/memory/sync_memory.py list

# 首次发布某文件后登记映射（拿回 nodeId）
python <ws>/.workbuddy/memory/sync_memory.py init --path docs/foo.md --node-id <NODE_ID>

# 脏了且在线则重新发布（token 由宿主经 connect_open_platform 换票后从 stdin 注入，不落盘）
echo "$TOKEN" | python <ws>/.workbuddy/memory/sync_memory.py push --path docs/foo.md --token-stdin
```

> **关键设计**：节点映射（path→node_id/url/hash/status）全部存在 `sync_state.json`
> （机器可读、零注入预算），MEMORY.md 只留一行指针。新增任意文件只动 `sync_state.json`，
> 不会把 MEMORY.md 推向 3000 字符上限——这是「每发一个资料库节点就在 MEMORY.md 加一行 URL」
> 那种做法的致命泄漏的根治方案。
>
> 依赖 WorkBuddy 内置「资料库(Library)」技能；其目录通过 `LIBRARY_SKILL_DIR` 环境变量指定，
> 未设置时按 Windows/macOS/Linux 常见路径自动探测。`check`/`list`/`init` 不需要该技能。

---

## 文件结构

```
workspace-memory-keeper/
├── SKILL.md                              # 技能本体（触发/机制/纪律/bootstrap/安装提示）
├── references/
│   └── memory-rules.md                   # 详细规则、证据、架构表、同步协议、检索优先级
├── scripts/
│   └── check_memory_budget.py            # 预算检查脚本（任意项目可用）
├── templates/
│   └── sync_memory.py.tmpl               # 通用同步薄启动器（复制到项目内即用）
├── README.md                             # 本文件
└── LICENSE                               # MIT
```

---

## 常见问题

**Q: 3000/4000 能调大吗？**
A: 不能（已核查平台无相关配置）。本技能是绕开：把增长推向零预算的日志/docs/资料库。

**Q: 压缩 MEMORY.md 腾空间不行吗？**
A: 不行。就地压缩会静默丢信息，且每次加细节都要重压，正是被本技能杜绝的丢信息路径。用 MOVE。

**Q: 字符数到底按什么算？**
A: Python `len()`（Unicode 码点），与平台注入预算一致。`wc -m` 在部分环境会多算组合字符，`wc -c` 算字节（CJK 不准）。

**Q: 这套机制跨项目通用吗？**
A: 纪律层（技能 + 用户级 MEMORY.md + 分层结构）天然跨项目；同步脚本每项目自带一份薄启动器（单源模板，避免 N 份漂移）；资料库节点按项目独立、统一挂 `/memory-hub/projects/<name>/` 便于跨项目检索。

---

## English Summary

**Problem:** WorkBuddy silently truncates the auto-injected `MEMORY.md` at ~3000 (workspace) /
4000 (user) characters; the on-disk file can be far larger, so important memory is lost without
warning. Re-compressing to save space drops information every time.

**Solution — layered memory discipline:**
- `MEMORY.md` stays a small, stable **index** (identity, pointers, red-lines, tiny sync status).
- Overflow goes to **budget-free** channels: append-only daily logs + `docs/*.md` + optional
  资料库 (Library) nodes. **MOVE, never compress.**
- The 3000/4000 cap is a hard platform limit (no local config to raise it) — design around it.
- On-demand retrieval is **relevance-first**: injected (P0) > workspace logs (P1) > project
  docs/library (P2) > cross-session search (P3).

**Bundled:** a budget-check script, a generic project-local library-sync launcher template
(`sync_memory.py`), and full rules/evidence reference. Installs with **zero changes** to your
existing memory files; first-run appends an idempotent discipline note you may decline.

MIT licensed.

---

## License

MIT — see [LICENSE](./LICENSE).
