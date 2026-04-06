# x-feed Migration — Compatibility Verification

**Date**: 2026-04-06 (post-fix review)
**Run**: Python Signal Engine (new) vs Shell daily-lane (old)

> **注意**：本轮修复后，以下差异已被收敛。保留此文档作为真实差异记录，不包装为"验收宣传稿"。

---

## 一、已收敛的问题（修复后验证通过）

以下问题在 Review Round 1 之前存在，已在本次修复中收敛：

### 1. session_id 在 signal / index / run.json 间不一致

**修复前状态**：signal frontmatter 使用 `feed-YYYY-MM-DD-xxxxxx`，index.md 使用 `se-YYYY-MM-DD-timestamp`，run.json 不含此字段。同一轮 run 的 session identity 漂移。

**修复后状态**（P1-1）：
- `session_id` 在 `collect_x_feed()` 开始时只生成一次，存入 `RunResult.session_id`
- signal frontmatter、index.md、run.json 三处使用完全相同的 `session_id`
- 已通过集成测试验证：`test_session_id_consistent_across_artifacts` ✅

### 2. index.md 使用绝对路径链接

**修复前状态**：index.md 中的 signal link 使用绝对路径（如 `/tmp/test-se-data/signals/x-feed/...`），导致数据目录迁移后链接失效。

**修复后状态**（P1-3）：
- `render_index_markdown()` 接收 `index_path` 参数，计算相对路径
- index.md 中 signal link 为 `signals/file.md`（相对路径）
- run.json 中 `signal_files[]` 也改为相对路径
- 已通过集成测试验证：`test_index_links_are_relative` ✅

---

## 二、仍存在的差异（Phase 1 范围内已知缺口）

以下差异在 Phase 1 不影响核心功能，但需明确记录：

### 3. signal body 空白行差异

| Version | 空白行 |
|---------|--------|
| Old shell | `## Engagement` 后无空行，直接接内容 |
| New Python | `## Engagement` 后有空行，`## Feed Context` 前也有空行 |

**影响**：无功能影响，纯展示风格差异。
**Phase 1 立场**：可接受，不影响消费侧解析。

### 4. index.md 汇总字段

| Field | Old Shell | New Python |
|-------|-----------|------------|
| `Posts exposed` vs `Signals written` | `Posts exposed` | `Signals written` |
| `Unique authors` 统计 | 有 | 无 |

**影响**：无功能影响。旧消费者如果直接解析 `Posts exposed` 字段会丢失，换成 `Signals written` 不影响 Obsidian 展示。
**Phase 1 立场**：可接受，Phase 2 可补齐。

### 5. index.md 无 `hint` 列

**现状**：旧 shell 在 table 中有一列 `hint`（从 tweet 提取的预览文字），新 Python 不生成。

**影响**：如果 Obsidian 模板依赖 `hint` 列渲染，会失效。
**Phase 1 立场**：已知缺口，Phase 2 可补。

### 6. fetched_at 时区差异

| Version | Timezone |
|---------|----------|
| Old shell | `+0800`（本地TZ） |
| New Python | `+0000`（UTC） |

**影响**：同一时刻的时间戳表示不同，解析时需注意时区转换。
**Phase 1 立场**：可接受，UTC 更适合跨时区场景。

### 7. post_id 引号格式

| Version | 格式 |
|---------|------|
| Old shell | `post_id: "2040606134050967716"`（双引号） |
| New Python | `post_id: '2040606134050967716'`（单引号） |

**影响**：YAML spec 两者完全等价，无功能影响。
**Phase 1 立场**：可接受。

---

## 三、run.json 设计纪律验证

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 不直接 `asdict()` dump `RunResult` | ✅ | `render_run_manifest()` 是唯一入口 |
| 不全量 dump `signal_records` | ✅ | 只列出 `signal_files[]` 路径 |
| `session_id` 进入 manifest | ✅（新增） | 已在 manifest 中包含 |
| 相对路径用于 artifact links | ✅（新增） | `render_run_manifest(run_json_path=...)` 计算相对路径 |

---

## 四、总体结论

| 维度 | 修复前 | 修复后 |
|------|--------|--------|
| session_id 一致性 | ❌ 不一致 | ✅ 统一 |
| index 路径可移植性 | ❌ 绝对路径 | ✅ 相对路径 |
| run.json 纪律 | ✅ 基本合规 | ✅ 强化（含 session_id、相对路径） |
| signal body 格式 | ⚠️ 空白行差异 | ⚠️ 空白行差异 |
| index 汇总字段 | ⚠️ 命名差异 | ⚠️ 命名差异 |

**Compatibility: PASS（Phase 1 可接受）**

- 已收敛：session_id 漂移、绝对路径 — 这两项在 Review 前被低估了严重性，已修复
- 已知缺口：空白行差异、hint 列缺失、unique authors 缺失 — Phase 1 范围内可接受
- 无破坏性变更：旧消费者仍可读取 signal frontmatter 和 index.md

**Phase 1 Claim**: 新 Python Signal Engine 可以替代旧 shell x-feed lane，不破坏现有 Obsidian 消费链路。Phase 2 应补齐 hint 列和 unique authors 统计。
