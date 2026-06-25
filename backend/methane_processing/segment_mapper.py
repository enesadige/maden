from __future__ import annotations

from typing import Any

from backend.methane_processing.core import (
    HAKI_GEOMETRY_RISK_PATH,
    HAKI_SEGMENTS_PATH,
    PRIMARY_METHANE_COLUMNS,
    REPO_ROOT,
    normalize_segment_id,
    read_json,
    safe_float,
)


def load_haki_segments() -> list[dict[str, Any]]:
    payload = read_json(HAKI_SEGMENTS_PATH)

    if not isinstance(payload, list):
        raise ValueError("Haki map_segments.json liste formatında olmalı.")

    segments = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        segment_id = normalize_segment_id(item.get("segment_id"))
        if not segment_id:
            continue

        normalized = dict(item)
        normalized["segment_id"] = segment_id
        segments.append(normalized)

    if not segments:
        raise RuntimeError("Haki segment dosyasından segment okunamadı.")

    return segments


def load_geometry_risk_by_segment() -> dict[str, dict[str, Any]]:
    payload = read_json(HAKI_GEOMETRY_RISK_PATH, default=[])

    if not isinstance(payload, list):
        return {}

    result: dict[str, dict[str, Any]] = {}

    for item in payload:
        if not isinstance(item, dict):
            continue

        segment_id = normalize_segment_id(item.get("segment_id"))
        if not segment_id:
            continue

        result[segment_id] = item

    return result


def load_legacy_fusion_segment_ids() -> set[str]:
    """
    Eski simulation/fusion pipeline processed/features/segments.json içindeki
    SEG_XXX segmentleriyle çalışıyor.

    Haki segmentleri S001+ devam edebilir; ancak mevcut fusion testinin
    tüm gaz sensörlerini yakalaması için ortak segmentleri tercih ederiz.
    """
    path = REPO_ROOT / "processed" / "features" / "segments.json"
    payload = read_json(path, default=[])

    if not isinstance(payload, list):
        return set()

    result: set[str] = set()

    for item in payload:
        if not isinstance(item, dict):
            continue

        segment_id = item.get("segment_id")
        if segment_id:
            result.add(normalize_segment_id(segment_id))

    return result


def segment_selection_score(
    segment: dict[str, Any],
    geometry_risk_lookup: dict[str, dict[str, Any]],
) -> float:
    """
    Gaz sensörünü yerleştirmek için segment öncelik skoru üretir.

    Amaç:
    Sensörü dijital ikizin riskli / kritik / bağlantı rolü yüksek bölgelerine
    simülasyon amaçlı yerleştirmek.
    """
    segment_id = segment["segment_id"]
    geometry = geometry_risk_lookup.get(segment_id, {})

    geometry_risk = safe_float(
        geometry.get("geometry_risk", segment.get("geometry_risk", 0.0))
    )

    connected_count = len(segment.get("connected_segments") or [])
    segment_type = str(segment.get("type", "")).lower()
    role = str(segment.get("role", "")).lower()

    score = geometry_risk

    if segment.get("is_risky"):
        score += 15

    if "junction" in segment_type:
        score += 8

    if "main" in role:
        score += 5

    if connected_count >= 3:
        score += 5

    if connected_count <= 1:
        score += 3

    return score


def build_sensor_mapping(
    methane_columns: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    MM263/MM264/MM256 kanallarını Haki segmentlerine bağlar.

    Bu mapping gerçek sensör koordinatı değil, demo/simülasyon yerleşimidir.
    """
    if methane_columns is None:
        methane_columns = PRIMARY_METHANE_COLUMNS

    segments = load_haki_segments()
    geometry_risk_lookup = load_geometry_risk_by_segment()

    legacy_fusion_ids = load_legacy_fusion_segment_ids()
    if legacy_fusion_ids:
        candidate_segments = [
            segment for segment in segments
            if segment["segment_id"] in legacy_fusion_ids
        ]
    else:
        candidate_segments = segments

    if len(candidate_segments) < len(methane_columns):
        candidate_segments = segments

    ranked_segments = sorted(
        candidate_segments,
        key=lambda item: segment_selection_score(item, geometry_risk_lookup),
        reverse=True,
    )

    if len(ranked_segments) < len(methane_columns):
        raise RuntimeError("Sensör yerleşimi için yeterli segment bulunamadı.")

    mapping: dict[str, dict[str, Any]] = {}

    for index, source_column in enumerate(methane_columns):
        segment = ranked_segments[index]
        segment_id = segment["segment_id"]
        geometry = geometry_risk_lookup.get(segment_id, {})

        mapping[source_column] = {
            "sensor_id": f"GAS_SENSOR_{index + 1:02d}",
            "segment_id": segment_id,
            "source_column": source_column,
            "placement_reason": "haki_geometry_risk_or_junction_priority",
            "segment_type": segment.get("type"),
            "segment_role": segment.get("role"),
            "geometry_risk": safe_float(
                geometry.get("geometry_risk", segment.get("geometry_risk", 0.0))
            ),
        }

    return mapping


def valid_segment_ids() -> set[str]:
    return {item["segment_id"] for item in load_haki_segments()}
