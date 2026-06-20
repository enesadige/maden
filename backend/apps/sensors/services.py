from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids
from apps.common.json_store import filter_time_step, load_json


def get_gas_sensors(time_step: int | None = 0) -> list[dict[str, Any]]:
    records = load_json("sensors/gas_sensors.json", default=[])
    selected = filter_time_step(records, time_step)
    return [normalize_record_ids(item) for item in selected]
