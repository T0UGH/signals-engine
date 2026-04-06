# Signal Engine x-feed Native Source Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `signal-engine` 的 `x-feed` lane 在不依赖 `opencli` 的前提下完成原生 X source 抓取，并同步清理 config、diagnose、tests、docs 中的 `opencli` 运行依赖痕迹，达到 C 级验收。

**Architecture:** 保留已经成立的 Phase 1 runtime / artifact 架构，只替换 `sources/x/opencli_feed.py` 背后的 source backend。新的 native source 采用 `auth / client / parser / models / errors / timeline` 小模块分层，`x_feed` lane 只消费标准化 tweet 结构，不知道任何 legacy backend 细节。Auth 采用 Cookie File 方案，不引入 browser daemon；HTTP client 采用 `httpx`；`run.json`、`index.md`、signal markdown 协议保持不变。

**Tech Stack:** Python 3.11, unittest, pathlib, json, yaml, httpx, existing Signal Engine runtime

---

## 0. 实现范围与完成定义

### 本次要做
- 创建 native X source 子系统
- 移除 `x-feed` 对 `opencli` shell 调用的运行依赖
- 把 `x-feed` lane 切换到 native source contract
- 重写 `diagnose --lane x-feed` 的检查逻辑为 native source 语义
- 迁移 config 语义，删除 `opencli.path` / `opencli.limit`
- 提供一次性 config migration 脚本
- 补齐 native source 的 source tests / lane tests / diagnose tests / artifact compatibility tests
- 增加迁移期 side-by-side fixture / 字段级对照资产
- 增加仓库级 opencli 残留守卫
- 清理 docs、注释、命令帮助中的 `opencli` 运行依赖说法

### 本次不做
- 不迁 `x-following`
- 不引入双 backend runtime
- 不做 plugin / source auto-discovery
- 不修改 `SignalRecord` / `RunResult` 协议
- 不改变 `signals/*.md` / `index.md` / `run.json` 合同
- 不扩展 article/search/following 等无关 X 能力
- 不引入 browser daemon、CDP、`page.evaluate()`、GitHub queryId fallback

### 完成标准
- 运行 `signal-engine collect --lane x-feed` 时不再 import / shell 调 `opencli`
- `diagnose --lane x-feed` 不再检查 `dist/main.js` / node probe
- 正式 config 不再包含 `opencli.*` 运行字段
- tests 覆盖 native source 成功 / 失败 / empty / schema error / rate limit / artifact compatibility
- 文档和帮助文案不再把 `opencli` 写成系统依赖
- 仓库中不存在 runtime/config/help/tests 里的 `opencli.path`、`dist/main.js`、`opencli binary` 等残留词

---

## 1. 关键实现决策（已拍板）

### 1.1 Auth 方案：Cookie File
选定方案：用户从浏览器导出 `cookies.json`，native source 直接读取 cookie file，不运行任何浏览器进程。

原因：
- browser daemon 会把 opencli 的 daemon 架构带进来，违反“不要把 signal-engine 做成 opencli 平台”
- Cookie File 是当前成本最低、边界最清晰的方案

### 1.2 HTTP Client：使用 `httpx`
- 使用 `httpx` 处理 cookie jar、timeout、transport errors
- 不手写 `urllib` cookie handling

### 1.3 不迁移的 opencli 逻辑
明确不迁入：
- browser session
- CDP daemon
- `page.evaluate()` 机制
- GitHub queryId fallback
- article/search/following 等额外能力

### 1.4 中文 design 是单一真源
实现时以：
- `docs/design/2026-04-06-x-feed-native-source-migration-design.zh-CN.md`
为主 spec。

英文 design 只在需要时同步，不作为实现约束真源。

---

## 2. 文件结构与职责

### 新建文件
- Create: `src/signal_engine/sources/x/models.py`
  - 定义 native source 标准化 tweet 结构
- Create: `src/signal_engine/sources/x/errors.py`
  - 定义 `AuthError` / `TransportError` / `RateLimitError` / `SchemaError` / `SourceUnavailableError`
- Create: `src/signal_engine/sources/x/auth.py`
  - 负责 auth material 加载与基本校验
- Create: `src/signal_engine/sources/x/client.py`
  - 负责 timeline transport / request building
