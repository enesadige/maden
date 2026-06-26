from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from django.conf import settings


class DataFileMissing(FileNotFoundError):
    pass


def data_root() -> Path:
    return Path(settings.MADENGUARD_DATA_ROOT)


def load_json(relative_path: str, default: Any | None = None) -> Any:
    path = data_root() / relative_path
    if not path.exists():
        if default is not None:
            return default
        raise DataFileMissing(f"Data file is missing: {path}")

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_first_json(relative_paths: list[str], default: Any | None = None) -> Any:
    for relative_path in relative_paths:
        path = data_root() / relative_path
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
    if default is not None:
        return default
    searched = ", ".join(str(data_root() / item) for item in relative_paths)
    raise DataFileMissing(f"Data file is missing. Searched: {searched}")


def available_files() -> list[str]:
    root = data_root()
    if not root.exists():
        return []
    return sorted(str(path.relative_to(root)) for path in root.rglob("*.json"))


def filter_time_step(records: list[dict[str, Any]], time_step: int | None = 0) -> list[dict[str, Any]]:
    if time_step is None:
        return records
    if not records or "time_step" not in records[0]:
        return records

    selected = [item for item in records if item.get("time_step") == time_step]
    if selected:
        return selected

    available = sorted({item.get("time_step") for item in records if item.get("time_step") is not None})
    if not available:
        return records

    fallback_step = available[0]
    return [item for item in records if item.get("time_step") == fallback_step]
