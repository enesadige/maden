from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from backend.methane_processing.core import (
    BACKEND_SAMPLE_ROOT,
    GAS_SENSORS_OUTPUT_PATH,
    REPO_ROOT,
    ensure_parent,
    read_json,
    write_json,
)


MODEL_NAME = "robust_mad_gas_anomaly_v1"
MODEL_VERSION = "2026-07-05"

ENVIRONMENTAL_AI_ANOMALY_OUTPUT_PATH = (
    BACKEND_SAMPLE_ROOT / "risk" / "environmental_ai_anomaly.json"
)

ENVIRONMENTAL_AI_MODEL_PARAMS_PATH = (
    BACKEND_SAMPLE_ROOT / "risk" / "environmental_ai_anomaly_model_params.json"
)

GAS_AI_MODEL_REPORT_PATH = (
    Path(__file__).resolve().parent / "GAS_AI_ANOMALY_MODEL_REPORT.md"
)


FEATURES: list[dict[str, Any]] = [
    {
        "name": "methane_value",
        "path": "methane_value",
        "higher_is_risky": True,
        "reason_high": "methane_value normal baseline üstünde",
        "reason_low": "methane_value normal baseline altında",
    },
    {
        "name": "methane_risk_score",
        "path": "methane_risk_score",
        "higher_is_risky": True,
        "reason_high": "methane_risk_score normal baseline üstünde",
        "reason_low": "methane_risk_score normal baseline altında",
    },
    {
        "name": "anomaly_score",
        "path": "anomaly_score",
        "higher_is_risky": True,
        "reason_high": "rolling anomaly_score normal baseline üstünde",
        "reason_low": "rolling anomaly_score normal baseline altında",
    },
    {
        "name": "environmental_risk",
        "path": "environmental_risk",
        "higher_is_risky": True,
        "reason_high": "environmental_risk normal baseline üstünde",
        "reason_low": "environmental_risk normal baseline altında",
    },
    {
        "name": "weighted_multi_sensor_risk",
        "path": "weighted_multi_sensor_risk",
        "higher_is_risky": True,
        "reason_high": "weighted_multi_sensor_risk normal baseline üstünde",
        "reason_low": "weighted_multi_sensor_risk normal baseline altında",
    },
    {
        "name": "methane_ppm",
        "path": "measurements.methane_ppm",
        "higher_is_risky": True,
        "reason_high": "methane_ppm normal baseline üstünde",
        "reason_low": "methane_ppm normal baseline altında",
    },
    {
        "name": "co_ppm",
        "path": "measurements.co_ppm",
        "higher_is_risky": True,
        "reason_high": "co_ppm normal baseline üstünde",
        "reason_low": "co_ppm normal baseline altında",
    },
    {
        "name": "oxygen_percent",
        "path": "measurements.oxygen_percent",
        "higher_is_risky": False,
        "reason_high": "oxygen_percent normal baseline üstünde",
        "reason_low": "oxygen_percent normal baseline altında",
    },
    {
        "name": "temperature_c",
        "path": "measurements.temperature_c",
        "higher_is_risky": True,
        "reason_high": "temperature_c normal baseline üstünde",
        "reason_low": "temperature_c normal baseline altında",
    },
    {
        "name": "humidity_percent",
        "path": "measurements.humidity_percent",
        "higher_is_risky": True,
        "reason_high": "humidity_percent normal baseline üstünde",
        "reason_low": "humidity_percent normal baseline altında",
    },
    {
        "name": "pressure_hpa",
        "path": "measurements.pressure_hpa",
        "higher_is_risky": None,
        "reason_high": "pressure_hpa normal baseline üstünde",
        "reason_low": "pressure_hpa normal baseline altında",
    },
    {
        "name": "component_methane_risk",
        "path": "component_scores.methane_risk",
        "higher_is_risky": True,
        "reason_high": "component methane_risk normal baseline üstünde",
        "reason_low": "component methane_risk normal baseline altında",
    },
    {
        "name": "component_co_risk",
        "path": "component_scores.co_risk",
        "higher_is_risky": True,
        "reason_high": "component co_risk normal baseline üstünde",
        "reason_low": "component co_risk normal baseline altında",
    },
    {
        "name": "component_oxygen_risk",
        "path": "component_scores.oxygen_risk",
        "higher_is_risky": True,
        "reason_high": "component oxygen_risk normal baseline üstünde",
        "reason_low": "component oxygen_risk normal baseline altında",
    },
    {
        "name": "component_temperature_risk",
        "path": "component_scores.temperature_risk",
        "higher_is_risky": True,
        "reason_high": "component temperature_risk normal baseline üstünde",
        "reason_low": "component temperature_risk normal baseline altında",
    },
    {
        "name": "component_humidity_risk",
        "path": "component_scores.humidity_risk",
        "higher_is_risky": True,
        "reason_high": "component humidity_risk normal baseline üstünde",
        "reason_low": "component humidity_risk normal baseline altında",
    },
    {
        "name": "component_pressure_risk",
        "path": "component_scores.pressure_risk",
        "higher_is_risky": True,
        "reason_high": "component pressure_risk normal baseline üstünde",
        "reason_low": "component pressure_risk normal baseline altında",
    },
    {
        "name": "sensor_reliability_score",
        "path": "sensor_reliability_score",
        "higher_is_risky": False,
        "reason_high": "sensor_reliability_score normal baseline üstünde",
        "reason_low": "sensor_reliability_score normal baseline altında",
    },
    {
        "name": "confidence",
        "path": "confidence",
        "higher_is_risky": False,
        "reason_high": "confidence normal baseline üstünde",
        "reason_low": "confidence normal baseline altında",
    },
]


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    if not math.isfinite(result):
        return default

    return result


