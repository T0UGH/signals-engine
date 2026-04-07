# x-following native migration design

## 1. 背景与目标

把 `x-following` lane 从 shell/opencli 桥接迁移到 Signal Engine Python native 实现，模式与 `x-feed` 对齐。

核心约束（来自用户确认）：
- **A**：Signal Engine 不该依赖太多外部 CLI 工具，运维负担重
- **B**：桥接出问题时排查链路长，native 更透明
- **C**：两条 X lane 应该架构一致，但 source 层不能耦合
- **两条 lane 独立**：不能共享同一个 timeline.py，必须拆成独立 source 子模块

---

## 2. 架构设计

### 2.1 目标结构

```
sources/x/
├── __init__.py           ← 共享导出
├── auth.py               ← 共享：cookie 加载、header 构造
├── client.py             ← 共享：httpx 基础封装（HTTP/1.1 transport、错误分类）
├── errors.py             ← 共享：AuthError / RateLimitError / SchemaError 等
├── models.py             ← 共享：NormalizedTweet 数据模型
├── feed/
│   ├── __init__.py
│   └── timeline.py       ← x-feed 专用：HomeTimeline queryId + 变量
└── following/
    ├── __init__.py
    └── timeline.py       ← x-following 专用：HomeLatestTimeline queryId + 变量
```

**关键原则**：
- `feed/timeline.py` 和 `following/timeline.py` 完全独立，各自持有自己的 queryId
- `auth.py` / `client.py` / `errors.py` / `models.py` 是真正的 shared lib，无业务逻辑
- 两条 lane 各自导入自己的 source 模块，lane 层不直接引用 shared source 文件

### 2.2 与 x-feed 的关系

- x-feed 导入 `from ..sources.x.feed.timeline import fetch_home_timeline`
- x-following 导入 `from ..sources.x.following.timeline import fetch_following_timeline`
- 两条 lane 的 source 路径完全不同，无耦合

---

## 3. x-following source 实现细节

### 3.1 API 端点

X 的 `HomeLatestTimeline` GraphQL 端点，X 内部用于"Following"标签页时间线。

和 `HomeTimeline` 的主要区别：
- 变量中没有 `latestControlAvailable: true`（LatestTimeline 本身就是 latest）
- 不混入社群推荐内容，是纯关注流

### 3.2 queryId 发现

HomeLatestTimeline 的 queryId 需要发现。推荐方式（二选一）：

**选项 A（推荐）**：从 xfetch 的 source map / JS bundle 中提取
- xfetch 是开源的（npm: `@lxgic/xfetch`）
- `HomeLatestTimeline` queryId 硬编码在其源码中
- 找到后作为常量写入 `following/timeline.py`

**选项 B**：probe 探测
- 向 X 的 GraphQL 端点发送请求，用候选 queryId 列表尝试
- 找到返回有效数据的那个
- 适合 queryId 频繁更换的场景

第一版实现用 **选项 A**，在代码注释里记录 queryId 来源，后续如果 X 更换了端点再升级为 probe。

### 3.3 核心函数签名

```python
def fetch_following_timeline(
    limit: int = 200,
    cookie_file: str | None = None,
    timeout: int = 30,
) -> list[NormalizedTweet]:
    """Fetch the X following timeline (people you follow).

    Args:
        limit: Maximum tweets to return (default 200, matching old shell config).
        cookie_file: Path to X cookie file. If None, uses ~/.signal-engine/x-cookies.json.
        timeout: HTTP timeout in seconds.

    Returns:
        List of NormalizedTweet, newest first.

    Raises:
        AuthError: cookie missing/invalid
        TransportError: network failure
        RateLimitError: HTTP 429
        SchemaError: X API response structure changed
        SourceUnavailableError: X server error (5xx)
    """
```

与 x-feed 的 `fetch_home_timeline` 完全对称，只是默认 limit 不同（100 vs 200）。

### 3.4 response parsing

和 `HomeTimeline` 的 parsing 逻辑几乎相同：
- 从 `data.home.home_timeline_urt.instructions` 取 `TimelineAddEntries`
- 遍历 entries，提取 `tweet_results.result`
- 解析 `core.user_results.result.legacy` 获取 author/text/engagement
- deduplicate by `rest_id`
- cursor pagination 支持多页

---

## 4. x-following lane 实现

### 4.1 lane collector 签名

