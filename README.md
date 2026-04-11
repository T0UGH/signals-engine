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

## v1 scope
- collect-only runtime
- signal markdown / index / state outputs
- thin run.json manifest
- first migration target: x-feed
