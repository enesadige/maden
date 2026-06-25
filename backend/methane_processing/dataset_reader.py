from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from backend.methane_processing.core import PRIMARY_METHANE_COLUMNS, safe_float


TIME_COLUMNS = ["year", "month", "day", "hour", "minute", "second"]


def build_timestamp(row: dict[str, Any]) -> str:
    """
    OpenML methane CSV içindeki ayrı zaman kolonlarından ISO timestamp üretir.
    Eksik/bozuk değerlerde source_row tabanlı fallback kullanılabilir.
    """
    try:
        year = int(float(row.get("year", 1970)))
        month = int(float(row.get("month", 1)))
        day = int(float(row.get("day", 1)))
        hour = int(float(row.get("hour", 0)))
        minute = int(float(row.get("minute", 0)))
        second = int(float(row.get("second", 0)))
    except (TypeError, ValueError):
        return ""

    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"


def read_methane_samples(
    csv_path: Path,
    methane_columns: list[str] | None = None,
    max_rows: int = 200_000,
    target_steps: int = 90,
) -> list[dict[str, Any]]:
    """
    Büyük methane CSV dosyasını tamamen belleğe almadan örnek timeline üretir.

    Her target step için bir ham satır seçilir.
    Seçilen satırda MM263/MM264/MM256 değerleri korunur.
    """
    if methane_columns is None:
        methane_columns = PRIMARY_METHANE_COLUMNS

    if not csv_path.exists():
        raise FileNotFoundError(f"Methane CSV bulunamadı: {csv_path}")

    if max_rows <= 0:
        raise ValueError("max_rows pozitif olmalı.")

    if target_steps <= 0:
        raise ValueError("target_steps pozitif olmalı.")

    sample_interval = max(1, max_rows // target_steps)
    samples: list[dict[str, Any]] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)

        if not reader.fieldnames:
            raise ValueError("Methane CSV kolon başlığı okunamadı.")

        missing = [col for col in methane_columns if col not in reader.fieldnames]
        if missing:
            raise ValueError(f"Methane CSV içinde eksik kolonlar var: {missing}")

        for source_row, row in enumerate(reader):
            if source_row >= max_rows:
                break

            if source_row % sample_interval != 0:
                continue

            if len(samples) >= target_steps:
                break

            sample: dict[str, Any] = {
                "time_step": len(samples),
                "source_row": source_row,
                "timestamp": build_timestamp(row),
            }

            for column in methane_columns:
                value = safe_float(row.get(column), default=0.0)

                # Negatif metan değeri risk hesabında fiziksel olarak anlamlı değil.
                sample[column] = max(0.0, value)

            samples.append(sample)

    if not samples:
        raise RuntimeError("Methane CSV'den hiç sample üretilemedi.")

    return samples
