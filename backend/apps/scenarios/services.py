from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids
from apps.common.json_store import load_json


def get_collapse_result() -> dict[str, Any]:
    result = load_json("scenarios/collapse_result.json", default={})
    normalized = normalize_record_ids(result)
    event = normalized.get("event")
    if isinstance(event, dict):
        normalized["event"] = normalize_record_ids(event)
    return normalized
