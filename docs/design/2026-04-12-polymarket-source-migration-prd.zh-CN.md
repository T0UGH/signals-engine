# Polymarket source 迁移到 signals-engine 的 PRD

- 日期：2026-04-12
- 状态：draft
- 目标仓库：`signals-engine`
- 来源参考：`~/workspace/last30days-skill/scripts/lib/polymarket.py`
- 文档类型：PRD（产品需求文档，不含实现方案）

---

## 1. 背景

`signals-engine` 当前已经具备多类 source / lane：

- X / Twitter 时间线类
- GitHub repo 变化类
- Product Hunt 榜单类
- Reddit public 讨论类

但它还缺少一类重要信号：

> **市场预期 / 概率判断 / 资金表达的共识变化**

`last30days-skill` 里的 `polymarket.py` 已经证明，Polymarket public API 可以稳定返回：

- AI 相关市场
- 具体问题（question）
- outcome 概率
- 交易量 / 流动性
- event / market URL

这类信号和 GitHub / Reddit / X 完全不同，不回答“代码改了什么”或“用户怎么吐槽”，而回答：

- 市场认为谁更可能领先
- 市场对 AI 模型 / 公司 / benchmark 的预期如何变化
- 哪些 AI 命题已经形成可量化概率

因此，Polymarket 适合进入 `signals-engine`，作为一条新的 **prediction / expectation source**。

---

## 2. 这份 PRD 要解决什么问题

本 PRD 要定义：

> `signals-engine` 是否应该引入 Polymarket source，以及它在产品上应该提供什么，不应该提供什么。

重点不是“能不能调 API”，而是：

1. 它在 `signals-engine` 里扮演什么角色；
2. 它输出什么样的 signal；
3. 它适合哪些主题；
4. 它不该被误用成什么；
5. 什么情况下这条迁移算成功。

---

## 3. 产品定位

### 3.1 这条 source 的角色

Polymarket 在 `signals-engine` 里的角色应定义为：

> **预测市场信号源 / 预期层信号源**

它主要提供：

- 概率
- 赔率
- 市场分歧
- 交易量所表达的关注度

而不是：

- 新闻正文
- 开发者经验帖
- 代码改动
- 产品 walkthrough

### 3.2 它补的是哪一块空白

相对于现有 source：

- GitHub 反映的是工程变化
- Reddit 反映的是社区讨论与用户反馈
- X 反映的是时间线传播与即时舆论
- Product Hunt 反映的是产品发布与榜单表现

Polymarket 补的是：

- **“市场认为会发生什么”**
- **“某个 AI 命题当前的概率是多少”**

这是一个新的观察维度，而不是旧 source 的替代品。

---

## 4. 目标用户价值

对于贵平当前关注的 AI / coding-agent 生态，这条 source 的价值主要在于：

### 4.1 模型竞争态势
例如：
- 哪家公司会拥有最强 AI 模型
- 哪家公司会拥有最强 coding AI 模型
- 哪个模型更可能在某 benchmark 上领先

### 4.2 公司与平台预期
例如：
- OpenAI / Anthropic / Google / Alibaba 等相关命题
- AI safety / regulation / benchmark 进展的市场预期

### 4.3 可量化的“热度不是噪音”
与普通内容源不同，Polymarket 的信号不是“谁发帖最多”，而是：

- 有没有真实市场
- 有没有真实价格
- 有没有真实交易量

这使它很适合被纳入日报/监控系统，作为一条更偏“概率层”的信号面。

---

## 5. 产品范围

## 5.1 本次要做的范围

本次产品范围应限制为：

### A. 支持 AI 相关 Polymarket 市场发现
用户可以围绕 AI 主题看到相关 market/event，例如：

- AI model ranking
- Coding AI model ranking
- Benchmark thresholds
- OpenAI / Anthropic / Google / Chinese AI company related markets

### B. 输出结构化 signals
每条 signal 至少应包含：

- 标题 / 问题
- source URL
- 市场当前 outcome 概率
- volume / liquidity（如有）
- 抓取时间
- 与 lane/query 的关系

### C. 让 Polymarket 成为一条独立 lane 的候选 source
这条 source 应该能被未来某条 lane 消费，例如：

- `polymarket-watch`
- `model-race-watch`

但本 PRD 不定义具体实现命名和代码结构。

---

## 5.2 本次明确不做的范围

### A. 不做交易功能
不做：
- 下单
- 钱包连接
- 持仓
- 买卖行为

这是只读 source，不是交易客户端。

### B. 不做完整研究引擎
不把它做成：
- topic research planner
- market explanation agent
- 基于 LLM 的大规模推理器

Polymarket 在 `signals-engine` 里应保持 collector/source 角色。

### C. 不要求提供新闻正文
Polymarket 本身不是正文内容源。
它不需要像 Reddit / YouTube transcript / GitHub release 那样提供大量原文。

### D. 不要求覆盖所有 AI 子领域
第一阶段不追求覆盖：
- 所有 agent workflow
- 所有 coding tool
- 所有 AI 公司新闻

只要能稳定覆盖一批高相关 AI 预测市场即可。

---

## 6. 产品约束

### 6.1 必须接受的事实
Polymarket 不是“内容型 source”，它是“预测型 source”。

因此它天然存在以下约束：

