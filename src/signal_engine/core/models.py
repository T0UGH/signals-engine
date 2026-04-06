"""Core data models for Signal Engine."""
from dataclasses import dataclass, field
from enum import Enum


class RunStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    EMPTY = "empty"


@dataclass
class SignalRecord:
    # Core fixed fields (align with v1 spec)
    lane: str
    signal_type: str
    source: str
    entity_type: str
    entity_id: str
    title: str
    source_url: str
    fetched_at: str
    file_path: str | None = None

    # x-feed explicit internal fields
    handle: str = ""
    post_id: str = ""
    created_at: str = ""
    position: int = 0
    text_preview: str = ""
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    views: int = 0


@dataclass
class RunResult:
    lane: str
    date: str
    status: RunStatus
    started_at: str
    finished_at: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    signal_records: list[SignalRecord] = field(default_factory=list)
    repos_checked: int = 0
    signals_written: int = 0
    signal_types_count: dict[str, int] = field(default_factory=dict)
    index_file: str | None = None
