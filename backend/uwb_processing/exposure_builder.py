"""Build occupancy-only worker exposure contributions for backend fusion.

Worker exposure risk represents occupancy contribution only. If a worker is
mapped to a segment, exposure is 100.0 regardless of localization reliability.
Low reliability is represented separately as tracking_risk_score.

Final fused segment risk and emergency routing are owned by backend risk/routing
modules, not by the UWB exposure builder.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any
import json
import sys

try:
    from backend.uwb_processing.core import (
        WorkerTimelineRecord, build_worker_exposure_record,
        tracking_risk_score_from_reliability, normalize_segment_id, to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.timeline_enricher import TimelineEnrichmentResult, enrich_timeline
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.uwb_processing.core import (
        WorkerTimelineRecord, build_worker_exposure_record,
        tracking_risk_score_from_reliability, normalize_segment_id, to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.timeline_enricher import TimelineEnrichmentResult, enrich_timeline


@dataclass(frozen=True)
class WorkerExposureRecord:
    worker_id: str
    tag_id: str
    segment_id: str | None
    time_step: int
    timestamp_s: float
    position: Any
    worker_exposure_risk: float
    tracking_risk_score: float
    position_reliability: float
    visible_anchor_count: int
    tracking_status: str
    dwell_time_s: float
    risk_level: str
    status: str
    source: str = "uwb_tracking"
    mapping_method: str = ""
    mapping_confidence: float = 0.0
    continuity_score: float = 0.0
    source_position_type: str = "mocap_ground_truth"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class SegmentExposureSummary:
    segment_id: str
    worker_ids: tuple[str, ...]
    worker_count: int
    exposure_record_count: int
    max_worker_exposure_risk: float
    mean_tracking_risk_score: float
    max_tracking_risk_score: float
    min_position_reliability: float
    mean_position_reliability: float
    max_position_reliability: float
    risk_level: str

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class ExposureBuildResult:
    exposure_records: tuple[WorkerExposureRecord, ...]
    segment_summaries: tuple[SegmentExposureSummary, ...]
    summary: dict[str, Any]

    def by_worker(self) -> dict[str, tuple[WorkerExposureRecord, ...]]:
        grouped: dict[str, list[WorkerExposureRecord]] = {}
        for record in self.exposure_records:
            grouped.setdefault(record.worker_id, []).append(record)
        return {key: tuple(sorted(value, key=lambda item: (item.time_step, item.timestamp_s))) for key, value in sorted(grouped.items())}

    def by_segment(self) -> dict[str, tuple[WorkerExposureRecord, ...]]:
        grouped: dict[str, list[WorkerExposureRecord]] = {}
        for record in self.exposure_records:
            if record.segment_id is not None:
                grouped.setdefault(record.segment_id, []).append(record)
        return {key: tuple(sorted(value, key=lambda item: (item.time_step, item.worker_id))) for key, value in sorted(grouped.items())}

    def to_summary(self) -> dict[str, Any]:
        return to_jsonable(self.summary)


def risk_level_from_exposure(worker_exposure_risk: float) -> str:
    if worker_exposure_risk >= 100.0:
        return "critical"
    if worker_exposure_risk >= 75.0:
        return "high"
    if worker_exposure_risk >= 40.0:
        return "medium"
    return "low"


def compute_dwell_times(records: tuple[WorkerTimelineRecord, ...]) -> dict[tuple[str, int], float]:
    grouped: dict[str, list[WorkerTimelineRecord]] = {}
    for record in records:
        grouped.setdefault(record.worker_id, []).append(record)
    dwell: dict[tuple[str, int], float] = {}
    for worker_id, worker_records in grouped.items():
        ordered = sorted(worker_records, key=lambda item: (item.time_step, item.timestamp_s))
        previous_interval = 0.0
        for index, record in enumerate(ordered):
            if index + 1 < len(ordered):
                interval = max(0.0, ordered[index + 1].timestamp_s - record.timestamp_s)
                previous_interval = interval
            else:
                interval = previous_interval
            dwell[(worker_id, record.time_step)] = round(interval, 4)
    return dwell


def build_exposure_record_from_timeline(record: WorkerTimelineRecord, dwell_time_s: float) -> WorkerExposureRecord:
    base = build_worker_exposure_record(
        worker_id=record.worker_id, tag_id=record.tag_id,
        segment_id=record.current_segment, time_step=record.time_step,
        position=record.position, position_reliability=record.position_reliability,
        visible_anchor_count=record.visible_anchor_count,
        tracking_status=record.tracking_status, dwell_time_s=dwell_time_s,
        status=record.status if record.current_segment is not None and record.status else "unknown",
    )
    return WorkerExposureRecord(
        worker_id=base["worker_id"], tag_id=base["tag_id"],
        segment_id=base["segment_id"], time_step=base["time_step"],
        timestamp_s=record.timestamp_s, position=record.position,
        worker_exposure_risk=base["worker_exposure_risk"],
        tracking_risk_score=round(tracking_risk_score_from_reliability(record.position_reliability), 4),
        position_reliability=base["position_reliability"],
        visible_anchor_count=base["visible_anchor_count"],
        tracking_status=base["tracking_status"], dwell_time_s=base["dwell_time_s"],
        risk_level=base["risk_level"], status=base["status"], source=base["source"],
        mapping_method=record.mapping_method, mapping_confidence=record.mapping_confidence,
        continuity_score=record.continuity_score,
        source_position_type=record.source_position_type,
    )


def build_exposure_records(enriched_timeline: tuple[WorkerTimelineRecord, ...]) -> tuple[WorkerExposureRecord, ...]:
    dwell = compute_dwell_times(enriched_timeline)
    return tuple(sorted(
        (build_exposure_record_from_timeline(record, dwell[(record.worker_id, record.time_step)]) for record in enriched_timeline),
        key=lambda item: (item.time_step, item.worker_id),
    ))


def build_segment_summaries(exposure_records: tuple[WorkerExposureRecord, ...], dataset: SegmentDataset) -> tuple[SegmentExposureSummary, ...]:
    grouped: dict[str, list[WorkerExposureRecord]] = {}
    for record in exposure_records:
        if record.segment_id is None:
            continue
        segment_id = normalize_segment_id(record.segment_id)
        if not dataset.has_segment(segment_id):
            raise ValueError(f"unknown exposure segment: {segment_id}")
        grouped.setdefault(segment_id, []).append(record)
    summaries = []
    for segment_id, records in sorted(grouped.items()):
        tracking = [record.tracking_risk_score for record in records]
        reliability = [record.position_reliability for record in records]
        maximum_exposure = max(record.worker_exposure_risk for record in records)
        summaries.append(SegmentExposureSummary(
            segment_id=segment_id, worker_ids=tuple(sorted({record.worker_id for record in records})),
            worker_count=len({record.worker_id for record in records}), exposure_record_count=len(records),
            max_worker_exposure_risk=maximum_exposure,
            mean_tracking_risk_score=round(sum(tracking) / len(tracking), 4),
            max_tracking_risk_score=max(tracking), min_position_reliability=min(reliability),
            mean_position_reliability=round(sum(reliability) / len(reliability), 4),
            max_position_reliability=max(reliability), risk_level=risk_level_from_exposure(maximum_exposure),
        ))
    return tuple(summaries)


def build_exposure_summary(exposure_records: tuple[WorkerExposureRecord, ...], segment_summaries: tuple[SegmentExposureSummary, ...], enrichment_result: TimelineEnrichmentResult) -> dict[str, Any]:
    count = len(exposure_records)
    tracking = [record.tracking_risk_score for record in exposure_records]
    reliability = [record.position_reliability for record in exposure_records]
    tracking_status_counts = Counter(record.tracking_status for record in exposure_records)
    risk_counts = Counter(record.risk_level for record in exposure_records)
    without_segment = sum(record.segment_id is None for record in exposure_records)
    fallback_count = sum(record.mapping_method in {"continuity_fallback", "start_segment_seed"} for record in exposure_records)
    warnings = [
        "worker exposure is occupancy contribution only and does not include gas/geometric risk fusion",
        "low localization reliability does not reduce worker exposure risk; it is represented as tracking_risk_score",
    ]
    if tracking_status_counts.get("no_tracking", 0):
        warnings.append("no_tracking records are retained with occupancy exposure and separate tracking risk")
    if fallback_count:
        warnings.append("fallback segment assignments contribute occupancy exposure with low mapping confidence")
    return {
        "exposure_record_count": count,
        "worker_count": len({record.worker_id for record in exposure_records}),
        "segments_with_workers_count": len(segment_summaries),
        "max_worker_exposure_risk": max((record.worker_exposure_risk for record in exposure_records), default=0.0),
        "records_with_worker_exposure": sum(record.worker_exposure_risk > 0 for record in exposure_records),
        "records_without_segment": without_segment,
        "mean_tracking_risk_score": round(sum(tracking) / count, 4) if count else 0.0,
        "max_tracking_risk_score": max(tracking) if tracking else 0.0,
        "min_position_reliability": min(reliability) if reliability else 0.0,
        "mean_position_reliability": round(sum(reliability) / count, 4) if count else 0.0,
        "max_position_reliability": max(reliability) if reliability else 0.0,
        "tracking_status_counts": {name: tracking_status_counts.get(name, 0) for name in ("full_tracking", "degraded_tracking", "weak_tracking", "no_tracking")},
        "risk_level_counts": {name: risk_counts.get(name, 0) for name in ("critical", "high", "medium", "low")},
        "enriched_timeline_record_count": len(enrichment_result.enriched_timeline),
        "warnings": warnings,
    }


def validate_exposure_result(result: ExposureBuildResult, dataset: SegmentDataset) -> None:
    if not result.exposure_records:
        raise ValueError("exposure result contains no records")
    for record in result.exposure_records:
        if not record.worker_id or not record.tag_id or record.time_step < 0:
            raise ValueError("invalid exposure identity or time step")
        position = record.position.to_dict() if hasattr(record.position, "to_dict") else record.position
        if not all(isfinite(float(position[axis])) for axis in ("x", "y", "z")):
            raise ValueError("exposure position must be finite")
        if not 0 <= record.position_reliability <= 1 or not 0 <= record.tracking_risk_score <= 100 or not 0 <= record.worker_exposure_risk <= 100:
            raise ValueError("exposure risk or reliability is out of range")
        if record.segment_id is not None:
            if not dataset.has_segment(record.segment_id) or record.worker_exposure_risk != 100.0 or record.risk_level != "critical":
                raise ValueError("mapped exposure must be critical with 100.0 occupancy risk")
        elif record.worker_exposure_risk != 0.0:
            raise ValueError("unmapped exposure must have zero occupancy risk")
    if any(not dataset.has_segment(summary.segment_id) for summary in result.segment_summaries):
        raise ValueError("segment exposure summary references unknown segment")
    if result.summary.get("exposure_record_count") != len(result.exposure_records):
        raise ValueError("exposure summary count mismatch")


def build_exposure(enrichment_result: TimelineEnrichmentResult | None = None, dataset: SegmentDataset | None = None, config: dict | None = None) -> ExposureBuildResult:
    config = load_config() if config is None else config
    dataset = load_segment_dataset(config) if dataset is None else dataset
    enrichment_result = enrich_timeline(config=config) if enrichment_result is None else enrichment_result
    records = build_exposure_records(enrichment_result.enriched_timeline)
    segment_summaries = build_segment_summaries(records, dataset)
    result = ExposureBuildResult(records, segment_summaries, build_exposure_summary(records, segment_summaries, enrichment_result))
    validate_exposure_result(result, dataset)
    return result


def _self_check() -> None:
    config = load_config()
    dataset = load_segment_dataset(config)
    enrichment_result = enrich_timeline(config=config)
    result = build_exposure(enrichment_result, dataset, config)
    validate_exposure_result(result, dataset)
    assert len(result.exposure_records) == len(enrichment_result.enriched_timeline)
    assert all(record.worker_exposure_risk == 100.0 for record in result.exposure_records if record.segment_id)
    assert all(record.worker_exposure_risk == 100.0 for record in result.exposure_records if record.segment_id and record.position_reliability < 0.6)
    assert result.segment_summaries
    print(json.dumps(result.to_summary(), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    _self_check()
    print("exposure_builder.py self-check passed")
