## 1. 总体结论

这份设计的大方向是对的：把 `github-watch` 从“单 lane、多 repo”拆成 repo-specific lanes，和当前实现里的真实耦合点基本一致。  
但要安全落地，还需要先补两条约束：state 必须按 lane 隔离，`repo` 单值配置必须做 fail-fast 校验。

## 2. 与当前 signals-engine 实现对齐的地方

- `src/signals_engine/lanes/registry.py` 和 `src/signals_engine/commands/lanes.py` 说明 lane 是显式注册、显式列出的，设计把三条新 lane 放进 registry 是对的。
- `src/signals_engine/lanes/github_watch.py` 里 `SignalRecord`、`RunResult`、配置读取、`register_lane()` 都把 `github-watch` 写死了，设计提出 generic collector + thin wrappers，正好命中当前耦合点。
- `src/signals_engine/signals/render.py` 和 `src/signals_engine/signals/frontmatter.py` 现在都把 `github-watch` 当成唯一 GitHub lane，设计要求把 GitHub 渲染从 lane 名解耦，这也是必须改的。
- `src/signals_engine/runtime/collect.py` 的 `lane -> module` 映射已经支持 `claude-code-watch -> claude_code_watch.py` 这种命名，wrapper 方案能直接接入。

## 3. 设计中还需要补强的地方

- 要明确 state 如何按 lane 隔离。当前 `_state_path()` 只用 `owner/repo/signal_type` 组 key；设计又建议保留旧 `github-watch` 做 A/B，对同一 repo 很容易串状态。
- 要明确单 repo 配置的失败语义。当前 repo 格式非法只是 warning 后跳过；拆成单 repo lane 后，`repo` 缺失或非法应直接 `FAILED`，不能落成 `EMPTY`。
- changelog state 最好也带上实际文件路径。当前 state key 只有 `changelog`，未来如果 lane 间或版本间切换 `CHANGELOG.md/CHANGES.md`，基线会混掉。

## 4. 实现顺序建议

- 先做 generic GitHub collector + 三个 wrapper，并同时改 `registry.py`、`commands/lanes.py`。
- 然后立刻改 `render.py`、`frontmatter.py`，让 GitHub 渲染按 `source + signal_type` 分派，而不是按 lane 名。
- 在 state lane-aware 之前，不建议同时跑旧 `github-watch` 和新 lane 做对照。
- `RunResult` 这一轮先别动，`repos_checked = 1` 可以接受。

## 5. 风险清单

- 最高风险：旧 lane 和新 lane 共存时状态串线，导致 changelog/readme 漏报或误报。
- 高风险：单 repo 配置错误被记成 `EMPTY`，运营上会被误判为“今天没变化”。
- 中风险：如果 GitHub 渲染仍写死 `record.lane == "github-watch"`，新 lane 产物会静默退回 generic fallback。
- 中风险：未来 `codex-watch` 引入 `merged_pr/commit` 后，GitHub 渲染不能只看 `source == "github"`，要继续按 `signal_type` 分流。

## 6. 最终建议

可以按这份设计推进，但先把“state 按 lane 隔离”和“`repo` 单值配置 fail-fast”写进设计正文，再进入实现。主线应保持为：一套 generic GitHub collector，三条薄 wrapper lanes，共享一套按 `source + signal_type` 分派的渲染协议。
