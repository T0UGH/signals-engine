# x-feed Native Source Migration — Implementation Plan

**日期：** 2026-04-06
**Author:** Arc
**Status:** Implementation Plan
**基于：** `docs/design/2026-04-06-x-feed-native-source-migration-design.zh-CN.md`

---

## 0. 前置说明：Auth 实现策略

这是 implementation plan 中最关键的架构决策，必须先明确。

**问题：** opencli 的 timeline 实现依赖浏览器会话（`page.goto('https://x.com')` + `page.evaluate()` 在浏览器上下文中执行 fetch）。这是因为 X 的 GraphQL API 需要同源 cookie。

**signal-engine 不能运行一个常驻浏览器 daemon**，否则就变成了"半个 opencli"。

**选定方案：Cookie File 方案**

- 用户从浏览器导出 `cookies.json`（X.com 登录态 cookies）
- `auth.py` 读取并解析 cookie file（支持 Netscape 格式或 JSON）
- `client.py` 用 `httpx` 或 `requests` 发 HTTP 请求，在请求头中注入 cookie 值
- 不运行任何浏览器进程

**为什么不用其他方案：**

| 方案 | 为什么不选 |
|------|-----------|
| 保留 browser daemon | 会变成 opencli fork，违反"不把 signal-engine 做成 opencli 平台" |
| 从零重写 X auth | 工作量过大，且 cookie file 是已验证的最小方案 |
| 只迁移 opencli 的 JSON output parsing | 没有解决核心依赖问题 |

**需要从 opencli 迁移的逻辑（仅此而已）：**
- `timeline.ts` 的 GraphQL URL 构建（hardcode queryId）
- `timeline.ts` 的响应解析路径（`data.home.home_timeline_urt.instructions[].entries[]...`）
- `registry.ts` 的 auth preflight check（cookie 文件存在性）
- 不迁移：browser bridge、CDP daemon、page evaluate 机制

---

## 1. 实施顺序

```
Phase 1：Source 子系统（纯 Python，无 lane 依赖）
  ↓
Phase 2：Config Migration（新 config schema 新鲜生效，config 文件迁移脚本）
  ↓
Phase 3：Lane 集成（x_feed.py 切换到 native source）
  ↓
Phase 4：Diagnose 重写（替换 opencli probe 为 native probe）
  ↓
Phase 5：测试补写（source / lane / diagnose tests）
  ↓
Phase 6：Artifact Compatibility 验证
  ↓
Phase 7：清理（删除 opencli_feed.py，移除旧 config 字段，删除旧 diagnose opencli probe）
```

**串行约束：**
- Phase 1 必须在 Phase 2 之前完成（config migration 依赖 source models）
- Phase 3 必须在 Phase 4 之前完成（diagnose 依赖 lane 切换后的行为）
- Phase 5 贯穿多个 phase，随代码走

**可以并入同一阶段的任务：** Phase 5 的测试可以在 Phase 1/2/3 开发期间同步写 fixture，不需要等代码完成。

---

## 2. 文件级改动清单

### 2.1 新建文件

| 文件路径 | 职责 |
|---------|------|
| `src/signal_engine/sources/x/__init__.py` | source package 导出，`X_SOURCE_ERRORS` 聚合 |
| `src/signal_engine/sources/x/errors.py` | 5 种错误类型：`AuthError`、`TransportError`、`RateLimitError`、`SchemaError`、`SourceUnavailableError` |
| `src/signal_engine/sources/x/models.py` | `NormalizedTweet` dataclass（含 design 中 9 个字段） |
| `src/signal_engine/sources/x/auth.py` | `load_auth()` 函数：发现 + 解析 cookie file；返回 `XAuth`（含 cookies dict + preflight） |
| `src/signal_engine/sources/x/client.py` | `XClient` 类：`fetch_timeline(limit)` 负责 HTTP 请求构造和执行 |
| `src/signal_engine/sources/x/parser.py` | `parse_timeline_response(raw_json)` 把 X API 原始响应映射为 `list[NormalizedTweet]` |
| `src/signal_engine/sources/x/timeline.py` | `fetch_home_timeline(limit: int, auth: XAuth, timeout: int) -> list[NormalizedTweet]`，暴露给 lane 的唯一入口 |
| `tests/test_x_native_source.py` | source 子系统测试（含 auth/parser/client 的 unit tests） |
| `scripts/migrate-x-feed-config.py` | 一次性 config 迁移脚本（读取旧 `opencli.*` 字段，输出新 `source.*` YAML） |
| `docs/verification/2026-04-06-x-feed-native-source-migration-verification.md` | migration verification 文档 |

