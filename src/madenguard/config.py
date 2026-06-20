from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "paths.json"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def project_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def ensure_project_dirs() -> None:
    for rel in [
        "config",
        "scripts",
        "src/madenguard",
        "processed/lidar_samples",
        "processed/features",
        "processed/timelines",
        "simulation_ready",
        "dashboards",
        "reports",
        "pipelines",
    ]:
        project_path(rel).mkdir(parents=True, exist_ok=True)


def configured_path(config: dict[str, Any], key: str) -> Path:
    value = config["paths"][key]
    return Path(value)

