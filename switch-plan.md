# 目标

把 collect 主线从 `daily-lane` 分阶段切换到 `signals-engine`，先完成默认入口、默认环境变量、默认配置路径、默认数据目录和文档口径的主线切换，再清理兼容层与测试调用方式。切换过程要求做到“新主线先可用、旧入口可回退、每一步都能单独验收”，避免一次性硬切导致已有 lane 采集链路失稳。

# 切换原则

- 先切默认入口，再切文档和测试，最后清理兼容层，不做一步到位的大爆改。
- 保持现有原生 lanes 可持续运行：`x-feed`、`x-following`、`github-watch`、`github-trending-weekly`、`product-hunt-watch` 在切换期间都必须能继续 collect。
- 每一阶段只收敛一类问题：默认值、文档、测试/调用、兼容清理，避免多个变量同时变化导致问题难定位。
- 新口径统一使用 `signals-engine` / `signal-engine` 命名；旧的 `DAILY_LANE_*` 与 `~/.daily-lane*` 只作为阶段性兼容，不再作为主推荐路径。
- 所有阶段都要求可回滚，且回滚优先通过恢复默认值顺序和保留旧环境变量兼容完成，而不是删代码后再补救。
- 验收以“命令可跑、产物可落、配置可读、文档可照做、测试可稳定复现”为准，不以单纯代码改完为准。

# 分阶段计划

## 阶段 1：切默认值主线，不切兼容层

- 改什么：把 `collect`、`diagnose`、`config check`、`status` 里默认读取的配置路径和数据目录，从 `DAILY_LANE_CONFIG` / `DAILY_LANE_DATA_DIR` 与 `~/.daily-lane*` 调整为 `SIGNALS_ENGINE_CONFIG` / `SIGNALS_ENGINE_DATA_DIR`（或项目最终确认的同义新变量）与 `~/.signal-engine/*`；同时保留旧变量回退顺序，确保未迁完环境的机器还能跑。
- 怎么验证：在不传 `--config`、`--data-dir` 的情况下分别执行 `signals-engine collect --lane x-feed --date 2026-04-06`、`signals-engine diagnose --lane x-feed`、`signals-engine config check`；验证默认读取的是新路径。再分别只设置旧变量、只设置新变量，确认新变量优先、旧变量仍可兜底。
- 暂时不改什么：不删除 `DAILY_LANE_*` 兼容分支，不清理旧目录数据，不改 lane 内部采集逻辑，不扩展新的 lane 能力。

## 阶段 2：切文档和操作口径

- 改什么：更新 `README.md` 和已有设计/验证文档中仍把 `signals-engine` 描述为“试点 x-feed”或仍引用 `daily-lane` 默认配置路径的内容，把主叙事改成“signals-engine 已是 collect 主线，daily-lane 只剩兼容/回滚角色”；把环境准备、配置示例、常用命令、目录约定全部切到新口径。
- 怎么验证：按 README 从零执行一次安装、配置检查、`collect`、`diagnose`；确认文档里给出的路径、环境变量、命令、输出位置与真实行为一致。抽查至少一份 design/verification 文档，确认没有把旧默认值写成当前推荐方案。
- 暂时不改什么：不在这一阶段删除历史设计文档，不重写所有迁移史料，不改实现代码里的兼容回退顺序。

## 阶段 3：切测试调用和运行环境清洁度

- 改什么：补齐围绕“默认环境名已切换”的测试，并把 CLI/运行时测试中的环境注入方式统一收敛，避免测试依赖隐式 `PYTHONPATH`、用户主目录残留文件或旧的 `daily-lane` 默认目录；把测试分成显式传参验证、默认值验证、兼容回退验证三类。
- 怎么验证：在干净环境下运行测试套件，至少覆盖 CLI help、默认 config/data-dir 解析、兼容旧变量回退、原生 lane collect smoke。重点确认不预置 `~/.daily-lane*` 也不会误通过，不预置 `~/.signal-engine/*` 时失败信息也清晰可判定。
- 暂时不改什么：不在这一阶段删除旧变量兼容测试，不做与当前切换无关的大规模测试重构，不引入新的测试框架。

