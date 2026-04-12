# Polymarket source 迁移设计

- 日期：2026-04-12
- 类型：设计文档
- 结论定位：将 Polymarket 作为 `signals-engine` 的概率/预期类 source 引入，而不是正文内容源

## 1. 设计目标

本设计的目标，不是把 `signals-engine` 扩展成一个研究助手，而是给现有信号系统补上一层此前缺失的观察维度：市场对未来事件的概率表达。

这条 source 的设计目标有四个：

- 让 `signals-engine` 能稳定表达“市场认为什么更可能发生”，补足现有 GitHub、Reddit、X、Product Hunt 主要观察“已经发生了什么”或“人们正在说什么”的缺口。
- 将 Polymarket 严格定义为概率/预期 source，而不是全文、新闻、教程、经验帖或工程变更 source。
- 让该 source 在 AI 主题下形成可复用、可解释、可索引的结构化 signal，尤其服务于 AI model race、coding AI、benchmark、company expectation 这四类高价值主题。
- 保持 `signals-engine` 的产品本质不变：它仍然是一个稳定的 signal system，而不是 topic research engine。

## 2. Source 能力边界

Polymarket 的强项是把一个命题压缩成可观测的市场结构。它能提供的核心能力应被定义为：

- 发现与某个主题相关的 event / market。
- 返回清晰的问题文本，以及当前 outcome 概率。
- 提供 volume、liquidity、价格变化这类可用于判断热度与市场强度的结构化指标。
- 提供 market 链接、更新时间、结束时间等可回看信息。
- 通过相关性过滤、去噪和排序，尽量只保留“主题相关且市场仍然活跃”的结果。

它不应被承诺具备以下能力：

- 不提供正文，不承担 full-text source 角色。
- 不解释新闻背景，不总结事件来龙去脉。
- 不覆盖代码改动、开发者工作流、教程细节、agent 使用经验。
- 不保证所有 query 都有高质量结果，尤其是过窄、过 workflow 化、过工具化的主题。
- 不提供交易、钱包、持仓或任何执行能力。

因此，Polymarket 不是一个“什么都能搜到一点”的主题入口，而是一个“当市场上存在明确命题时，能够返回概率表达”的 source。对它来说，弱 query、空结果和偏公司/偏 benchmark 的结果都是 source 性质的一部分，不应被误判为产品缺陷。

## 3. 产品角色与系统位置

在产品结构里，Polymarket 应处于 expectation layer。

它与现有 source 的关系不是替代，而是互补：

- GitHub 提供工程变化。
- Reddit 提供社区讨论与用户反馈。
- X 提供时间线传播与即时舆论。
- Product Hunt 提供产品发布与榜单表现。
- Polymarket 提供市场对未来结果的概率判断与资金表达的预期。

因此，Polymarket 的系统位置应被理解为“补充一个新维度”，而不是“再加一个内容源”。它最合适的工作方式，是把结构化 signal 送入 lane 与日报体系，和其他 source 并列出现，让用户同时看到：

- 事情发生了什么；
- 人们怎么讨论它；
- 市场认为接下来更可能发生什么。

这也意味着它不能主导产品叙事。`signals-engine` 不应围绕 Polymarket 长出大段解释、推理链或主题研究流程；它应继续以稳定、可解释、可复放的 signal 为中心。

## 4. 推荐 lane 形态

Polymarket 最适合进入“主题收敛、命题明确、预期导向”的 lane，而不是进入“泛 topic 搜索”或“workflow 细节追踪”型 lane。

推荐的 lane 形态是以下四类：

- AI model race：观察谁被市场视为更可能在模型能力上领先。
- Coding AI：观察 coding AI 模型、coding arena、编码能力竞争等命题。
- Benchmark / capability thresholds：观察某个 benchmark 是否会在某时间窗口前被突破，或某能力门槛是否会被达到。
- AI company expectation：观察 OpenAI、Anthropic、Google、Alibaba、xAI、DeepSeek 等公司的预期变化。

这些 lane 的共同特征是：

- 主题边界清楚。
- 命题可被概率化表达。
- 结果更容易形成稳定对比。
- 更符合 Polymarket 的现有市场供给结构。

不推荐的 lane 形态包括：

- coding workflow 细节追踪。
- Claude Code / Codex / OpenClaw 教程或使用经验聚合。
- 泛化为“所有 coding-agent topic 都有高质量市场信号”的总入口。

换言之，Polymarket 最适合作为“预期层 lane”的 source，而不是“工作流知识 lane”的 source。

## 5. Signal 语义设计

Polymarket signal 的基本语义，应是“某一主题下，一个仍然活跃的市场命题，在当前时刻的概率表达”。

