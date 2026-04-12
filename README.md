# Signals Engine

Python collect CLI for signal-oriented collection lanes.

## Install

```bash
pip install signals-engine
signals-engine --help
python3.11 -m signals_engine.cli --help
```

## Usage

```bash
signals-engine collect --lane x-feed --date 2026-04-06
signals-engine diagnose --lane x-feed
signals-engine collect --lane reddit-watch --date 2026-04-11 --config ~/.signal-engine/config/lanes.yaml
```

## X auth setup

`x-feed` and `x-following` now prefer `browser-session` auth. Start a dedicated Chrome profile with CDP enabled, log into X once in that profile, then point the lane config at the running browser session.

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=$HOME/.signal-engine/chrome-profile
```

```yaml
lanes:
  x-feed:
    source:
      auth:
        mode: browser-session
        cdp_url: http://127.0.0.1:9222
        target_url: https://x.com
      limit: 100
      timeout_seconds: 30

  x-following:
    source:
      auth:
        mode: browser-session
        cdp_url: http://127.0.0.1:9222
      limit: 200
      timeout_seconds: 30
```

Legacy `cookie-file` auth is still supported when explicitly selected:

```yaml
lanes:
  x-feed:
    source:
      auth:
        mode: cookie-file
        cookie_file: ~/.signal-engine/x-cookies.json
```

In `browser-session` mode, Signal Engine does not export or manage X session cookies. It connects to the live Chrome session over CDP, extracts `ct0` from the page context, and performs GraphQL requests inside the browser with `credentials: 'include'`.

## Supported lanes

- x-feed
- x-following
- github-watch
- claude-code-watch
- openclaw-watch
- codex-watch
- reddit-watch
- github-trending-weekly
- product-hunt-watch
- polymarket-watch

### Example reddit-watch config

`reddit-watch` is scoped to **AI coding / agent workflow discussions**. It is not intended to pull generic Reddit news or broad tech chatter.

```yaml
lanes:
  reddit-watch:
    enabled: true
    queries:
      - Claude Code workflows
      - Codex agent
      - OpenClaw
      - AI coding agents
    lookback_days: 30
    max_threads: 5
    max_per_query: 3
    subreddits:
      - ClaudeAI
      - LocalLLaMA
      - PromptEngineering
      - artificial
```

### Example polymarket-watch config

`polymarket-watch` is a Polymarket-backed **prediction-market lane** scoped to market expectation / probability signals around AI model race, coding AI, benchmarks, and company expectations. It is not a workflow-detail or full-text research lane.

```yaml
lanes:
  polymarket-watch:
    source:
      max_pages: 2
      timeout: 15
    max_per_query: 3
    queries:
      - topic: model-race
        query: best AI model
      - topic: coding-ai
        query: coding AI
      - topic: benchmark
        query: AI benchmark
      - topic: company-expectation
        query: OpenAI Anthropic Google
```

## v1 scope
- collect-only runtime
- signal markdown / index / state outputs
- thin run.json manifest
- first migration target: x-feed
