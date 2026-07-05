from __future__ import annotations

from statistics import median
from typing import Any


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


def annotate_segment_ai_insights(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach an explainable unsupervised anomaly layer without changing final risk.

    This is intentionally dependency-free. It behaves like a small unsupervised
    anomaly detector over the current segment distribution: each segment is
    compared to robust median/MAD baselines, feature scores are weighted, and the
    top deviations become human-readable reasons.
    """
    if not records:
        return records

    stats = _robust_feature_stats(records)
    model_info = {
        "model_type": "robust_unsupervised_segment_anomaly",
        "method": "median_mad_robust_zscore",
        "training_scope": "current_segment_distribution",
        "trained_on_segments": len(records),
        "feature_weights": dict(FEATURE_WEIGHTS),
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
        reasons = [
            FEATURE_LABELS[feature]
            for feature, detail in ranked
            if detail["score"] >= 30.0
        ][:3]
        if not reasons:
            reasons = ["segment dağılımı içinde olağan"]

        insights = {
            **model_info,
            "ai_anomaly_score": anomaly_score,
            "ai_anomaly_level": _level(anomaly_score),
            "top_features": ranked[:3],
            "reasons": reasons,
            "explanation": "Segment değerleri aynı zaman adımındaki diğer segmentlerin robust median/MAD baz çizgisiyle karşılaştırıldı.",
        }

        record["ai_anomaly_score"] = anomaly_score
        record["ai_anomaly_level"] = insights["ai_anomaly_level"]
        record["ai_insights"] = insights
        record.setdefault("risk_breakdown", {})["ai_insights"] = insights

    return records
