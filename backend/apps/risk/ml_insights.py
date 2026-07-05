from __future__ import annotations

import csv
from statistics import median
from typing import Any

from django.conf import settings

from apps.common.ids import normalize_segment_id


FEATURE_WEIGHTS = {
    "geometry_risk": 0.25,
    "environmental_risk": 0.30,
    "worker_exposure_risk": 0.18,
    "tracking_risk_score": 0.10,
    "worker_behavior_anomaly_score": 0.12,
    "behavior_event_count": 0.05,
}

FEATURE_LABELS = {
    "geometry_risk": "geometri normal dışı",
    "environmental_risk": "çevresel/gaz normal dışı",
    "worker_exposure_risk": "işçi maruziyeti yüksek",
    "tracking_risk_score": "konum takibi güvensiz",
    "worker_behavior_anomaly_score": "davranış anomalisi",
    "behavior_event_count": "anomali olay yoğunluğu",
}

GEOMETRY_MODEL_FEATURES = {
    "geometry_risk": 0.10,
    "narrow_passage_risk": 0.11,
    "exit_distance_risk": 0.08,
    "single_connection_risk": 0.08,
    "limited_alternative_route_risk": 0.08,
    "critical_passage_risk": 0.10,
    "sparse_geometry_risk": 0.09,
    "degree": 0.06,
    "length_m": 0.06,
    "width_m": 0.06,
    "height_m": 0.06,
    "point_density": 0.06,
    "point_count": 0.08,
    "bbox_height_z": 0.08,
    "width_proxy": 0.10,
    "height_proxy": 0.08,
    "ceiling_roughness": 0.12,
    "narrowness_score": 0.16,
    "low_ceiling_score": 0.12,
    "ceiling_roughness_score": 0.12,
    "geometry_change_score": 0.14,
}

GEOMETRY_FEATURE_LABELS = {
    "geometry_risk": "geometri risk skoru yüksek",
    "narrow_passage_risk": "dar geçit riski yüksek",
    "exit_distance_risk": "çıkışa uzaklık riski yüksek",
    "single_connection_risk": "tek bağlantılı segment riski",
    "limited_alternative_route_risk": "alternatif rota kısıtlı",
    "critical_passage_risk": "kritik geçiş segmenti",
    "sparse_geometry_risk": "seyrek nokta yoğunluğu",
    "degree": "bağlantı sayısı olağan dışı",
    "length_m": "segment uzunluğu dağılımdan sapıyor",
    "width_m": "segment genişliği dağılımdan sapıyor",
    "height_m": "segment yüksekliği dağılımdan sapıyor",
    "point_density": "nokta yoğunluğu dağılımdan sapıyor",
    "point_count": "nokta sayısı segment dağılımından sapıyor",
    "bbox_height_z": "yükseklik aralığı olağan dışı",
    "width_proxy": "geçit genişliği dağılımdan sapıyor",
    "height_proxy": "tavan yüksekliği dağılımdan sapıyor",
    "ceiling_roughness": "tavan pürüzlülüğü olağan dışı",
    "narrowness_score": "dar geçit anomalisi",
    "low_ceiling_score": "düşük tavan anomalisi",
    "ceiling_roughness_score": "tavan yüzeyi düzensizliği",
    "geometry_change_score": "geometri değişim skoru yüksek",
}

WORKER_MODEL_WEIGHTS = {
    "behavior_anomaly_score": 0.34,
    "critical_behavior_event_count": 0.20,
    "behavior_event_count": 0.16,
    "worker_exposure_risk": 0.12,
    "tracking_risk_score": 0.18,
}

