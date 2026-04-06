# Signal Engine x-feed Native Source Migration Design

**日期：** 2026-04-06  
**状态：** 待评审草案  
**范围：** 在保留 Phase 1 runtime / artifact 架构的前提下，用 Signal Engine 原生 X source 实现替换 `x-feed` 当前对 `opencli` 的依赖。

---

## 1. 目标

把 `signal-engine` 的 `x-feed` lane 从 `opencli` 上彻底迁下来，使得：

- `signal-engine collect --lane x-feed` 不再通过 shell 调 `opencli`
- `signal-engine` 自己拥有并维护 X source backend
- 已经在 Phase 1 立住的 runtime 行为保持不变：
  - `SignalRecord`
  - `RunResult`
  - `signals/*.md`
  - `index.md`
  - `run.json`
  - `collect / diagnose / status / config`
- 代码仓、配置、诊断、测试、文档都不再把 `opencli` 当成系统依赖

这次迁移属于 **B2 路线**：

- 不是完全从零重写一套 X 抓取逻辑
- 也不是继续在运行时依赖 `opencli`
- 而是把已经在 `opencli` 中验证过的 X adapter 核心逻辑，受控地迁入 `signal-engine`

---

## 2. 非目标

这份设计**不包含**以下内容：

- 重做 `SignalRecord` / `RunResult`
- 重做 artifact 协议（`signals/*.md`、`index.md`、`run.json`）
- 迁移其他 X lane，例如 `x-following`
- 引入 plugin system 或 source auto-discovery
- 在 `signal-engine` 内保留 `opencli` 作为正式 fallback backend
- 把 `signal-engine` 扩成 `opencli` 的通用替代品
- 从零开始做一套全新的 X 逆向抓取工程

---

## 3. 验收级别

这次迁移按 **Level C 完成标准** 验收：

> 不仅 `x-feed` 在运行时要摆脱 `opencli`，而且代码仓、配置、诊断、测试、正式文档也都不能再把 `opencli` 当成受支持系统的一部分。

只要出现下面任一情况，就不能算迁移完成：

- runtime 仍然 shell 调 `opencli`
- config 仍然沿用 `opencli.path` 这类语义
- diagnose 仍然检查 `dist/main.js`
- docs 仍然把 `opencli` 写成运行依赖
- tests 仍然主要围绕旧 backend 假设构造

---

## 4. 推荐方案

### 4.1 选定方向

采用**受控迁移**策略：

- 保留 Phase 1 已经成立的 runtime / artifact 架构
- 只替换 X source backend
- 只迁入 `x-feed` 所需的最小 X timeline 获取逻辑
- 迁入后的代码必须按 Signal Engine 自己的边界重组
- 不在 `signal-engine` 内保留 `opencli_legacy` 或双 backend runtime 支持

### 4.2 为什么这样选

这个方案平衡了三件事：

1. **比运行时复用更干净**：`signal-engine` 真正获得独立运行能力
2. **比完全重写更省**：不用从零重新摸一遍 X 获取链路
3. **比大改架构更稳**：不会冲掉已经在 Phase 1 验证过的 runtime 设计

---

## 5. 架构设计

## 5.1 保持稳定的 runtime 边界

下面这些层在概念上保持不变：

- `commands/`
- `runtime/`
- `lanes/x_feed.py`
- `SignalRecord` / `RunResult`
- signal markdown render / writer
- index render / writer
- run manifest mapper / writer

`x-feed` lane 仍然只消费一个 source 接口，拿到规范化的 feed item 后，再映射成 `SignalRecord` 和 artifact。

### 设计规则

`x-feed` lane 不应该知道：

- source 是怎么发请求的
- 内部用了 cookies、feature flags 还是别的 auth 方式
- 任何历史上的 `opencli` 命令语义
- 任何浏览器或 transport 细节

它只应该知道：

- 怎么调 source
- source 返回什么标准字段
- 怎么把这些字段映射成 `SignalRecord`

---

## 5.2 新的 source 子系统

建议目录结构如下：

```text
src/signal_engine/sources/x/
  __init__.py
  auth.py
  client.py
  parser.py
  models.py
  errors.py
  timeline.py
```

