from __future__ import annotations

import math
from collections import deque


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0

    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(0.0, variance))


def rolling_anomaly_scores(
    values: list[float],
    window_size: int = 12,
    max_z_score: float = 4.0,
) -> list[float]:
    """
    Sensör bazlı rolling z-score anomaly hesabı.

    Mevcut değer, kendi baseline hesabına dahil edilmez.
    Baseline sadece önceki window değerlerinden oluşur.
    """
    if window_size < 3:
        raise ValueError("window_size en az 3 olmalı.")

    window: deque[float] = deque(maxlen=window_size)
    scores: list[float] = []

    for value in values:
        if len(window) < 3:
            scores.append(0.0)
            window.append(value)
            continue

        history = list(window)
        baseline_mean = mean(history)
        baseline_std = stddev(history)

        if baseline_std <= 1e-9:
            anomaly = 0.0 if abs(value - baseline_mean) <= 1e-9 else 1.0
        else:
            z_score = abs((value - baseline_mean) / baseline_std)
            anomaly = min(1.0, z_score / max_z_score)

        scores.append(round(anomaly, 6))
        window.append(value)

    return scores
