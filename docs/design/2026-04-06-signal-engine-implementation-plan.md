# Signal Engine v1 First-Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有 collect 语义的前提下，为 `signal-engine` 建立 Python collect runtime 的第一版骨架，并完成 `x-feed` 首条 lane 迁移，产出兼容的 `signals/*.md`、`index.md` 和新的 `run.json`，同时补齐 `diagnose / status / config check` 的最小闭环。

**Architecture:** 第一版坚持 collect-only、internal-objects-first。运行时以内存中的 `SignalRecord` / `RunResult` 为事实源，`signals/*.md`、`index.md`、`run.json` 都由对象派生生成，其中 `run.json` 必须通过单独 mapper 渲染，不能直接序列化内部对象。目录分层以职责清晰为先：CLI 参数分发保持薄，lane 只做 orchestration，source 负责取数，signals 负责 markdown/index 渲染，runtime 负责 run-level 纪律能力。

**Tech Stack:** Python CLI, dataclass, argparse/typer（按现有骨架择一沿用）, PyYAML, subprocess, pytest

---

## 0. 已拍板边界

### 本阶段要做
- Python CLI 命令树可用
- `SignalRecord` / `RunResult` dataclass 立住
- `signals/*.md` / `index.md` / `run.json` 由内部对象统一渲染
- 迁移 `x-feed`
- `diagnose --lane x-feed`
- `status --lane x-feed --date ...`
- `config check`
- compatibility verification

### 本阶段不做
- `x-following`
- `github-trending-weekly`
- `github-watch`
- `product-hunt-watch`
- filtering / dedupe / ranking / processing layer
- DB
- plugin / dynamic loading / auto-discovery
- total run manifest
- attempts history

---

## 1. 最终拍板的设计决策

### 1.1 执行顺序
采用以下顺序，而不是一上来直接把真实 lane 和渲染链混在一起：

1. 立 CLI / context / paths / model 基础骨架
2. 先用 fixture/test data 跑通渲染链
3. 再接入真实 `x-feed`
4. 再补 `diagnose / status / config check`
5. 最后做旧 shell lane 的 compatibility verification

### 1.2 dataclass 原则
- `SignalRecord` 保留固定核心字段
- 允许少量显式的 `x-feed` 内部字段
- 不把 `metadata: dict` 作为主要逃生口
- 不把 dataclass 直接做成 frontmatter 镜像
- `RunResult.status` 使用 enum，不用裸字符串

### 1.3 `run.json` 原则
- 必须通过单独 mapper 生成
- 禁止 `asdict(run_result)` 直接落盘
- 禁止全量导出 `signal_records`
- 禁止泄露 lane-specific 内部字段或渲染临时字段
- mapper 放在 `runtime/run_manifest.py`，不放到通用 output 杂糅层

### 1.4 分层原则
- `commands/`：CLI 参数解析与分发
- `core/`：models / context / paths / errors
- `runtime/`：collect orchestration、status、diagnose、run manifest
- `lanes/`：lane orchestration，只组织 source → model → render/write
- `sources/`：取数与 probe
- `signals/`：signal markdown / index render 与 write
- `state/`：第一阶段留空壳或极薄占位

---

## 2. 目标目录结构

```text
src/signal_engine/
  cli.py
  commands/
    collect.py
    diagnose.py
    status.py
    lanes.py
    config.py
  core/
    models.py
    context.py
    paths.py
    errors.py
  runtime/
    collect.py
    diagnose.py
    status.py
    run_manifest.py
  lanes/
    registry.py
    x_feed.py
  sources/
    x/
      opencli_feed.py
  signals/
    frontmatter.py
    render.py
    writer.py
    index.py
tests/
  test_models.py
  test_signal_render.py
  test_index_render.py
  test_run_manifest.py
  test_x_feed_collect.py
  test_cli_commands.py
```

---

## 3. 文件职责说明

- `src/signal_engine/cli.py`
  - 挂接一级命令树
  - 只做参数入口与 dispatch

