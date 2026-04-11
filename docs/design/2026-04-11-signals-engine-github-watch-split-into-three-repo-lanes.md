# 2026-04-11｜signals-engine：把 github-watch 拆成三条 repo-specific lanes

## 1. 这次改的仓库和目标

这次真正该改的是：

- `~/workspace/signals-engine`

不是 `daily-lane` 的 shell runtime。

在 `signals-engine` 里，当前 GitHub 长期跟进能力已经原生实现为：

- `src/signals_engine/lanes/github_watch.py`

它现在是一个**单 lane、多 repo** 的 Python collector：

- lane id: `github-watch`
- config shape: `lanes.github-watch.repos[]`
- signals: `release / changelog / readme`

而我们现在要讨论的，不是 shell 层怎么拆，而是：

> **在 `signals-engine` 现有 Python 架构里，怎么把 `github-watch` 从一条 multi-repo lane，拆成三条 repo-specific lanes。**

目标三条 lane：

- `claude-code-watch`
- `openclaw-watch`
- `codex-watch`

---

## 2. 先说结论

基于当前 `signals-engine` 代码结构，我的结论是：

### 2.1 应该拆，而且现在拆比继续堆 repo if/else 更顺
当前 `github_watch.py` 已经把三件事绑死在一起：

1. lane id 是 `github-watch`
2. 配置入口是 `lanes["github-watch"]`
3. 运行对象是 `repos[]`

这意味着只要继续保留单 lane，多仓策略差异就只能继续塞进同一个 collector 里。

而 Claude Code / OpenClaw / Codex 的真实观察面已经明显不一样：

- Claude Code：`release-first`
- OpenClaw：`release/changelog-first`，后续要留 PR-assisted 口
- Codex：最终应转向 `merged-pr / commit`，继续把它和另外两仓绑在一条 lane 里会越来越别扭

### 2.2 但在 `signals-engine` 里，不该简单复制三份 lane 文件
在这个仓里，最合理的做法不是直接复制：

- `github_watch.py`
- `claude_code_watch.py`
- `openclaw_watch.py`
- `codex_watch.py`

然后各改一点。

因为当前 `github_watch.py` 里已经有大量**可复用的 repo collector 逻辑**：

- `_collect_releases_for_repo`
- `_collect_changelog_for_repo`
- `_collect_readme_for_repo`
- `_build_release_signal`
- `_build_changelog_signal`
- `_build_readme_signal`

真正需要拆开的，是：

- lane 配置入口
- lane 注册入口
- lane -> signal 渲染映射
- run summary 的语义

所以更合理的方向是：

> **保留一套可复用的 GitHub repo watch collector，把 lane 级差异外提到 config + registry + small runner layer。**

---

## 3. 当前代码里哪些地方是“真的耦合点”

这次不是抽象谈“应该重构”，而是具体到当前代码，真正会卡拆分的地方有下面几层。

## 3.1 lane 注册层现在只有一个 `github-watch`
文件：

- `src/signals_engine/lanes/registry.py`

当前 registry 明确只注册：

- `x-feed`
- `x-following`
- `github-watch`
- `github-trending-weekly`
- `product-hunt-watch`

所以拆分后最直接的变化一定包括：

- registry 要新增三条 lane id
- `lanes list` 命令输出会变化
- `collect --lane ...` 的合法值会变化

## 3.2 `github_watch.py` 现在把 lane id 写死了
文件：

- `src/signals_engine/lanes/github_watch.py`

写死点包括：

1. `SignalRecord(lane="github-watch", ...)`
2. `RunResult(lane="github-watch", ...)`
3. 配置读取：`ctx.config.get("lanes", {}).get("github-watch", {})`
4. 文件尾部注册：`register_lane("github-watch", collect_github_watch)`
5. debug log tag 也是 `[github-watch]`

也就是说，它现在不是“GitHub repo watch generic runner”，而是：

> **一个功能可复用，但 lane 身份完全写死的具体实现。**

## 3.3 render/frontmatter 层也把 `github-watch` 当成唯一 GitHub lane
文件：

- `src/signals_engine/signals/render.py`
- `src/signals_engine/signals/frontmatter.py`

现在逻辑是：

- `record.lane == "github-watch"` -> 用 GitHub body renderer
- `record.lane == "github-watch"` -> release frontmatter 补 `version / published_at / prerelease`

这说明一个关键点：

> 当前代码里，GitHub signal 的渲染分派是**按 lane 名**做的，不是按 signal family / source 做的。

所以一旦 lane 拆成：

- `claude-code-watch`
- `openclaw-watch`
- `codex-watch`

这两层一定要一起改，否则 signal markdown 会退回 generic fallback。

## 3.4 `RunResult` 目前仍带着 multi-repo 语义
文件：

- `src/signals_engine/core/models.py`
- `src/signals_engine/runtime/run_manifest.py`
- `src/signals_engine/signals/render.py`

`RunResult` 当前有：

- `repos_checked`
- `signals_written`
- `signal_types_count`

这本身不是问题，但它默认在语义上更贴近：

> 一次 lane run 扫了一组 repos

拆成 repo-specific lane 后：

