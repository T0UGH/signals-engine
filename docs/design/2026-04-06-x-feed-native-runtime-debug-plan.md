# x-feed Native Runtime Debug & Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `signal-engine` 当前“CLI 看似成功但可能根本未执行”的真实运行闭环问题，并用独立临时目录验证 native `x-feed` 的 diagnose / collect / artifact 产物是否真的按预期生成。

**Architecture:** 这不是继续扩 native source 功能，而是一次聚焦的 runtime-debug 收口。先修 CLI 入口与最小调试可观测性，再把真实运行结果强制落到独立临时目录，最后检查 `signals/*.md`、`index.md`、`run.json` 是否由这次运行新生成。日志先采用最小侵入方案：stderr + 临时目录内 `debug.log`。

**Tech Stack:** Python 3.11, argparse CLI, existing Signal Engine runtime, unittest, pathlib

---

## 0. 范围与完成定义

### 本次要做
- 修复 `src/signal_engine/cli.py` 缺失 `__main__` 入口的问题
- 为 diagnose / collect 增加最小调试日志（stderr + 文件）
- 增加 `--data-dir` 真实运行验证路径，明确写入到独立临时目录
- 为 CLI 入口与真实运行补测试
- 验证 native `x-feed` 在临时目录下是否真实生成：
  - `signals/*.md`
  - `index.md`
  - `run.json`
- 把这次真实运行的验证结果写成一份短验证记录

### 本次不做
- 不继续扩展 native source 功能
- 不重做 logging framework
- 不改 artifact 协议
- 不重新设计 config 系统
- 不引入复杂 observability / tracing 基础设施

### 完成标准
- `python3.11 -m signal_engine.cli diagnose --lane x-feed` 会真正执行 `main()`
- `python3.11 -m signal_engine.cli collect --lane x-feed --date ...` 会真正执行 collect
- CLI 运行时能在 stderr 明确输出关键阶段
- 同时在临时目录内留下 `debug.log`
- 用一个全新临时目录运行后，能明确判断：
  - 本次是否真的生成了新 signal files
  - `index.md` 是否生成
  - `run.json` 是否生成
- 若失败，日志中能直接看出失败点

---

## 1. 文件结构与职责

### 修改文件
- Modify: `src/signal_engine/cli.py`
  - 补 `__main__` 入口，保证 `python -m signal_engine.cli` 真执行 `main()`
- Modify: `src/signal_engine/commands/collect.py`
  - 增加最小调试输出，明确 data_dir / config / result status
- Modify: `src/signal_engine/commands/diagnose.py`
  - 增加最小调试输出，明确命令已执行
- Modify: `src/signal_engine/lanes/x_feed.py`
  - 在关键节点增加最小 debug hooks：fetch start/end、artifact write start/end、write fail
- Modify: `src/signal_engine/runtime/run_manifest.py`
  - 如需要，补写 run.json 落盘前后的最小 debug 记录

### 新建文件
- Create: `src/signal_engine/core/debuglog.py`
  - 极薄的调试日志辅助：同时写 stderr 和可选文件路径
- Create: `tests/test_cli_entrypoint.py`
  - 验证 `python -m signal_engine.cli` 会真正进入 `main()` 的测试
- Create: `tests/test_runtime_debug_logging.py`
  - 验证 debug.log 至少写出关键事件
- Create: `docs/verification/2026-04-06-x-feed-native-runtime-debug-check.md`
  - 记录这次真实运行验证结论

---

## 2. 设计决策（实现时必须遵守）

### 2.1 日志先做最小方案
只做：
- stderr
- 临时目录 `debug.log`

不做：
- log rotation
- structured JSON logs
- logging framework 大改

### 2.2 验证必须使用独立临时目录
这次不能继续写到 `~/.daily-lane-data` 再猜是不是旧产物。

必须使用一个明确的新目录，例如：
- `/tmp/signal-engine-debug/2026-04-06-run-001/`

### 2.3 真实运行验证优先级高于单元测试表面通过
单元测试可以留，但这次的核心验收是：
- CLI 真的运行
- 临时目录产物真的落地
- 日志能解释行为

---

## 3. 任务拆分

### Task 1: 修 CLI 入口

**Files:**
- Modify: `src/signal_engine/cli.py`
- Create: `tests/test_cli_entrypoint.py`

- [ ] **Step 1: 写 failing test，验证 CLI 模块作为 `-m` 入口时会调用 `main()`**

示例思路：
```python
def test_cli_module_has_main_entrypoint():
    # 断言 cli.py 文本中存在 __main__ 入口，或通过 subprocess 验证行为
    ...
```

- [ ] **Step 2: 运行测试确认当前失败**

Run:
```bash
python3.11 -m unittest tests.test_cli_entrypoint -v
```
Expected: FAIL，指出模块入口未执行。

- [ ] **Step 3: 在 `src/signal_engine/cli.py` 底部添加入口**

目标代码：
```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
python3.11 -m unittest tests.test_cli_entrypoint -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/signal_engine/cli.py tests/test_cli_entrypoint.py
git commit -m "fix: add cli module entrypoint"
```

---

### Task 2: 增加极薄 debug logging 能力

**Files:**
- Create: `src/signal_engine/core/debuglog.py`
- Modify: `src/signal_engine/commands/collect.py`
- Modify: `src/signal_engine/commands/diagnose.py`
- Modify: `src/signal_engine/lanes/x_feed.py`
- Modify: `src/signal_engine/runtime/run_manifest.py`
- Create: `tests/test_runtime_debug_logging.py`

