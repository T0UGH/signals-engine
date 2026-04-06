"""Run context for Signal Engine."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunContext:
    """Immutable run context passed through the collect pipeline."""
    lane: str
    date: str
    data_dir: Path
    config: dict
    debug_log_path: Path | None = field(default=None)

    @property
    def signals_dir(self) -> Path:
        return self.data_dir / "signals" / self.lane / self.date / "signals"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "signals" / self.lane / "state"

    @property
    def index_path(self) -> Path:
        return self.data_dir / "signals" / self.lane / self.date / "index.md"

    @property
    def run_json_path(self) -> Path:
        return self.data_dir / "signals" / self.lane / self.date / "run.json"

    def ensure_dirs(self) -> None:
        self.signals_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
