"""Plan graph-constrained infrastructure cables between UWB anchors.

Cable topology follows Haki graph adjacency and is not emergency routing. Haki
provides bounds-center graph geometry, so waypoints are approximate and do not
represent exact tunnel-wall or centerline routing. This module writes no files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import json
from math import isfinite
import re
from typing import Any

try:
    from .anchor_planner import AnchorPlanResult, plan_anchors
    from .config_loader import load_config
    from .core import (
        Anchor,
        CableLink,
        Point3D,
        Segment,
        distance_3d,
        normalize_anchor_id,
        normalize_cable_id,
        normalize_segment_id,
    )
    from .segment_loader import SegmentDataset, load_segment_dataset
except ImportError:  # Supports ``python backend/uwb_processing/cable_planner.py``.
    from anchor_planner import AnchorPlanResult, plan_anchors  # type: ignore
    from config_loader import load_config  # type: ignore
    from core import (  # type: ignore
        Anchor,
        CableLink,
        Point3D,
        Segment,
        distance_3d,
        normalize_anchor_id,
        normalize_cable_id,
        normalize_segment_id,
    )
    from segment_loader import SegmentDataset, load_segment_dataset  # type: ignore


ALLOWED_CONNECTION_TYPES = {"primary", "cross_link", "branch", "intra_segment"}


@dataclass(frozen=True)
class CablePlanResult:
    cables: tuple[CableLink, ...]
    head_end_anchor_id: str
    head_end_segment_id: str
    cable_report: dict[str, Any]
    cables_by_anchor: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        report = self.cable_report
        return {
            "cable_count": len(self.cables),
            "primary_count": report.get("primary_count", 0),
            "cross_link_count": report.get("cross_link_count", 0),
            "branch_count": report.get("branch_count", 0),
            "intra_segment_count": report.get("intra_segment_count", 0),
            "head_end_anchor_id": self.head_end_anchor_id,
            "head_end_segment_id": self.head_end_segment_id,
            "connected_anchor_count": report.get("connected_anchor_count", 0),
            "isolated_anchor_count": report.get("isolated_anchor_count", 0),
            "max_anchor_degree": report.get("max_anchor_degree", 0),
            "mean_anchor_degree": report.get("mean_anchor_degree", 0.0),
            "warnings": list(report.get("warnings", [])),
        }


def build_anchor_lookup(anchors: tuple[Anchor, ...]) -> dict[str, Anchor]:
    lookup: dict[str, Anchor] = {}
    for anchor in anchors:
        if anchor.anchor_id in lookup:
            raise ValueError(f"duplicate anchor ID: {anchor.anchor_id}")
        lookup[anchor.anchor_id] = anchor
    return lookup


def group_anchors_by_segment(
    anchors: tuple[Anchor, ...],
) -> dict[str, tuple[Anchor, ...]]:
    grouped: dict[str, list[Anchor]] = {}
    for anchor in anchors:
        grouped.setdefault(anchor.segment_id, []).append(anchor)
    return {
        segment_id: tuple(sorted(values, key=lambda anchor: anchor.anchor_id))
        for segment_id, values in sorted(grouped.items())
    }


def select_head_end_anchor(
    dataset: SegmentDataset,
    anchors: tuple[Anchor, ...],
    config: dict[str, Any],
) -> Anchor:
    if not anchors:
        raise ValueError("cannot select a head end without anchors")
    mode = config["cable_topology"].get("head_end_selection", "nearest_exit")
    if mode == "first_anchor":
        return min(anchors, key=lambda anchor: anchor.anchor_id)
    exit_anchors = [anchor for anchor in anchors if anchor.segment_id in dataset.exits]
    if exit_anchors:
        return min(exit_anchors, key=lambda anchor: (anchor.segment_id, anchor.anchor_id))
    return min(anchors, key=lambda anchor: anchor.anchor_id)


def edge_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((normalize_anchor_id(a), normalize_anchor_id(b))))


def segment_edge_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((normalize_segment_id(a), normalize_segment_id(b))))


def shortest_segment_path(
    dataset: SegmentDataset, start_segment: str, end_segment: str
) -> tuple[str, ...]:
    start = normalize_segment_id(start_segment)
    end = normalize_segment_id(end_segment)
    if start not in dataset.segments or end not in dataset.segments:
        return ()
    if start == end:
        return (start,)
    queue: list[tuple[float, str, tuple[str, ...]]] = [(0.0, start, (start,))]
    best = {start: 0.0}
    while queue:
        cost, current, path = heapq.heappop(queue)
        if current == end:
            return path
        if cost > best.get(current, float("inf")):
            continue
        for neighbor in dataset.neighbors(current):
            weight = dataset.edge_weight(current, neighbor, 1.0)
            next_cost = cost + (weight if weight is not None else 1.0)
            if next_cost >= best.get(neighbor, float("inf")):
                continue
            best[neighbor] = next_cost
            heapq.heappush(queue, (next_cost, neighbor, path + (neighbor,)))
    return ()


def distance_between_anchors(a: Anchor, b: Anchor) -> float:
    return distance_3d(a.position, b.position)


def clamp_point_to_segment_bounds(point: Point3D, segment: Segment) -> Point3D:
    """Clamp a point into a segment's bounds when bounds are available."""
    if segment.bounds is None:
        return point
    return Point3D(
        max(segment.bounds.min_x, min(point.x, segment.bounds.max_x)),
        max(segment.bounds.min_y, min(point.y, segment.bounds.max_y)),
        max(segment.bounds.min_z, min(point.z, segment.bounds.max_z)),
    )


