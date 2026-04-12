## 1. 目标与范围

本次实施的目标，是把 Polymarket 作为 signals-engine 中新的概率/预期类 source 接入现有信号体系，补足 GitHub、Reddit、X、Product Hunt 主要覆盖“已发生变化”与“正在被讨论”但缺少“市场认为接下来更可能发生什么”的观察维度。

本次范围只包括以下四类能力：

- 发现与 AI 主题相关的 Polymarket event 和 market。
- 将 market 数据整理为可索引、可解释、可并列消费的结构化 signal。
- 让这类 signal 能进入以 AI model race、coding AI、benchmark、company expectation 为核心的 lane。
- 在展示与排序上明确其为概率表达，而非事实陈述或正文内容。

本次明确不进入以下范围：

- 不做交易、钱包、持仓或任何执行能力。
- 不把 Polymarket 当作 full-text 内容源，不补正文、长文、教程或经验帖。
- 不承诺覆盖 coding workflow 细节、agent 编排细节或工具使用经验。
- 不把 signals-engine 扩展成 topic research engine。

实施过程中必须持续保持两个产品约束：第一，Polymarket 只补“预期层”，不能替代现有 source；第二，当 query 天然偏弱时，允许弱结果或空结果，不以“必须有内容”作为成功标准。

## 2. 复用与迁移来源

本次迁移的产品与数据来源，来自已有 PRD 与设计文档中明确沉淀出的三类经验，而不是重新定义一个新的研究型模块。

- 第一类是只读采集经验。已有来源已经证明 Polymarket public API 可以稳定提供 AI 相关 market、问题文本、outcome 概率、交易量、流动性以及 event 或 market 链接。本次应复用这种“公开数据读取与结构化抽取”的能力边界。
- 第二类是主题选择经验。优先主题应直接继承既有结论，聚焦 AI model race、coding AI、benchmark 或 capability thresholds、AI company expectation 四类，而不是从 workflow 或教程类主题切入。
- 第三类是产品口径经验。迁移时要保留“这是 expectation source，不是正文 source”的定位，同时把旧来源中对 AI 命题的发现能力，迁移成 signals-engine 可消费的 signal 语义、排序逻辑和 lane 归属逻辑。

需要明确迁移但不照搬的部分有三项：

- 不迁移任何研究助手式扩展，不增加解释链、主题推理链或长文总结职责。
- 不把 market 热度直接当作相关性，必须先过主题相关性判断，再使用 volume、liquidity、价格变化做排序强化。
- 不把旧来源中“能搜到一些结果”当作目标，而要把“稳定输出少量高相关、可比较、可回看 signal”作为目标。

## 3. 目标产物

本次实施完成后，应交付以下产物：

- 一个可独立启停的 Polymarket source 能力，定位为只读的 prediction 或 expectation source。
- 一套面向 signals-engine 的 Polymarket signal 结构，至少覆盖问题文本、概率、强度指标、时间信息、原始链接、lane 或 query 归属。
- 一套面向代表性主题的发现与过滤规则，优先服务 AI model race、coding AI、benchmark、company expectation 四类 lane。
- 一套明确的排序与展示规则，使用户先看懂命题，再看懂当前概率与市场强度，而不是先看到 market 标识或抽象外壳。
- 一套弱结果与空结果处理规则，确保过窄、过 workflow 化、过工具化 query 不会被噪音结果填充。
- 一套上线后的验证口径与回退口径，保证引入该 source 后，signals-engine 仍然是稳定信号系统，而不是围绕单一主题不断展开解释的研究系统。

## 4. 分阶段实施步骤

第一阶段：冻结产品口径与主题边界。

- 先把 Polymarket 在系统中的角色固定为“概率/预期类 source”，并将其与 GitHub、Reddit、X、Product Hunt 的互补关系写入实现约束。
- 将首批允许进入的主题收敛为四类：AI model race、coding AI、benchmark 或 capability thresholds、AI company expectation。
- 同时列出明确不承诺覆盖的主题，至少包括 coding workflow 细节、教程经验、agent 编排实践。
- 该阶段完成标准是：后续实现不再讨论“要不要扩成内容源或研究入口”，而只围绕 signal 生产展开。

第二阶段：建立 market 发现与候选集收敛机制。

