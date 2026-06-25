from __future__ import annotations

from backend.methane_processing.core import clamp, risk_status


def percentile(values: list[float], p: float) -> float:
    clean = sorted(value for value in values if value == value)

    if not clean:
        return 0.0

    if len(clean) == 1:
        return clean[0]

    position = (len(clean) - 1) * (p / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(clean) - 1)
    weight = position - lower

    return clean[lower] * (1 - weight) + clean[upper] * weight


def robust_value_scores(values: list[float]) -> list[float]:
    """
    Metan seviyesini 0-1 aralığına normalize eder.

    Min-max yerine p10-p95 aralığı kullanılır.
    Sensör değeri neredeyse sabitse otomatik yüksek risk üretilmez.
    """
    if not values:
        return []

    p10 = percentile(values, 10)
    p95 = percentile(values, 95)
    span = p95 - p10

    if span <= 1e-9:
        # Sabit ve değişmeyen sensör yüksek risk sayılmasın.
        stable_score = 0.0 if max(values) <= 0 else 0.25
        return [stable_score for _ in values]

    scores = []
    for value in values:
        score = (value - p10) / span
        scores.append(clamp(score, 0.0, 1.0))

    return scores


def methane_risk_scores(
    methane_values: list[float],
    anomaly_scores: list[float],
    value_weight: float = 0.60,
    anomaly_weight: float = 0.40,
) -> list[float]:
    if len(methane_values) != len(anomaly_scores):
        raise ValueError("methane_values ve anomaly_scores uzunlukları eşit olmalı.")

    value_scores = robust_value_scores(methane_values)

    risks = []
    for value_score, anomaly_score in zip(value_scores, anomaly_scores):
        score = 100.0 * (
            value_weight * value_score
            + anomaly_weight * clamp(anomaly_score, 0.0, 1.0)
        )
        risks.append(round(clamp(score, 0.0, 100.0), 3))

    return risks


def status_for_score(score: float) -> str:
    return risk_status(score)
