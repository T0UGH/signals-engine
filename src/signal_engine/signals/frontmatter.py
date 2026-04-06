"""Signal markdown frontmatter generation."""
import yaml
from ..core import SignalRecord


def build_frontmatter(record: SignalRecord) -> str:
    """Build YAML frontmatter from a SignalRecord.

    Lane-specific fields (handle, post_id, etc.) are included as-is.
    """
    # Collect all non-None fields for frontmatter
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

    # Add x-feed specific fields if present
    if record.handle:
        fields["handle"] = record.handle
    if record.post_id:
        fields["post_id"] = record.post_id
    if record.created_at:
        fields["created_at"] = record.created_at
    if record.position:
        fields["position"] = record.position

    return yaml.dump(fields, allow_unicode=True, sort_keys=False).rstrip()