### `auth.py`
职责：
- 加载认证材料
- 校验 auth 是否存在、格式是否合理
- 向 source 层暴露统一的 auth state

例如：
- cookie 文件发现
- cookie 解析
- auth preflight validation

### `client.py`
职责：
- 构造 home timeline 请求
- 执行 transport
- 把请求层和解析层隔开

### `parser.py`
职责：
- 把原始 X timeline 响应转成标准化 source-side 对象
- 明确集中处理 schema 假设
- 显式探测 schema drift

### `models.py`
职责：
- 定义 source 层标准化后的数据结构
- 承载 `x-feed` lane 所依赖的最小 source contract

### `errors.py`
职责：
- 定义 source 专属错误类型
- 区分 auth、transport、rate-limit、parse、schema 等失败类型

### `timeline.py`
职责：
- 暴露 lane 使用的稳定入口，例如：
  - `fetch_home_timeline(limit: int) -> list[NormalizedTweet]`

---

## 6. Source Contract

`x-feed` lane 只依赖一份规范化 tweet 结构，至少包含这些字段：

- `id`
- `author`
- `text`
- `likes`
- `retweets`
- `replies`
- `views`
- `created_at`
- `url`

这就是当前 Phase 1 artifact 生成真正需要的最小字段集。

### Contract 规则

lane 只依赖这份标准化字段集。

它**不依赖**：

- 原始 X 响应结构
- 旧 `opencli` 的字段命名
- transport 细节
- 浏览器 / CDP 细节
- 请求签名、feature flags 等内部实现

---

## 7. 错误模型

native X source 应显式定义错误分类，例如：

- `AuthError`
- `TransportError`
- `RateLimitError`
- `SchemaError`
- `SourceUnavailableError`

这样做的原因是：

当前 Phase 1 runtime 已经区分了 `SUCCESS / EMPTY / FAILED`，native source 迁移后应该让诊断更清楚，而不是更模糊。

### 边界映射要求

在 lane/runtime 边界：

- auth / transport / schema 失败应变成结构化 run errors
- empty feed 必须和 source breakage 区分开
- diagnose 必须能够指出到底是哪一层坏了

---

## 8. Config 设计

迁移完成后，config 必须去 `opencli` 化。

### 需要移除的现有语义
下面这类配置不应继续作为正式配置形态存在：

- `lanes.x-feed.opencli.path`
- `lanes.x-feed.opencli.limit`

### native config 方向
配置应该描述 source 本身，而不是旧 backend。比如：

```yaml
lanes:
  x-feed:
    enabled: true
    source:
      limit: 100
      timeout_seconds: 30
      auth:
        cookie_file: ~/.signal-engine/x-cookies.json
```

字段名字实现时可以细调，但规则不能变：

> config 应表达 native source 的运行需求，而不是 legacy backend 的 plumbing。

---

## 9. Diagnose 设计

`diagnose --lane x-feed` 必须停止检查 `opencli` 风格的运行条件。

### 需要去掉的旧检查
- `dist/main.js` 是否存在
- `node ... twitter timeline ...` probe
- `opencli binary` 这类文案

### 新 diagnose 最小检查项
建议至少包括：

1. source config 可解析
2. auth material 存在
3. auth material 格式可用
4. native timeline probe 可跑
5. probe 响应能解析成标准字段
6. output data dir 可写

### diagnose 输出语义
应该围绕 native source 展示，例如：

- auth state: OK / FAIL
- timeline probe: OK / FAIL
- response parse: OK / FAIL
- output dir: OK / FAIL

这不只是改词，而是系统边界的正式收口。

---

## 10. 数据流

迁移后的 `x-feed` 数据流应为：

1. `collect_x_feed()` 调 native source 入口
2. source 内部：
   - 读 auth
   - 发 timeline 请求
   - 解析响应
   - 返回标准化 tweets
3. lane 把标准化 tweets 映射成 `SignalRecord`
4. runtime 继续负责写出：
   - signal markdown files
   - `index.md`
   - `run.json`

runtime 继续负责：
- run state
- artifact discipline
- final status semantics
- receipt generation