- Create: `src/signal_engine/sources/x/parser.py`
  - 负责 raw response -> normalized tweet
- Create: `src/signal_engine/sources/x/timeline.py`
  - 暴露 `fetch_home_timeline()`，作为 lane 唯一入口
- Create: `tests/test_x_source_native.py`
  - source 层单元测试
- Create: `tests/test_x_feed_diagnose_native.py`
  - diagnose 原生 source 语义测试
- Create: `tests/fixtures/x/README.md`
  - fixture 来源与字段说明
- Create: `tests/fixtures/x/timeline-opencli-reference.json`
  - 迁移期对照基线 fixture
- Create: `tests/fixtures/x/timeline-native-reference.json`
  - native parser / source 验证 fixture
- Create: `tests/test_repo_no_opencli_runtime_refs.py`
  - 仓库级 opencli 残留守卫
- Create: `scripts/migrate-x-feed-config.py`
  - 一次性 config 迁移脚本
- Create: `docs/verification/2026-04-06-x-feed-native-source-migration-check.md`
  - native source compatibility / migration verification 记录

### 修改文件
- Modify: `src/signal_engine/sources/x/__init__.py`
  - 导出 native source 入口
- Modify: `src/signal_engine/lanes/x_feed.py`
  - 从 native source 获取 timeline；删掉 `opencli_feed` 依赖
- Modify: `src/signal_engine/runtime/diagnose.py`
  - 从 opencli probe 改成 native auth/probe/parse 诊断
- Modify: `src/signal_engine/commands/config.py`
  - config check 适配新的 source config
- Modify: `src/signal_engine/commands/collect.py`
  - 更新帮助文案与 config 语义说明
- Modify: `tests/test_x_feed_collect.py`
  - lane 测试从 opencli mock 改为 native source mock；增加 artifact compatibility assertions
- Modify: `docs/design/2026-04-06-x-feed-native-source-migration-design.zh-CN.md`
  - 如需要，补 implementation note 或状态更新

### 删除文件
- Delete: `src/signal_engine/sources/x/opencli_feed.py`
  - 在全仓确认无引用后删除

---

## 3. 设计决策（实现时必须遵守）

### 3.1 lane 只依赖标准化 source contract
`x_feed.py` 不允许知道：
- cookie 文件细节
- request 拼装细节
- parser 原始 schema
- legacy opencli 字段

它只允许依赖：
- `fetch_home_timeline(limit=...)`
- 返回的标准化 tweet 字段

### 3.2 不保留 runtime fallback backend
实现中不允许：
- `backend=opencli_legacy`
- 根据 config 在 native/opencli 间切换
- 任何“迁移期正式后门”

### 3.3 diagnose 语义必须原生化
`diagnose --lane x-feed` 不能再出现：
- opencli binary
- dist/main.js
- node timeline probe

### 3.4 config 语义必须原生化
新的 `lanes.x-feed` config 只能表达 native source 需求，例如：
- `source.limit`
- `source.timeout_seconds`
- `source.auth.cookie_file`

### 3.5 artifact 协议不借机改动
source migration 不得顺手改变：
- signal frontmatter contract
- `index.md` 基本结构
- `run.json` contract

### 3.6 native source 最小边界
公开 API 只允许暴露：
- `fetch_home_timeline()`

本次实现中不得新增公开的：
- article
- search
- following
- profile
- trends
相关接口。

---

## 4. 任务拆分

### Task A: 建立 source contract、错误模型、对照 fixture 资产

**Files:**
- Create: `src/signal_engine/sources/x/models.py`
- Create: `src/signal_engine/sources/x/errors.py`
- Modify: `src/signal_engine/sources/x/__init__.py`
- Create: `tests/fixtures/x/README.md`
- Create: `tests/fixtures/x/timeline-opencli-reference.json`
- Create: `tests/fixtures/x/timeline-native-reference.json`
- Create: `tests/test_x_source_native.py`

- [ ] **Step 1: 写 failing test，定义 `NormalizedTweet` 最小字段 contract**

```python
def test_normalized_tweet_requires_phase1_fields():
    tweet = NormalizedTweet(
        id="123",
        author="testuser",
        text="hello",
        likes=1,
        retweets=2,
        replies=3,
        views=4,
        created_at="2026-04-06T10:00:00Z",
        url="https://x.com/test/status/123",
    )
    assert tweet.id == "123"
    assert tweet.author == "testuser"
```