- 有些 query 会很强（如 `AI` / `Claude` / `Coding AI`）
- 有些 query 会很弱（如 `Codex`）
- 有些结果偏公司/估值，不一定偏工程工作流

这不是 bug，而是 source 性质决定的。

### 6.2 不能把它误判成 coding-agent 主信号源
对贵平当前核心主题而言：

- Polymarket 适合补“预期层”
- 不适合单独承担“coding-agent 生态变化主观测面”

也就是说，它不能替代：
- GitHub
- Reddit
- YouTube

### 6.3 必须控制 query / lane 的产品口径
如果 query 太泛（例如纯 `AI`），结果会偏：

- 模型排行
- 公司估值
- benchmark 命题

如果 query 更贴近 coding 场景（例如 `Coding AI`），结果才更接近贵平想要的方向。

所以未来产品必须明确：

> Polymarket 更适合“AI model race / benchmark / company expectation”，不适合泛化承诺为“所有 coding-agent topic 都有高质量市场信号”。

---

## 7. 建议的产品主题边界

第一阶段建议优先聚焦以下主题簇：

### 7.1 AI model race
- top AI model
- best Chinese AI company
- #1 AI model by date

### 7.2 Coding AI
- best coding AI model
- coding arena score
- coding model ranking

### 7.3 Benchmark / capability thresholds
- arena score thresholds
- frontier benchmark thresholds
- capability milestone questions

### 7.4 AI company expectation
- OpenAI
- Anthropic
- Google
- Alibaba
- xAI
- DeepSeek

不建议第一阶段主打：
- Codex workflow
- Claude Code tutorial signals
- agent 使用经验

因为这些不是 Polymarket 的强项。

---

## 8. 输出内容要求

如果未来这条 source 被 lane 消费，单条 signal 至少应该让用户一眼看懂：

### 8.1 这是什么市场
例如：
- 哪家公司会拥有最强 coding AI 模型
- 某个 benchmark 是否会在某日期前被突破

### 8.2 当前概率是什么
例如：
- Yes / No
- 或多 outcome 中领先项及其概率

### 8.3 热度/权重如何
例如：
- volume
- liquidity

### 8.4 为什么它值得看
即便不做 LLM 推理，也至少应让输出具备：
- 清楚的问题文本
- 清楚的赔率结构
- 清楚的市场链接

用户不应该只看到一串 market id。

---

## 9. 成功标准

本次迁移在产品上应满足以下成功标准：

### 9.1 Source 角色清楚
团队和用户都能明确理解：

- 这条 source 是 **prediction/expectation layer**
- 不是正文新闻源
- 不是工程变更源

### 9.2 AI 相关 query 能稳定产出有价值市场
至少应能对下面类型 query 产出明显有意义的结果：

- `AI`
- `Claude`
- `Coding AI`
- `OpenAI`
- `Anthropic`

并且结果中能看到：
- 真实 market question
- 真实 outcome 概率
- 有意义的市场链接

### 9.3 输出不应沦为“只有标题的空壳”
虽然它不是正文源，但它必须至少提供：
- 问题文本
- 概率
- volume/liquidity

否则它对 `signals-engine` 的价值就不成立。

### 9.4 不误伤主线产品定位
迁入后，`signals-engine` 仍应保持：

> 稳定、可解释、可复放的信号系统

而不是因为 Polymarket 的存在，被带偏成泛研究引擎。

---

## 10. 风险

### 10.1 结果偏“公司/估值”，不够“workflow”
这是当前最现实的风险。

对于贵平真正关心的：
- coding agents
- Claude Code
- Codex workflow
- OpenClaw workflow

Polymarket 的覆盖可能不够深。

### 10.2 query 稍微不准，结果就会偏泛 AI
例如：
- `AI` 可能回很多模型排名和公司竞争
- `OpenAI` 可能回 IPO / valuation 相关

所以产品上必须允许清晰限定主题，而不是默认它天然懂用户想看什么。

### 10.3 它很容易显得“很酷，但不够落地”
如果只是展示概率，而不能稳定进入日报体系，用户会觉得它只是好玩。

因此它必须以 **signal source** 身份被消费，而不是作为孤立演示存在。

---

## 11. 本 PRD 的结论

结论非常明确：

> **Polymarket 值得从 `last30days-skill` 迁入 `signals-engine`。**

但迁入时必须严格定义它的角色：

- 它是 **预测市场 source**
- 它补的是 **预期层 / 概率层**
- 它适合 AI model race / coding AI / benchmark / company expectation
- 它不适合被当成 coding workflow 主信号源
- 它不是正文内容源

如果按这个边界推进，它会成为 `signals-engine` 里一条有独特价值的新 source；
如果边界不清，它很容易被误用，并在产品上显得“方向很炫但对日报不够实用”。

---

## 12. 下一步（非实现）

在进入编码前，下一步只需要做产品决策，不需要做实现细节讨论：

1. 是否确认把 Polymarket 纳入第一波 source migration；
2. 是否确认它的主题边界优先放在：
   - AI model race
   - Coding AI
   - benchmark thresholds
   - AI company expectation
3. 是否确认它在日报体系中的定位是：
   - 补充预期层
   - 而不是替代正文型主 source

这三点定下来之后，后续实现应由专业 coding agent 执行。