source 继续负责：
- acquisition
- normalization
- source-specific failure classification

---

## 11. 验证策略

因为产品内不保留双 backend，对照验证必须在迁移过程中显式完成。

## 11.1 字段级验证

在迁移开发阶段，用临时脚本或 fixture 做 side-by-side comparison，验证 native source 输出和旧 backend 在关键字段上是否对齐：

- 条目数量
- `id`
- `author`
- `url`
- `text`
- engagement 字段
- timestamp 的存在性与格式

这类对照可以存在于迁移期工具或验证文档中，但不应变成永久 runtime feature。

## 11.2 Artifact 级验证

运行 native `x-feed` collect，并验证：

- `signals_written` 是否合理
- frontmatter 关键字段是否兼容
- `index.md` 结构是否仍可消费
- `run.json` 是否仍然是诚实的最终收据

## 11.3 Failure-mode 验证

必须显式覆盖：

- 缺失 / 无效 auth
- transport failure
- schema parse failure
- empty feed
- partial signal write failure
- index write failure
- run manifest write failure

---

## 12. 测试要求

native migration 至少要新增或改写这些测试：

### Source tests
- auth loading success / failure
- timeline fetch success
- parser 在代表性 fixture 上成功
- parser 在 malformed fixture 上明确失败

### Lane / runtime tests
- native source 成功路径
- native empty-source 路径
- native source error 路径
- partial signal write failure
- 最终 `run.json` 反映最终 status

### Diagnose tests
- auth failure 报告正确
- parse failure 报告正确
- probe success / failure 语义正确

### Compatibility tests
- 真实 artifact 关键字段仍满足当前 Phase 1 contract

---

## 13. 迁移约束

### 约束 1：不保留 runtime fallback backend
`signal-engine` 产品运行链路中不保留 `opencli_legacy`。

### 约束 2：不能把半清理当完成
只是去掉 `subprocess.run()`，但 config / diagnose / docs 还保留 opencli 形状，不算完成。

### 约束 3：防止平台蔓延
只迁 `x-feed` timeline collection 所需最小逻辑，不顺手吞掉 article / search / following 等无关能力。

### 约束 4：artifact 协议不能被无意破坏
如果需要修改 frontmatter / run-manifest / artifact contract，那必须是单独设计决策，不能作为 source migration 的副作用发生。

---

## 14. 主要风险

## 14.1 Auth handling 是最高脆弱区
如果 auth loading 和 auth diagnosis 没有清楚拆开，迁完之后问题只会更难排。

## 14.2 Schema drift 可能被隐式带进来
如果 parser 逻辑只是机械搬运，而没有把 schema 假设显式化，那么 `signal-engine` 只是继承了旧 fragility，并没有真正变稳。

## 14.3 过度迁移风险
最大的危险不是“迁不下来”，而是把太多 opencli 结构一起带进来，最后变成一个半 fork 的大杂烩。

### 必要缓解
在 implementation 前，必须先明确：
- 具体迁哪些 X 相关逻辑
- 明确不迁哪些类别

## 14.4 验证不足风险
由于不保留双 backend runtime，这次迁移必须靠更强的测试和明确的对照验证来兜住。如果验证弱，系统表面上看起来独立了，字段语义却可能已经漂了。

---

## 15. 推荐结论

推荐按**受控 native-source migration**推进：

- 保留当前 runtime / artifact 架构
- 只迁 `x-feed` 所需的最小 X timeline 获取逻辑
- 迁入后按 `signal-engine` 自己的 source subsystem 边界重组
- 从 runtime、config、diagnostics、tests、supported docs 中移除 `opencli`
- 不保留产品内双 backend，而依靠迁移期显式验证来保证行为对齐

这样既满足了你选定的目标：

> Signal Engine 作为产品系统，真正 end-to-end 拥有 `x-feed`，同时又避免掉进“从零重写一整套 X 逆向工程”的大坑。

---

## 16. 下一步

如果这份设计确认通过，下一份文档应是 implementation plan，拆出具体任务，包括：

- source subsystem 创建
- config migration
- diagnose rewrite
- test migration
- compatibility verification
- 清理和删除旧 `opencli` 依赖痕迹
