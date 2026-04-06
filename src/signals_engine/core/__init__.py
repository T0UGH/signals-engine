"""Core module: models, context, paths, errors."""
from .models import RunStatus, SignalRecord, RunResult
from .context import RunContext
from .paths import signal_file_path, index_file_path, run_json_path, state_file_path
from .errors import (
    SignalEngineError,
    SourceError,
    ConfigError,
    RenderError,
    WriteError,
)

__all__ = [
    "RunStatus",
    "SignalRecord",
    "RunResult",
    "RunContext",
    "signal_file_path",
    "index_file_path",
    "run_json_path",
    "state_file_path",
    "SignalEngineError",
    "SourceError",
    "ConfigError",
    "RenderError",
    "WriteError",
]