- [ ] **Step 2: 写 failing test，锁定 source error types**

```python
def test_x_source_errors_are_distinct_types():
    assert issubclass(AuthError, Exception)
    assert issubclass(RateLimitError, Exception)
    assert AuthError is not RateLimitError
```

- [ ] **Step 3: 添加迁移期 fixture 说明与代表性对照样本**

要求：
- `tests/fixtures/x/README.md` 说明 fixture 来源、时间、脱敏规则
- 至少准备 2 份 fixture：
  - 旧 backend 参考结构
  - native parser 目标结构样本

- [ ] **Step 4: 实现 `NormalizedTweet` 和 source error classes 的最小版本**

需要实现：
- `NormalizedTweet`
- `AuthError`
- `TransportError`
- `RateLimitError`
- `SchemaError`
- `SourceUnavailableError`

- [ ] **Step 5: 运行测试确认通过**

Run:
```bash
python3.11 -m unittest tests.test_x_source_native -v
```
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/signal_engine/sources/x/models.py src/signal_engine/sources/x/errors.py src/signal_engine/sources/x/__init__.py tests/fixtures/x tests/test_x_source_native.py
git commit -m "feat: add native x source contract errors and fixtures"
```

---

### Task B: 实现 `auth.py`

**Files:**
- Create: `src/signal_engine/sources/x/auth.py`
- Modify: `tests/test_x_source_native.py`

- [ ] **Step 1: 写 failing test，文件不存在时报 `AuthError`**

```python
def test_load_auth_raises_auth_error_when_cookie_missing():
    with self.assertRaises(AuthError):
        load_auth(cookie_file="/tmp/not-found.json")
```

- [ ] **Step 2: 写 failing test，缺少必要 cookies 时失败**

```python
def test_load_auth_requires_auth_token_and_ct0():
    with self.assertRaises(AuthError):
        load_auth(cookie_file="tests/fixtures/x/missing-required-cookies.json")
```

- [ ] **Step 3: 实现 `load_auth()` 最小版本**

要求：
- 支持 JSON cookie file
- 如有余力可顺手支持 Netscape format
- 校验必要 cookie：`auth_token`、`ct0`
- 返回结构化 `XAuth`

- [ ] **Step 4: 运行 auth 相关测试并通过**

Run:
```bash
python3.11 -m unittest tests.test_x_source_native -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/signal_engine/sources/x/auth.py tests/test_x_source_native.py
git commit -m "feat: add native x auth loader"
```

---

### Task C: 实现 `client.py` 与 `parser.py`

**Files:**
- Create: `src/signal_engine/sources/x/client.py`
- Create: `src/signal_engine/sources/x/parser.py`
- Modify: `tests/test_x_source_native.py`

- [ ] **Step 1: 写 failing test，验证 client 构造 HomeTimeline 请求**

```python
def test_client_builds_home_timeline_request():
    client = XClient(auth=sample_auth, timeout=30)
    request = client.build_home_timeline_request(limit=2)
    assert "graphql" in request.url
    assert "HomeTimeline" in request.url
```

- [ ] **Step 2: 写 failing test，timeout 映射为 `TransportError`**

```python
def test_client_maps_timeout_to_transport_error():
    with self.assertRaises(TransportError):
        client.fetch_timeline(limit=2)
```

- [ ] **Step 3: 写 failing test，429 映射为 `RateLimitError`**

```python
def test_client_maps_429_to_rate_limit_error():
    with self.assertRaises(RateLimitError):
        client.fetch_timeline(limit=2)
```

- [ ] **Step 4: 写 failing test，parser 成功解析代表性 fixture**

```python
def test_parse_timeline_response_returns_normalized_tweets():
    tweets = parse_timeline_response(SAMPLE_TIMELINE_JSON)
    assert tweets[0].id == "123"
    assert tweets[0].author == "testuser"
```

- [ ] **Step 5: 写 failing test，bad payload 抛 `SchemaError`**

```python
def test_parse_timeline_response_raises_schema_error_on_bad_payload():
    with self.assertRaises(SchemaError):
        parse_timeline_response({"unexpected": True})