### 2.2 修改文件

| 文件路径 | 改动说明 |
|---------|---------|
| `src/signal_engine/lanes/x_feed.py` | `fetch_opencli_feed()` → `timeline.fetch_home_timeline()`；删除 `from ..sources.x.opencli_feed import`；config key 从 `opencli.*` 改为 `source.*` |
| `src/signal_engine/runtime/diagnose.py` | 替换 SOURCE 分支的 opencli binary probe 为 native auth probe + timeline probe；删除 `_probe_opencli()` |
| `src/signal_engine/core/errors.py` | 无改动（`SourceError` 继续存在，供 lane 层捕获 source 错误） |

### 2.3 删除文件

| 文件路径 | 原因 |
|---------|------|
| `src/signal_engine/sources/x/opencli_feed.py` | opencli 桥接层，migration 完成后不再需要 |

### 2.4 不改动的文件（确认不受影响）

| 文件 | 原因 |
|------|------|
| `core/models.py`（SignalRecord / RunResult）| design 明确不重做 |
| `signals/render.py` / `signals/writer.py` | artifact 协议不变 |
| `runtime/collect.py` | lane 集成接口不变 |
| `runtime/run_manifest.py` | receipt 协议不变 |
| `commands/` | CLI 接口不变 |

---

## 3. Source 子系统切分方案

### 3.1 `errors.py` — 错误类型

```python
class XSourceError(Exception): ...
class AuthError(XSourceError): ...        # cookie 无效/缺失/格式错误
class TransportError(XSourceError): ...  # HTTP 请求失败/超时
class RateLimitError(XSourceError): ...    # 429 或 explicit signal
class SchemaError(XSourceError): ...      # 响应结构不符合预期
class SourceUnavailableError(XSourceError): ...
```

**设计原则：** 每个错误类型对应一个可诊断的失败根因。lane 层捕获 `XSourceError` 做边界映射。

### 3.2 `models.py` — 数据模型

```python
@dataclass
class NormalizedTweet:
    id: str
    author: str          # screen_name
    text: str
    likes: int
    retweets: int
    replies: int
    views: int
    created_at: str     # ISO8601，UTC
    url: str            # https://x.com/{author}/status/{id}
```

**注意：** `NormalizedTweet` 是 source 子系统的内部类型，lane 负责映射为 `SignalRecord`。两边使用不同的 dataclass。

### 3.3 `auth.py` — 认证加载

```python
@dataclass
class XAuth:
    cookies: dict[str, str]   # {cookie_name: value}
    # preflight 已验证

def load_auth(cookie_file: str | Path) -> XAuth:
    """
    1. 发现并读取 cookie file（支持 netscape format 和 JSON）
    2. 校验必要 cookie 存在（auth_token, ct0）
    3. 返回 XAuth
    """
```

**关键设计：** `load_auth()` 做 preflight 校验（文件存在 + 格式合法 + 必要字段存在），但不做网络请求验证。网络请求验证由 `client.py` 在 timeline probe 时做。

**不迁移 opencli 的哪些 auth 逻辑：**
- 不迁移 browser session 管理
- 不迁移 `page.goto()` / `page.evaluate()` 机制
- 不迁移 GitHub queryId fallback 逻辑（直接 hardcode 当前已知的 queryId）

### 3.4 `client.py` — HTTP 客户端

```python
class XClient:
    GRAPHQL_URL = "https://x.com/i/api/graphql/{query_id}/HomeTimeline"
    HOME_TIMELINE_QUERY_ID = "Cwsrks3yvZIW8Cny34fpqA"  # 2026-04 当前 queryId，需维护

    def __init__(self, auth: XAuth, timeout: int = 30):
        self.session = httpx.Client(timeout=timeout)
        self.auth = auth
        self._inject_auth_headers(self.session)

    def fetch_timeline(self, limit: int) -> dict:
        """
        1. 构造 GraphQL GET 请求（limit → count param）
        2. 用 auth headers 发请求
        3. 返回解析前的原始 JSON dict
        4. 处理 429 / 401 / 5xx
        """
```