单条 signal 应至少包含以下语义层：

- 命题层：这是什么问题，用户正在看哪个 event 或 market。
- 概率层：当前领先 outcome 是什么，其概率是多少；若是多 outcome 场景，应展示最值得看的前几个 outcome。
- 强度层：volume、liquidity、近期价格变化共同构成这条 signal 的市场强度。
- 时间层：这条 signal 是何时抓取的，市场何时结束，用户能据此判断时效性。
- 归属层：这条 signal 属于哪个 lane / query 语境，而不是脱离上下文的孤立 market。

其中最关键的语义约束有三点：

- 第一，概率不是事实。它表达的是市场预期，而不是世界状态本身。
- 第二，相关性应先于热度。高 volume、高 liquidity 只能强化“已经相关”的结果，不能挽救语义上不相干的市场。
- 第三，signal 应尽量呈现“用户真正想比较的对象”，而不是只抛出一个抽象的 Yes / No 外壳。对于同一事件下包含多个可比较对象的场景，展示层应优先暴露用户可读的对象与其概率，而不是只暴露原始市场结构。

这一定义保证了 Polymarket signal 既有足够的信息密度，又不会滑向研究型解释。

## 6. 展示与索引原则

展示上，Polymarket signal 必须做到“一眼可读”。用户不应看到一串 market id，也不应看到只有标题、没有概率与权重的空壳结果。

推荐的展示顺序是：

- 先展示问题文本或事件标题，让用户知道这是什么命题。
- 再展示当前 outcome 概率，让用户马上理解市场倾向。
- 再展示 volume、liquidity、价格变化，帮助用户判断这条 signal 值不值得看。
- 最后提供原始 market 链接和时间信息，支持回看与验证。

索引上，应坚持以下原则：

- 以主题相关性为第一索引轴，而不是以市场热度为第一索引轴。
- 以 AI model、coding AI、benchmark、company 这类高价值主题簇做聚合，而不是做无限展开的 topic research。
- 只索引活跃、开放、具有流动性且语义相关的市场；低相关结果宁可丢弃，也不应为了“看起来有内容”而保留噪音。
- 将 Polymarket 视为结构化信号块，而不是长文阅读入口；它的展示应该短、硬、可比较。

这一原则的目的，是确保 `signals-engine` 的索引秩序仍然围绕 signal，而不是围绕“可展开的研究页面”。

## 7. 风险、误用与非目标

这条 source 的主要风险，不在于接不接得上 API，而在于产品是否会错误承诺它的覆盖面。

主要风险包括：

- query 一旦过泛，结果会明显偏向模型排名、公司竞争、估值或 benchmark 命题。
- 用户可能把概率误读成事实，把市场共识误读成客观结论。
- 对真正 workflow 导向的话题，Polymarket 往往覆盖不深，容易显得“看起来很酷，但离日常使用不够近”。
- 如果展示层过度解释、过度延展，很容易把 `signals-engine` 带向 topic research engine。

典型误用包括：

- 把 Polymarket 当成 coding-agent 主信号源。
- 期待它回答 Claude Code、Codex workflow、agent 编排细节这类工程实践问题。
- 用它替代 GitHub、Reddit、X、Product Hunt，而不是与这些 source 互补。

明确的非目标包括：

- 不做交易端。
- 不做 full-text 内容源。
- 不做工作流知识库。
- 不做“所有 AI 子领域一网打尽”的总入口。
- 不把 `signals-engine` 改造成围绕单个 topic 进行持续研究和解释的系统。

## 8. 验收口径

本设计成立，至少应满足以下验收口径：

- 团队与用户都能清楚理解：Polymarket 是概率/预期 source，不是正文 source。
- 在 AI、Claude、Coding AI、OpenAI、Anthropic 等代表性主题下，系统能够稳定给出可读的 market signal，而不是只有标题的空结果。
- 单条 signal 至少能让用户看清楚问题文本、当前概率、volume 或 liquidity、原始链接与时间信息。
- 结果分布能够体现 Polymarket 的真实强项：AI model race、coding AI、benchmark、company expectation，而不是假装覆盖 coding workflow 细节。
- 当 query 相关性不足时，系统能够接受弱结果甚至空结果，而不是输出大量噪音。
- 引入这条 source 后，`signals-engine` 的整体形态仍然是稳定的 signal system：结果可解释、可回看、可并列消费，而不是被带偏成 topic research engine。
- 与 GitHub、Reddit、X、Product Hunt 的互补关系在产品上是可感知的：用户能看出它提供的是“市场认为会发生什么”，而不是已有 source 的重复版本。