def get_segment_representative_position(segment: Segment) -> Point3D | None:
    """Return the best available representative position for a segment."""
    return segment.center or (segment.bounds.center() if segment.bounds else None)


def infer_segment_direction(
    dataset: SegmentDataset, segment_id: str
) -> tuple[float, float, float] | None:
    """Infer a corridor direction from neighboring segment centers."""
    segment = dataset.get_segment(segment_id)
    representative = get_segment_representative_position(segment)
    neighbors = [
        get_segment_representative_position(dataset.get_segment(neighbor_id))
        for neighbor_id in dataset.neighbors(segment_id)
    ]
    centers = [point for point in neighbors if point is not None]
    if len(centers) >= 2:
        first, second = max(
            (
                (left, right)
                for index, left in enumerate(centers)
                for right in centers[index + 1 :]
            ),
            key=lambda pair: distance_3d(pair[0], pair[1]),
        )
        return (
            second.x - first.x,
            second.y - first.y,
            second.z - first.z,
        )
    if len(centers) == 1 and representative is not None:
        neighbor = centers[0]
        return (
            neighbor.x - representative.x,
            neighbor.y - representative.y,
            neighbor.z - representative.z,
        )
    return None


def wall_point_for_segment(
    dataset: SegmentDataset,
    segment_id: str,
    reference_position: Point3D | None,
    config: dict[str, Any],
) -> Point3D | None:
    """Return a bounds-clamped wall-adjacent approximation for one segment."""
    segment = dataset.get_segment(segment_id)
    representative = reference_position or get_segment_representative_position(segment)
    if segment.bounds is None:
        return representative

    bounds = segment.bounds
    wall_offset = max(0.0, float(config["cable_topology"]["wall_offset_m"]))
    anchor_height = float(config.get("anchor_placement", {}).get("anchor_height_m", 0.0))
    reference = representative or bounds.center()
    direction = infer_segment_direction(dataset, segment_id)
    if direction is None or (direction[0] == 0.0 and direction[1] == 0.0):
        x_dominant = (bounds.max_x - bounds.min_x) >= (bounds.max_y - bounds.min_y)
    else:
        x_dominant = abs(direction[0]) >= abs(direction[1])
    if x_dominant:
        point = Point3D(
            reference.x,
            bounds.min_y + wall_offset,
            bounds.min_z + anchor_height,
        )
    else:
        point = Point3D(
            bounds.min_x + wall_offset,
            reference.y,
            bounds.min_z + anchor_height,
        )
    return clamp_point_to_segment_bounds(point, segment)