WORKER_FEATURE_LABELS = {
    "behavior_anomaly_score": "worker davranış anomalisi yüksek",
    "critical_behavior_event_count": "kritik UWB davranış olayı var",
    "behavior_event_count": "davranış olayı yoğunluğu yüksek",
    "worker_exposure_risk": "segmentte worker maruziyeti var",
    "tracking_risk_score": "konum takip riski yüksek",
}


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _robust_feature_stats(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for feature in FEATURE_WEIGHTS:
        values = [_as_float(record.get(feature)) for record in records]
        if not values:
            stats[feature] = {"median": 0.0, "mad": 1.0}
            continue
        center = median(values)
        deviations = [abs(value - center) for value in values]
        mad = median(deviations) or 1.0
        stats[feature] = {"median": center, "mad": mad}
    return stats


def _feature_score(value: float, center: float, mad: float) -> tuple[float, float]:
    robust_z = abs(value - center) / (1.4826 * mad)
    score = min(100.0, robust_z / 3.0 * 100.0)
    return round(score, 3), round(robust_z, 3)


def _level(score: float) -> str:
    if score >= 75:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _repo_root():
    return settings.PROJECT_ROOT


def _read_json_features() -> list[dict[str, Any]]:
    path = _repo_root() / "processed" / "features" / "lidar_geometry_features.json"
    if not path.exists():
        return []
    try:
        import json

        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def _read_csv_features() -> list[dict[str, Any]]:
    path = _repo_root() / "processed" / "features" / "lidar_geometry_features.csv"
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def _load_lidar_geometry_features() -> dict[str, dict[str, Any]]:
    records = _read_json_features() or _read_csv_features()
    normalized: dict[str, dict[str, Any]] = {}
    for item in records:
        segment_id = normalize_segment_id(item.get("segment_id"))
        if not segment_id:
            continue
        normalized[segment_id] = item
    return normalized


def _geometry_feature_record(record: dict[str, Any], processed_features: dict[str, dict[str, Any]]) -> dict[str, Any]:
    segment_id = record.get("segment_id")
    feature_record = dict(processed_features.get(segment_id, {}))
    feature_record["segment_id"] = segment_id
    feature_record["geometry_risk"] = record.get("geometry_risk", feature_record.get("lidar_geometry_risk", 0.0))
    for key, value in (record.get("geometry_metrics") or {}).items():
        feature_record[key] = value
    for key, value in (record.get("geometry_components") or {}).items():
        feature_record[key] = value
    return feature_record


def _numeric_feature_stats(
    records: list[dict[str, Any]],
    features: dict[str, float],
) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for feature in features:
        values = [_as_float(record.get(feature)) for record in records if record.get(feature) not in (None, "")]
        if not values:
            stats[feature] = {"median": 0.0, "mad": 1.0}
            continue
        center = median(values)
        deviations = [abs(value - center) for value in values]
        mad = median(deviations) or 1.0
        stats[feature] = {"median": center, "mad": mad}
    return stats


def _feature_rankings(
    record: dict[str, Any],
    stats: dict[str, dict[str, float]],
    weights: dict[str, float],
) -> tuple[float, list[tuple[str, dict[str, float]]]]:
    weighted_total = 0.0
    feature_scores: dict[str, dict[str, float]] = {}
    weight_total = sum(weights.values()) or 1.0
    for feature, weight in weights.items():
        value = _as_float(record.get(feature))
        baseline = stats.get(feature, {"median": 0.0, "mad": 1.0})
        score, robust_z = _feature_score(value, baseline["median"], baseline["mad"])
        feature_scores[feature] = {
            "value": round(value, 3),
            "score": score,
            "robust_z": robust_z,
            "baseline": round(baseline["median"], 3),
        }
        weighted_total += score * (weight / weight_total)
    ranked = sorted(
        feature_scores.items(),
        key=lambda item: (item[1]["score"], item[1]["robust_z"]),
        reverse=True,
    )
    return round(min(100.0, weighted_total), 3), ranked


def _geometry_model(
    record: dict[str, Any],
    geometry_feature_records: dict[str, dict[str, Any]],
    geometry_stats: dict[str, dict[str, float]],
) -> dict[str, Any]:
    feature_record = geometry_feature_records.get(record.get("segment_id"))
    if not feature_record:
        fallback_score = _as_float(record.get("geometry_risk"))
        return {
            "model_type": "lidar_geometry_anomaly",
            "method": "fallback_geometry_risk",
            "feature_source": "geometry_risk.json",
            "score": round(fallback_score, 3),
            "level": _level(fallback_score),
            "reasons": (record.get("active_reasons") or [])[:2] or ["LiDAR geometri risk skoru kullanıldı"],
            "top_features": [],
        }

    score, ranked = _feature_rankings(feature_record, geometry_stats, GEOMETRY_MODEL_FEATURES)
    domain_risk = _as_float(feature_record.get("geometry_risk")) or _as_float(feature_record.get("lidar_geometry_risk"))
    combined = round(min(100.0, (score * 0.72) + (domain_risk * 0.28)), 3)
    reasons = [
        GEOMETRY_FEATURE_LABELS.get(feature, feature)
        for feature, detail in ranked
        if detail["score"] >= 30.0
    ][:3]
    if not reasons:
        reasons = ["segment geometri dağılımı içinde olağan"]
    return {
        "model_type": "lidar_geometry_anomaly",
        "method": "robust_mad_over_haki_geometry_metrics",
        "feature_source": "geometry_risk metrics/components + processed lidar features when available",
        "score": combined,
        "level": _level(combined),
        "reasons": reasons,
        "top_features": ranked[:4],
        "domain_geometry_risk": round(domain_risk, 3),
    }


def _worker_behavior_model(record: dict[str, Any], worker_stats: dict[str, dict[str, float]]) -> dict[str, Any]:
    score, ranked = _feature_rankings(record, worker_stats, WORKER_MODEL_WEIGHTS)
    direct_score = _as_float(record.get("worker_behavior_anomaly_score"))
    combined = round(min(100.0, max(score, direct_score)), 3)
    event_types = record.get("behavior_anomaly_event_types") or []
    reasons = [
        WORKER_FEATURE_LABELS.get(feature, feature)
        for feature, detail in ranked
        if detail["score"] >= 25.0 and _as_float(detail["value"]) > 0
    ][:3]
    if event_types:
        reasons.extend([f"UWB event: {event_type}" for event_type in event_types[:2]])
    if not reasons:
        reasons = ["worker davranışı bu segmentte olağan"]
    return {
        "model_type": "worker_behavior_anomaly",
        "method": "robust_mad_over_worker_timeline_and_uwb_events",
        "feature_source": "worker timeline + behavior_anomaly_events",
        "score": combined,
        "level": _level(combined),
        "reasons": reasons[:4],
        "top_features": ranked[:4],
        "event_types": event_types,
        "worker_ids": record.get("behavior_anomaly_worker_ids") or record.get("active_worker_ids") or [],
    }


def _environmental_ai_signal(record: dict[str, Any]) -> dict[str, Any]:
    risk = _as_float(record.get("environmental_risk"))
    anomaly = _as_float(record.get("environmental_component_scores", {}).get("methane_risk"))
    weighted = _as_float(record.get("weighted_multi_sensor_risk"))
    score = round(max(risk, anomaly, weighted), 3)
    reasons = list(record.get("environmental_risk_reason") or [])
    if risk > 0 and not reasons:
        reasons.append("çevresel/gaz risk sinyali mevcut")
    if not reasons:
        reasons.append("çevresel sinyal olağan")
    return {
        "model_type": "environmental_ai_signal",
        "method": "existing_multisensor_risk_signal_no_new_training",
        "feature_source": "environmental_risk.json",
        "score": score,
        "level": _level(score),
        "reasons": reasons[:4],
        "raw_methane_risk": round(risk, 3),
        "weighted_multi_sensor_risk": round(weighted, 3),
    }


def annotate_segment_ai_insights(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach explainable AI/ML anomaly layers without changing final risk.

    This intentionally avoids weak raw-data claims. The LiDAR model uses the
    existing geometry feature table, the worker model uses timeline/UWB anomaly
    signals, and environmental AI stays a signal until raw methane data is
    available for a real gas model.
    """
    if not records:
        return records

    stats = _robust_feature_stats(records)
    processed_geometry_features = _load_lidar_geometry_features()
    geometry_feature_records = {
        record.get("segment_id"): _geometry_feature_record(record, processed_geometry_features)
        for record in records
        if record.get("segment_id")
    }
    geometry_stats = _numeric_feature_stats(list(geometry_feature_records.values()), GEOMETRY_MODEL_FEATURES)
    worker_stats = _numeric_feature_stats(records, WORKER_MODEL_WEIGHTS)
    model_info = {
        "model_type": "explainable_hybrid_ai_anomaly_fusion",
        "method": "lidar_geometry_model + worker_behavior_model + environmental_signal + robust_segment_distribution",
        "training_scope": "current_segment_distribution",
        "trained_on_segments": len(records),
        "feature_weights": {
            "distribution_model": 0.25,
            "lidar_geometry_model": 0.35,
            "worker_behavior_model": 0.25,
            "environmental_signal": 0.15,
        },
        "black_box": False,
    }

    for record in records:
        feature_scores: dict[str, dict[str, float]] = {}
        weighted_total = 0.0
        for feature, weight in FEATURE_WEIGHTS.items():
            value = _as_float(record.get(feature))
            score, robust_z = _feature_score(value, stats[feature]["median"], stats[feature]["mad"])
            feature_scores[feature] = {
                "value": round(value, 3),
                "score": score,
                "robust_z": robust_z,
                "baseline": round(stats[feature]["median"], 3),
            }
            weighted_total += score * weight

        anomaly_score = round(min(100.0, weighted_total), 3)
        ranked = sorted(
            feature_scores.items(),
            key=lambda item: (item[1]["score"], item[1]["robust_z"]),
            reverse=True,
        )
        distribution_reasons = [
            FEATURE_LABELS[feature]
            for feature, detail in ranked
            if detail["score"] >= 30.0
        ][:3]
        if not distribution_reasons:
            distribution_reasons = ["segment dağılımı içinde olağan"]

        geometry_ai = _geometry_model(record, geometry_feature_records, geometry_stats)
        worker_ai = _worker_behavior_model(record, worker_stats)
        environmental_ai = _environmental_ai_signal(record)
        fused_score = round(
            min(
                100.0,
                (anomaly_score * 0.25)
                + (geometry_ai["score"] * 0.35)
                + (worker_ai["score"] * 0.25)
                + (environmental_ai["score"] * 0.15),
            ),
            3,
        )
        reasons = []
        for source in (geometry_ai, worker_ai, environmental_ai):
            if source["score"] >= 30:
                reasons.extend(source["reasons"][:2])
        if fused_score >= 30:
            reasons.extend(distribution_reasons[:2])
        if not reasons:
            reasons = ["segment için AI/ML anomalisi düşük"]

        insights = {
            **model_info,
            "ai_anomaly_score": fused_score,
            "ai_anomaly_level": _level(fused_score),
            "distribution_model": {
                "score": anomaly_score,
                "level": _level(anomaly_score),
                "top_features": ranked[:3],
                "reasons": distribution_reasons,
            },
            "geometry_model": geometry_ai,
            "worker_behavior_model": worker_ai,
            "environmental_signal": environmental_ai,
            "top_features": ranked[:3],
            "reasons": list(dict.fromkeys(reasons))[:5],
            "explanation": "LiDAR geometri feature modeli, worker davranış anomalisi, çevresel risk sinyali ve segment dağılım modeli açıklanabilir şekilde birleştirildi.",
        }

        record["ai_anomaly_score"] = fused_score
        record["ai_anomaly_level"] = insights["ai_anomaly_level"]
        record["ai_insights"] = insights
        breakdown = record.setdefault("risk_breakdown", {})
        breakdown["ai_insights"] = insights
        breakdown["geometry_ai"] = geometry_ai
        breakdown["worker_behavior_ai"] = worker_ai
        breakdown["environmental_ai"] = environmental_ai

    return records
