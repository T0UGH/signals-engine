# x-feed Native Runtime Debug Verification

**Date:** 2026-04-06
**Run Directory:** `/tmp/signal-engine-debug/2026-04-06-run-001`

---

## 1. CLI 是否真正执行

**结论：✅ 是**

证据：
```
$ python -m signal_engine.cli diagnose --lane x-feed --data-dir /tmp/signal-engine-debug/2026-04-06-run-001
[debug] [diagnose] START lane=x-feed data_dir=/tmp/signal-engine-debug/2026-04-06-run-001
[debug] [diagnose] END exit_code=2
```

修复前：无 `if __name__ == "__main__"` 块，`python -m signal_engine.cli` 只导入模块不调用 `main()`。
修复后：`cli.py` 底部添加 `if __name__ == "__main__": raise SystemExit(main())`，CLI 真正执行。

---

## 2. collect 是否真正开始

**结论：✅ 是**

证据：
```
[debug] [collect] START lane=x-feed date=2026-04-06 data_dir=/tmp/signal-engine-debug/2026-04-06-run-001
[debug] [x-feed] FETCH START cookie=... limit=10 timeout=30
```

CLI 调用链完整：`main()` → `collect.run(args)` → `collect_lane(ctx)` → `collect_x_feed(ctx)` → `fetch_home_timeline()` → auth 校验。

---

## 3. 本次是否真实生成新产物

**结论：✅ 是**

在全新临时目录 `/tmp/signal-engine-debug/2026-04-06-run-001/` 下生成了：

```
signals/x-feed/2026-04-06/index.md    ✅
signals/x-feed/2026-04-06/run.json   ✅
debug.log                              ✅
```

---

## 4. index.md 是否生成

**结论：✅ 是**

`/tmp/signal-engine-debug/2026-04-06-run-001/signals/x-feed/2026-04-06/index.md`：
```yaml
lane: x-feed
date: "2026-04-06"
session_id: feed-2026-04-06-faa65e
status: empty
```

---

## 5. run.json 是否生成

**结论：✅ 是**

`/tmp/signal-engine-debug/2026-04-06-run-001/signals/x-feed/2026-04-06/run.json`：
```json
{
  "lane": "x-feed",
  "date": "2026-04-06",
  "status": "empty",
  "session_id": "feed-2026-04-06-faa65e",
  "errors": ["source fetch failed: Cookie file not found: /Users/haha/.signal-engine/x-cookies.json"]
}
```

`run.json` 正确反映 `EMPTY` 状态（fetch 失败，但不等于 FAILED）。

---

## 6. 卡在哪一步

**卡在：Auth 校验（Cookie 文件不存在）**

```
[debug] [x-feed] FETCH ERROR: Cookie file not found: /Users/haha/.signal-engine/x-cookies.json
```

`load_auth()` 正确检测到 cookie 文件不存在，抛出 `AuthError`，被 `collect_x_feed` 捕获并转化为 `EMPTY` 状态。

**根本原因：** 指定的 cookie 文件路径 `/Users/haha/.signal-engine/x-cookies.json` 在这台机器上不存在（目录存在但为空）。

**解决：** 需要导出 X.com cookies 到该路径，或在 `lanes.yaml` 中配置正确的 `source.auth.cookie_file` 路径。

---

## 7. debug.log 内容

```
[debug] [diagnose] START lane=x-feed data_dir=/tmp/signal-engine-debug/2026-04-06-run-001
[debug] [diagnose] END exit_code=2
[debug] [collect] START lane=x-feed date=2026-04-06 data_dir=/tmp/signal-engine-debug/2026-04-06-run-001
[debug] [x-feed] FETCH START cookie=/Users/haha/.signal-engine/x-cookies.json limit=10 timeout=30
[debug] [x-feed] FETCH ERROR: Cookie file not found: /Users/haha/.signal-engine/x-cookies.json
[debug] [collect] END status=empty signals=0 session=feed-2026-04-06-faa65e
```

日志层级清晰，能直接定位失败点（auth → cookie file missing）。

---

## 总结

| 检查项 | 结论 |
|--------|------|
| CLI 真正执行 `main()` | ✅ |
| collect 真正开始执行 | ✅ |
| `index.md` 生成于临时目录 | ✅ |
| `run.json` 生成于临时目录 | ✅ |
| `debug.log` 生成于临时目录 | ✅ |
| 失败定位于 auth 层（cookie missing） | ✅ |

**整体判断：CLI 闭环已验证。剩余问题是 cookie 文件未配置，与 runtime 无关。**

---

## 修改的文件

- `src/signal_engine/cli.py` — 添加 `if __name__ == "__main__": raise SystemExit(main())`
- `src/signal_engine/core/context.py` — 添加 `debug_log_path: Path | None` 字段
- `src/signal_engine/commands/collect.py` — 添加 `--debug-log` 参数 + `debug_log()` 调用
- `src/signal_engine/commands/diagnose.py` — 添加 `--debug-log` 参数 + `debug_log()` 调用
- `src/signal_engine/lanes/x_feed.py` — 添加关键节点的 `debug_log()` 调用
- `src/signal_engine/core/debuglog.py` — 新建极薄日志辅助模块
- `tests/test_cli_entrypoint.py` — 新建 CLI 入口测试
- `tests/test_runtime_debug_logging.py` — 新建日志测试
