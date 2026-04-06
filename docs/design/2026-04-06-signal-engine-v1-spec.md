# 2026-04-06｜Signal Engine v1 spec

## 1. 目标

Signal Engine v1 是一个 **Python collect CLI**。

它的目标是：
- 承接 `daily-lane` 当前的 collect 职责
- 用更清晰的 runtime 结构重建 collect 层
- 保持现有 signal 产物链路可继续工作
- 补齐运行纪律层的基础能力
  - `diagnose`
  - `status`
  - `config-check`
  - `run.json`

---

## 2. 第一版边界

### 2.1 做什么
Signal Engine v1 只做到 **collect runtime**：

- collect
- normalize
- signal markdown 写入
- `index.md` 写入
- `state/*` 写入
- `run.json` 写入
- `diagnose`
- `status`
- `config check`
- 预留很薄的 mock 能力

### 2.2 不做什么
第一版明确不做：

- filtering
- dedupe
- ranking
- processing layer
- agent synthesis
- plugin system
- dynamic adapter loading
- 总 run manifest
- attempts history
- DB 事实源

一句话：

> v1 是 collect runtime，不是 processing engine，也不是 CLI platform。

---

## 3. CLI 命令树

第一版一级命令树已定为：

```bash
signal-engine collect
signal-engine diagnose
signal-engine status
signal-engine lanes
signal-engine config
```

### 推荐交互形态

```bash
signal-engine collect --lane x-feed --date 2026-04-06
signal-engine diagnose --lane x-feed
signal-engine status --lane x-feed --date 2026-04-06
signal-engine lanes list
signal-engine config check
```

### 设计原则

- `collect / diagnose / status` 是一级动作
- `lane` 是目标对象
- 不做 `signal-engine x-feed collect` 这种 lane-first 命令树

---

## 4. 内部模型

### 4.1 存储原则
第一版采用：

> **内存对象 + 文件落地**

不引入 DB 作为事实源。

### 4.2 typed model
第一版内部对象使用：
- Python `dataclass`

不先上 Pydantic。

### 4.3 `SignalRecord`
表示单条 signal 的内部事实源。

建议字段：
- `signal_type`
- `source`
- `title`
- `source_url`
- `fetched_at`
- `file_path`
- `lane`
- `entity_id`
- `entity_type`

### 4.4 `RunResult`
表示一次 lane/day collect run 的内部事实源。

建议至少包含：
- `lane`
- `date`
- `status`
- `started_at`
- `finished_at`
- `warnings`
- `errors`
- `signal_records`
- `repos_checked`
- `signals_written`
- `signal_types_count`
- `index_file`

### 4.5 关键语义

- `SignalRecord` 先成型，再统一渲染 signal markdown
- 运行时内存里保留完整 `signal_records[]`
- 但 `run.json` 不全量落这些记录

---

## 5. 输出协议

第一版保留现有产物，同时补一个新的 run-level manifest。

### 5.1 保留的产物
- `signals/*.md`
- `index.md`
- `state/*`

### 5.2 新增的产物
- `run.json`

---

## 6. `index.md` 的定位

`index.md` 第一版继续保留，但架构上：

> **明确降级为派生产物。**

它不是事实源，只是兼容现有链路的人类可读入口。

---

## 7. `run.json` 规则

### 7.1 定位
`run.json` 是：

> **run-level manifest / 运行收据**

不是第二套 signal 内容系统。

### 7.2 粒度
按 **lane/day** 写，例如：
- `signals/x-feed/2026-04-06/run.json`
- `signals/github-watch/2026-04-06/run.json`

### 7.3 生命周期
- 每次 collect 都写
- 成功失败都写
- 覆盖写
- 不保留 attempts history

### 7.4 最小字段
第一版字段已定为：
- `lane`
- `date`
- `status`
- `started_at`
- `finished_at`
- `warnings`
- `errors`
- `summary.repos_checked`
- `summary.signals_written`
- `summary.signal_types`
- `artifacts.index_file`
- `artifacts.signal_files`

### 7.5 渲染方式
`run.json` 不直接等于 `RunResult` 全量序列化。

而是：

> `RunResult` → manifest mapper → `run.json`

也就是内部模型和外部协议分离。

---

## 8. 目录与事实源关系

第一版事实关系应明确为：

### 内部事实源
- `SignalRecord`
- `RunResult`

### 外部落地产物
- signal markdown
- `index.md`
- `state/*`
- `run.json`

### 规则
- 对象优先
- 文件派生
- 不允许不同输出各自生成一套业务逻辑

---

## 9. 第一批迁移范围

第一批迁移范围已定：

> **只迁 `x-feed`**

### 不在第一批的
- `x-following`
- `github-trending-weekly`
- `github-watch`
- `product-hunt-watch`

### 原因
- 用最小 lane 先验证 Python CLI runtime
- 避免一开始把 lane 迁移和复杂 stateful 逻辑绑在一起

---

## 10. 第一批实现目标

第一批实现不等于“做完整 Signal Engine”，而是：

### 10.1 先有 Python CLI 骨架
至少包括：
- 命令树
- `dataclass` 内部模型
- 基础渲染层
- `run.json` mapper
- signal/index writer 骨架

### 10.2 再完成 `x-feed`
要求：
- 跑通 collect
- 写出兼容 signal markdown
- 写出兼容 `index.md`
- 生成 `run.json`

---

## 11. 验收原则

### 11.1 对外兼容
第一批 `x-feed` 迁移时，对外应尽量兼容：
- 目录结构
- signal 文件命名
- signal markdown 基本格式
- `index.md` 基本结构

### 11.2 可允许变化
可以变化的部分：
- 内部实现方式
- 中间对象结构
- 代码组织
- 新增 `run.json`

### 11.3 不允许变化
不应变化的部分：
- lane 基本职责
- collect 结果语义
- 现有链路依赖的核心产物位置
- 第一版边界（不能偷偷加入 ranking/filtering）

---

## 12. 设计原则总括

Signal Engine v1 应遵守：

1. **collect-only**
2. **runtime, not platform**
3. **internal objects first**
4. **files are derived artifacts**
5. **run manifest stays thin**
6. **compatibility outside, cleanup inside**