def make_wall_constrained_waypoints_for_segment_path(
    dataset: SegmentDataset,
    start_anchor: Anchor,
    end_anchor: Anchor,
    segment_path: tuple[str, ...],
    config: dict[str, Any],
) -> tuple[Point3D, ...]:
    """Build one wall-adjacent, bounds-constrained waypoint per path segment.

    Cable waypoints are constrained using segment bounds and wall offsets. This is a bounds-based wall-adjacent approximation, not exact mesh-based wall routing. Exact wall routing requires Haki to provide tunnel wall geometry, centerline/start-end geometry, or a wall/path polyline layer.
    """
    if not segment_path:
        raise ValueError("segment_path must not be empty")
    if len(segment_path) == 1:
        references = (start_anchor.position, end_anchor.position)
        generated = [
            wall_point_for_segment(dataset, segment_path[0], reference, config)
            for reference in references
        ]
    else:
        generated = []
        for index, segment_id in enumerate(segment_path):
            if index == 0:
                reference = start_anchor.position
            elif index == len(segment_path) - 1:
                reference = end_anchor.position
            else:
                reference = get_segment_representative_position(
                    dataset.get_segment(segment_id)
                )
            generated.append(
                wall_point_for_segment(dataset, segment_id, reference, config)
            )
    waypoints: list[Point3D] = []
    for point in generated:
        if point is not None and (not waypoints or point != waypoints[-1]):
            waypoints.append(point)
    if not waypoints:
        fallback = start_anchor.position
        waypoints.append(fallback)
        if end_anchor.position != fallback:
            waypoints.append(end_anchor.position)
    return tuple(waypoints)


def validate_wall_waypoints_for_path(
    dataset: SegmentDataset,
    segment_path: tuple[str, ...],
    waypoints: tuple[Point3D, ...],
) -> tuple[bool, list[str]]:
    """Validate finite wall waypoints and bounded-segment containment."""
    warnings: list[str] = []
    if not waypoints:
        return False, ["cable path has no waypoints"]
    if any(
        not all(isfinite(value) for value in (point.x, point.y, point.z))
        for point in waypoints
    ):
        return False, ["cable path contains non-finite waypoint coordinates"]
    for segment_id in segment_path:
        segment = dataset.get_segment(segment_id)
        if segment.bounds is None:
            warnings.append(
                f"{segment_id} has no bounds; center/reference waypoint fallback was used"
            )
            continue
        if not any(segment.bounds.contains(point) for point in waypoints):
            return False, warnings + [
                f"no wall waypoint for {segment_id} is inside segment bounds"
            ]
    return True, warnings


def add_cable_candidate(
    candidates: list[dict[str, Any]],
    from_anchor: Anchor,
    to_anchor: Anchor,
    segment_path: tuple[str, ...],
    waypoints: tuple[Point3D, ...],
    connection_type: str,
    cable_type: str = "ethernet_or_fiber",
) -> None:
    if from_anchor.anchor_id == to_anchor.anchor_id:
        return
    if not segment_path:
        raise ValueError("cable candidate segment_path must not be empty")
    if connection_type not in ALLOWED_CONNECTION_TYPES:
        raise ValueError(f"unsupported connection_type: {connection_type}")
    key = edge_key(from_anchor.anchor_id, to_anchor.anchor_id)
    if any(candidate["edge_key"] == key for candidate in candidates):
        return
    candidates.append(
        {
            "edge_key": key,
            "from_anchor": from_anchor.anchor_id,
            "to_anchor": to_anchor.anchor_id,
            "segment_path": tuple(normalize_segment_id(item) for item in segment_path),
            "waypoints": waypoints,
            "cable_type": cable_type,
            "connection_type": connection_type,
        }
    )


def add_intra_segment_links(
    candidates: list[dict[str, Any]],
    dataset: SegmentDataset,
    anchors_by_segment: dict[str, tuple[Anchor, ...]],
    config: dict[str, Any],
) -> None:
    for segment_id, anchors in sorted(anchors_by_segment.items()):
        ordered = tuple(sorted(anchors, key=lambda anchor: anchor.anchor_id))
        for first, second in zip(ordered, ordered[1:]):
            add_cable_candidate(
                candidates,
                first,
                second,
                (segment_id,),
                make_wall_constrained_waypoints_for_segment_path(
                    dataset, first, second, (segment_id,), config
                ),
                "intra_segment",
            )


def _nearest_anchor_pair(
    first: tuple[Anchor, ...], second: tuple[Anchor, ...]
) -> tuple[Anchor, Anchor]:
    return min(
        ((left, right) for left in first for right in second),
        key=lambda pair: (
            distance_between_anchors(pair[0], pair[1]),
            pair[0].anchor_id,
            pair[1].anchor_id,
        ),
    )


