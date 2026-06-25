from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

BACKEND_SAMPLE_ROOT = REPO_ROOT / "backend" / "data_processed" / "sample"
PROCESSED_TIMELINES_DIR = REPO_ROOT / "processed" / "timelines"
SIMULATION_READY_DIR = REPO_ROOT / "simulation_ready"
REPORTS_DIR = REPO_ROOT / "reports"

HAKI_SEGMENTS_PATH = BACKEND_SAMPLE_ROOT / "haki_lidar" / "segments" / "map_segments.json"
HAKI_GEOMETRY_RISK_PATH = BACKEND_SAMPLE_ROOT / "haki_lidar" / "risk" / "geometry_risk.json"

GAS_SENSORS_OUTPUT_PATH = BACKEND_SAMPLE_ROOT / "sensors" / "gas_sensors.json"
GAS_SENSOR_MAPPING_OUTPUT_PATH = BACKEND_SAMPLE_ROOT / "sensors" / "gas_sensor_mapping.json"
METHANE_PIPELINE_SUMMARY_PATH = BACKEND_SAMPLE_ROOT / "sensors" / "methane_pipeline_summary.json"

ENVIRONMENTAL_RISK_OUTPUT_PATH = BACKEND_SAMPLE_ROOT / "risk" / "environmental_risk.json"
RISK_SEGMENTS_OUTPUT_PATH = BACKEND_SAMPLE_ROOT / "risk" / "risk_segments.json"

PROCESSED_GAS_TIMELINE_PATH = PROCESSED_TIMELINES_DIR / "gas_sensors_timeline.json"
SIMULATION_READY_GAS_TIMELINE_PATH = SIMULATION_READY_DIR / "gas_sensors_timeline.json"

GAS_RISK_REPORT_PATH = REPORTS_DIR / "gas_risk_report.md"

PRIMARY_METHANE_COLUMNS = ["MM263", "MM264", "MM256"]

DEFAULT_MAX_METHANE_ROWS = 200_000
DEFAULT_GAS_TIMELINE_STEPS = 90


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_output_dirs() -> None:
    for path in [
        BACKEND_SAMPLE_ROOT / "sensors",
        BACKEND_SAMPLE_ROOT / "risk",
        PROCESSED_TIMELINES_DIR,
        SIMULATION_READY_DIR,
        REPORTS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"JSON dosyası bulunamadı: {path}")

    text = path.read_text(encoding="utf-8").strip()

    if not text:
        if default is not None:
            return default
        raise ValueError(f"JSON dosyası boş: {path}")

    return json.loads(text)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_project_config() -> dict[str, Any]:
    config_path = REPO_ROOT / "config" / "paths.json"
    return read_json(config_path, default={})


def methane_csv_path(config: dict[str, Any]) -> Path:
    """
    Methane CSV yolunu güvenli şekilde çözer.

    Öncelik:
    1. MADENGUARD_METHANE_CSV environment variable
    2. config/paths.json içindeki paths.methane_csv

    Böylece kişisel local path config dosyasına commit edilmez.
    """
    env_path = os.environ.get("MADENGUARD_METHANE_CSV")
    if env_path:
        return Path(env_path).expanduser()

    configured = config.get("paths", {}).get("methane_csv")
    if configured:
        return Path(configured).expanduser()

    raise ValueError(
        "Methane CSV yolu bulunamadı. "
        "MADENGUARD_METHANE_CSV environment variable tanımla."
    )


def runtime_int(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get("runtime", {}).get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_segment_id(value: Any) -> str:
    """
    SEG_047, S47 veya 47 değerlerini S047 formatına çevirir.
    """
    text = str(value).strip()
    match = re.search(r"(\d+)$", text)
    if not match:
        return text
    return f"S{int(match.group(1)):03d}"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    if result != result:
        return default

    if result in (float("inf"), float("-inf")):
        return default

    return result


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def risk_status(score: float) -> str:
    """
    Backend gas sensor status alanı için ortak seviye üretir.
    """
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "normal"


def risk_level(score: float) -> str:
    """
    Risk dosyası için aynı seviye adlandırmasını kullanıyoruz.
    """
    return risk_status(score)