```

- [ ] **Step 6: 实现 `client.py` 最小版本**

要求：
- 使用 `httpx`
- 处理 timeout、401、429、5xx
- hardcode 当前 working queryId
- 不做 GitHub queryId fallback

- [ ] **Step 7: 实现 `parser.py` 最小版本**

要求：
- 明确 key chain
- 不用松散 `get()` 链式兜底掩盖 schema drift
- 异常路径抛 `SchemaError`
- 处理 text / views 的代表性场景

- [ ] **Step 8: 运行 client/parser tests 并通过**

Run:
```bash
python3.11 -m unittest tests.test_x_source_native -v
```
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add src/signal_engine/sources/x/client.py src/signal_engine/sources/x/parser.py tests/test_x_source_native.py
git commit -m "feat: add native x client and parser"
```

---

### Task D: 实现 `timeline.py` 并完成字段级对照测试

**Files:**
- Create: `src/signal_engine/sources/x/timeline.py`
- Modify: `tests/test_x_source_native.py`

- [ ] **Step 1: 写 failing test，`fetch_home_timeline()` 串起 auth/client/parser**

```python
def test_fetch_home_timeline_calls_auth_client_and_parser():
    tweets = fetch_home_timeline(limit=2, cookie_file="tests/fixtures/x/cookies.json", timeout=30)
    assert len(tweets) == 2
```

- [ ] **Step 2: 写字段级 side-by-side 对照测试**

```python
def test_native_output_matches_reference_fields():
    native = fetch_home_timeline(...)
    reference = load_reference_fixture(...)
    assert len(native) == len(reference)
    assert native[0].id == reference[0]["id"]
    assert native[0].author == reference[0]["author"]
```

- [ ] **Step 3: 实现 `timeline.py` 最小版本**

要求：
- lane 只通过这个入口拿数据
- 不暴露 raw JSON 给 lane

- [ ] **Step 4: 运行 source tests 并通过**

Run:
```bash
python3.11 -m unittest tests.test_x_source_native -v
```
Expected: PASS

- [ ] **Step 5: 检查没有新增 article/search/following 公开接口**

Run:
```bash
cd /Users/haha/workspace/signal-engine && rg -n "def (fetch_article|fetch_search|fetch_following|fetch_profile|fetch_trends)" src/signal_engine/sources/x
```
Expected: no matches

- [ ] **Step 6: 提交**

```bash
git add src/signal_engine/sources/x/timeline.py tests/test_x_source_native.py
git commit -m "feat: add native x timeline entrypoint"
```

---

### Task E: Config migration + lane 切换

**Files:**
- Create: `scripts/migrate-x-feed-config.py`
- Modify: `src/signal_engine/lanes/x_feed.py`
- Modify: `src/signal_engine/commands/config.py`
- Modify: `src/signal_engine/commands/collect.py`
- Modify: `tests/test_x_feed_collect.py`

- [ ] **Step 1: 写 failing test，旧 `opencli.*` 配置给出迁移提示或失败**

```python
def test_collect_rejects_legacy_opencli_config_without_native_source_config():
    with self.assertRaises(ConfigError):
        collect_x_feed(ctx_with_legacy_opencli_config)
```

- [ ] **Step 2: 写 failing test，native `source.*` 配置可通过**

```python
def test_collect_accepts_native_source_config():
    result = collect_x_feed(ctx_with_native_source_config)
    assert result is not None
```

- [ ] **Step 3: 实现 `migrate-x-feed-config.py`**

要求：
- 把 `opencli.limit` → `source.limit`
- 删除 `opencli.path`
- 提示用户补 `source.auth.cookie_file`
- 这是一次性辅助脚本，不参与 runtime

- [ ] **Step 4: 修改 `x_feed.py` 使用 `fetch_home_timeline()`**

要求：
- 删除 `fetch_opencli_feed`
- 改从 `source.*` 读取 limit/timeout/auth
- 保持 artifact / status 语义不变

- [ ] **Step 5: 前移全仓引用检查，确认可删旧 backend**

Run:
```bash
cd /Users/haha/workspace/signal-engine && rg -n "opencli_feed" src tests docs scripts
```
Expected: only the old file itself and planned deletion target remain

- [ ] **Step 6: 删除 `opencli_feed.py`**

