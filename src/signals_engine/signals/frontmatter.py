"""Signal markdown frontmatter generation."""
import yaml
from ..core import SignalRecord


def build_frontmatter(record: SignalRecord) -> str:
    """Build YAML frontmatter from a SignalRecord.

    Lane-specific fields (handle, post_id, etc.) are included as-is.
    x-feed Phase-1 fields (session_id, post_type, feed_context) are
    added for backward compatibility with the old shell implementation.
    """
    # Core fields
    fields = {
        "type": record.signal_type,
        "lane": record.lane,
        "source": record.source,
        "entity_type": record.entity_type,
        "entity_id": record.entity_id,
        "title": record.title,
        "url": record.source_url,
        "fetched_at": record.fetched_at,
    }

    # x-feed Phase-1 fields for backward compatibility with old shell
    if record.lane == "x-feed":
        if record.session_id:
            fields["session_id"] = record.session_id
        if record.handle:
            fields["handle"] = record.handle
        if record.post_id:
            fields["post_id"] = record.post_id
        if record.created_at:
            fields["created_at"] = record.created_at
        if record.position:
            fields["position"] = record.position
        # Phase-1 constants
        fields["post_type"] = "unknown"
        fields["feed_context"] = "unknown"
    else:
        # Non-x-feed lanes: include optional fields only if non-zero/empty
        if record.handle:
            fields["handle"] = record.handle
        if record.post_id:
            fields["post_id"] = record.post_id
        if record.created_at:
            fields["created_at"] = record.created_at
        if record.position:
            fields["position"] = record.position

    # x-following enrichment fields
    if record.lane == "x-following":
        if getattr(record, "group", ""):
            fields["group"] = record.group
        if getattr(record, "tags", None):
            fields["tags"] = record.tags

    if record.lane == "reddit-watch":
        if getattr(record, "group", ""):
            fields["group"] = record.group
        if getattr(record, "query", ""):
            fields["query"] = record.query

    if record.source == "polymarket":
        if getattr(record, "group", ""):
            fields["group"] = record.group
        if getattr(record, "query", ""):
            fields["query"] = record.query
        if getattr(record, "event_title", ""):
            fields["event_title"] = record.event_title
        if getattr(record, "primary_outcome", ""):
            fields["primary_outcome"] = record.primary_outcome
            fields["primary_probability"] = getattr(record, "primary_probability", 0.0)
        if getattr(record, "outcome_probabilities", None):
            fields["outcomes"] = record.outcome_probabilities
        if getattr(record, "volume_24h", 0.0):
            fields["volume_24h"] = record.volume_24h
        if getattr(record, "volume_30d", 0.0):
            fields["volume_30d"] = record.volume_30d
        if getattr(record, "liquidity", 0.0):
            fields["liquidity"] = record.liquidity
        if getattr(record, "price_movement", ""):
            fields["price_movement"] = record.price_movement
        if getattr(record, "end_date", ""):
            fields["end_date"] = record.end_date

    # GitHub repo-watch fields
    if record.source == "github" and record.signal_type == "release":
        if getattr(record, "post_id", ""):
            fields["version"] = record.post_id  # tag
        if getattr(record, "created_at", ""):
            fields["published_at"] = record.created_at
        if hasattr(record, "prerelease"):
            fields["prerelease"] = record.prerelease

    return yaml.dump(fields, allow_unicode=True, sort_keys=False).rstrip()