def add_graph_adjacent_links(
    candidates: list[dict[str, Any]],
    dataset: SegmentDataset,
    anchors_by_segment: dict[str, tuple[Anchor, ...]],
    config: dict[str, Any],
) -> None:
    for edge in sorted(dataset.edges, key=lambda item: item.key()):
        source_anchors = anchors_by_segment.get(edge.source, ())
        target_anchors = anchors_by_segment.get(edge.target, ())
        if not source_anchors or not target_anchors:
            continue
        source, target = _nearest_anchor_pair(source_anchors, target_anchors)
        path = (edge.source, edge.target)
        add_cable_candidate(
            candidates,
            source,
            target,
            path,
            make_wall_constrained_waypoints_for_segment_path(
                dataset, source, target, path, config
            ),
            "primary",
        )


def _component_from_candidates(
    start_anchor_id: str, candidates: list[dict[str, Any]]
) -> set[str]:
    adjacency: dict[str, set[str]] = {}
    for candidate in candidates:
        left, right = candidate["edge_key"]
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    component = {start_anchor_id}
    stack = [start_anchor_id]
    while stack:
        current = stack.pop()
        for neighbor in adjacency.get(current, ()):
            if neighbor not in component:
                component.add(neighbor)
                stack.append(neighbor)
    return component


def build_primary_backbone(
    candidates: list[dict[str, Any]],
    dataset: SegmentDataset,
    anchors: tuple[Anchor, ...],
    head_end_anchor: Anchor,
    config: dict[str, Any],
) -> None:
    lookup = build_anchor_lookup(anchors)
    component = _component_from_candidates(head_end_anchor.anchor_id, candidates)
    remaining = sorted(set(lookup) - component)
    while remaining:
        anchor = lookup[remaining[0]]
        options: list[tuple[float, str, tuple[str, ...]]] = []
        for connected_id in sorted(component):
            connected = lookup[connected_id]
            path = shortest_segment_path(
                dataset, connected.segment_id, anchor.segment_id
            )
            if path:
                options.append(
                    (distance_between_anchors(connected, anchor), connected_id, path)
                )
        if not options:
            remaining.pop(0)
            continue
        _, connected_id, path = min(options)
        connected = lookup[connected_id]
        add_cable_candidate(
            candidates,
            connected,
            anchor,
            path,
            make_wall_constrained_waypoints_for_segment_path(
                dataset, connected, anchor, path, config
            ),
            "branch",
        )
        component = _component_from_candidates(head_end_anchor.anchor_id, candidates)
        remaining = sorted(set(lookup) - component)


def add_cross_links(
    candidates: list[dict[str, Any]],
    dataset: SegmentDataset,
    anchors: tuple[Anchor, ...],
    anchors_by_segment: dict[str, tuple[Anchor, ...]],
    config: dict[str, Any],
) -> None:
    cable_config = config["cable_topology"]
    if not cable_config["enable_cross_links"]:
        return
    maximum = float(cable_config["max_cross_link_distance_m"])
    for junction_id in sorted(
        segment_id for segment_id in dataset.segments if dataset.degree(segment_id) >= 3
    ):
        junction_anchors = anchors_by_segment.get(junction_id, ())
        if not junction_anchors:
            continue
        junction_anchor = junction_anchors[0]
        existing_pairs = {candidate["edge_key"] for candidate in candidates}
        for neighbor_id in dataset.neighbors(junction_id):
            neighbor_anchors = anchors_by_segment.get(neighbor_id, ())
            alternatives = sorted(
                (
                    anchor
                    for anchor in neighbor_anchors
                    if edge_key(junction_anchor.anchor_id, anchor.anchor_id)
                    not in existing_pairs
                    and distance_between_anchors(junction_anchor, anchor) <= maximum
                ),
                key=lambda anchor: (
                    distance_between_anchors(junction_anchor, anchor),
                    anchor.anchor_id,
                ),
            )
            if not alternatives:
                continue
            target = alternatives[0]
            path = (junction_id, neighbor_id)
            add_cable_candidate(
                candidates,
                junction_anchor,
                target,
                path,
                make_wall_constrained_waypoints_for_segment_path(
                    dataset, junction_anchor, target, path, config
                ),
                "cross_link",
            )
            existing_pairs.add(edge_key(junction_anchor.anchor_id, target.anchor_id))


