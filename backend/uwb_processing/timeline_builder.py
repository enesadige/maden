"""Build the pre-enrichment worker timeline for the UWB MVP.

Timeline records preserve mapping confidence and mapping method because segment
assignment is approximate in the MVP. Fallback-based records are usable for
demo continuity but should not be interpreted as high-confidence calibrated
localization.
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
        WorkerTimelineRecord,
        MappedPosition,
        Point3D,
        clamp,
        reliability_status,
        to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_mapper import SegmentMappingResult, map_segments
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.uwb_processing.core import (
        WorkerTimelineRecord,
        MappedPosition,
        Point3D,
        clamp,
        reliability_status,
        to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_mapper import SegmentMappingResult, map_segments


@dataclass(frozen=True)
class WorkerLatestSnapshot:
    worker_id: str
    tag_id: str
    time_step: int
    timestamp_s: float
    current_segment: str | None
    position: Point3D
    position_reliability: float
    status: str
    mapping_method: str
    mapping_confidence: float
    continuity_score: float
    flight_signal_reliability: float
    source_trial: str
    source_position_type: str = "mocap_ground_truth"

    def to_dict(self) -> dict[str, Any]:
        position = self.position.to_dict()
        return {
            "worker_id": self.worker_id,
            "tag_id": self.tag_id,
            "time_step": self.time_step,
            "timestamp_s": self.timestamp_s,
            "current_segment": self.current_segment,
            "position": position,
            "position_reliability": self.position_reliability,
            "status": self.status,
            "mapped_segment_id": self.current_segment,
            "uwb_pose": dict(position),
            "motion_status": self.status,
            "mapping_method": self.mapping_method,
            "mapping_confidence": self.mapping_confidence,
            "continuity_score": self.continuity_score,
            "flight_signal_reliability": self.flight_signal_reliability,
            "source_trial": self.source_trial,
            "source_position_type": self.source_position_type,
            "source": "uwb_tracking",
        }


@dataclass(frozen=True)
class TimelineBuildResult:
    timeline: tuple[WorkerTimelineRecord, ...]
    latest_workers: tuple[WorkerLatestSnapshot, ...]
    summary: dict[str, Any]

    def by_worker(self) -> dict[str, tuple[WorkerTimelineRecord, ...]]:
        grouped: dict[str, list[WorkerTimelineRecord]] = {}
        for record in self.timeline:
            grouped.setdefault(record.worker_id, []).append(record)
        return {
            worker_id: tuple(
                sorted(records, key=lambda item: (item.time_step, item.timestamp_s))
            )
            for worker_id, records in sorted(grouped.items())
        }

    def to_summary(self) -> dict[str, Any]:
        return to_jsonable(self.summary)


def base_reliability_from_mapping(mapped: MappedPosition) -> float:
    value = clamp(
        0.60 * clamp(mapped.mapping_confidence)
        + 0.25 * clamp(mapped.continuity_score)
        + 0.15 * clamp(mapped.flight_signal_reliability)
    )
    if mapped.current_segment is None:
        value = min(value, 0.25)
    if mapped.mapping_method == "continuity_fallback":
        value = min(value, 0.35)
    elif mapped.mapping_method == "start_segment_seed":
        value = min(value, 0.30)
    return round(value, 4)


def status_from_base_reliability(value: float) -> str:
    value = clamp(value)
    if value >= 0.60:
        return "safe"
    if value >= 0.30:
        return "uncertain"
    return "low_confidence"


def build_timeline_record(mapped: MappedPosition) -> WorkerTimelineRecord:
    base_reliability = base_reliability_from_mapping(mapped)
    return WorkerTimelineRecord(
        worker_id=mapped.worker_id,
        tag_id=mapped.tag_id,
        time_step=mapped.time_step,
        timestamp_s=mapped.timestamp_s,
        position=mapped.position,
        current_segment=mapped.current_segment,
        visible_anchor_count=0,
        visible_anchors=(),
        tracking_status="pending_anchor_enrichment",
        position_reliability=base_reliability,
        reliability_status=reliability_status(base_reliability),
        mapping_method=mapped.mapping_method,
        mapping_confidence=mapped.mapping_confidence,
        continuity_score=mapped.continuity_score,
        flight_signal_reliability=mapped.flight_signal_reliability,
        source_trial=mapped.source_trial,
        source_position_type=mapped.source_position_type,
        status=status_from_base_reliability(base_reliability),
    )


def build_timeline_records(
    mapped_positions: tuple[MappedPosition, ...],
) -> tuple[WorkerTimelineRecord, ...]:
    return tuple(
        sorted(
            (build_timeline_record(mapped) for mapped in mapped_positions),
            key=lambda item: (item.time_step, item.worker_id),
        )
    )


def latest_snapshot_for_worker(
    records: tuple[WorkerTimelineRecord, ...],
) -> WorkerLatestSnapshot:
    if not records:
        raise ValueError("cannot build a latest snapshot from no timeline records")
    record = max(records, key=lambda item: (item.time_step, item.timestamp_s))
    return WorkerLatestSnapshot(
        worker_id=record.worker_id,
        tag_id=record.tag_id,
        time_step=record.time_step,
        timestamp_s=record.timestamp_s,
        current_segment=record.current_segment,
        position=record.position,
        position_reliability=record.position_reliability,
        status=record.status,
        mapping_method=record.mapping_method,
        mapping_confidence=record.mapping_confidence,
        continuity_score=record.continuity_score,
        flight_signal_reliability=record.flight_signal_reliability,
        source_trial=record.source_trial,
        source_position_type=record.source_position_type,
    )


def build_latest_worker_snapshots(
    timeline: tuple[WorkerTimelineRecord, ...],
) -> tuple[WorkerLatestSnapshot, ...]:
    grouped: dict[str, list[WorkerTimelineRecord]] = {}
    for record in timeline:
        grouped.setdefault(record.worker_id, []).append(record)
    return tuple(
        latest_snapshot_for_worker(tuple(grouped[worker_id]))
        for worker_id in sorted(grouped)
    )


def build_worker_timeline_summary(
    timeline: tuple[WorkerTimelineRecord, ...],
) -> dict[str, Any]:
    count = len(timeline)
    worker_counts = Counter(record.worker_id for record in timeline)
    status_counts = Counter(record.status for record in timeline)
    method_counts = Counter(record.mapping_method for record in timeline)
    fallback_count = method_counts.get("continuity_fallback", 0) + method_counts.get(
        "start_segment_seed", 0
    )
    reliabilities = [record.position_reliability for record in timeline]
    segments = sorted(
        {record.current_segment for record in timeline if record.current_segment is not None}
    )
    warnings = [
        "final anchor-based reliability is not computed yet",
        "timeline is pre-distance-enrichment",
    ]
    if fallback_count:
        warnings.insert(
            0,
            "fallback-based timeline records preserve low mapping confidence and are for demo continuity",
        )
    return {
        "timeline_record_count": count,
        "worker_count": len(worker_counts),
        "time_step_min": min((record.time_step for record in timeline), default=None),
        "time_step_max": max((record.time_step for record in timeline), default=None),
        "timestamp_min_s": min((record.timestamp_s for record in timeline), default=None),
        "timestamp_max_s": max((record.timestamp_s for record in timeline), default=None),
        "unique_segments_visited": segments,
        "unique_segments_visited_count": len(segments),
        "records_by_worker": dict(sorted(worker_counts.items())),
        "records_by_status": {
            status: status_counts.get(status, 0)
            for status in ("safe", "uncertain", "low_confidence")
        },
        "records_by_mapping_method": {
            method: method_counts.get(method, 0)
            for method in (
                "bounds_contains",
                "nearest_center",
                "continuity_fallback",
                "start_segment_seed",
                "unknown",
            )
        },
        "mean_base_position_reliability": (
            round(sum(reliabilities) / count, 4) if count else 0.0
        ),
        "min_base_position_reliability": (
            round(min(reliabilities), 4) if reliabilities else 0.0
        ),
        "fallback_record_count": fallback_count,
        "fallback_record_ratio": round(fallback_count / count, 4) if count else 0.0,
        "warnings": warnings,
    }


def validate_timeline_result(result: TimelineBuildResult) -> None:
    if not result.timeline:
        raise ValueError("timeline contains no records")
    if not result.latest_workers:
        raise ValueError("timeline contains no latest worker snapshots")
    for record in result.timeline:
        if not record.worker_id or not record.tag_id:
            raise ValueError("timeline worker_id and tag_id must be non-empty")
        if not all(isfinite(value) for value in record.position.to_dict().values()):
            raise ValueError("timeline position must contain finite coordinates")
        if record.time_step < 0:
            raise ValueError("timeline time_step must be non-negative")
        if not 0.0 <= record.position_reliability <= 1.0:
            raise ValueError("position_reliability must be in [0, 1]")
        if not 0.0 <= record.mapping_confidence <= 1.0:
            raise ValueError("mapping_confidence must be in [0, 1]")
        if not 0.0 <= record.continuity_score <= 1.0:
            raise ValueError("continuity_score must be in [0, 1]")
        if record.tracking_status != "pending_anchor_enrichment":
            raise ValueError("timeline record was enriched before the enrichment stage")
        if record.source_position_type != "mocap_ground_truth":
            raise ValueError("unexpected source_position_type")
    latest_ids = [snapshot.worker_id for snapshot in result.latest_workers]
    if len(latest_ids) != len(set(latest_ids)):
        raise ValueError("latest worker IDs must be unique")
    if result.summary.get("timeline_record_count") != len(result.timeline):
        raise ValueError("timeline summary count does not match timeline")


def build_timeline(
    mapping_result: SegmentMappingResult | None = None,
    config: dict | None = None,
) -> TimelineBuildResult:
    config = load_config() if config is None else config
    mapping_result = map_segments(config=config) if mapping_result is None else mapping_result
    timeline = build_timeline_records(mapping_result.mapped_positions)
    latest_workers = build_latest_worker_snapshots(timeline)
    summary = build_worker_timeline_summary(timeline)
    result = TimelineBuildResult(timeline, latest_workers, summary)
    validate_timeline_result(result)
    return result


def _self_check() -> None:
    config = load_config()
    result = build_timeline(config=config)
    validate_timeline_result(result)
    assert result.timeline
    assert result.latest_workers
    assert all(
        record.tracking_status == "pending_anchor_enrichment"
        for record in result.timeline
    )
    for snapshot in result.latest_workers:
        payload = snapshot.to_dict()
        assert "mapped_segment_id" in payload
        assert "uwb_pose" in payload
        assert "motion_status" in payload
        assert payload["mapped_segment_id"] == payload["current_segment"]
        assert payload["uwb_pose"] == payload["position"]
        assert payload["motion_status"] == payload["status"]
    print(json.dumps(result.to_summary(), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    _self_check()
    print("timeline_builder.py self-check passed")
