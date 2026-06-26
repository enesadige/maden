from __future__ import annotations

import re
from typing import Any


SEGMENT_ID_KEYS = {
    "segment_id",
    "mapped_segment_id",
    "current_segment",
    "worker_segment",
    "blocked_segment",
    "source",
    "target",
    "exit_segment",
}


def normalize_segment_id(value: Any) -> Any:
    """Normalize SEG_047, S47 or 47 to the canonical S047 format."""
    if value is None:
        return None

    text = str(value).strip()
    match = re.search(r"(\d+)$", text)
    if not match:
        return text

    return f"S{int(match.group(1)):03d}"


def normalize_risk_level(value: Any) -> Any:
    if value is None:
        return None
    return str(value).strip().lower()


def normalize_record_ids(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    for key in SEGMENT_ID_KEYS:
        if key in normalized:
            normalized[key] = normalize_segment_id(normalized[key])
    if "risk_level" in normalized:
        normalized["risk_level"] = normalize_risk_level(normalized["risk_level"])
    return normalized