def build_cable_id(index: int) -> str:
    if isinstance(index, bool) or not isinstance(index, int) or index <= 0:
        raise ValueError("cable index must be a positive integer")
    return normalize_cable_id(index)


def finalize_cables(candidates: list[dict[str, Any]]) -> tuple[CableLink, ...]:
    priority = {"primary": 0, "intra_segment": 1, "branch": 2, "cross_link": 3}
    ordered = sorted(
        candidates,
        key=lambda item: (
            priority[item["connection_type"]],
            item["from_anchor"],
            item["to_anchor"],
        ),
    )
    return tuple(
        CableLink(
            cable_id=build_cable_id(index),
            from_anchor=item["from_anchor"],
            to_anchor=item["to_anchor"],
            segment_path=item["segment_path"],
            waypoints=item["waypoints"],
            cable_type=item["cable_type"],
            connection_type=item["connection_type"],
        )
        for index, item in enumerate(ordered, 1)
    )


def build_cables_by_anchor(
    cables: tuple[CableLink, ...],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for cable in cables:
        grouped.setdefault(cable.from_anchor, []).append(cable.cable_id)
        grouped.setdefault(cable.to_anchor, []).append(cable.cable_id)
    return {
        anchor_id: tuple(sorted(cable_ids))
        for anchor_id, cable_ids in sorted(grouped.items())
    }


def build_cable_report(
    dataset: SegmentDataset,
    anchors: tuple[Anchor, ...],
    cables: tuple[CableLink, ...],
    head_end_anchor: Anchor,
    config: dict[str, Any],
) -> dict[str, Any]:
    degrees = {anchor.anchor_id: 0 for anchor in anchors}
    type_counts = {name: 0 for name in ALLOWED_CONNECTION_TYPES}
    for cable in cables:
        degrees[cable.from_anchor] += 1
        degrees[cable.to_anchor] += 1
        type_counts[cable.connection_type] += 1
    isolated = sorted(anchor_id for anchor_id, degree in degrees.items() if degree == 0)
    warnings = [
        "cable topology follows Haki graph adjacency and is not emergency routing",
        "cable paths use bounds-wall approximation, not exact tunnel wall mesh routing",
        "cable waypoints are clamped to segment bounds when bounds are available",
        "Cable waypoints are constrained using segment bounds and wall offsets. This is a bounds-based wall-adjacent approximation, not exact mesh-based wall routing. Exact wall routing requires Haki to provide tunnel wall geometry, centerline/start-end geometry, or a wall/path polyline layer.",
    ]
    if config["cable_topology"].get("head_end_selection") not in {
        "nearest_exit", "first_anchor"
    }:
        warnings.append("invalid head_end_selection; nearest_exit fallback was used")
    degree_values = list(degrees.values())
    return {
        "geometry_mode": config["anchor_placement"]["geometry_mode"],
        "routing_surface": "tunnel_wall_approximation",
        "wall_offset_m": float(config["cable_topology"]["wall_offset_m"]),
        "anchor_count": len(anchors),
        "cable_count": len(cables),
        "primary_count": type_counts["primary"],
        "intra_segment_count": type_counts["intra_segment"],
        "branch_count": type_counts["branch"],
        "cross_link_count": type_counts["cross_link"],
        "head_end_anchor_id": head_end_anchor.anchor_id,
        "head_end_segment_id": head_end_anchor.segment_id,
        "connected_anchor_count": len(anchors) - len(isolated),
        "isolated_anchor_count": len(isolated),
        "isolated_anchors": isolated,
        "max_anchor_degree": max(degree_values) if degree_values else 0,
        "mean_anchor_degree": (
            round(sum(degree_values) / len(degree_values), 4) if degree_values else 0.0
        ),
        "warnings": warnings,
    }


def plan_cables(
    dataset: SegmentDataset | None = None,
    anchor_plan: AnchorPlanResult | None = None,
    config: dict[str, Any] | None = None,
) -> CablePlanResult:
    normalized_config = load_config() if config is None else config
    segment_dataset = (
        load_segment_dataset(normalized_config) if dataset is None else dataset
    )
    anchors_result = (
        plan_anchors(segment_dataset, normalized_config)
        if anchor_plan is None
        else anchor_plan
    )
    anchors = anchors_result.anchors
    head_end = select_head_end_anchor(segment_dataset, anchors, normalized_config)
    grouped = group_anchors_by_segment(anchors)
    candidates: list[dict[str, Any]] = []
    add_intra_segment_links(candidates, segment_dataset, grouped, normalized_config)
    add_graph_adjacent_links(candidates, segment_dataset, grouped, normalized_config)
    build_primary_backbone(
        candidates, segment_dataset, anchors, head_end, normalized_config
    )
    add_cross_links(candidates, segment_dataset, anchors, grouped, normalized_config)
    cables = finalize_cables(candidates)
    result = CablePlanResult(
        cables=cables,
        head_end_anchor_id=head_end.anchor_id,
        head_end_segment_id=head_end.segment_id,
        cable_report=build_cable_report(
            segment_dataset, anchors, cables, head_end, normalized_config
        ),
        cables_by_anchor=build_cables_by_anchor(cables),
    )
    validate_cable_plan(segment_dataset, anchors_result, result)
    return result


def validate_cable_plan(
    dataset: SegmentDataset,
    anchor_plan: AnchorPlanResult,
    result: CablePlanResult,
) -> None:
    anchors = build_anchor_lookup(anchor_plan.anchors)
    if len(anchors) > 1 and not result.cables:
        raise ValueError("cable plan must contain cables when multiple anchors exist")
    if result.head_end_anchor_id not in anchors:
        raise ValueError("head-end anchor is not in the anchor plan")
    if result.cable_report.get("routing_surface") != "tunnel_wall_approximation":
        raise ValueError("cable report must declare tunnel_wall_approximation")
    cable_ids: set[str] = set()
    for cable in result.cables:
        if cable.cable_id in cable_ids:
            raise ValueError(f"duplicate cable ID: {cable.cable_id}")
        if not re.fullmatch(r"C\d{3}", cable.cable_id):
            raise ValueError(f"non-canonical cable ID: {cable.cable_id}")
        if cable.from_anchor not in anchors or cable.to_anchor not in anchors:
            raise ValueError(f"cable has unknown endpoint: {cable.cable_id}")
        if cable.from_anchor == cable.to_anchor:
            raise ValueError(f"cable is a self-link: {cable.cable_id}")
        if not cable.segment_path:
            raise ValueError(f"cable has empty segment_path: {cable.cable_id}")
        if any(segment_id not in dataset.segments for segment_id in cable.segment_path):
            raise ValueError(f"cable path references unknown segment: {cable.cable_id}")
        if any(
            not dataset.is_graph_adjacent(first, second)
            for first, second in zip(cable.segment_path, cable.segment_path[1:])
        ):
            raise ValueError(f"cable path does not follow graph: {cable.cable_id}")
        if cable.connection_type not in ALLOWED_CONNECTION_TYPES:
            raise ValueError(f"invalid connection type: {cable.cable_id}")
        wall_valid, wall_warnings = validate_wall_waypoints_for_path(
            dataset, cable.segment_path, cable.waypoints
        )
        if not wall_valid:
            detail = "; ".join(wall_warnings)
            raise ValueError(f"invalid wall waypoints for {cable.cable_id}: {detail}")
        cable_ids.add(cable.cable_id)
    if result.cable_report.get("cable_count") != len(result.cables):
        raise ValueError("cable report count does not match cable plan")


def _self_check() -> None:
    config = load_config()
    dataset = load_segment_dataset(config)
    anchor_plan = plan_anchors(dataset, config)
    result = plan_cables(dataset, anchor_plan, config)
    validate_cable_plan(dataset, anchor_plan, result)
    anchor_ids = {anchor.anchor_id for anchor in anchor_plan.anchors}
    assert result.cables
    assert result.head_end_anchor_id in anchor_ids
    assert all(
        cable.from_anchor in anchor_ids and cable.to_anchor in anchor_ids
        for cable in result.cables
    )
    assert result.cable_report["cable_count"] == len(result.cables)
    assert result.cable_report["routing_surface"] == "tunnel_wall_approximation"
    assert result.cable_report["wall_offset_m"] >= 0
    print(json.dumps(result.to_summary(), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    _self_check()
    print("cable_planner.py self-check passed")
