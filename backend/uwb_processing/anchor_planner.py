"""Plan dynamic UWB anchors from Haki's bounds-center graph geometry.

The current Haki handoff provides bounds-center geometry. Dynamic anchor planning is performed at segment/graph level using segment centers, bounds, graph edges and edge weights. Exact centerline-based tunnel curve placement is not available until Haki provides centerline/start-end geometry.

All placement and coverage results are in-memory infrastructure estimates. They
do not claim true line-of-sight or exact LiDAR tunnel-curve placement.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from math import ceil, isfinite
import re
from typing import Any

try:
    from .config_loader import load_config
    from .core import (
        Anchor,
        Point3D,
        Segment,
        angle_between_vectors_deg,
        clamp,
        distance_3d,
        normalize_anchor_id,
        normalize_segment_id,
        vector_between,
    )
    from .segment_loader import SegmentDataset, load_segment_dataset
except ImportError:  # Supports ``python backend/uwb_processing/anchor_planner.py``.
    from config_loader import load_config  # type: ignore
    from core import (  # type: ignore
        Anchor,
        Point3D,
        Segment,
        angle_between_vectors_deg,
        clamp,
        distance_3d,
        normalize_anchor_id,
        normalize_segment_id,
        vector_between,
    )
    from segment_loader import SegmentDataset, load_segment_dataset  # type: ignore


@dataclass(frozen=True)
class AnchorPlanResult:
    anchors: tuple[Anchor, ...]
    coverage_report: dict[str, Any]
    anchors_by_segment: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        reasons = self.coverage_report.get("anchors_by_reason", {})
        return {
            "anchor_count": len(self.anchors),
            "covered_segment_count": self.coverage_report.get("covered_segment_count", 0),
            "undercovered_segment_count": self.coverage_report.get(
                "undercovered_segment_count", 0
            ),
            "exit_anchor_count": reasons.get("exit_gateway", 0),
            "junction_anchor_count": reasons.get("junction", 0),
            "dead_end_anchor_count": reasons.get("dead_end", 0),
            "risk_anchor_count": reasons.get("risk_density", 0),
            "curve_anchor_count": reasons.get("curve_turn", 0),
            "long_edge_anchor_count": reasons.get("long_edge_intermediate", 0),
            "min_visible_anchor_estimate": self.coverage_report.get(
                "min_visible_anchor_estimate", 0
            ),
            "mean_visible_anchor_estimate": self.coverage_report.get(
                "mean_visible_anchor_estimate", 0.0
            ),
            "max_visible_anchor_estimate": self.coverage_report.get(
                "max_visible_anchor_estimate", 0
            ),
            "warnings": list(self.coverage_report.get("warnings", [])),
        }


def get_anchor_position_for_segment(segment: Segment, anchor_height_m: float) -> Point3D:
    height = float(anchor_height_m)
    if not isfinite(height):
        raise ValueError("anchor_height_m must be finite")
    representative = segment.center or (segment.bounds.center() if segment.bounds else None)
    x = representative.x if representative else 0.0
    y = representative.y if representative else 0.0
    if segment.bounds:
        z = clamp(
            segment.bounds.min_z + height,
            segment.bounds.min_z,
            segment.bounds.max_z,
        )
    elif representative:
        z = representative.z
    else:
        z = height
    return Point3D(x, y, z)


def segment_is_junction(dataset: SegmentDataset, segment_id: str) -> bool:
    return dataset.degree(segment_id) >= 3


def segment_is_dead_end(dataset: SegmentDataset, segment_id: str) -> bool:
    return dataset.degree(segment_id) == 1


def segment_is_exit(segment: Segment) -> bool:
    return segment.is_exit or segment.is_exit_candidate


def segment_risk_score(segment: Segment) -> float:
    if segment.geometry_risk is None:
        return 0.0
    value = float(segment.geometry_risk)
    if not isfinite(value):
        raise ValueError(f"Non-finite geometry risk for {segment.segment_id}")
    if value > 1.0:
        value /= 100.0
    return clamp(value)


def segment_is_high_risk(segment: Segment, threshold: float = 0.70) -> bool:
    return segment.is_risky or segment_risk_score(segment) >= clamp(threshold)


def segment_is_curve_or_turn(
    dataset: SegmentDataset, segment_id: str, threshold_deg: float
) -> bool:
    canonical = normalize_segment_id(segment_id)
    neighbors = dataset.neighbors(canonical)
    segment = dataset.get_segment(canonical)
    if len(neighbors) != 2 or segment.center is None:
        return False
    first = dataset.get_segment(neighbors[0])
    second = dataset.get_segment(neighbors[1])
    if first.center is None or second.center is None:
        return False
    angle = angle_between_vectors_deg(
        vector_between(segment.center, first.center),
        vector_between(segment.center, second.center),
    )
    return abs(180.0 - angle) >= float(threshold_deg)


def important_reasons_for_segment(
    dataset: SegmentDataset, segment: Segment, config: dict[str, Any]
) -> list[str]:
    placement = config["anchor_placement"]
    reasons = ["base_coverage"]
    if placement["junction_extra_anchor"] and segment_is_junction(dataset, segment.segment_id):
        reasons.append("junction")
    if placement["dead_end_extra_anchor"] and segment_is_dead_end(dataset, segment.segment_id):
        reasons.append("dead_end")
    if placement["exit_extra_anchor"] and segment_is_exit(segment):
        reasons.append("exit_gateway")
    if placement["risk_zone_extra_anchor"] and segment_is_high_risk(segment):
        reasons.append("risk_density")
    if placement["curve_extra_anchor"] and segment_is_curve_or_turn(
        dataset, segment.segment_id, placement["turn_angle_threshold_deg"]
    ):
        reasons.append("curve_turn")
    if segment.length_m is not None and ceil(
        max(segment.length_m, 0.0) / placement["anchor_spacing_m"]
    ) > 1:
        reasons.append("long_segment")
    return reasons


def anchor_count_for_segment(
    segment: Segment, config: dict[str, Any], reasons: list[str]
) -> int:
    spacing = float(config["anchor_placement"]["anchor_spacing_m"])
    count = 1
    if segment.length_m is not None:
        count = max(count, ceil(max(segment.length_m, 0.0) / spacing))
    count += sum(
        reason in reasons
        for reason in ("junction", "dead_end", "exit_gateway", "risk_density", "curve_turn")
    )
    return max(1, count)


def clamp_point_to_bounds(point: Point3D, segment: Segment) -> Point3D:
    if segment.bounds is None:
        return point
    return Point3D(
        clamp(point.x, segment.bounds.min_x, segment.bounds.max_x),
        clamp(point.y, segment.bounds.min_y, segment.bounds.max_y),
        clamp(point.z, segment.bounds.min_z, segment.bounds.max_z),
    )


def make_segment_anchor_positions(
    dataset: SegmentDataset,
    segment: Segment,
    count: int,
    config: dict[str, Any],
) -> list[Point3D]:
    placement = config["anchor_placement"]
    base = get_anchor_position_for_segment(segment, placement["anchor_height_m"])
    if count <= 1:
        return [base]
    neighbor_centers = [
        dataset.get_segment(neighbor).center
        for neighbor in dataset.neighbors(segment.segment_id)
        if dataset.get_segment(neighbor).center is not None
    ]
    positions = [base]
    if neighbor_centers:
        for index in range(1, count):
            target = neighbor_centers[(index - 1) % len(neighbor_centers)]
            cycle = (index - 1) // len(neighbor_centers)
            fraction = min(0.45, 0.18 + cycle * 0.09)
            candidate = clamp_point_to_bounds(
                Point3D(
                    base.x + (target.x - base.x) * fraction,
                    base.y + (target.y - base.y) * fraction,
                    base.z,
                ),
                segment,
            )
            if candidate not in positions:
                positions.append(candidate)
    elif segment.bounds:
        span = segment.bounds.max_x - segment.bounds.min_x
        for index in range(1, count):
            fraction = index / count
            candidate = Point3D(
                segment.bounds.min_x + span * fraction,
                base.y,
                base.z,
            )
            candidate = clamp_point_to_bounds(candidate, segment)
            if candidate not in positions:
                positions.append(candidate)
    return positions


def build_anchor_id(index: int) -> str:
    if isinstance(index, bool) or not isinstance(index, int) or index <= 0:
        raise ValueError("anchor index must be a positive integer")
    return normalize_anchor_id(index)


def add_anchor_candidate(
    candidates: list[dict[str, Any]],
    segment_id: str,
    position: Point3D,
    coverage_radius_m: float,
    reason: str,
    anchor_type: str = "relay",
) -> None:
    canonical = normalize_segment_id(segment_id)
    key = (canonical, round(position.x, 4), round(position.y, 4), round(position.z, 4))
    for candidate in candidates:
        existing = candidate["position"]
        existing_key = (
            candidate["segment_id"],
            round(existing.x, 4),
            round(existing.y, 4),
            round(existing.z, 4),
        )
        if existing_key == key:
            merged = set(candidate["placement_reason"].split("+"))
            merged.update(reason.split("+"))
            candidate["placement_reason"] = "+".join(sorted(merged))
            if candidate["anchor_type"] == "relay" and anchor_type != "relay":
                candidate["anchor_type"] = anchor_type
            return
    candidates.append(
        {
            "segment_id": canonical,
            "position": position,
            "coverage_radius_m": float(coverage_radius_m),
            "placement_reason": reason,
            "anchor_type": anchor_type,
        }
    )


def add_long_edge_anchors(
    candidates: list[dict[str, Any]],
    dataset: SegmentDataset,
    config: dict[str, Any],
) -> None:
    placement = config["anchor_placement"]
    threshold = float(placement["long_edge_threshold_m"])
    radius = float(placement["coverage_radius_m"])
    height = float(placement["anchor_height_m"])
    for edge in sorted(dataset.edges, key=lambda item: item.key()):
        if edge.weight <= threshold:
            continue
        source = dataset.get_segment(edge.source)
        target = dataset.get_segment(edge.target)
        if source.center is None or target.center is None:
            continue
        intermediate_count = max(1, ceil(edge.weight / threshold) - 1)
        for index in range(1, intermediate_count + 1):
            fraction = index / (intermediate_count + 1)
            endpoint = source if fraction <= 0.5 else target
            z = source.center.z + (target.center.z - source.center.z) * fraction
            if endpoint.bounds:
                z = clamp(
                    endpoint.bounds.min_z + height,
                    endpoint.bounds.min_z,
                    endpoint.bounds.max_z,
                )
            point = Point3D(
                source.center.x + (target.center.x - source.center.x) * fraction,
                source.center.y + (target.center.y - source.center.y) * fraction,
                z,
            )
            point = clamp_point_to_bounds(point, endpoint)
            add_anchor_candidate(
                candidates,
                endpoint.segment_id,
                point,
                radius,
                "long_edge_intermediate",
                "long_edge_relay",
            )


def finalize_anchors(
    candidates: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[Anchor, ...]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            item["segment_id"],
            item["placement_reason"],
            item["position"].x,
            item["position"].y,
            item["position"].z,
        ),
    )
    maximum = config["anchor_placement"].get("max_anchor_count")
    if maximum is not None:
        ordered = ordered[: int(maximum)]
    return tuple(
        Anchor(
            anchor_id=build_anchor_id(index),
            segment_id=item["segment_id"],
            position=item["position"],
            coverage_radius_m=item["coverage_radius_m"],
            anchor_type=item["anchor_type"],
            placement_reason=item["placement_reason"],
        )
        for index, item in enumerate(ordered, 1)
    )


def estimate_visible_anchors_for_segment(
    segment: Segment,
    anchors: tuple[Anchor, ...],
    coverage_radius_m: float,
) -> tuple[int, tuple[str, ...]]:
    representative = segment.center or (segment.bounds.center() if segment.bounds else None)
    if representative is None:
        return 0, ()
    visible = tuple(
        anchor.anchor_id
        for anchor in anchors
        if anchor.status == "active"
        and distance_3d(representative, anchor.position) <= coverage_radius_m
    )
    return len(visible), visible


def build_coverage_report(
    dataset: SegmentDataset,
    anchors: tuple[Anchor, ...],
    config: dict[str, Any],
) -> dict[str, Any]:
    placement = config["anchor_placement"]
    radius = float(placement["coverage_radius_m"])
    target = int(placement["min_visible_anchors_2d"]) + int(placement["redundancy"])
    counts: list[int] = []
    undercovered: list[dict[str, Any]] = []
    for segment_id, segment in sorted(dataset.segments.items()):
        count, visible = estimate_visible_anchors_for_segment(segment, anchors, radius)
        counts.append(count)
        if count < target:
            undercovered.append(
                {
                    "segment_id": segment_id,
                    "visible_anchor_estimate": count,
                    "visible_anchors": list(visible),
                    "target_visible_anchors": target,
                }
            )
    reasons: Counter[str] = Counter()
    for anchor in anchors:
        reasons.update(anchor.placement_reason.split("+"))
    return {
        "geometry_mode": placement["geometry_mode"],
        "coverage_radius_m": radius,
        "anchor_spacing_m": float(placement["anchor_spacing_m"]),
        "min_visible_anchors_2d": int(placement["min_visible_anchors_2d"]),
        "redundancy": int(placement["redundancy"]),
        "target_visible_anchors": target,
        "segment_count": len(dataset.segments),
        "generated_anchor_count": len(anchors),
        "covered_segment_count": len(dataset.segments) - len(undercovered),
        "undercovered_segment_count": len(undercovered),
        "undercovered_segments": undercovered,
        "min_visible_anchor_estimate": min(counts) if counts else 0,
        "mean_visible_anchor_estimate": round(sum(counts) / len(counts), 4) if counts else 0.0,
        "max_visible_anchor_estimate": max(counts) if counts else 0,
        "anchors_by_reason": dict(sorted(reasons.items())),
        "warnings": [
            "coverage is estimated using bounds-center graph geometry, not true LOS",
            "centerline/start/end unavailable; long-edge anchors are approximate",
        ],
    }


def build_anchors_by_segment(
    anchors: tuple[Anchor, ...],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for anchor in anchors:
        grouped.setdefault(anchor.segment_id, []).append(anchor.anchor_id)
    return {
        segment_id: tuple(sorted(anchor_ids))
        for segment_id, anchor_ids in sorted(grouped.items())
    }


def plan_anchors(
    dataset: SegmentDataset | None = None,
    config: dict[str, Any] | None = None,
) -> AnchorPlanResult:
    normalized_config = load_config() if config is None else config
    segment_dataset = (
        load_segment_dataset(normalized_config) if dataset is None else dataset
    )
    placement = normalized_config["anchor_placement"]
    candidates: list[dict[str, Any]] = []
    for segment in segment_dataset.segments.values():
        reasons = important_reasons_for_segment(segment_dataset, segment, normalized_config)
        count = anchor_count_for_segment(segment, normalized_config, reasons)
        positions = make_segment_anchor_positions(
            segment_dataset, segment, count, normalized_config
        )
        anchor_type = (
            "gateway" if "exit_gateway" in reasons
            else "junction" if "junction" in reasons
            else "relay"
        )
        reason = "+".join(reasons)
        for position in positions:
            add_anchor_candidate(
                candidates,
                segment.segment_id,
                position,
                placement["coverage_radius_m"],
                reason,
                anchor_type,
            )
    add_long_edge_anchors(candidates, segment_dataset, normalized_config)
    anchors = finalize_anchors(candidates, normalized_config)
    result = AnchorPlanResult(
        anchors=anchors,
        coverage_report=build_coverage_report(
            segment_dataset, anchors, normalized_config
        ),
        anchors_by_segment=build_anchors_by_segment(anchors),
    )
    validate_anchor_plan(segment_dataset, result)
    return result


def validate_anchor_plan(dataset: SegmentDataset, result: AnchorPlanResult) -> None:
    if not result.anchors:
        raise ValueError("anchor plan must contain at least one anchor")
    ids: set[str] = set()
    for anchor in result.anchors:
        if anchor.anchor_id in ids:
            raise ValueError(f"duplicate anchor ID: {anchor.anchor_id}")
        if not re.fullmatch(r"A\d{3}", anchor.anchor_id):
            raise ValueError(f"non-canonical anchor ID: {anchor.anchor_id}")
        if anchor.segment_id not in dataset.segments:
            raise ValueError(f"anchor references unknown segment: {anchor.segment_id}")
        if not all(isfinite(value) for value in (
            anchor.position.x, anchor.position.y, anchor.position.z
        )):
            raise ValueError(f"anchor position is not finite: {anchor.anchor_id}")
        if not isfinite(anchor.coverage_radius_m) or anchor.coverage_radius_m <= 0.0:
            raise ValueError(f"invalid coverage radius: {anchor.anchor_id}")
        ids.add(anchor.anchor_id)
    if result.coverage_report.get("generated_anchor_count") != len(result.anchors):
        raise ValueError("coverage report anchor count does not match anchor plan")


def _self_check() -> None:
    config = load_config()
    dataset = load_segment_dataset(config)
    result = plan_anchors(dataset, config)
    validate_anchor_plan(dataset, result)
    assert result.anchors
    assert all(anchor.anchor_id.startswith("A") for anchor in result.anchors)
    assert all(anchor.segment_id in dataset.segments for anchor in result.anchors)
    assert result.coverage_report["generated_anchor_count"] == len(result.anchors)
    print(json.dumps(result.to_summary(), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    _self_check()
    print("anchor_planner.py self-check passed")