def get_nested(record: dict[str, Any], path: str, default: float = 0.0) -> float:
    current: Any = record

    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        if part not in current:
            return default
        current = current[part]

    return as_float(current, default)


def level_for_score(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def robust_mad(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0

    center = float(median(values))
    deviations = [abs(value - center) for value in values]
    mad = float(median(deviations))

    if mad <= 1e-9:
        mean_abs_dev = sum(deviations) / max(len(deviations), 1)
        mad = mean_abs_dev

    if mad <= 1e-9:
        mad = 1.0

    return center, mad


def robust_z_score(value: float, center: float, mad: float) -> float:
    return abs(0.6745 * (value - center) / mad)


def fit_model(records: list[dict[str, Any]]) -> dict[str, Any]:
    feature_stats: dict[str, dict[str, Any]] = {}

    for feature in FEATURES:
        values = [get_nested(record, feature["path"]) for record in records]
        center, mad = robust_mad(values)

        feature_stats[feature["name"]] = {
            "path": feature["path"],
            "median": round(center, 6),
            "mad": round(mad, 6),
            "min": round(min(values), 6) if values else 0.0,
            "max": round(max(values), 6) if values else 0.0,
            "higher_is_risky": feature["higher_is_risky"],
        }

    return {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "record_count": len(records),
        "feature_count": len(FEATURES),
        "features": feature_stats,
    }


def z_to_score(z_value: float) -> float:
    """
    Robust z-score değerini 0-100 arası anomaly skoruna çevirir.
    z≈0 normal, z≈6 ve üzeri kritik anomali kabul edilir.
    """
    return round(clamp((z_value / 6.0) * 100.0, 0.0, 100.0), 3)


def risk_context_score(record: dict[str, Any]) -> float:
    environmental_risk = as_float(record.get("environmental_risk"))
    methane_risk = as_float(record.get("methane_risk_score"))
    weighted_risk = as_float(record.get("weighted_multi_sensor_risk"))
    anomaly_score = as_float(record.get("anomaly_score")) * 100.0

    return max(environmental_risk, methane_risk, weighted_risk, anomaly_score)


def reason_for_feature(
    *,
    feature: dict[str, Any],
    value: float,
    center: float,
) -> str:
    """
    Reason listesinde sadece risk yönlü sapmaları gösterir.

    higher_is_risky=True  -> sadece baseline üstü sapma risk nedeni sayılır.
    higher_is_risky=False -> sadece baseline altı sapma risk nedeni sayılır.
    higher_is_risky=None  -> iki yönlü sapma da reason olabilir.
    """
    higher_is_risky = feature.get("higher_is_risky")

    if value >= center:
        if higher_is_risky is False:
            return ""
        return str(feature["reason_high"])

    if higher_is_risky is True:
        return ""

    return str(feature["reason_low"])


def build_reasons(
    *,
    record: dict[str, Any],
    top_feature_deviations: list[dict[str, Any]],
    gas_ai_anomaly_score: float,
) -> list[str]:
    reasons: list[str] = []

    for item in top_feature_deviations:
        if item["robust_z_score"] >= 2.5 and item["reason"]:
            reasons.append(item["reason"])

    methane_risk = as_float(record.get("methane_risk_score"))
    environmental_risk = as_float(record.get("environmental_risk"))
    weighted_risk = as_float(record.get("weighted_multi_sensor_risk"))
    anomaly_score = as_float(record.get("anomaly_score"))
    confidence = as_float(record.get("confidence"), 1.0)

    measurements = record.get("measurements", {})
    component_scores = record.get("component_scores", {})

    co_ppm = 0.0
    oxygen_percent = 20.9
    temperature_c = 23.0
    co_risk = 0.0
    oxygen_risk = 0.0

    if isinstance(measurements, dict):
        co_ppm = as_float(measurements.get("co_ppm"))
        oxygen_percent = as_float(measurements.get("oxygen_percent"), 20.9)
        temperature_c = as_float(measurements.get("temperature_c"), 23.0)

    if isinstance(component_scores, dict):
        co_risk = as_float(component_scores.get("co_risk"))
        oxygen_risk = as_float(component_scores.get("oxygen_risk"))

    if methane_risk >= 80:
        reasons.append("methane_risk_score kritik seviyede")
    elif methane_risk >= 60:
        reasons.append("methane_risk_score yüksek seviyede")

    if environmental_risk >= 80:
        reasons.append("environmental_risk kritik seviyede")
    elif environmental_risk >= 60:
        reasons.append("environmental_risk yüksek seviyede")

    if weighted_risk >= 80:
        reasons.append("weighted_multi_sensor_risk kritik seviyede")
    elif weighted_risk >= 60:
        reasons.append("weighted_multi_sensor_risk yüksek seviyede")

    if anomaly_score >= 0.8:
        reasons.append("rolling anomaly_score çok yüksek")

    if co_risk >= 60 or co_ppm >= 50:
        reasons.append("CO sinyali normal üstü risk gösteriyor")

    if oxygen_risk >= 60 or oxygen_percent <= 19.0:
        reasons.append("O2 seviyesi normal baseline altında")

    if temperature_c >= 32:
        reasons.append("sıcaklık seviyesi normal üstünde")

    if confidence < 0.95:
        reasons.append("sensor confidence düşük veya doğrulama gerektiriyor")

    if gas_ai_anomaly_score < 30 and not reasons:
        reasons.append("çok değişkenli gaz profili normal baseline'a yakın")

    unique_reasons: list[str] = []
    for reason in reasons:
        if reason not in unique_reasons:
            unique_reasons.append(reason)

    return unique_reasons[:8]


def score_record(
    *,
    record: dict[str, Any],
    model_params: dict[str, Any],
) -> dict[str, Any]:
    feature_stats = model_params["features"]
    deviations: list[dict[str, Any]] = []

    for feature in FEATURES:
        name = feature["name"]
        stats = feature_stats[name]

        value = get_nested(record, feature["path"])
        center = as_float(stats["median"])
        mad = as_float(stats["mad"], 1.0)

        z_value = robust_z_score(value, center, mad)

        deviations.append(
            {
                "feature": name,
                "value": round(value, 6),
                "median": round(center, 6),
                "mad": round(mad, 6),
                "robust_z_score": round(z_value, 3),
                "reason": reason_for_feature(
                    feature=feature,
                    value=value,
                    center=center,
                ),
            }
        )

    deviations.sort(key=lambda item: item["robust_z_score"], reverse=True)

    top_three = deviations[:3]
    top_three_z = [item["robust_z_score"] for item in top_three]

    robust_anomaly_score = z_to_score(
        sum(top_three_z) / max(len(top_three_z), 1)
    )

    context_score = risk_context_score(record)

    gas_ai_anomaly_score = round(
        clamp(
            (0.65 * robust_anomaly_score) + (0.35 * context_score),
            0.0,
            100.0,
        ),
        3,
    )

    reasons = build_reasons(
        record=record,
        top_feature_deviations=deviations[:6],
        gas_ai_anomaly_score=gas_ai_anomaly_score,
    )

    return {
        "sensor_id": record.get("sensor_id"),
        "segment_id": record.get("segment_id"),
        "time_step": int(record.get("time_step", 0)),
        "gas_ai_anomaly_score": gas_ai_anomaly_score,
        "gas_ai_anomaly_level": level_for_score(gas_ai_anomaly_score),
        "gas_ai_reasons": reasons,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "robust_anomaly_score": robust_anomaly_score,
        "risk_context_score": round(context_score, 3),
        "top_anomaly_features": deviations[:5],
        "methane_risk_score": round(as_float(record.get("methane_risk_score")), 3),
        "environmental_risk": round(as_float(record.get("environmental_risk")), 3),
        "weighted_multi_sensor_risk": round(
            as_float(record.get("weighted_multi_sensor_risk")),
            3,
        ),
        "confidence": round(as_float(record.get("confidence"), 1.0), 3),
    }


def validate_ai_records(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []

    if not records:
        return ["environmental_ai_anomaly output boş"]

    required_fields = {
        "sensor_id",
        "segment_id",
        "time_step",
        "gas_ai_anomaly_score",
        "gas_ai_anomaly_level",
        "gas_ai_reasons",
        "model_name",
        "model_version",
    }

    allowed_levels = {"low", "medium", "high", "critical"}

    for index, record in enumerate(records):
        missing = sorted(required_fields - set(record.keys()))
        if missing:
            errors.append(f"ai[{index}] eksik alanlar: {missing}")
            continue

        score = as_float(record.get("gas_ai_anomaly_score"), -1.0)
        if not 0 <= score <= 100:
            errors.append(f"ai[{index}] gas_ai_anomaly_score aralık dışı")

        if record.get("gas_ai_anomaly_level") not in allowed_levels:
            errors.append(f"ai[{index}] gas_ai_anomaly_level geçersiz")

        if not isinstance(record.get("gas_ai_reasons"), list):
            errors.append(f"ai[{index}] gas_ai_reasons liste değil")

    return errors


def build_report(
    *,
    records: list[dict[str, Any]],
    ai_records: list[dict[str, Any]],
    validation_errors: list[str],
) -> str:
    level_counts = Counter(record["gas_ai_anomaly_level"] for record in ai_records)
    sensor_counts = Counter(str(record.get("sensor_id")) for record in records)
    segment_counts = Counter(str(record.get("segment_id")) for record in records)

    top_records = sorted(
        ai_records,
        key=lambda item: item["gas_ai_anomaly_score"],
        reverse=True,
    )[:10]

    lines: list[str] = [
        "# Gas AI Anomaly Model Raporu",
        "",
        "## 1. Amaç",
        "",
        "Bu rapor, Recep tarafındaki gaz/metan/çevresel risk pipeline için eklenen "
        "açıklanabilir AI/ML anomaly modelini açıklar.",
        "",
        "Model, gerçek etiketli bir classification modeli değildir. Elimizde normal/anormal "
        "etiketli saha verisi olmadığı için dependency-free, unsupervised, robust MAD tabanlı "
        "anomaly detection yaklaşımı kullanılmıştır.",
        "",
        "## 2. Kullanılan Veri",
        "",
        f"- Input dosyası: `{repo_relative(GAS_SENSORS_OUTPUT_PATH)}`",
        f"- İşlenen kayıt sayısı: `{len(records)}`",
        f"- Sensör sayısı: `{len(sensor_counts)}`",
        f"- Segment sayısı: `{len(segment_counts)}`",
        "",
        "Kullanılan input mevcut pipeline tarafından üretilen `gas_sensors.json` dosyasıdır. "
        "Raw methane CSV doğrudan bu modelde tekrar okunmamıştır; methane CSV önceki pipeline "
        "tarafından işlenmiş ve bu modele processed timeline olarak verilmiştir.",
        "",
        "## 3. Önemli Veri Sınırı",
        "",
        "CO, O2, sıcaklık, nem ve basınç değerleri gerçek saha sensörü ölçümü değildir. "
        "Bu değerler mevcut methane risk sinyali, anomaly score, sensor_id ve time_step "
        "üzerinden deterministic demo/simülasyon bağlamı olarak üretilmiştir.",
        "",
        "Bu nedenle model gerçek çoklu gaz saha modeli olarak değil, mevcut methane tabanlı "
        "pipeline üzerinde çalışan açıklanabilir environmental anomaly sinyali olarak "
        "değerlendirilmelidir.",
        "",
        "## 4. Model",
        "",
        f"- Model adı: `{MODEL_NAME}`",
        f"- Model versiyonu: `{MODEL_VERSION}`",
        "- Model tipi: `unsupervised robust MAD anomaly detection`",
        "- Dependency: Ek Python paketi gerektirmez.",
        "",
        "Model her feature için median ve MAD değerlerini öğrenir. Her sensor-time kaydı için "
        "robust z-score hesaplanır. En sapkın feature'lar ve mevcut risk bağlamı birlikte "
        "`gas_ai_anomaly_score` skoruna dönüştürülür.",
        "",
        "## 5. Kullanılan Feature'lar",
        "",
    ]

    for feature in FEATURES:
        lines.append(f"- `{feature['path']}`")

    lines.extend(
        [
            "",
            "## 6. Skorlama",
            "",
            "Model iki ana sinyali birleştirir:",
            "",
            "```text",
            "gas_ai_anomaly_score = 0.65 * robust_anomaly_score + 0.35 * risk_context_score",
            "```",
            "",
            "- `robust_anomaly_score`: Feature'ların median/MAD baseline'a göre sapması.",
            "- `risk_context_score`: environmental_risk, methane_risk_score, weighted_multi_sensor_risk ve anomaly_score bağlamı.",
            "",
            "Risk seviyeleri:",
            "",
            "```text",
            "0-29.999   -> low",
            "30-59.999  -> medium",
            "60-79.999  -> high",
            "80-100     -> critical",
            "```",
            "",
            "## 7. Sonuç Özeti",
            "",
            f"- Level counts: `{dict(sorted(level_counts.items()))}`",
            f"- Validation error count: `{len(validation_errors)}`",
            "",
            "## 8. En Anormal 10 Kayıt",
            "",
        ]
    )

    for item in top_records:
        lines.append(
            "- "
            f"time_step=`{item['time_step']}`, "
            f"sensor_id=`{item['sensor_id']}`, "
            f"segment_id=`{item['segment_id']}`, "
            f"score=`{item['gas_ai_anomaly_score']}`, "
            f"level=`{item['gas_ai_anomaly_level']}`, "
            f"reasons=`{item['gas_ai_reasons']}`"
        )

    lines.extend(
        [
            "",
            "## 9. Output Dosyaları",
            "",
            f"- `{repo_relative(ENVIRONMENTAL_AI_ANOMALY_OUTPUT_PATH)}`",
            f"- `{repo_relative(ENVIRONMENTAL_AI_MODEL_PARAMS_PATH)}`",
            f"- `{repo_relative(GAS_AI_MODEL_REPORT_PATH)}`",
            "",
            "## 10. MVP Kullanılabilirlik",
            "",
            "Bu model MVP içinde güvenli şekilde ek AI anomaly sinyali olarak kullanılabilir. "
            "Final risk skorunu doğrudan ezmemeli; backend tarafında `ai_insights` veya "
            "`risk_breakdown.environmental_ai` alanlarında açıklayıcı sinyal olarak gösterilmelidir.",
            "",
            "Modelin anlamı: Bu kayıt, kendi processed gaz timeline baseline'ına göre normal mi, "
            "yoksa çok değişkenli çevresel profil açısından sapkın mı?",
            "",
            "## 11. Sınırlar",
            "",
            "- Etiketli supervised model değildir.",
            "- Gerçek CO/O2/sıcaklık/nem/basınç saha datası kullanılmamıştır.",
            "- Model çıktısı trapped/mahsuriyet kararı değildir.",
            "- Model çıktısı nihai güvenlik kararı değildir.",
            "- Output sadece açıklanabilir AI anomaly sinyali olarak kullanılmalıdır.",
            "",
        ]
    )

    if validation_errors:
        lines.extend(["## 12. Validation Hataları", ""])
        for error in validation_errors[:20]:
            lines.append(f"- {error}")
        lines.append("")

    return "\n".join(lines)


def build_gas_ai_anomaly() -> dict[str, Any]:
    records = read_json(GAS_SENSORS_OUTPUT_PATH, default=[])

    if not isinstance(records, list) or not records:
        raise RuntimeError(
            "gas_sensors.json bulunamadı veya boş. "
            "Önce scripts/05_build_gas_timeline.py çalıştır."
        )

    model_params = fit_model(records)

    ai_records = [
        score_record(record=record, model_params=model_params)
        for record in records
    ]

    ai_records.sort(key=lambda item: (item["time_step"], item["sensor_id"]))

    validation_errors = validate_ai_records(ai_records)
    if validation_errors:
        for error in validation_errors[:20]:
            print(f"[gas-ai][validation-error] {error}")
        raise RuntimeError(
            f"Gas AI anomaly validation failed. error_count={len(validation_errors)}"
        )

    model_params["level_counts"] = dict(
        sorted(Counter(item["gas_ai_anomaly_level"] for item in ai_records).items())
    )
    model_params["top_anomaly_records"] = sorted(
        ai_records,
        key=lambda item: item["gas_ai_anomaly_score"],
        reverse=True,
    )[:10]
    model_params["validation"] = {
        "ok": True,
        "error_count": 0,
        "errors": [],
        "record_count": len(ai_records),
    }

    report = build_report(
        records=records,
        ai_records=ai_records,
        validation_errors=validation_errors,
    )

    ensure_parent(ENVIRONMENTAL_AI_ANOMALY_OUTPUT_PATH)
    ensure_parent(ENVIRONMENTAL_AI_MODEL_PARAMS_PATH)
    ensure_parent(GAS_AI_MODEL_REPORT_PATH)

    write_json(ENVIRONMENTAL_AI_ANOMALY_OUTPUT_PATH, ai_records)
    write_json(ENVIRONMENTAL_AI_MODEL_PARAMS_PATH, model_params)
    GAS_AI_MODEL_REPORT_PATH.write_text(report, encoding="utf-8")

    return {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "input_path": repo_relative(GAS_SENSORS_OUTPUT_PATH),
        "output_path": repo_relative(ENVIRONMENTAL_AI_ANOMALY_OUTPUT_PATH),
        "model_params_path": repo_relative(ENVIRONMENTAL_AI_MODEL_PARAMS_PATH),
        "report_path": repo_relative(GAS_AI_MODEL_REPORT_PATH),
        "record_count": len(ai_records),
        "level_counts": model_params["level_counts"],
        "validation": model_params["validation"],
    }