- `repos_checked` 不会错
- 但基本恒等于 1
- 语义会变弱

这里的关键不是“必须立刻删字段”，而是要明确：

- **阶段 1 可以继续保留**，保持协议稳定
- 但不要再把后续设计建立在“一个 lane 本来就该扫多个 repo”的假设上

---

## 4. 在 signals-engine 里最合理的拆法

## 4.1 不建议的拆法：复制三个 lane 文件
不建议直接复制出：

- `claude_code_watch.py`
- `openclaw_watch.py`
- `codex_watch.py`

原因：

1. 90% 逻辑是重复的
2. release/changelog/readme 的 bugfix 将来要改三遍
3. Codex 后续虽然会分化得更厉害，但第一阶段还没到必须完全分家 collector 的程度

## 4.2 推荐拆法：generic GitHub repo watch + 三个 lane wrapper
更顺的结构是：

### A. 抽一个可复用 module
例如：

- `src/signals_engine/lanes/github_repo_watch.py`

里面放：

- repo 级 release collector
- repo 级 changelog collector
- repo 级 readme collector
- generic run function

### B. 三个薄 wrapper lane
例如：

- `claude_code_watch.py`
- `openclaw_watch.py`
- `codex_watch.py`

每个 wrapper 只做三件事：

1. 指定 lane id
2. 从 `ctx.config["lanes"][lane_name]` 取本 lane 配置
3. 调 generic GitHub repo watch runner

也就是说：

```text
generic GitHub repo collector
+ thin per-lane wrappers
+ per-lane config
```

这比“三份大文件复制”干净得多，也比“一个文件里靠 if lane == ...”更容易维护。

---

## 5. 配置怎么变才对

## 5.1 当前配置形状的问题
当前 `github_watch.py` 明确假设：

```yaml
lanes:
  github-watch:
    repos:
      - anthropics/claude-code
      - openclaw/openclaw
      - openai/codex
    signals:
      release: ...
      changelog: ...
      readme: ...
```

问题不是 YAML 写法丑，而是它把三种 repo 策略绑定成了同一份 signal config。

## 5.2 repo-specific lane 后应改成单仓配置
建议改成：

```yaml
lanes:
  claude-code-watch:
    repo: anthropics/claude-code
    signals:
      release:
        enabled: true
        lookback_days: 7
        max_per_repo: 3
      changelog:
        enabled: true
        files: [CHANGELOG.md, CHANGES.md, HISTORY.md]
      readme:
        enabled: true

  openclaw-watch:
    repo: openclaw/openclaw
    signals:
      release:
        enabled: true
        lookback_days: 7
        max_per_repo: 3
      changelog:
        enabled: true
        files: [CHANGELOG.md, CHANGES.md, HISTORY.md]
      readme:
        enabled: true
      # future:
      # merged_pr:
      #   enabled: false

  codex-watch:
    repo: openai/codex
    signals:
      release:
        enabled: true
        lookback_days: 7
        max_per_repo: 3
      changelog:
        enabled: false
      readme:
        enabled: false
      # future target:
      # merged_pr:
      #   enabled: true
      # commit:
      #   enabled: true
```

## 5.3 为什么在 signals-engine 里也应该强制 `repo` 而不是 `repos`
因为这里的目标不是“允许未来继续往一个 lane 塞多个 repo”，而是：

> **通过配置形状直接把 lane 语义锁定成 repo-specific。**

这样有三个好处：

1. `collect` 逻辑天然更简单
2. `RunResult` 不再默认围绕 repo loop 组织主语义
3. 后续给 Codex 做独立 collector 时，不会再绕回 multi-repo lane

---

## 6. 三条 lane 的第一阶段策略

这里要按 `signals-engine` 当前代码能力来定，而不是按理想终态乱写。

## 6.1 `claude-code-watch`
第一阶段建议：

- `release`: enabled
- `changelog`: enabled
- `readme`: enabled

定位：

> `release-first + changelog-support`

原因：

- 当前 `signals-engine` 已经有成熟的 release/changelog/readme collector
- Claude Code 正好适配这套 collector
- 这是最稳的一条 repo-specific lane

## 6.2 `openclaw-watch`
第一阶段建议：

- `release`: enabled
- `changelog`: enabled
- `readme`: enabled

定位：

> `release/changelog-first`

并且文档里明确预留：

- future: `merged_pr` / PR-assisted

原因：

- 以当前代码能力，这条也能先稳定落地
- 但它和 Claude Code 不同，后续更可能需要 PR 主题流补边

## 6.3 `codex-watch`
这里要分清“第一阶段可落地”和“终态方向”。

### 第一阶段可落地版本
先用现有 collector 体系落一个过渡版：

- `release`: enabled
- `changelog`: disabled
- `readme`: disabled

也就是：

> 先把 lane topology 拆对

### 终态方向
Codex 的真正目标不应长期停在 release-only：

- primary: `merged_pr`
- secondary: `commit`
- tertiary: `release`

也就是：

> `merged-PR-first + commit-second + release-third`

这个点非常重要：

- **拆 lane ≠ Codex 的 collector 已经做对**
- 拆 lane 只是先把结构改对
- collector 升级要作为下一阶段单独做