## 阶段 4：收口兼容层并完成主线切换

- 改什么：在前 3 阶段稳定后，评估是否把 `DAILY_LANE_*` 降级为显式兼容说明或彻底移除；同步收口代码注释、帮助文案、报错文案、运行日志中的旧命名，把“signals-engine 是 collect 主线”固化为唯一默认心智模型。
- 怎么验证：完整跑一轮主链路命令与测试，确认仓库主文档、CLI 帮助、默认路径、日志、诊断输出都不再把 `daily-lane` 作为主推荐。再做一次回归检查，确认 5 个现有原生 lanes 都还能注册并执行到各自 collector。
- 暂时不改什么：不处理 collect 主线之外的更大范围重命名，不追求一次清除所有历史文档痕迹，不动与 lane collect 无关的子系统。

# 每阶段验收标准

- 阶段 1：默认不传参时，主命令优先使用新环境变量和新默认目录；显式设置旧变量时仍可运行；`x-feed` 至少能完成一次真实或 smoke collect，`diagnose` 输出可读。
- 阶段 2：README 按文档步骤可操作成功；主文档中不再把 `daily-lane` 当成当前推荐默认值；至少一份设计文档和一份验证文档与当前实现口径一致。
- 阶段 3：测试在干净环境中可稳定运行；“新默认值”“旧变量兼容”“显式传参覆盖默认值”三类场景都有自动化覆盖；测试失败时能直接看出是路径、配置还是环境问题。
- 阶段 4：CLI、runtime、文档、日志口径一致；仓库内主路径不再依赖旧命名作为默认值；5 个现有原生 lanes 的注册与 collect 主链路回归通过。

# 风险回滚方案

- 保留双轨默认解析顺序一段时间：先读新变量，再回退旧变量；在确认外部调用方全部迁走前，不直接删除旧变量支持。
- 回滚优先级一：恢复默认值解析顺序与帮助文案，不动 lane 采集实现，这样回滚面最小。
- 回滚优先级二：README 与操作文档可以先回退到“signals-engine 为主、daily-lane 可兜底”的双轨说法，避免因为文档超前导致执行失败。
- 回滚优先级三：测试若因环境清洁化改造导致 CI 不稳定，可先保留旧测试入口并把新测试标记为增量检查，待环境固定后再收口。
- 数据层面不做 destructive 迁移：旧目录与新目录并存，禁止在切换阶段自动搬迁或删除 `~/.daily-lane-data` 中的历史产物。
- 若阶段 4 收口后发现外部仍依赖旧变量，直接恢复兼容分支并延后删除窗口，不做硬切。

# 建议先改的文件

1. `src/signals_engine/commands/collect.py`：当前默认值切换的主入口，先改它最能直接推动 collect 主线转向。
2. `src/signals_engine/commands/diagnose.py`：命令层仍默认读旧 config，必须和 collect 一起切，避免入口口径分裂。
3. `src/signals_engine/commands/config.py`：`config check` 仍绑定旧变量，是最容易暴露“主线没切干净”的地方。
4. `src/signals_engine/runtime/diagnose.py`：运行时诊断仍默认指向 `~/.daily-lane*`，不改会让 diagnose 和 collect 行为不一致。
5. `src/signals_engine/runtime/status.py`：状态读取默认目录还在旧数据根，主线切换后需要同步。
6. `README.md`：当前对外入口文档仍停留在试点表述，需要尽快和实现对齐。
7. `tests/test_cli_entrypoint.py`：可先补 CLI 层最基础的环境与入口验证，作为新默认值切换后的 smoke 防线。
8. `tests/test_x_feed_collect.py`、`tests/test_x_following_collect.py`、`tests/test_product_hunt_watch.py`：优先在现有 lane collect 测试上补默认路径/环境变量覆盖，避免只测 help 不测主链路。
