# 2026-04-06｜x-feed migration spec

## 1. 目标

把当前 `daily-lane` 里的 `x-feed` 从 shell lane 迁到 Signal Engine Python CLI，作为第一批试点。

目标不是“顺手优化一切”，而是：
- 验证 Signal Engine v1 的 Python CLI 骨架
- 验证内部模型 → 文件产物的渲染链
- 保持 `x-feed` 现有 collect 语义基本兼容
- 新增 `run.json`

---

## 2. 当前源对象

当前 shell 实现：
- `daily-lane/lanes/x-feed.sh`

当前职责：
- 调 opencli 获取 timeline/feed JSON
- 逐条写 signal markdown
- 生成 `index.md`
- 输出统计

---

## 3. 第一批迁移范围

### 做什么
- 迁 `x-feed` collect 主流程
- 迁 `index.md` 生成
- 新增 `run.json`
- 接入 Signal Engine CLI：
  - `collect`
  - `diagnose`
  - `status`
  - `lanes list`
  - `config check`

### 不做什么
- 不改业务语义
- 不加 filtering/ranking
- 不改成 processing layer
- 不顺手迁 `x-following`
- 不顺手重做 opencli 本身调用方式

---

## 4. 输入

### CLI 入口

```bash
signal-engine collect --lane x-feed --date 2026-04-06
```

### 配置来源

第一版仍读取现有配置里的 `x-feed` 部分，至少兼容这些关键项：
- `opencli.path`
- `opencli.limit`

### 外部依赖
- `opencli` 可执行
- 返回 JSON 可解析

---

## 5. 内部运行模型

### 5.1 `SignalRecord`
每条 feed exposure 转成一条 `SignalRecord`。

建议映射关系：
- `signal_type`: `feed-exposure`
- `source`: `x`
- `lane`: `x-feed`
- `entity_type`: `author`
- `entity_id`: handle
- `title`: `@handle #position`
- `source_url`: tweet url
- `fetched_at`: 本条 tweet/create time 或抓取时间（以当前兼容行为为准）
- `file_path`: 渲染后产物路径

### 5.2 `RunResult`
一次 `x-feed` collect 形成一个 `RunResult`。

至少包含：
- lane=`x-feed`
- date
- status
- started_at / finished_at
- warnings / errors
- signal_records[]
- signals_written
- index_file

---

## 6. 输出

### 6.1 signal markdown
继续生成：
- `signals/*.md`

要求：
- 文件命名规则尽量兼容当前版本
- frontmatter 关键字段尽量兼容
- body 结构尽量兼容

原则：
- 不要求逐字符兼容
- 但要保证旧链路还能读
- 人看起来语义一致
- 下游日报链不因格式大变而失效

### 6.2 `index.md`
继续生成：
- `index.md`

要求：
- 结构尽量兼容当前 `x-feed` index
- 仍保留当前作为导航入口的作用
- 但架构上它是派生产物

### 6.3 `run.json`
新增：
- `run.json`

路径：
- `signals/x-feed/<date>/run.json`

字段遵循 v1 spec。

---

## 7. 兼容性要求

### 7.1 必须兼容
- lane 目录结构
- signal markdown 仍能被现有链路消费
- `index.md` 仍可作为人工入口
- collect 结果语义不变
- 对相同输入，不应出现明显少抓/乱抓

### 7.2 可以变化
- 内部实现方式
- 中间对象结构
- Python 代码组织
- 增加 `run.json`
- 少量非关键文本格式细节

### 7.3 不应变化
- lane 职责边界
- 输出主路径
- 每条 signal 的核心信息
- `x-feed` 作为 collect lane 的定位

---

## 8. diagnose / status 在 `x-feed` 第一批中的最低要求

### 8.1 `diagnose --lane x-feed`
最低检查项建议：
- 配置可加载
- `opencli.path` 存在/可执行
- `opencli` 基本调用可用
- 输出目录可写

先不要做得太重。

### 8.2 `status --lane x-feed --date ...`
最低返回内容建议：
- 该日是否有 `run.json`
- run status
- signals_written
- `index.md` 是否存在
- signal_files 数量

---

## 9. 实现拆分建议

### Step 1：骨架
- Python CLI 入口
- `collect/diagnose/status/lanes/config`
- `dataclass`
- signal writer / index writer / run manifest mapper 骨架

### Step 2：迁 `x-feed`
- opencli 调用
- JSON parsing
- `SignalRecord` 映射
- markdown render
- index render
- run.json render

### Step 3：验证
- 与旧 shell lane 对比产物
- try-run
- 检查兼容性边界

---

## 10. 验收标准

如果第一批 `x-feed` 迁移完成，至少应满足：

1. 能跑：
```bash
signal-engine collect --lane x-feed --date <date>
```

2. 会产出：
- signal markdown
- `index.md`
- `run.json`

3. `diagnose` 可用：
```bash
signal-engine diagnose --lane x-feed
```

4. `status` 可用：
```bash
signal-engine status --lane x-feed --date <date>
```

5. 输出语义与旧版 shell lane 基本一致

---

## 11. 一句话总结

> `x-feed` 第一批迁移不是为了证明 Python 更优雅，而是为了验证：Signal Engine v1 的 Python CLI 骨架、内部对象模型、派生产物链（signal markdown / index.md / run.json）是否成立，而且不破坏现有 collect 语义。