```bash
git rm src/signal_engine/sources/x/opencli_feed.py
```

- [ ] **Step 7: 更新 lane tests 到 native source 语义**

至少覆盖：
- native source success
- native source empty
- `AuthError` / `TransportError` / `SchemaError` / `RateLimitError`
- partial signal write failure 时 `run.json` 仍反映最终 status

- [ ] **Step 8: 运行 collect tests 并通过**

Run:
```bash
python3.11 -m unittest tests.test_x_feed_collect -v
```
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add scripts/migrate-x-feed-config.py src/signal_engine/lanes/x_feed.py src/signal_engine/commands/config.py src/signal_engine/commands/collect.py tests/test_x_feed_collect.py
git commit -m "feat: migrate x-feed lane and config to native source"
```

---

### Task F: 重写 diagnose 为 native source 语义

**Files:**
- Modify: `src/signal_engine/runtime/diagnose.py`
- Create: `tests/test_x_feed_diagnose_native.py`

- [ ] **Step 1: 写 failing test，`auth_file` 检查缺失时 FAIL**

```python
def test_diagnose_auth_file_missing_reports_fail():
    result = diagnose_lane("x-feed", data_dir=tmpdir, config=sample_native_config)
    self.assertIn("auth file", result.output.lower())
    self.assertIn("FAIL", result.output)
```

- [ ] **Step 2: 写 failing test，`auth_valid` 检查输出 native 语义**

```python
def test_diagnose_auth_valid_reports_ok():
    result = diagnose_lane("x-feed", data_dir=tmpdir, config=valid_native_config)
    self.assertIn("auth valid", result.output.lower())
```

- [ ] **Step 3: 写 failing test，`timeline_probe` 失败可区分 transport / rate limit / schema**

```python
def test_diagnose_timeline_probe_reports_rate_limit():
    result = diagnose_lane("x-feed", data_dir=tmpdir, config=rate_limited_config)
    self.assertIn("rate", result.output.lower())
```

- [ ] **Step 4: 写 failing test，diagnose 输出中不再出现 opencli 语义**

```python
def test_diagnose_output_has_no_opencli_terms():
    result = diagnose_lane("x-feed", data_dir=tmpdir, config=valid_native_config)
    self.assertNotIn("opencli", result.output.lower())
    self.assertNotIn("dist/main.js", result.output.lower())
```

- [ ] **Step 5: 实现 diagnose 的原生检查项**

至少实现：
- source config
- auth_file
- auth_valid
- timeline_probe
- response_parse
- output_dir

- [ ] **Step 6: 运行 diagnose tests 并通过**

Run:
```bash
python3.11 -m unittest tests.test_x_feed_diagnose_native -v
```
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add src/signal_engine/runtime/diagnose.py tests/test_x_feed_diagnose_native.py
git commit -m "feat: rewrite x-feed diagnose for native source"
```

---

### Task G: artifact compatibility 自动化测试 + 端到端验证

**Files:**
- Modify: `tests/test_x_feed_collect.py`
- Create: `docs/verification/2026-04-06-x-feed-native-source-migration-check.md`

- [ ] **Step 1: 新增 artifact-level 自动化断言**

至少锁定：
- signal markdown frontmatter 关键字段
- `index.md` 关键结构
- `run.json` final receipt 关键字段

- [ ] **Step 2: 写 failing test，partial signal failure 时 `run.json.status == failed`**

如未保留则补写，确保 native source 下仍成立。

- [ ] **Step 3: 写字段级对照结论到 verification 文档**

至少覆盖：
- count
- id
- author
- url
- text
- engagement
- timestamp

- [ ] **Step 4: 跑全量测试**

Run:
```bash
python3.11 -m unittest discover -s tests -v
```
Expected: 全部 PASS

- [ ] **Step 5: 做一次真实 try-run（如果本机 auth 可用）**

Run:
```bash
python3.11 -m signal_engine.cli collect --lane x-feed --date 2026-04-06 --config <native-config>
python3.11 -m signal_engine.cli diagnose --lane x-feed --config <native-config>
python3.11 -m signal_engine.cli status --lane x-feed --date 2026-04-06
```

- [ ] **Step 6: 写 verification 结论**

结论必须回答：
- 是否完成 C 级验收
- 系统里是否仍有 opencli 运行依赖
- native source 是否可替代旧 backend