**重要：** `httpx` 是新引入的依赖。考虑用标准库 `urllib` 避免引入新依赖（但 `httpx` 的 cookie jar 支持更好）。**建议用 `httpx`**，因为 signal-engine 已经是 Python 3.11+，引入一个 HTTP client 的复杂度低于手写 cookie handling。

### 3.5 `parser.py` — 响应解析

```python
def parse_timeline_response(raw: dict) -> list[NormalizedTweet]:
    """
    1. 沿 X API 响应路径找到 entries 数组
    2. 对每个 entry，提取 tweet REST ID、author、text、engagement 字段
    3. 处理不同 text 来源（note_tweet vs legacy.full_text）
    4. 处理 view count 格式（可能是 "1.2K" 字符串或纯数字）
    5. 构造 NormalizedTweet，异常时抛出 SchemaError
    """
```

**Schema drift 防护：**
- 解析路径使用明确的 key chain，不使用 `get()` 链式降级
- 任何预期的 key 缺失时立即抛出 `SchemaError`（不静默跳过）
- fixture 覆盖主流场景（普通 tweet、retweet、reply、长文 tweet）

### 3.6 `timeline.py` — 入口函数

```python
def fetch_home_timeline(
    limit: int = 100,
    cookie_file: str | None = None,
    timeout: int = 30,
) -> list[NormalizedTweet]:
    """
    暴露给 lane 的唯一稳定入口。

    1. load_auth(cookie_file)  → XAuth
    2. XClient(auth).fetch_timeline(limit)  → raw dict
    3. parse_timeline_response(raw)  → list[NormalizedTweet]
    4. 截断到 limit 条
    5. 返回
    """
```

**lane 从不直接创建 `XClient` 或调用 `auth.py`。** lane 只调用 `fetch_home_timeline()`，所有内部细节封装在此函数内。

---

## 4. Config Migration 方案

### 4.1 旧 config 语义（需移除）

```yaml
lanes:
  x-feed:
    enabled: true
    opencli:
      path: ~/.openclaw/workspace/github/opencli  # 删除
      limit: 100                                  # 迁移为 source.limit
```

### 4.2 新 config 语义

```yaml
lanes:
  x-feed:
    enabled: true
    source:
      limit: 100              # 从 opencli.limit 迁移
      timeout_seconds: 30      # 新增，对应 client.py timeout
      auth:
        cookie_file: ~/.signal-engine/x-cookies.json  # 用户导出路径
```

### 4.3 Migration 步骤

**第一步：** 写 `scripts/migrate-x-feed-config.py`（一次性脚本）

```python
# 读取 ~/.daily-lane/config/lanes.yaml
# 如果存在 opencli.path 或 opencli.limit：
#   - 生成 cookie_file 路径推断（或要求用户指定）
#   - 输出 migration 提示
#   - 将 opencli.limit → source.limit
#   - 将 opencli.path 删除
# 如果不存在 opencli.*：无操作
```

**第二步：** config schema 更新

- `runtime/collect.py` 和 `lanes/x_feed.py` 中读取 `lanes["x-feed"]["source"]["limit"]`（带默认值）
- 不再读取 `lanes["x-feed"]["opencli"]`

**第三步：** 报错/迁移提示

- 如果 `opencli.*` 存在但 `source.*` 不存在：打印明确的迁移提示，然后退出（或临时 fallback）
- 如果两者都没有：报错说缺少 auth 配置

### 4.4 Cookie File 发现顺序

`auth.py` 的 `load_auth()` 应按以下顺序发现 cookie file：

1. 显式传入的 `cookie_file` 参数（优先级最高）
2. `source.auth.cookie_file`（来自 config）
3. `~/.signal-engine/x-cookies.json`（默认位置）

---

## 5. Diagnose 重写方案

### 5.1 移除的检查项

- `dist/main.js` 是否存在 → **删除**
- `node ... twitter timeline --limit 1` probe → **删除**
- `opencli binary` 文案 → **删除**

### 5.2 新增的检查项（SOURCE 分支重构）

| 检查项 | 语义 | FAIL 条件 |
|--------|------|----------|
| `auth_file` | cookie file 存在且可读 | 文件不存在或不可读 |
| `auth_valid` | cookie file 可解析，必要字段存在 | 解析失败或 `auth_token` / `ct0` 缺失 |
| `timeline_probe` | native `fetch_home_timeline(limit=1)` 可执行 | HTTP 请求失败（网络/认证/超时）|
| `response_parse` | probe 响应可解析为 NormalizedTweet | JSON decode 失败或 schema 不匹配 |
| `output_dir` | 信号输出目录可写 | 同现有逻辑 |

