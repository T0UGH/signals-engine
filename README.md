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
```

## v1 scope
- collect-only runtime
- signal markdown / index / state outputs
- thin run.json manifest
- first migration target: x-feed
