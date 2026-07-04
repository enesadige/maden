from __future__ import annotations

from pathlib import Path
from typing import Any
from copy import deepcopy
import json
import threading

from django.conf import settings


class DataFileMissing(FileNotFoundError):
    pass


_JSON_CACHE: dict[Path, tuple[int, int, Any]] = {}
_JSON_CACHE_LOCK = threading.Lock()


def data_root() -> Path:
    return Path(settings.MADENGUARD_DATA_ROOT)


def _load_json_file(path: Path) -> Any:
    stat = path.stat()
    cache_key = path.resolve()
    with _JSON_CACHE_LOCK:
        cached = _JSON_CACHE.get(cache_key)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return deepcopy(cached[2])

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    with _JSON_CACHE_LOCK:
        _JSON_CACHE[cache_key] = (stat.st_mtime_ns, stat.st_size, payload)
    return deepcopy(payload)


def load_json(relative_path: str, default: Any | None = None) -> Any:
    path = data_root() / relative_path
    if not path.exists():
        if default is not None:
            return default
        raise DataFileMissing(f"Data file is missing: {path}")
    return _load_json_file(path)


def load_first_json(relative_paths: list[str], default: Any | None = None) -> Any:
    for relative_path in relative_paths:
        path = data_root() / relative_path
        if path.exists():
            return _load_json_file(path)
    if default is not None:
        return default
    searched = ", ".join(str(data_root() / item) for item in relative_paths)
    raise DataFileMissing(f"Data file is missing. Searched: {searched}")


def available_files() -> list[str]:
    root = data_root()
    if not root.exists():
        return []
    return sorted(str(path.relative_to(root)) for path in root.rglob("*.json"))


def filter_time_step(
    records: list[dict[str, Any]],
    time_step: int | None = 0,
    fallback: str = "first",
) -> list[dict[str, Any]]:
    if time_step is None:
        return records
    if not records or "time_step" not in records[0]:
        return records

    selected = [item for item in records if item.get("time_step") == time_step]
    if selected:
        return selected

    if fallback == "none":
        return []

    available = sorted({item.get("time_step") for item in records if item.get("time_step") is not None})
    if not available:
        return records

    if fallback == "last_lte":
        previous_steps = [step for step in available if step <= time_step]
        fallback_step = previous_steps[-1] if previous_steps else available[0]
    elif fallback == "nearest":
        fallback_step = min(available, key=lambda step: abs(step - time_step))
    else:
        fallback_step = available[0]
    return [item for item in records if item.get("time_step") == fallback_step]


def available_time_steps(relative_path: str) -> list[int]:
    data = load_json(relative_path, default=[])
    records = data.get("records", []) if isinstance(data, dict) else data
    return sorted(
        {
            int(item["time_step"])
            for item in records
            if isinstance(item, dict) and item.get("time_step") is not None
        }
    )
