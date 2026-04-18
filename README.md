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
signals-engine collect --lane hacker-news-watch --date 2026-04-18 --config ~/.signal-engine/config/lanes.yaml
signals-engine collect --lane hacker-news-search-watch --date 2026-04-18 --config ~/.signal-engine/config/lanes.yaml
signals-engine collect --lane weather-watch --date 2026-04-18 --config ~/.signal-engine/config/lanes.yaml
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
- hacker-news-watch
- hacker-news-search-watch
- github-trending-weekly
- product-hunt-watch
- polymarket-watch
- weather-watch

### Example hacker-news-watch config

`hacker-news-watch` collects raw Hacker News discussion material from the official Firebase API. It stores the HN discussion URL as the canonical source and keeps the external article URL separately when one exists.

```yaml
lanes:
  hacker-news-watch:
    enabled: true
    story_list: top
    max_stories: 10
    fetch_top_comments: true
    max_top_comments: 3
```

### Example hacker-news-search-watch config

`hacker-news-search-watch` is a discovery lane. It uses Algolia HN Search to find query-matched story hits, deduplicates them by HN story id, and then hydrates canonical story details from the official Firebase API before writing raw discussion corpus signals.

```yaml
lanes:
  hacker-news-search-watch:
    enabled: true
    queries:
      - agent workflow
      - terminal coding agent
      - AI benchmark
    max_hits_per_query: 5
    fetch_top_comments: true
    max_top_comments: 3
```

### Example reddit-watch config

`reddit-watch` is scoped to **AI coding / agent workflow discussions**. It is not intended to pull generic Reddit news or broad tech chatter.
Set `fetch_top_comments: false` to reduce Reddit request pressure and lower the chance that top-comment lookups amplify rate-limit (`429`) responses.

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
    fetch_top_comments: false
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

### Example weather-watch config

`weather-watch` uses the keyless Open-Meteo forecast API to write one daily weather signal for the report date. The default config works for Beijing Haidian with no secrets required.

```yaml
lanes:
  weather-watch:
    latitude: 39.9593
    longitude: 116.2981
    location_name: 北京·海淀
    timezone: Asia/Shanghai
```

## v1 scope
- collect-only runtime
- signal markdown / index / state outputs
- thin run.json manifest
- first migration target: x-feed