- [ ] **Step 7: 提交**

```bash
git add tests/test_x_feed_collect.py docs/verification/2026-04-06-x-feed-native-source-migration-check.md
git commit -m "test: add native x-feed artifact compatibility coverage"
```

---

### Task H: 清理 opencli 运行依赖痕迹并增加仓库级守卫

**Files:**
- Create: `tests/test_repo_no_opencli_runtime_refs.py`
- Modify: `docs/design/2026-04-06-x-feed-native-source-migration-design.zh-CN.md`
- Modify: relevant code comments / docstrings in `src/signal_engine/lanes/x_feed.py`, `runtime/diagnose.py`, `commands/collect.py`

- [ ] **Step 1: grep 全仓 opencli 痕迹**

Run:
```bash
cd /Users/haha/workspace/signal-engine && rg -n "opencli.path|opencli.limit|dist/main.js|opencli binary|node .*twitter timeline|opencli" src tests docs scripts
```
Expected: 只允许 design/verification 中作为历史背景出现，runtime/help/tests/config 中不得出现。

- [ ] **Step 2: 写 repo guard failing test**

```python
def test_runtime_repo_has_no_opencli_runtime_refs():
    banned = ["opencli.path", "opencli.limit", "dist/main.js", "opencli binary"]
    ...
```

- [ ] **Step 3: 清理 runtime/help/tests/config 中残留词**

保留原则：
- design / verification 文档中可作为历史背景提及
- runtime help / config docs / diagnose output / tests 中不允许继续把它写成系统依赖

- [ ] **Step 4: 运行 repo guard tests 并通过**

Run:
```bash
python3.11 -m unittest tests.test_repo_no_opencli_runtime_refs -v
```
Expected: PASS

- [ ] **Step 5: 跑全量测试确认无回归**

Run:
```bash
python3.11 -m unittest discover -s tests -v
```
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src tests docs scripts
git commit -m "chore: remove opencli runtime references from x-feed native migration"
```

---

## 5. 执行顺序建议

推荐严格按下面顺序执行：

1. Task A — contract / errors / fixtures
2. Task B — auth
3. Task C — client / parser
4. Task D — timeline + field-level comparison
5. Task E — config migration + lane 切换 + 删除 old backend
6. Task F — diagnose rewrite
7. Task G — artifact compatibility + end-to-end verification
8. Task H — repo-wide cleanup + guard

不要一开始就：
- 直接删 `opencli_feed.py`
- 或先改 diagnose / docs
- 或一边改 source 一边改 artifact 协议

---

## 6. 验收 checklist

### 功能
- [ ] `x-feed` 不再依赖 opencli runtime
- [ ] native source 成功路径可跑
- [ ] native empty path 可跑
- [ ] native source error path 可解释
- [ ] rate limit 与 transport/schema/auth 可区分

### 代码
- [ ] `src/` 运行链路里不再 import / shell 调 opencli
- [ ] 没有 `opencli_legacy` / runtime fallback
- [ ] 没有新增 article/search/following 等公开接口

### 配置
- [ ] `lanes.x-feed` 正式 config 不再使用 `opencli.*`
- [ ] 有一次性 config migration 脚本

### diagnose
- [ ] diagnose 输出只反映 native source 语义
- [ ] diagnose 中不再出现 `opencli binary` / `dist/main.js`

### artifact
- [ ] signal markdown contract 未被破坏
- [ ] `index.md` 仍可消费
- [ ] `run.json` 仍为 truthful final receipt

### 文档与仓库卫生
- [ ] 正式 docs/help 不再把 opencli 写成系统依赖
- [ ] repo guard 能阻止旧残留词回流

### 验证
- [ ] source tests 通过
- [ ] lane tests 通过
- [ ] diagnose tests 通过
- [ ] repo guard tests 通过
- [ ] 全量 unittest 通过
- [ ] verification 文档已完成

---

## 7. 最终交付说明

完成后，交付物至少应包括：
- native source 子系统代码
- 切换后的 `x_feed.py`
- 重写后的 diagnose/config
- 更新后的 tests
- 字段级对照 fixture 与 verification 文档
- config migration 脚本
- repo-wide opencli 残留守卫
- 删除 opencli runtime 依赖后的 clean repo state
