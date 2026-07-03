"""Build rule-based UWB worker behavior anomaly events.

This module reads existing UWB in-memory pipeline results and Haki segment graph/risk
handoffs. It does not write files and does not perform emergency routing.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path
import sys
from typing import Any

try:
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.core import WorkerTimelineRecord, normalize_segment_id, to_jsonable
    from backend.uwb_processing.distance_matrix import compute_distance_matrix
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.timeline_builder import build_timeline
    from backend.uwb_processing.timeline_enricher import TimelineEnrichmentResult, enrich_timeline
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.core import WorkerTimelineRecord, normalize_segment_id, to_jsonable
    from backend.uwb_processing.distance_matrix import compute_distance_matrix
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.timeline_builder import build_timeline
    from backend.uwb_processing.timeline_enricher import TimelineEnrichmentResult, enrich_timeline


ALLOWED_EVENT_TYPES = {
    "stationary_too_long",
    "low_position_reliability",
    "tracking_lost_in_risky_segment",
    "entered_high_risk_segment",
    "near_blocked_segment",
    "route_deviation",
}
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}

DEFAULT_THRESHOLDS = {
    "low_reliability_threshold": 0.35,
    "stationary_time_threshold_s": 45.0,
    "high_risk_segment_threshold": 0.70,
    "near_blocked_graph_distance": 2,
    "route_deviation_graph_distance": 3,
}


@dataclass(frozen=True)
class BehaviorAnomalyEvent:
    event_id: str
    worker_id: str
    tag_id: str
    time_step: int
    timestamp_s: float
    segment_id: str | None
    event_type: str
    severity: str
    score: float
    position_reliability: float
    tracking_status: str
    reason: str
    source: str = "uwb_behavior_anomaly"
    mvp_rule_based: bool = True

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class BehaviorAnomalyBuildResult:
    events: tuple[BehaviorAnomalyEvent, ...]
    summary: dict[str, Any]
    warnings: tuple[str, ...]

    def to_summary(self) -> dict[str, Any]:
        return to_jsonable(self.summary)

    def to_events_payload(self) -> dict[str, Any]:
        return {
            "source": "uwb_behavior_anomaly",
            "mvp_rule_based": True,
            "events": [event.to_dict() for event in self.events],
            "summary": self.to_summary(),
            "warnings": list(self.warnings),
        }

    def to_summary_payload(self) -> dict[str, Any]:
        return {
            "source": "uwb_behavior_anomaly",
            "mvp_rule_based": True,
            "summary": self.to_summary(),
            "warnings": list(self.warnings),
        }


def _behavior_config(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("behavior_anomaly")
    if not isinstance(raw, dict):
        raw = {}
    merged = dict(DEFAULT_THRESHOLDS)
    for key in DEFAULT_THRESHOLDS:
        if key in raw:
            merged[key] = raw[key]
    return merged


def _finite_thresholds(config: dict[str, Any]) -> dict[str, float | int]:
    raw = _behavior_config(config)
    thresholds: dict[str, float | int] = {}
    for key, default in DEFAULT_THRESHOLDS.items():
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise ValueError(f"behavior_anomaly.{key} must be a finite number")
        if key.endswith("graph_distance"):
            if int(value) < 1:
                raise ValueError(f"behavior_anomaly.{key} must be at least 1")
            thresholds[key] = int(value)
        else:
            if float(value) < 0:
                raise ValueError(f"behavior_anomaly.{key} must be non-negative")
            thresholds[key] = float(value)
    return thresholds


def _segment_risk(dataset: SegmentDataset, segment_id: str | None) -> float:
    if segment_id is None:
        return 0.0
    try:
        canonical = normalize_segment_id(segment_id)
    except ValueError:
        return 0.0
    segment = dataset.segments.get(canonical)
    if segment is None:
        return 0.0
    if segment.geometry_risk is not None:
        return float(segment.geometry_risk)
    return 1.0 if segment.is_risky else 0.0


def _severity_from_score(score: float) -> str:
    if score >= 90.0:
        return "critical"
    if score >= 70.0:
        return "high"
    if score >= 40.0:
        return "medium"
    return "low"


def _event(
    sequence: int,
    record: WorkerTimelineRecord,
    event_type: str,
    score: float,
    reason: str,
    severity: str | None = None,
) -> BehaviorAnomalyEvent:
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"unsupported anomaly event_type: {event_type}")
    bounded_score = round(max(0.0, min(100.0, float(score))), 4)
    selected_severity = severity or _severity_from_score(bounded_score)
    return BehaviorAnomalyEvent(
        event_id=f"UWB_ANOMALY_{sequence:06d}",
        worker_id=record.worker_id,
        tag_id=record.tag_id,
        time_step=record.time_step,
        timestamp_s=round(float(record.timestamp_s), 4),
        segment_id=record.current_segment,
        event_type=event_type,
        severity=selected_severity,
        score=bounded_score,
        position_reliability=round(float(record.position_reliability), 4),
        tracking_status=record.tracking_status,
        reason=reason,
    )


def _graph_distance(dataset: SegmentDataset, start_segment: str | None, end_segment: str | None, max_depth: int) -> int | None:
    if start_segment is None or end_segment is None:
        return None
    try:
        start = normalize_segment_id(start_segment)
        end = normalize_segment_id(end_segment)
    except ValueError:
        return None
    if start not in dataset.segments or end not in dataset.segments:
        return None
    if start == end:
        return 0
    queue = deque([(start, 0)])
    visited = {start}
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for neighbor in dataset.neighbors(current):
            if neighbor == end:
                return depth + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))
    return None


def _nearest_blocked_distance(dataset: SegmentDataset, segment_id: str | None, max_depth: int) -> int | None:
    distances = [
        distance
        for blocked in dataset.blocked_segments
        for distance in [_graph_distance(dataset, segment_id, blocked, max_depth)]
        if distance is not None
    ]
    return min(distances) if distances else None


def _records_by_worker(enrichment_result: TimelineEnrichmentResult) -> dict[str, tuple[WorkerTimelineRecord, ...]]:
    grouped: dict[str, list[WorkerTimelineRecord]] = {}
    for record in enrichment_result.enriched_timeline:
        grouped.setdefault(record.worker_id, []).append(record)
    return {
        worker_id: tuple(sorted(records, key=lambda item: (item.time_step, item.timestamp_s)))
        for worker_id, records in sorted(grouped.items())
    }


def build_behavior_anomalies(
    config: dict[str, Any] | None = None,
    dataset: SegmentDataset | None = None,
    enrichment_result: TimelineEnrichmentResult | None = None,
) -> BehaviorAnomalyBuildResult:
    """Build rule-based UWB behavior anomaly events in memory only."""
    config = load_config() if config is None else config
    dataset = load_segment_dataset(config) if dataset is None else dataset
    if enrichment_result is None:
        timeline_result = build_timeline(config=config)
        distance_result = compute_distance_matrix(timeline_result=timeline_result, dataset=dataset, config=config)
        enrichment_result = enrich_timeline(timeline_result=timeline_result, distance_result=distance_result, config=config)

    thresholds = _finite_thresholds(config)
    low_reliability_threshold = float(thresholds["low_reliability_threshold"])
    stationary_time_threshold_s = float(thresholds["stationary_time_threshold_s"])
    high_risk_segment_threshold = float(thresholds["high_risk_segment_threshold"])
    near_blocked_graph_distance = int(thresholds["near_blocked_graph_distance"])
    route_deviation_graph_distance = int(thresholds["route_deviation_graph_distance"])

    events: list[BehaviorAnomalyEvent] = []
    warnings: list[str] = [
        "behavior anomaly events are rule-based MVP analytics and not certified safety decisions",
        "route_deviation is graph-continuity analytics only and not emergency routing",
    ]
    if not dataset.blocked_segments:
        warnings.append("no blocked segment exists in Haki segment data; near_blocked_segment rule skipped")

    sequence = 1
    for worker_records in _records_by_worker(enrichment_result).values():
        previous_segment: str | None = None
        stationary_segment: str | None = None
        stationary_start_timestamp: float | None = None
        stationary_emitted_for: set[str] = set()
        for record in worker_records:
            segment_id = record.current_segment
            risk = _segment_risk(dataset, segment_id)

            if record.position_reliability < low_reliability_threshold:
                score = (1.0 - record.position_reliability) * 100.0
                events.append(_event(
                    sequence,
                    record,
                    "low_position_reliability",
                    score,
                    f"position_reliability {record.position_reliability:.4f} is below threshold {low_reliability_threshold:.4f}",
                ))
                sequence += 1

            if record.tracking_status == "no_tracking" and risk >= high_risk_segment_threshold:
                events.append(_event(
                    sequence,
                    record,
                    "tracking_lost_in_risky_segment",
                    max(90.0, risk * 100.0),
                    f"tracking_status is no_tracking in high-risk segment with risk {risk:.4f}",
                    severity="critical",
                ))
                sequence += 1

            if (
                previous_segment is not None
                and segment_id is not None
                and segment_id != previous_segment
                and risk >= high_risk_segment_threshold
            ):
                events.append(_event(
                    sequence,
                    record,
                    "entered_high_risk_segment",
                    max(70.0, risk * 100.0),
                    f"worker entered high-risk segment {segment_id} from {previous_segment}; risk {risk:.4f}",
                ))
                sequence += 1

            if dataset.blocked_segments and segment_id is not None:
                blocked_distance = _nearest_blocked_distance(dataset, segment_id, near_blocked_graph_distance)
                if blocked_distance is not None:
                    score = 100.0 if blocked_distance == 0 else max(40.0, 80.0 - (blocked_distance * 15.0))
                    events.append(_event(
                        sequence,
                        record,
                        "near_blocked_segment",
                        score,
                        f"worker segment is {blocked_distance} graph step(s) from a blocked segment",
                    ))
                    sequence += 1

            if previous_segment is not None and segment_id is not None and segment_id != previous_segment:
                distance = _graph_distance(dataset, previous_segment, segment_id, route_deviation_graph_distance)
                if distance is None:
                    events.append(_event(
                        sequence,
                        record,
                        "route_deviation",
                        75.0,
                        f"worker jumped from {previous_segment} to non-adjacent segment {segment_id} beyond {route_deviation_graph_distance} graph step(s)",
                        severity="high",
                    ))
                    sequence += 1

            if segment_id != stationary_segment:
                stationary_segment = segment_id
                stationary_start_timestamp = float(record.timestamp_s)
            elif segment_id is not None and stationary_start_timestamp is not None:
                duration_s = float(record.timestamp_s) - stationary_start_timestamp
                stationary_key = f"{record.worker_id}:{segment_id}:{stationary_start_timestamp:.4f}"
                if duration_s > stationary_time_threshold_s and stationary_key not in stationary_emitted_for:
                    stationary_emitted_for.add(stationary_key)
                    score = min(100.0, 40.0 + duration_s - stationary_time_threshold_s)
                    events.append(_event(
                        sequence,
                        record,
                        "stationary_too_long",
                        score,
                        f"worker stayed in {segment_id} for {duration_s:.1f}s, exceeding threshold {stationary_time_threshold_s:.1f}s",
                    ))
                    sequence += 1

            if segment_id is not None:
                previous_segment = segment_id

    events_tuple = tuple(sorted(events, key=lambda item: (item.time_step, item.worker_id, item.event_type, item.event_id)))
    type_counts = Counter(event.event_type for event in events_tuple)
    severity_counts = Counter(event.severity for event in events_tuple)
    worker_counts = Counter(event.worker_id for event in events_tuple)
    summary = {
        "source": "uwb_behavior_anomaly",
        "mvp_rule_based": True,
        "event_count": len(events_tuple),
        "event_count_by_type": {event_type: type_counts.get(event_type, 0) for event_type in sorted(ALLOWED_EVENT_TYPES)},
        "event_count_by_severity": {severity: severity_counts.get(severity, 0) for severity in ("low", "medium", "high", "critical")},
        "worker_count_with_events": len(worker_counts),
        "event_count_by_worker": dict(sorted(worker_counts.items())),
        "configured_thresholds": dict(sorted(thresholds.items())),
        "blocked_segment_count": len(dataset.blocked_segments),
        "high_risk_segment_threshold": high_risk_segment_threshold,
        "warnings": warnings,
    }
    result = BehaviorAnomalyBuildResult(events_tuple, summary, tuple(warnings))
    validate_behavior_anomaly_result(result, enrichment_result, dataset)
    return result


def validate_behavior_anomaly_result(
    result: BehaviorAnomalyBuildResult,
    enrichment_result: TimelineEnrichmentResult | None = None,
    dataset: SegmentDataset | None = None,
) -> None:
    event_ids: set[str] = set()
    known_workers: set[str] | None = None
    if enrichment_result is not None:
        known_workers = {record.worker_id for record in enrichment_result.enriched_timeline}
    for event in result.events:
        if event.event_id in event_ids:
            raise ValueError(f"duplicate behavior anomaly event_id: {event.event_id}")
        event_ids.add(event.event_id)
        if event.event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"invalid behavior anomaly event_type: {event.event_type}")
        if event.severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"invalid behavior anomaly severity: {event.severity}")
        if not event.worker_id or not event.tag_id or event.time_step < 0:
            raise ValueError("behavior anomaly event identity or time is invalid")
        if known_workers is not None and event.worker_id not in known_workers:
            raise ValueError(f"behavior anomaly references unknown worker: {event.worker_id}")
        if event.segment_id is not None and dataset is not None and not dataset.has_segment(event.segment_id):
            raise ValueError(f"behavior anomaly references unknown segment: {event.segment_id}")
        if not isfinite(event.timestamp_s) or not isfinite(event.score) or not 0.0 <= event.score <= 100.0:
            raise ValueError("behavior anomaly event timestamp or score is invalid")
        if not isfinite(event.position_reliability) or not 0.0 <= event.position_reliability <= 1.0:
            raise ValueError("behavior anomaly event position_reliability is invalid")
        if event.source != "uwb_behavior_anomaly" or event.mvp_rule_based is not True:
            raise ValueError("behavior anomaly event source contract is invalid")
        if not event.reason:
            raise ValueError("behavior anomaly event reason is required")
    type_counts = Counter(event.event_type for event in result.events)
    summary_counts = result.summary.get("event_count_by_type")
    if result.summary.get("event_count") != len(result.events):
        raise ValueError("behavior anomaly summary event_count mismatch")
    if not isinstance(summary_counts, dict):
        raise ValueError("behavior anomaly summary event_count_by_type is required")
    for event_type in ALLOWED_EVENT_TYPES:
        if summary_counts.get(event_type, 0) != type_counts.get(event_type, 0):
            raise ValueError(f"behavior anomaly summary count mismatch for {event_type}")
    json.dumps(result.to_events_payload())
    json.dumps(result.to_summary_payload())


def _self_check() -> None:
    config = load_config()
    dataset = load_segment_dataset(config)
    timeline_result = build_timeline(config=config)
    distance_result = compute_distance_matrix(timeline_result=timeline_result, dataset=dataset, config=config)
    enrichment_result = enrich_timeline(timeline_result=timeline_result, distance_result=distance_result, config=config)
    result = build_behavior_anomalies(config=config, dataset=dataset, enrichment_result=enrichment_result)
    validate_behavior_anomaly_result(result, enrichment_result, dataset)
    assert set(result.summary["event_count_by_type"]) == ALLOWED_EVENT_TYPES
    assert all(event.event_type in ALLOWED_EVENT_TYPES for event in result.events)
    print(json.dumps(result.to_summary_payload(), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    _self_check()
    print("behavior_anomaly_builder.py self-check passed")