- `src/signal_engine/commands/*.py`
  - 各子命令参数适配
  - 调用 `runtime/` 或 `lanes/` 的能力

- `src/signal_engine/core/models.py`
  - 定义 `SignalRecord`、`RunResult`、`RunStatus`

- `src/signal_engine/core/context.py`
  - 运行上下文：date、lane、data_dir、config

- `src/signal_engine/core/paths.py`
  - 输出路径规则
  - `signals/<lane>/<date>/...` 的规范化生成

- `src/signal_engine/runtime/run_manifest.py`
  - `render_run_manifest(run_result)`
  - `write_run_manifest(...)`

- `src/signal_engine/runtime/collect.py`
  - 通用 collect orchestration 入口
  - 根据 lane 分发到对应 lane runner

- `src/signal_engine/runtime/diagnose.py`
  - `x-feed` 相关最小诊断项

- `src/signal_engine/runtime/status.py`
  - 基于既有产物读取状态

- `src/signal_engine/lanes/registry.py`
  - lane 名称到实现的静态映射
  - 第一版不用动态注册

- `src/signal_engine/lanes/x_feed.py`
  - `x-feed` lane orchestration
  - 不直接拼 markdown，不直接硬写 run.json

- `src/signal_engine/sources/x/opencli_feed.py`
  - 封装 `opencli` timeline/feed 调用
  - 返回 Python 原始结构

- `src/signal_engine/signals/frontmatter.py`
  - frontmatter 生成逻辑

- `src/signal_engine/signals/render.py`
  - `SignalRecord -> markdown`
  - `RunResult + records -> index.md`

- `src/signal_engine/signals/writer.py`
  - 原子写 signal markdown / index 文件

- `src/signal_engine/signals/index.py`
  - index 数据准备或专门 index render 封装

---

## 4. dataclass 草案

### 4.1 `SignalRecord`

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class SignalRecord:
    # 核心固定字段
    lane: str
    signal_type: str
    source: str
    entity_type: str
    entity_id: str
    title: str
    source_url: str
    fetched_at: str
    file_path: Optional[str] = None

    # x-feed 第一阶段显式内部字段
    handle: str = ""
    post_id: str = ""
    created_at: str = ""
    position: int = 0
    text_preview: str = ""
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    views: int = 0
```

#### 说明
- 核心字段对齐 v1 spec
- `post_id` 是否与 `entity_id` 重合可在实现时二选一，但第一阶段允许并存，优先保持可读性
- 不设通用 `metadata` 作为默认出口
- 如果后续必须扩展，新增字段应显式加进 dataclass，而不是偷塞 dict

### 4.2 `RunStatus`

```python
from enum import Enum

class RunStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    EMPTY = "empty"
```

### 4.3 `RunResult`

```python
from dataclasses import dataclass, field

@dataclass
class RunResult:
    lane: str
    date: str
    status: RunStatus
    started_at: str
    finished_at: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    signal_records: list[SignalRecord] = field(default_factory=list)
    repos_checked: int = 0
    signals_written: int = 0
    signal_types_count: dict[str, int] = field(default_factory=dict)
    index_file: str | None = None
```

#### 说明
- 运行时保留完整 `signal_records`
- `signal_types_count` 是内部聚合字段，可供 summary 使用
- `run.json` 不直接落 `signal_records`

---

## 5. `run.json` mapper 最终方案

### 模块
- `src/signal_engine/runtime/run_manifest.py`

### 接口

```python
def render_run_manifest(run_result: RunResult) -> dict:
    return {
        "lane": run_result.lane,
        "date": run_result.date,
        "status": run_result.status.value,
        "started_at": run_result.started_at,
        "finished_at": run_result.finished_at,
        "warnings": run_result.warnings,
        "errors": run_result.errors,
        "summary": {
            "repos_checked": run_result.repos_checked,
            "signals_written": run_result.signals_written,
            "signal_types": run_result.signal_types_count,
        },
        "artifacts": {
            "index_file": run_result.index_file,
            "signal_files": [r.file_path for r in run_result.signal_records if r.file_path],
        },
    }