- [ ] **Step 1: 写 failing test，验证 debug helper 能写 stderr 和文件**

```python
def test_debuglog_writes_to_file_when_path_given():
    ...
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
python3.11 -m unittest tests.test_runtime_debug_logging -v
```
Expected: FAIL，提示 debug helper 不存在。

- [ ] **Step 3: 实现 `debuglog.py` 最小版本**

要求：
- 提供单个 `debug_log(message, log_file=None)` 之类的薄函数
- 同时写 stderr
- 若提供 `log_file`，则 append 到文件

- [ ] **Step 4: 在 collect/diagnose 加最小日志点**

至少记录：
- command start
- parsed lane/date/data_dir/config path
- command end + exit status

- [ ] **Step 5: 在 `x_feed.py` 加关键日志点**

至少记录：
- fetch start
- fetch returned count
- signal write start/end
- index write start/end
- run.json write start/end
- any exception message

- [ ] **Step 6: 运行测试确认通过**

Run:
```bash
python3.11 -m unittest tests.test_runtime_debug_logging -v
```
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add src/signal_engine/core/debuglog.py src/signal_engine/commands/collect.py src/signal_engine/commands/diagnose.py src/signal_engine/lanes/x_feed.py src/signal_engine/runtime/run_manifest.py tests/test_runtime_debug_logging.py
git commit -m "feat: add minimal runtime debug logging"
```

---

### Task 3: 用独立临时目录做真实运行验证

**Files:**
- Create: `docs/verification/2026-04-06-x-feed-native-runtime-debug-check.md`

- [ ] **Step 1: 创建全新临时目录**

Run:
```bash
mkdir -p /tmp/signal-engine-debug/2026-04-06-run-001
```

- [ ] **Step 2: 用该目录跑 diagnose**

Run:
```bash
cd /Users/haha/workspace/signal-engine
PYTHONPATH=src python3.11 -m signal_engine.cli diagnose --lane x-feed --data-dir /tmp/signal-engine-debug/2026-04-06-run-001
```

- [ ] **Step 3: 用该目录跑 collect**

Run:
```bash
cd /Users/haha/workspace/signal-engine
PYTHONPATH=src python3.11 -m signal_engine.cli collect --lane x-feed --date 2026-04-06 --data-dir /tmp/signal-engine-debug/2026-04-06-run-001
```

- [ ] **Step 4: 检查真实产物是否存在**

至少检查：
```bash
find /tmp/signal-engine-debug/2026-04-06-run-001 -maxdepth 5 | sort
```

要求确认：
- `signals/*.md`
- `index.md`
- `run.json`
- `debug.log`

- [ ] **Step 5: 若缺少任一产物，先从 `debug.log` 定位原因，不允许猜**

查看：
```bash
cat /tmp/signal-engine-debug/2026-04-06-run-001/debug.log
```

- [ ] **Step 6: 把结果写入 verification 文档**

文档必须回答：
- CLI 是否真正执行
- collect 是否真正开始
- 本次是否真实生成新产物
- `run.json` 是否真实落地
- 若失败，具体卡在哪一步

- [ ] **Step 7: 提交**

```bash
git add docs/verification/2026-04-06-x-feed-native-runtime-debug-check.md
git commit -m "docs: add native runtime debug verification"
```

---

### Task 4: 为真实运行闭环补自动化测试（最小）

**Files:**
- Modify: `tests/test_cli_entrypoint.py`
- Modify: `tests/test_runtime_debug_logging.py`
- Modify: `tests/test_x_feed_collect.py`

- [ ] **Step 1: 写 failing test，验证 collect 在独立 data_dir 下会尝试写 run.json**

不要求真访问 X，可 mock source，但要锁定：
- `ctx.run_json_path`
- `write_run_manifest()` 被调用

- [ ] **Step 2: 写 failing test，验证 CLI 至少打印 command start/end debug lines**

- [ ] **Step 3: 实现最小测试所需代码调整**

- [ ] **Step 4: 跑相关测试并通过**

Run:
```bash
python3.11 -m unittest tests.test_cli_entrypoint tests.test_runtime_debug_logging tests.test_x_feed_collect -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_cli_entrypoint.py tests/test_runtime_debug_logging.py tests/test_x_feed_collect.py
git commit -m "test: cover cli runtime debug closure"
```

---

## 4. 执行顺序

必须按顺序：

1. Task 1 — 修 CLI 入口
2. Task 2 — 加最小 debug logging
3. Task 3 — 用独立临时目录做真实运行验证
4. Task 4 — 补最小自动化闭环测试

不要跳过 Task 3。  
这次问题的关键不是“测试绿不绿”，而是“真实运行到底有没有发生”。

---

## 5. 验收 checklist

- [ ] `python -m signal_engine.cli ...` 真的执行 `main()`
- [ ] CLI 至少输出 command start/end 到 stderr
- [ ] 临时目录里出现 `debug.log`
- [ ] 本次运行的 signal files 生成在独立临时目录
- [ ] `index.md` 真实生成
- [ ] `run.json` 真实生成
- [ ] verification 文档说明清楚本次真实运行结果
- [ ] 相关 unittest 通过

---

## 6. 最终交付

完成后，至少应交付：
- 修过入口的 `cli.py`
- 最小 debug logging 能力
- 一个独立临时目录下的真实运行产物
- 一份 runtime debug verification 文档
- 覆盖这次 root-cause 的自动化测试