### 5.3 诊断输出语义

```text
SOURCE
  [OK/FAIL] cookie file: {path}
  [OK/FAIL] auth valid: {reason if fail}
  [OK/FAIL] timeline probe: {ok / fail_reason}
  [OK/FAIL] response parse: {ok / fail_reason}
```

### 5.4 实现注意

- `diagnose_lane()` 应 catch `XSourceError` 并将其映射为具体的 FAIL 行
- 不需要网络请求的检查（auth_file、auth_valid）应优先执行（fail fast）
- `timeline_probe` 使用 `timeout=10`（比生产 `timeout=30` 更短，诊断不需要等满）

---

## 6. 测试与验证计划

### 6.1 Source Tests（`tests/test_x_native_source.py`）

| 测试 | 内容 |
|------|------|
| `test_auth_valid_cookie_file` | 有效 cookie file → XAuth 非空 |
| `test_auth_missing_file` | 文件不存在 → `FileNotFoundError` |
| `test_auth_malformed_file` | 格式错误 → `AuthError` |
| `test_auth_missing_required_cookies` | 缺少 auth_token → `AuthError` |
| `test_parser_normal_tweet` | fixture 解析正确字段 |
| `test_parser_retweet` | retweet 走 note_tweet.text 分支 |
| `test_parser_long_text` | 长文走 note_tweet_results 路径 |
| `test_parser_schema_mismatch` | 响应缺少关键字段 → `SchemaError` |
| `test_client_unauthorized` | HTTP 401 → `AuthError` |
| `test_client_rate_limited` | HTTP 429 → `RateLimitError` |
| `test_client_network_error` | 连接失败 → `TransportError` |

**Fixtures：** 需要从真实 X API 响应中提取 2-3 个 fixture JSON，保存到 `tests/fixtures/x-timeline-*.json`。可以从 opencli 的测试数据迁移（如果有），或手动构造最小有效响应。

### 6.2 Lane / Runtime Tests

| 测试 | 内容 |
|------|------|
| `test_collect_success_native` | 成功路径：native source → SUCCESS，所有 artifact 正确 |
| `test_collect_empty_native` | 空 feed → EMPTY |
| `test_collect_auth_error_native` | `AuthError` → FAILED，诊断层可感知 |
| `test_collect_transport_error` | `TransportError` → FAILED |
| `test_collect_schema_error` | `SchemaError` → FAILED |
| `test_collect_partial_signal_failure` | 已有（Phase 1），不受 migration 影响 |

**Mock 策略：** mock `timeline.fetch_home_timeline`（在 `x_feed.py` 导入处 mock），不 mock HTTP 层——HTTP 层属于 source 子系统内部，由 source tests 覆盖。

### 6.3 Diagnose Tests

| 测试 | 内容 |
|------|------|
| `test_diagnose_auth_file_missing` | cookie file 不存在 → FAIL + 具体文案 |
| `test_diagnose_auth_valid` | 有效 cookie → OK 行 |
| `test_diagnose_timeline_probe_fail` | native probe 失败 → FAIL |

### 6.4 Artifact Compatibility Tests（扩展现有 suite）

在 `test_x_feed_collect.py` 中新增：

| 测试 | 内容 |
|------|------|
| `test_collect_success_real_artifacts` | 已存在（Phase 1），验证 artifact 内容不变 |
| `test_compat_signal_markdown_fields` | 新增：验证 signal markdown frontmatter 关键字段（id/author/text/url/engagement）|

**验证方法：** 运行一次真实的 `collect_x_feed()`（带真实 cookie file），检查 artifact 文件中的字段是否与 Phase 1 兼容。

### 6.5 Migration Verification 文档结构

```
# x-feed Native Source Migration — Verification

## 验证时间
{timestamp}

## Field-level Comparison
| 字段 | opencli source | native source | 是否一致 |
|------|---------------|--------------|---------|
| id | ✓ | ✓ | ? |
| author | ✓ | ✓ | ? |
| text | ✓ | ✓ | ? |
| ... | ... | ... | ... |

## Artifact Compatibility
- [ ] signals/*.md frontmatter 关键字段不变
- [ ] index.md 结构不变
- [ ] run.json receipt 格式不变

## Failure Mode 对照
| 失败场景 | opencli behavior | native behavior | 是否一致 |
|----------|-----------------|----------------|---------|
| 缺失 cookie | ? | ? | ? |
| 无效 cookie | ? | ? | ? |
| 空 feed | ? | ? | ? |
| HTTP 401 | ? | ? | ? |
```