---

## 7. signals-engine 里具体要改哪些代码

## 7.1 lane registry
文件：

- `src/signals_engine/lanes/registry.py`

要改成新增三条：

- `claude-code-watch`
- `openclaw-watch`
- `codex-watch`

旧 `github-watch` 的处理有两种可选：

### 方案 A：保留一段时间
- 作为 legacy lane 存在
- 便于迁移期并行比对

### 方案 B：直接切换
- 从 registry 中删除
- 全面转三条新 lane

我更推荐：

> **先保留 `github-watch` 一段时间做 A/B 对照。**

因为 `signals-engine` 现在正处于接管 collect 的阶段，过早删旧 lane 会削弱回归验证能力。

## 7.2 collect implementation
文件：

- `src/signals_engine/lanes/github_watch.py`

建议重构成两层：

### generic layer
- `collect_github_repo_watch(ctx, lane_name)` 或同类入口

### wrapper layer
- `collect_claude_code_watch(ctx)`
- `collect_openclaw_watch(ctx)`
- `collect_codex_watch(ctx)`

关键变化包括：

1. `lane` 不再写死为 `github-watch`
2. 配置读取从：
   - `ctx.config["lanes"]["github-watch"]`
   改成：
   - `ctx.config["lanes"][ctx.lane]`
   或 wrapper 明确传入 lane name
3. repo 从 `repos[]` 改为 `repo`
4. summary 逻辑从 repo loop 主导改成 single repo 主导

## 7.3 render/frontmatter
文件：

- `src/signals_engine/signals/render.py`
- `src/signals_engine/signals/frontmatter.py`

这里不要再用：

- `record.lane == "github-watch"`

作为 GitHub signal 的唯一识别条件。

建议改成按 **signal/source family** 判断，至少做到下面这种级别：

### render
如果：

- `record.source == "github"`
- 且 `record.signal_type in {release, changelog, readme}`

就走 GitHub body renderer。

### frontmatter
如果：

- `record.source == "github"`
- 且 `record.signal_type == "release"`

就补：

- `version`
- `published_at`
- `prerelease`

这样三条新 lane 都能共享同一套 GitHub 渲染协议。

## 7.4 tests
当前测试里虽然还没专门测 `github_watch`，但下面这些会被影响：

- `tests/test_render.py`
- 未来 `lanes list` / collect registry 相关测试

至少需要补：

1. registry 能列出三条新 lane
2. GitHub signals 在三条新 lane 下仍能正确 render frontmatter/body
3. `run.json` / `index.md` 在 repo-specific lane 下仍可工作
4. `codex-watch` 在 changelog/readme 关闭时不会误写这两类 signal

---

## 8. 关于 `RunResult` / `run.json` / `index.md` 要不要现在就重构

我的判断是：

> **先不要大动协议，只做最小兼容改动。**

### 当前可以接受保留的东西
- `repos_checked`
- `signals_written`
- `signal_types_count`

即使 repo-specific lane 下：

- `repos_checked = 1`

也完全能接受。

### 为什么现在不建议一起重构
因为这次真正要解决的是：

- lane topology 错了
- config shape 错了
- render dispatch 写死了

如果这时再顺手重做：

- `RunResult`
- `run.json` schema
- `index.md` 文案

排障面会明显变大。

所以在 `signals-engine` 里，最稳的切法是：

1. 先拆 lane
2. 先让三条 lane 正常 collect / render / 写产物
3. 再考虑是否把 `repos_checked` 从协议里降级

---

## 9. 推荐迁移顺序（signals-engine 版）

### Phase 1：结构拆分
1. 新增三条 lane id 到 registry
2. 将 `github_watch.py` 重构为 generic GitHub repo watch collector + thin wrappers
3. 配置从 `repos[]` 改为 repo-specific `repo`
4. 让三条新 lane 都能单独 collect

### Phase 2：渲染层解耦
5. `render.py` 不再只认 `github-watch`
6. `frontmatter.py` 不再只认 `github-watch`
7. 三条新 lane 写出的 signal markdown 与 run artifacts 保持兼容

### Phase 3：迁移验证
8. 保留旧 `github-watch` 一段时间做对照
9. 跑真实日期样本比较：
   - `github-watch`
   - `claude-code-watch`
   - `openclaw-watch`
   - `codex-watch`
10. 确认内容层能消费三条新 lane 产物后，再考虑下掉旧 lane

### Phase 4：Codex collector 升级
11. 单独设计 `codex-watch` 的 `merged_pr / commit` collectors
12. 再决定是否让 `codex-watch` 彻底脱离当前 release-based collector 路径

---

## 10. 一句话结论

在 `signals-engine` 里，这次正确的改法不是“照着 daily-lane 再拆一轮 shell lane”，而是：

> **把现在的 `github_watch.py` 从“固定 lane + 多 repo collector”重构成“可复用的 GitHub repo watch collector”，然后用三条 repo-specific lane wrapper（`claude-code-watch / openclaw-watch / codex-watch`）接起来；同时把 render/frontmatter 从 `lane == github-watch` 改成真正可共享的 GitHub signal family 分派。**