```python
def collect_x_following(ctx: RunContext) -> RunResult:
    """Collect x-following signals via native X source.

    Config keys read:
        lanes["x-following"]["source"]["auth"]["cookie_file"]
        lanes["x-following"]["source"]["limit"]              (default: 200)
        lanes["x-following"]["source"]["timeout_seconds"]    (default: 30)
        lanes["x-following"]["enrichment"]                 (list of {handle, group, tags})
    """
```

### 4.2 enrichment 处理

enrichment 配置结构（保持与旧 shell 脚本兼容）：

```yaml
lanes:
  x-following:
    enrichment:
      - handle: AnthropicAI
        group: claude-core
        tags: []
```

在 collector 里，对每条 tweet 的 author handle 做 lookup：
- 命中的附加 `group` 和 `tags` 到 SignalRecord
- 未命中的 group 设为 `"uncategorized"`

### 4.3 SignalRecord 字段

```python
SignalRecord(
    lane="x-following",
    signal_type="post",              # 区别于 x-feed 的 "feed-exposure"
    source="x",
    entity_type="author",
    entity_id=handle,
    title=f"@{handle}",
    source_url=url,
    fetched_at=fetched_at,
    file_path=file_path,
    # x-following 特有
    session_id=session_id,
    handle=handle,
    post_id=post_id,
    created_at=created_at,
    position=position,
    text_preview=text[:120],
    likes=likes,
    retweets=retweets,
    replies=replies,
    views=views,
    group=group,                    # from enrichment
    tags=tags,                      # from enrichment
)
```

### 4.4 index.md 格式

与旧 shell 脚本生成的格式基本一致，确保历史可对比：

```markdown
---
lane: x-following
date: "2026-04-08"
generated_at: "2026-04-08T01:30:00+0800"
status: success
---

# x-following — 2026-04-08

## Run Summary

- Signals produced: 142
- Unique authors: 38

## Signals

| type | title | fetched_at | author | signal_link | source_url | hint |
| ...  | ...   | ...        | ...    | ...         | ...        | ...  |
```

---

## 5. 实现步骤

### Step 1：拆分 x-feed 现有 source

把 `sources/x/timeline.py` 里的 `fetch_home_timeline` 相关代码移到新目录结构：

```
sources/x/feed/timeline.py    ← 从原 timeline.py 移出
sources/x/following/timeline.py ← 新建（stub + HomeLatestTimeline）
```

同时创建：
```
sources/x/auth.py
sources/x/client.py
sources/x/errors.py
sources/x/models.py
```

这些是真正的 shared lib，从现有 timeline.py 里提取复用。

### Step 2：发现 HomeLatestTimeline queryId

从 xfetch 源码或 JS bundle 中提取 `HomeLatestTimeline` queryId，写入常量。

### Step 3：实现 fetch_following_timeline

在 `sources/x/following/timeline.py` 实现完整函数，包含：
- auth 加载
- httpx 请求（HTTP/1.1 transport）
- GraphQL 变量构造
- response parsing
- cursor pagination
- deduplication

### Step 4：实现 x-following lane collector

在 `lanes/` 新建 `x_following.py`：
- 读取配置（cookie_file / limit / timeout / enrichment）
- 调用 `fetch_following_timeline()`
- 生成 SignalRecord（含 enrichment group/tags）
- 写 signals / index.md / run.json

### Step 5：注册 lane

在 `lanes/registry.py` 添加 `"x-following"` 注册。

### Step 6：测试

- 单元测试：`test_x_following_collect.py`
- mock 测试：用 x-feed 的 fixture 格式生成 following 数据 fixture
- 真实 e2e 测试（需要 cookie 文件）

---

## 6. 待确认事项

### HomeLatestTimeline queryId

需要从 xfetch 源码中提取。xfetch 的 `TimelineMixin.getHomeLatestTimeline` 用了哪个 queryId 待确认。

**Action**：在 xfetch 的 compiled JS bundle 或 source 里搜索 `HomeLatestTimeline`。

---

## 7. 验收标准

1. `signals-engine collect --lane x-following --date 2026-04-08` 能完整运行
2. 生成 `signals/x-following/2026-04-08/index.md` 和 `run.json`
3. signals 数量和 engagement 数据与旧 shell 版本可比（允许有合理差异）
4. `signals-engine diagnose --lane x-following` 正常输出
5. 76 个 x-feed 相关测试全部仍然通过（无 regression）
6. x-following 自己新增的测试全部通过
7. 两条 lane 的 source 层完全独立，无相互引用
