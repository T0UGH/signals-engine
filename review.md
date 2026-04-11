# 总结结论

基于当前已验证证据，`signals-engine` 已明显越过“骨架项目”阶段，进入“可切换但尚未完全切干净”的阶段。其核心判断依据是：一方面，Python 原生 collect CLI 已成型，`src/signals_engine/cli.py` 中已经具备 `collect`、`diagnose`、`status`、`lanes`、`config` 五类主命令；另一方面，五条主 lane 已具备对应的原生实现和注册结果，`lanes list` 输出已覆盖 `x-feed`、`x-following`、`github-watch`、`github-trending-weekly`、`product-hunt-watch`。

这说明项目已经具备承接 `daily-lane` collect 职责的主体能力，也与 `docs/design/2026-04-06-signal-engine-v1-spec.md` 中“接管 `daily-lane` collect responsibilities，并以 Python collect CLI 重建 collect layer”的目标基本对齐。但仓库仍保留明显的历史兼容层：默认配置路径、默认数据目录、环境变量名仍以 `daily-lane` 为中心，README 叙述也没有跟上实现状态。因此，当前更适合“分阶段切换”，不适合“宣告已经彻底完成切换并清理完旧系统边界”。

# 已完成部分

- 目标层面：`docs/design/2026-04-06-signal-engine-v1-spec.md` 已明确产品目标是接管 `daily-lane` 的 collect 职责；从已存在实现看，这一目标已经不是停留在设计文档，而是进入可运行状态。
- CLI 入口层面：`src/signals_engine/cli.py` 已形成清晰命令树，包含 `collect`、`diagnose`、`status`、`lanes`、`config`，说明运行入口、诊断入口和配置入口都已成体系，而非单 lane 脚本拼接。
- lane 实现层面：以下原生 lane 文件均已存在，覆盖当前主干能力面：
  - `src/signals_engine/lanes/x_feed.py`
  - `src/signals_engine/lanes/x_following.py`
  - `src/signals_engine/lanes/github_watch.py`
  - `src/signals_engine/lanes/github_trending_weekly.py`
  - `src/signals_engine/lanes/product_hunt_watch.py`
- lane 注册层面：`lanes list` 的输出与 `daily-lane/lanes/` 下的 shell lanes 一一对应，后者已有：
  - `x-feed.sh`
  - `x-following.sh`
  - `github-watch.sh`
  - `github-trending-weekly.sh`
  - `product-hunt-watch.sh`
  这表明主力 lane 的“旧壳”与“新核”之间已经具备可比对、可替换关系。
- runtime 层面：以下关键运行时文件均已存在，说明 collect/diagnose/status/run manifest 已经不是占位：
  - `src/signals_engine/runtime/collect.py`
  - `src/signals_engine/runtime/diagnose.py`
  - `src/signals_engine/runtime/status.py`
  - `src/signals_engine/runtime/run_manifest.py`
- 数据模型与产物契约层面：`src/signals_engine/core/models.py` 已存在；`src/signals_engine/core/context.py` 与 `src/signals_engine/core/paths.py` 已表明产物目录契约围绕 `signals/<lane>/<date>/signals`、`index.md`、`run.json` 以及 lane `state` 展开，说明 collect 输出结构已经统一。
- manifest 层面：`src/signals_engine/runtime/run_manifest.py` 已确认 `run.json` 通过专用 mapper 渲染，而不是直接 `asdict()` 落盘。这是一个工程上积极的信号，意味着对外产物结构已开始从内部数据结构解耦，后续做 schema 稳定化和兼容性控制会更容易。
- lane 细节层面：
  - `src/signals_engine/lanes/github_watch.py` 已原生实现 `release + changelog + readme` 的收集，并区分不同类型写 signal 和维护各自 state。
  - `src/signals_engine/lanes/x_feed.py` 已使用原生 X source，并明确写出 `signals`、`index`、`run.json` 以及显式状态语义。
- 演进速度层面：最近提交历史显示项目在连续补齐与修正，而不是停滞：
  - `a1dc195` 引入 `x-following`
  - `3d64116` 引入 `github-watch`
  - `fde120e` 引入 `github-trending-weekly`
  - `82081da` 引入 `product-hunt-watch`
  - `f436b7e` 修复 `product-hunt-watch` 等问题并补到 22 个测试
  - `4499b6b` 继续修正时间戳、remaining logic、`httpx` context manager、pipe escape、debug log
  这说明项目已从“做一个 lane 试试”进入“多 lane 原生化并持续修边”的阶段。

# 关键验证结果

- Git 工作树状态干净，分支为 `main...origin/main`。这意味着本次判断不是建立在未提交临时修改之上，证据基线相对稳定。
- 测试方面，验证结果分成两层：
  - 直接执行 `pytest -q` 在 collection 阶段失败，原因是模块导入路径缺失。
  - 执行 `PYTHONPATH=src pytest -q` 后通过，结果为 `111 passed in 0.94s`。
