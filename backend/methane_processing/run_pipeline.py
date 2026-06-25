from __future__ import annotations

from backend.methane_processing.core import (
    DEFAULT_GAS_TIMELINE_STEPS,
    DEFAULT_MAX_METHANE_ROWS,
    ENVIRONMENTAL_RISK_OUTPUT_PATH,
    GAS_RISK_REPORT_PATH,
    GAS_SENSOR_MAPPING_OUTPUT_PATH,
    GAS_SENSORS_OUTPUT_PATH,
    METHANE_PIPELINE_SUMMARY_PATH,
    PROCESSED_GAS_TIMELINE_PATH,
    RISK_SEGMENTS_OUTPUT_PATH,
    SIMULATION_READY_GAS_TIMELINE_PATH,
    ensure_output_dirs,
    load_project_config,
    methane_csv_path,
    read_json,
    runtime_int,
    write_json,
)
from backend.methane_processing.dataset_reader import read_methane_samples
from backend.methane_processing.segment_mapper import build_sensor_mapping
from backend.methane_processing.timeline_builder import (
    build_environmental_risk_records,
    build_gas_sensor_timeline,
    build_markdown_report,
    summarize_timeline,
)
from backend.methane_processing.validate_outputs import validate_all_outputs


def to_legacy_segment_id(segment_id: str) -> str:
    """
    Legacy simulation pipeline SEG_XXX formatı kullanıyor.
    Backend handoff dosyaları SXXX formatında kalır; sadece simulation_ready
    timeline için segment_id değeri SEG_XXX formatına çevrilir.
    """
    text = str(segment_id).strip()
    if text.startswith("S") and text[1:].isdigit():
        return f"SEG_{int(text[1:]):03d}"
    return text


def build_fusion_compatible_timeline(
    gas_timeline: list[dict],
) -> list[dict]:
    """
    Eski fusion scripti processed/features/segments.json içindeki SEG_XXX
    segment ID'leriyle join yaptığı için simulation_ready çıktısında segment_id
    legacy formata çevrilir.

    canonical_segment_id alanı korunur.
    """
    result = []

    for record in gas_timeline:
        item = dict(record)
        item["canonical_segment_id"] = record["segment_id"]
        item["segment_id"] = to_legacy_segment_id(record["segment_id"])
        result.append(item)

    return result


def ensure_risk_segments_is_valid_json() -> None:
    """
    risk_segments.json Enes'in final risk output dosyasıdır.
    Biz final risk üretmiyoruz.

    Ancak mevcut branch'ta dosya boşsa backend json.load sırasında kırılabilir.
    Bu yüzden dosya yoksa veya boş/bozuksa geçerli boş liste olarak yazarız.
    """
    try:
        payload = read_json(RISK_SEGMENTS_OUTPUT_PATH, default=[])
    except Exception:
        payload = []

    if payload is None:
        payload = []

    if not isinstance(payload, list):
        return

    write_json(RISK_SEGMENTS_OUTPUT_PATH, payload)


def run() -> dict:
    """
    Methane processing pipeline ana giriş noktası.
    """
    ensure_output_dirs()

    config = load_project_config()

    csv_path = methane_csv_path(config)
    max_rows = runtime_int(config, "max_methane_rows", DEFAULT_MAX_METHANE_ROWS)
    target_steps = runtime_int(config, "gas_timeline_steps", DEFAULT_GAS_TIMELINE_STEPS)

    print(f"[methane] CSV: {csv_path}")
    print(f"[methane] max_rows={max_rows}, target_steps={target_steps}")

    sensor_mapping = build_sensor_mapping()
    samples = read_methane_samples(
        csv_path=csv_path,
        max_rows=max_rows,
        target_steps=target_steps,
    )

    gas_timeline = build_gas_sensor_timeline(
        samples=samples,
        sensor_mapping=sensor_mapping,
    )

    environmental_risk = build_environmental_risk_records(gas_timeline)

    validation = validate_all_outputs(
        gas_timeline=gas_timeline,
        environmental_risk=environmental_risk,
    )

    if not validation["ok"]:
        for error in validation["errors"][:20]:
            print(f"[methane][validation-error] {error}")
        raise RuntimeError(
            f"Methane output validation failed. error_count={validation['error_count']}"
        )

    summary = summarize_timeline(
        gas_timeline=gas_timeline,
        environmental_risk=environmental_risk,
        sensor_mapping=sensor_mapping,
        methane_csv_path=str(csv_path),
        max_rows=max_rows,
        target_steps=target_steps,
    )
    summary["validation"] = validation

    fusion_compatible_timeline = build_fusion_compatible_timeline(gas_timeline)

    # Backend handoff canonical SXXX segment ID formatında kalır.
    write_json(GAS_SENSORS_OUTPUT_PATH, gas_timeline)

    # Legacy simulation/fusion pipeline SEG_XXX segment ID formatını bekliyor.
    write_json(PROCESSED_GAS_TIMELINE_PATH, fusion_compatible_timeline)
    write_json(SIMULATION_READY_GAS_TIMELINE_PATH, fusion_compatible_timeline)

    write_json(ENVIRONMENTAL_RISK_OUTPUT_PATH, environmental_risk)
    write_json(GAS_SENSOR_MAPPING_OUTPUT_PATH, sensor_mapping)
    write_json(METHANE_PIPELINE_SUMMARY_PATH, summary)

    ensure_risk_segments_is_valid_json()

    GAS_RISK_REPORT_PATH.write_text(
        build_markdown_report(summary),
        encoding="utf-8",
    )

    print(f"[methane] gas records: {len(gas_timeline)}")
    print(f"[methane] environmental risk records: {len(environmental_risk)}")
    print(f"[methane] max risk: {summary['max_methane_risk_score']}")
    print("[methane] output validation: OK")

    return summary


def main() -> None:
    run()


if __name__ == "__main__":
    main()