```

### 纪律
- 这是 `RunResult -> run.json` 的唯一出口
- 禁止直接 `asdict(run_result)`
- 禁止输出完整 records 内容
- 未来如要加字段，必须显式改 mapper 和测试

---

## 6. `x-feed` 第一阶段迁移方案

### 6.1 shell → Python 映射

- `opencli` 调用 → `sources/x/opencli_feed.py`
- feed JSON 解析 → `x_feed.py` 中的数据适配
- 单条记录映射 → `SignalRecord`
- signal markdown 渲染 → `signals/render.py`
- `index.md` 渲染 → `signals/index.py` / `signals/render.py`
- `run.json` 生成 → `runtime/run_manifest.py`

### 6.2 `x_feed.py` 的职责
只做 orchestration：
1. 调 source 拉取 feed
2. 把原始 row 转成 `SignalRecord`
3. 调 signal writer 写每条 markdown
4. 汇总 `RunResult`
5. 渲染并写 `index.md`
6. 渲染并写 `run.json`
7. 返回 `RunResult`

明确不做：
- 不在 lane 文件内大段拼 markdown
- 不在 lane 文件内自己实现 run.json schema
- 不在 lane 文件内夹带 diagnose/status 逻辑

### 6.3 source 封装最小要求
- 封装 `opencli` 路径与参数
- 返回 Python list/dict
- 抛出明确异常或错误结果
- 第一阶段不做复杂 retry/recovery

### 6.4 兼容目标
必须尽量兼容：
- 目录结构
- signal 文件命名
- signal markdown 核心 frontmatter
- `index.md` 基本结构
- collect 结果语义

允许微调：
- 少量文本格式
- 内部实现方式
- 新增 `run.json`

---

## 7. 最终实施步骤

### Task 1: 立住核心骨架

**Files:**
- Create: `src/signal_engine/core/models.py`
- Create: `src/signal_engine/core/context.py`
- Create: `src/signal_engine/core/paths.py`
- Modify: `src/signal_engine/cli.py`
- Create: `src/signal_engine/commands/collect.py`
- Create: `src/signal_engine/commands/diagnose.py`
- Create: `src/signal_engine/commands/status.py`
- Create: `src/signal_engine/commands/lanes.py`
- Create: `src/signal_engine/commands/config.py`
- Test: `tests/test_models.py`
- Test: `tests/test_cli_commands.py`

- [ ] Step 1: 写 `RunStatus` / `SignalRecord` / `RunResult` 的失败测试
- [ ] Step 2: 实现 dataclass 与最小构造逻辑
- [ ] Step 3: 写 CLI 一级命令树测试
- [ ] Step 4: 实现 `collect / diagnose / status / lanes list / config check` 的参数入口
- [ ] Step 5: 跑测试并通过
- [ ] Step 6: 提交一次骨架 commit

### Task 2: 先锁渲染链（fixture 驱动）

**Files:**
- Create: `src/signal_engine/signals/frontmatter.py`
- Create: `src/signal_engine/signals/render.py`
- Create: `src/signal_engine/signals/writer.py`
- Create: `src/signal_engine/signals/index.py`
- Create: `src/signal_engine/runtime/run_manifest.py`
- Test: `tests/test_signal_render.py`
- Test: `tests/test_index_render.py`
- Test: `tests/test_run_manifest.py`

- [ ] Step 1: 写 `SignalRecord -> markdown` 的失败测试
- [ ] Step 2: 写 `RunResult -> run.json` 的失败测试
- [ ] Step 3: 写 `RunResult + records -> index.md` 的失败测试
- [ ] Step 4: 实现 signal markdown render
- [ ] Step 5: 实现 index render
- [ ] Step 6: 实现 `render_run_manifest()`
- [ ] Step 7: 实现 writer 的原子写逻辑
- [ ] Step 8: 跑上述测试并通过
- [ ] Step 9: 提交一次 render-chain commit

### Task 3: 接入 `x-feed` 真实 lane

**Files:**
- Create: `src/signal_engine/lanes/registry.py`
- Create: `src/signal_engine/lanes/x_feed.py`
- Create: `src/signal_engine/sources/x/opencli_feed.py`
- Create or Modify: `src/signal_engine/runtime/collect.py`
- Test: `tests/test_x_feed_collect.py`

- [ ] Step 1: 写 source 层失败测试（调用参数 / 返回结构）
- [ ] Step 2: 实现 `opencli` fetch 封装
- [ ] Step 3: 写 `row -> SignalRecord` 映射测试
- [ ] Step 4: 实现 `x-feed` collect orchestration
- [ ] Step 5: 让 collect 能写出 signal markdown / `index.md` / `run.json`
- [ ] Step 6: 跑 lane 测试并通过
- [ ] Step 7: 提交一次 x-feed migration commit

### Task 4: 补最小运行纪律层

**Files:**
- Create or Modify: `src/signal_engine/runtime/diagnose.py`
- Create or Modify: `src/signal_engine/runtime/status.py`
- Modify: `src/signal_engine/commands/diagnose.py`
- Modify: `src/signal_engine/commands/status.py`
- Modify: `src/signal_engine/commands/config.py`
- Test: `tests/test_cli_commands.py`

- [ ] Step 1: 写 `config check` 的失败测试
- [ ] Step 2: 实现配置加载与校验
- [ ] Step 3: 写 `diagnose --lane x-feed` 的失败测试
- [ ] Step 4: 实现 diagnose 最小检查项（配置 / opencli / 输出目录）
- [ ] Step 5: 写 `status --lane x-feed --date ...` 的失败测试
- [ ] Step 6: 实现 status 基于 `run.json` + `index.md` 的读取
- [ ] Step 7: 跑相关测试并通过
- [ ] Step 8: 提交一次 runtime-discipline commit

### Task 5: compatibility verification

**Files:**
- Create: `docs/verification/2026-04-06-x-feed-migration-check.md`

- [ ] Step 1: 用同一输入跑旧 shell `x-feed`
- [ ] Step 2: 用同一输入跑新 Python `x-feed`
- [ ] Step 3: 对比 signal 文件数
- [ ] Step 4: 对比 signal markdown 核心字段
- [ ] Step 5: 对比 `index.md` 关键摘要
- [ ] Step 6: 检查 `run.json` 字段完整性与覆盖写行为
- [ ] Step 7: 记录允许差异与实际结论
- [ ] Step 8: 提交一次 verification commit

---

## 8. 验收标准

### 必须成立
- `signal-engine collect --lane x-feed --date <date>` 能跑
- 生成 `signals/*.md`
- 生成 `index.md`
- 生成 `run.json`
- `signal-engine diagnose --lane x-feed` 能跑
- `signal-engine status --lane x-feed --date <date>` 能跑
- `signal-engine config check` 能跑

### 最好成立
- 旧 shell lane 与新 Python lane 的 signal 数量一致或足够接近
- signal markdown 核心信息一致
- `index.md` 关键摘要一致
- 同一天重复运行时 `run.json` 正常覆盖写

---

## 9. 风险与防脏规则

### 风险 1：lane 文件重新长成 shell 风格
**防治：** `x_feed.py` 不直接拼 markdown，只调 render/write。

### 风险 2：`run.json` 长胖
**防治：** 单独 mapper + 白盒测试；不导出 records 全量内容。

### 风险 3：为了兼容旧产物不敢立内部模型
**防治：** 先锁对象和 render 链，再谈兼容验证。

### 风险 4：`diagnose/status/config` 一上来平台化
**防治：** 第一阶段只服务 `x-feed` 最小闭环。

---

## 10. 最终一句话执行口径

> 先把骨架立正，先锁内部对象到派生产物的渲染链，再迁 `x-feed`；第一阶段只求 collect runtime 成立、对外兼容、`run.json` 克制、运行纪律最小闭环，不做多 lane 抽象，不做平台，不做 processing。