- 这组结果说明两个事实：
  - 代码本身已经具备较完整的测试覆盖和可通过性。
  - 但当前测试/打包/开发环境约定还没有完全收敛，至少“直接跑 pytest”这条最朴素路径仍不成立。
- CLI 能力验证方面，`src/signals_engine/cli.py` 中的命令树已存在，且 `lanes list` 输出已包含五条主 lane。这不是单文件存在性的证据，而是“命令入口 + lane 注册结果”同时成立的证据。
- README 与实现状态不一致：README 仍写着 `first migration target: x-feed`，但当前仓库内已存在五条主 lane 的原生实现。这个偏差虽然不直接影响运行，但会直接影响团队对迁移进度的判断，属于工程管理层面的验证结果。

# 风险与缺口

- 历史兼容边界尚未清理干净。`src/signals_engine/commands/collect.py` 仍默认读取 `DAILY_LANE_CONFIG`、`DAILY_LANE_DATA_DIR`，默认配置路径仍指向 `~/.daily-lane/config/lanes.yaml`，默认数据目录仍指向 `~/.daily-lane-data`。类似默认值也出现在 `src/signals_engine/commands/config.py`、`src/signals_engine/commands/diagnose.py`、`src/signals_engine/runtime/status.py`、`src/signals_engine/runtime/diagnose.py`。
- 上述问题的工程含义不是“兼容旧系统不好”，而是“系统身份和切换边界不清晰”。只要默认值仍然指向旧命名空间，团队在运维、排障、文档编写和用户心智上就会持续混淆 `signals-engine` 与 `daily-lane` 的边界。
- 测试入口不够稳。`pytest -q` 失败而 `PYTHONPATH=src pytest -q` 成功，说明测试成功依赖额外环境约束。这会带来两个直接风险：
  - 新开发者或 CI 配置者容易得到假阴性失败。
  - 发布前验证和本地验证之间容易出现“命令不一致”。
- README 过时。README 仍将 `x-feed` 表述为“first migration target”，但实现已经覆盖五条主 lane。这会造成错误预期：外部读者会低估迁移完成度，内部成员会误判优先级和剩余工作量。
- 当前状态虽然已经可切换，但还不能视为“完成收口”。从证据看，项目已经拥有原生 collect 主体、lane 主体和产物契约，但“默认配置命名、文档口径、最小运行路径”仍残留旧系统痕迹，因此还不适合把旧兼容层当作长期正式边界。

# 是否适合现在切换

适合现在开始切换，但不适合一次性彻底切换。

更具体地说：

- 如果“切换”的含义是开始让 `signals-engine` 承担主路径 collect 工作，并逐 lane 替换 `daily-lane/lanes/*.sh` 的实际执行逻辑，那么答案是适合。证据是五条主 lane 已全部具备原生实现，CLI 和 runtime 也已成型，测试在正确环境下已达到 `111 passed in 0.94s`。
- 如果“切换”的含义是立即宣布 `daily-lane` 已经完全退出、旧命名和旧路径可以被忽略，那么答案是否定的。因为默认环境变量、默认配置路径、默认数据目录、README 叙述都还保留明显旧系统中心视角。
- 因此，当前最准确的表述应是：`signals-engine` 已经进入“可切换、可灰度、可逐步替代”的阶段，但尚未进入“旧系统痕迹已清理完毕、可以正式收口”的阶段。

# 建议的切换顺序

1. 先切运行路径，不先切兼容层。优先让实际 collect 执行尽量经过 `src/signals_engine/cli.py` 暴露的 `collect` / `lanes` / `status` / `diagnose` 能力，确认五条主 lane 都以 `signals-engine` 为主入口运行。
2. 再切文档口径。首先更新 README，将“`first migration target: x-feed`”改成反映当前真实状态的描述，明确五条主 lane 已具备原生实现，避免团队继续按过时里程碑讨论项目。
3. 然后收敛默认配置与默认数据目录。重点清理以下位置中的 `daily-lane` 默认值与环境变量命名：
   - `src/signals_engine/commands/collect.py`
   - `src/signals_engine/commands/config.py`
   - `src/signals_engine/commands/diagnose.py`
   - `src/signals_engine/runtime/status.py`
   - `src/signals_engine/runtime/diagnose.py`
   建议策略是先保留兼容读取，再引入 `signals-engine` 自身默认值，并把旧变量降级为显式兼容层，而不是继续作为默认主路径。
4. 接着收敛验证命令。至少要把“开发者和 CI 的标准测试命令”统一下来，避免继续出现 `pytest -q` 失败而 `PYTHONPATH=src pytest -q` 成功的双轨状态。
5. 最后再考虑正式切断 `daily-lane` 壳层的默认依赖。等默认路径、默认环境变量、README、测试入口都完成收口后，再把 `daily-lane/lanes/*.sh` 从“兼容入口”降级为“过渡层”甚至移除，届时再对外宣布完成迁移会更稳妥。