---

## 7. 风险与取舍

### 7.1 Auth Fragility（最高风险）

**风险：** Cookie file 的 `auth_token` 和 `ct0` 有时效性（通常几天到几周）。用户需要定期刷新 cookie file。

**缓解：**
- `auth.py` 的 preflight 检查能快速告知用户 cookie 是否过期（不需要等到 collect 时才报错）
- diagnose 的 `auth_valid` 检查能让用户在 CI / cron 场景下提前知道问题
- 文档说明 cookie 刷新流程

**未解决的问题：** X 的 cookie 刷新没有 programmatic 方案。用户必须手动从浏览器导出。这是产品限制，不是代码 bug。

### 7.2 Schema Drift

**风险：** X 随时可能改变 GraphQL 响应结构（field 改名、path 变化）。Parser 抛 `SchemaError` 会导致 lane 直接 FAILED。

**缓解：**
- `SchemaError` 包含尽量多的上下文（缺失的 key path）
- Migration verification 文档记录当前已知 working 的 queryId
- 如果 X 改了 queryId，只需更新 `client.py` 中的 `HOME_TIMELINE_QUERY_ID` 常量

**未解决：** 没有自动 queryId 刷新机制。如果 X 改变 queryId，需要人工介入更新代码。这与 opencli 的行为一致（opencli 也依赖 hardcoded queryId + GitHub fallback）。

### 7.3 过度迁移风险

**风险：** 把 opencli 的 browser daemon、CDP bridge 等不需要的结构也迁进来。

**缓解：**
- 严格按 §3 切分方案执行，不越界
- `sources/x/` 只包含 timeline fetch 逻辑
- `sources/x/` 不做：browser session、page navigation、plugin discovery

### 7.4 验证不足风险

**风险：** 没有双 backend 做 side-by-side 对照，migration 后行为可能漂移。

**缓解：**
- Migration verification 文档要求真实跑一次对照
- Source tests 用 real HTTP fixtures，确保 parser 覆盖所有已知的 X 响应类型
- Phase 1 现有的 artifact compatibility tests 不需要重写，直接覆盖

### 7.5 httpx 引入风险

**风险：** 引入新依赖增加构建复杂度。

**缓解：** signal-engine 已是 Python 3.11+，httpx 是成熟库（Pydantic 团队维护）。若不想引入，`urllib.request` + `http.cookiejar` 可以替代但代码更冗长。当前选择 **httpx**。

---

## 8. 实现优先级排序（Task 顺序）

```
Task A: 搭建 source 子系统骨架
  - sources/x/__init__.py
  - sources/x/errors.py
  - sources/x/models.py
  (无外部依赖，可独立验证)

Task B: 实现 auth.py
  - load_auth() 实现
  - 单元测试（mock cookie file）
  (无网络依赖，可快速验证)

Task C: 实现 client.py + parser.py
  - GraphQL URL / header 构造
  - HTTP 请求
  - 响应解析
  (用 mock httpx fixture 验证)

Task D: 实现 timeline.py
  - 组装 auth + client + parser
  - 入口函数
  (Task A+B+C 完成后才能跑通)

Task E: Config migration 脚本 + x_feed.py 切换
  - scripts/migrate-x-feed-config.py
  - x_feed.py 改 import
  - config key 切换

Task F: Diagnose 重写
  - 替换 opencli probe → native probe
  - 新增诊断测试

Task G: 端到端验证
  - 真实 cookie file 跑一次 collect
  - 验证 artifact 内容
  - 填写 Migration Verification 文档

Task H: 清理
  - 删除 opencli_feed.py
  - 删除 diagnose 中的 opencli 相关代码
  - 更新 docs（移除 opencli 依赖描述）
```

---

## 9. 明确不包含的范围

以下内容**不在本次 migration 范围内**，即使 opencli 有相关代码：

- X Search API
- X Trends / API
- Article / Newsletter 获取
- User profile 获取
- Following / Followers 获取
- Twitter OpenAPI 的 GitHub queryId 自动刷新
- 任何浏览器自动化机制（CDP、Puppeteer、Playwright）
- opencli 的 plugin discovery 系统