- 围绕 lane 或 query 语境进行市场发现，不做无限展开的 topic 搜索。
- 候选集只保留与主题语义相关、仍然活跃、开放且具备一定市场强度的 event 或 market。
- 发现过程要能同时保留 query 语境与 market 归属，避免输出脱离上下文的孤立 market。
- 对于泛 query，要允许结果自然偏向模型竞争、公司竞争与 benchmark 命题；但若偏离当前 lane 语义，应在这一阶段被过滤掉。
- 该阶段完成标准是：代表性主题能够得到稳定候选集，弱主题则得到有限候选或空结果。

第三阶段：完成 signal 归一化与语义成型。

- 将候选 market 转成统一 signal 语义，确保每条结果都可回答“这是什么命题、市场当前倾向是什么、市场强度如何、属于哪个主题上下文”。
- 多 outcome 场景下，优先提炼用户真正想比较的对象与其概率，而不是只输出抽象的 Yes 或 No 外壳。
- 概率、volume、liquidity、近期价格变化、抓取时间、结束时间等信息应在此阶段统一口径。
- 强度排序应以相关性优先，热度只用于强化已经相关的结果，不能反向把无关市场推上来。
- 该阶段完成标准是：单条 signal 已具备足够的信息密度，可直接进入 lane 展示，不依赖额外解释段落才能读懂。

第四阶段：完成 lane 集成与展示约束落地。

- 将 Polymarket 作为独立 source 接入适合的 lane，而不是当成所有 AI topic 的通用补充项。
- 展示顺序固定为“先命题，再概率，再强度，再时间与链接”，保证用户一眼可读。
- 展示内容保持短、硬、可比较，不补长解释，不展开研究型叙述。
- 与其他 source 并列消费时，需突出它回答的是“市场认为更可能发生什么”，而不是重复已有 source 的新闻、社区讨论或工程变化。
- 该阶段完成标准是：同一 lane 中，用户能明显感受到 Polymarket 提供的是预期层，而非正文层。

第五阶段：完成验证、灰度与回退准备。

- 先使用代表性主题进行验证，确认高相关主题能稳定产出可读 signal。
- 再使用边界主题进行验证，确认 workflow 类 query 可以合理返回弱结果或空结果，而不是填充噪音。
- 在正式放量前，应保留 source 级关闭能力，确保出现误用、误读或噪音扩散时可快速退出，不影响现有 source 运行。
- 该阶段完成标准是：产品定位、数据契约、展示规则、负向边界和关闭策略都已验证通过。

## 5. 数据与信号契约

Polymarket 的数据与信号契约必须围绕“概率表达”而不是“内容表达”设计。

输入契约：

- 输入单位是 lane 或 query 语境，而不是开放式研究问题。
- 输入主题必须优先映射到 AI model race、coding AI、benchmark、company expectation 这四类高价值簇。
- 过泛 query 可以接受，但需要在后续阶段通过相关性收敛；过窄且明显偏 workflow 的 query，应允许直接进入弱结果或空结果路径。

候选 market 契约：

- 候选结果必须具备可读的问题文本或事件标题。
- 候选结果必须具备可访问的 event 或 market 链接。
- 候选结果必须处于仍可观察的状态，至少要能判断其活跃性、开放性与时效性。
- 候选结果如果缺失基础概率信息或缺乏最基本的市场强度信息，不应进入最终 signal。

单条 signal 最低字段契约：

- 命题信息：问题文本，必要时补充事件标题以帮助用户理解上下文。
- 概率信息：当前领先 outcome，以及对应概率；多 outcome 场景至少保留最值得比较的前几个对象。
- 强度信息：volume、liquidity，以及可用时的近期价格变化。
- 时间信息：抓取时间与市场结束时间。
- 来源信息：原始 market 或 event 链接。
- 归属信息：当前 lane、query 或主题簇归属。

解释契约：

- 概率表达的是市场预期，不是事实，不应在任何层面被改写成断言句。
- 相关性高于热度，volume 与 liquidity 只能帮助排序，不能替代主题判断。
- Polymarket signal 是结构化信号块，不承担正文阅读入口职责。
- 当 market 只能提供较弱语义时，允许放弃输出，而不是为了完整度保留噪音。

排序契约：

- 第一排序轴是主题相关性。
- 第二排序轴是市场强度，主要由 volume、liquidity 和价格变化共同构成。
- 第三排序轴是时间有效性，优先保证用户看到仍然值得观察的 market。

## 6. 测试与验证计划

验证计划应直接服务于产品定位，而不是只验证“能否拿到数据”。

第一类验证是主题命中验证。

- 针对 AI model race、coding AI、benchmark、company expectation 四类主题，各准备代表性 query，确认系统能稳定返回可读 signal。
- 验证重点不是结果数量，而是结果是否真正落在该主题上，且能让用户直接读懂命题和概率。

第二类验证是边界与负向验证。

- 使用明显偏 workflow、教程或使用经验的问题做验证，确认系统不会假装有覆盖面。
- 当结果天然稀缺时，应验证系统可以输出弱结果或空结果，而不是用低相关 market 填充。

第三类验证是契约完整性验证。

- 每条 signal 都必须能看到问题文本、概率、至少一项市场强度指标、时间信息与原始链接。
- 多 outcome 场景必须验证展示对象是否可比较，避免只看到抽象外壳。
- 概率表述必须保持为市场预期，不得在展示中被误导为事实。

第四类验证是排序与去噪验证。

- 对混合候选集验证相关性是否优先于热度。
- 验证高 volume 但语义无关的 market 不会压过低一些但更相关的 market。
- 验证低相关、低流动性、已不活跃或时效性不足的结果能够被稳定剔除。

第五类验证是系统定位验证。

- 在与 GitHub、Reddit、X、Product Hunt 并列的消费场景中，确认 Polymarket 呈现的是“未来概率判断”这一新增维度。
- 验证展示层没有长篇解释、研究型延展或内容源式展开，确保 signals-engine 仍然保持稳定 signal system 的形态。

## 7. 风险与回退策略

风险一：query 过泛，结果向模型排行、公司竞争或 benchmark 命题倾斜，偏离当前 lane 的实际意图。

- 应对策略是先收窄主题簇，再用相关性过滤，而不是直接依赖热度排序。
- 回退策略是缩小首批支持的 lane 与 query 范围，仅保留高相关主题簇。

风险二：用户把概率误读为事实，把市场共识误读为客观结论。

- 应对策略是所有展示都保留“命题 + 概率 + 时间 + 来源链接”的结构，避免断言式文案。
- 回退策略是降低展示层的概括力度，只保留最原始、最明确的概率表达字段。

风险三：workflow 类主题覆盖不足，团队或用户误以为 source 质量不稳定。

- 应对策略是从一开始就把 Polymarket 定义为 expectation source，只承诺 AI model race、coding AI、benchmark、company expectation 等高匹配场景。
- 回退策略是从不适配的 lane 中撤出该 source，避免继续制造错误预期。

风险四：为追求“看起来有内容”，系统保留了低相关或低质量市场，导致 signal 噪音上升。

- 应对策略是接受弱结果和空结果，明确“无高质量 market”本身就是有效输出。
- 回退策略是进一步提高相关性与活跃度阈值，减少输出数量，优先保住信号质量。

风险五：展示层不断加解释，最终把 signals-engine 带向 topic research engine。

- 应对策略是坚持结构化 signal 块输出，不追加研究型扩展能力。
- 回退策略是移除额外解释层，只保留命题、概率、强度、时间、链接和 lane 归属。

风险六：引入新 source 后影响现有系统稳定性或产品叙事重心。

- 应对策略是让 Polymarket 以独立 source 身份接入，并保持可独立关闭。
- 回退策略是按 source 维度整体下线 Polymarket，不影响 GitHub、Reddit、X、Product Hunt 的既有能力。

## 8. 完成定义

以下条件同时满足时，本次迁移可判定完成：

- 团队能够一致说明 Polymarket 在 signals-engine 中是概率或预期 source，而不是正文内容源。
- 系统在 AI model race、coding AI、benchmark、company expectation 的代表性主题下，能够稳定产出可读、可比较、可回看的 signal。
- 每条合格 signal 至少具备命题信息、概率信息、市场强度信息、时间信息、来源链接与 lane 或 query 归属。
- 多 outcome 场景能够展示用户真正关心的比较对象，而不是只暴露抽象 market 外壳。
- 对 workflow 细节、教程经验、agent 编排等弱匹配主题，系统能够接受弱结果或空结果，不制造覆盖幻觉。
- 排序结果能够体现“相关性优先、热度其次、时效性兜底”的原则。
- 与 GitHub、Reddit、X、Product Hunt 并列消费时，用户能明确感知 Polymarket 提供的是“市场认为接下来更可能发生什么”的新增维度。
- 引入该 source 后，signals-engine 仍保持稳定 signal system 的产品形态，没有滑向 topic research engine。
- Polymarket source 具备独立关闭能力，必要时可以整条回退，而不破坏现有 source 的运行与产品叙事。
