"""Shared models and utilities for the MadenGuard UWB worker-tracking MVP.

The current Haki handoff provides bounds-center geometry. Dynamic anchor planning is performed at segment/graph level using segment centers, bounds, graph edges and edge weights. Exact centerline-based tunnel curve placement is not available until Haki provides centerline/start-end geometry.

UTIL UWB pose_x, pose_y and pose_z values are motion-capture ground-truth proxy positions, not real UWB-estimated miner positions. In this MVP they are used only as worker movement proxies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from math import acos, degrees, isfinite, sqrt
from typing import Any, Iterable
import re


def ensure_finite_number(value: Any, field_name: str = "value") -> float:
    """Return *value* as a finite float or raise ``ValueError``."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    return number


def is_finite_number(value: Any) -> bool:
    """Return whether *value* can be represented as a finite float."""
    try:
        ensure_finite_number(value)
    except ValueError:
        return False
    return True


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    """Constrain a finite number to an inclusive finite range."""
    number = ensure_finite_number(value)
    lower = ensure_finite_number(min_value, "min_value")
    upper = ensure_finite_number(max_value, "max_value")
    if lower > upper:
        raise ValueError("min_value must not exceed max_value")
    return max(lower, min(number, upper))


def round_float(value: float, digits: int = 4) -> float:
    """Round a finite number to the requested decimal precision."""
    if isinstance(digits, bool) or not isinstance(digits, int):
        raise ValueError("digits must be an integer")
    return round(ensure_finite_number(value), digits)


@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", ensure_finite_number(self.x, "x"))
        object.__setattr__(self, "y", ensure_finite_number(self.y, "y"))
        object.__setattr__(self, "z", ensure_finite_number(self.z, "z"))

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_any(cls, value: Any) -> "Point3D":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            if "x" not in value or "y" not in value:
                raise ValueError("point mapping must contain x and y")
            return cls(value["x"], value["y"], value.get("z", 0.0))
        if isinstance(value, (list, tuple)) and len(value) in (2, 3):
            return cls(value[0], value[1], value[2] if len(value) == 3 else 0.0)
        raise ValueError("point must be Point3D, a mapping, or a 2/3 item sequence")


@dataclass(frozen=True)
class Bounds3D:
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float = 0.0
    max_z: float = 0.0

    def __post_init__(self) -> None:
        for name in ("min_x", "max_x", "min_y", "max_y", "min_z", "max_z"):
            object.__setattr__(self, name, ensure_finite_number(getattr(self, name), name))
        if self.min_x > self.max_x or self.min_y > self.max_y or self.min_z > self.max_z:
            raise ValueError("bounds minimums must not exceed maximums")

    def contains(self, point: Point3D, margin: float = 0.0) -> bool:
        candidate = Point3D.from_any(point)
        padding = ensure_finite_number(margin, "margin")
        return (
            self.min_x - padding <= candidate.x <= self.max_x + padding
            and self.min_y - padding <= candidate.y <= self.max_y + padding
            and self.min_z - padding <= candidate.z <= self.max_z + padding
        )

    def center(self) -> Point3D:
        return Point3D(
            (self.min_x + self.max_x) / 2.0,
            (self.min_y + self.max_y) / 2.0,
            (self.min_z + self.max_z) / 2.0,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "min_x": self.min_x,
            "max_x": self.max_x,
            "min_y": self.min_y,
            "max_y": self.max_y,
            "min_z": self.min_z,
            "max_z": self.max_z,
        }

    @classmethod
    def from_any(cls, value: Any) -> "Bounds3D":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            required = ("min_x", "max_x", "min_y", "max_y")
            if any(name not in value for name in required):
                raise ValueError("bounds mapping must contain x/y minimums and maximums")
            return cls(
                value["min_x"], value["max_x"], value["min_y"], value["max_y"],
                value.get("min_z", 0.0), value.get("max_z", 0.0),
            )
        if isinstance(value, (list, tuple)) and len(value) in (4, 6):
            return cls(*value) if len(value) == 6 else cls(*value, 0.0, 0.0)
        raise ValueError("bounds must be Bounds3D, a mapping, or a 4/6 item sequence")


@dataclass(frozen=True)
class Segment:
    segment_id: str
    name: str = ""
    type: str = ""
    role: str = ""
    center: Point3D | None = None
    bounds: Bounds3D | None = None
    length_m: float | None = None
    connected_segments: tuple[str, ...] = field(default_factory=tuple)
    is_exit: bool = False
    is_exit_candidate: bool = False
    is_blocked: bool = False
    is_risky: bool = False
    geometry_risk: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    weight: float = 1.0
    is_blocked: bool = False

    def key(self) -> tuple[str, str]:
        return tuple(sorted((self.source, self.target)))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class Anchor:
    anchor_id: str
    segment_id: str
    position: Point3D
    coverage_radius_m: float
    anchor_type: str = "relay"
    placement_reason: str = "coverage_optimization"
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CableLink:
    cable_id: str
    from_anchor: str
    to_anchor: str
    segment_path: tuple[str, ...]
    waypoints: tuple[Point3D, ...] = field(default_factory=tuple)
    cable_type: str = "ethernet_or_fiber"
    connection_type: str = "primary"
    status: str = "intact"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class RawPose:
    worker_id: str
    tag_id: str
    time_step: int
    timestamp_s: float
    source_trial: str
    source_pose: Point3D
    tdoa_sample_count: int = 0
    anchor_pair_count: int = 0
    source_position_type: str = "mocap_ground_truth"


@dataclass(frozen=True)
class MappedPosition:
    worker_id: str
    tag_id: str
    time_step: int
    timestamp_s: float
    position: Point3D
    current_segment: str | None
    mapping_method: str
    mapping_confidence: float
    continuity_score: float
    flight_signal_reliability: float
    source_trial: str
    source_position_type: str = "mocap_ground_truth"


@dataclass(frozen=True)
class DistanceObservation:
    time_step: int
    worker_id: str
    tag_id: str
    current_segment: str | None
    worker_position: Point3D
    anchor_id: str
    anchor_segment: str
    anchor_position: Point3D
    distance_2d_m: float
    distance_3d_m: float
    coverage_radius_m: float
    within_range: bool
    anchor_status: str
    visible: bool
    signal_quality_est: float
    visibility_reason: str = ""


@dataclass(frozen=True)
class WorkerTimelineRecord:
    worker_id: str
    tag_id: str
    time_step: int
    timestamp_s: float
    position: Point3D
    current_segment: str | None
    visible_anchor_count: int = 0
    visible_anchors: tuple[str, ...] = field(default_factory=tuple)
    tracking_status: str = "no_tracking"
    position_reliability: float = 0.0
    reliability_status: str = "poor"
    mapping_method: str = ""
    mapping_confidence: float = 0.0
    continuity_score: float = 0.0
    flight_signal_reliability: float = 0.0
    source_trial: str = ""
    source_position_type: str = "mocap_ground_truth"
    status: str = "safe"


def _normalize_numeric_id(value: Any, pattern: str, prefix: str, width: int) -> str:
    if isinstance(value, bool):
        raise ValueError(f"invalid {prefix} identifier: {value!r}")
    text = str(value).strip().upper()
    match = re.fullmatch(pattern, text)
    if not match:
        raise ValueError(f"invalid {prefix} identifier: {value!r}")
    number = int(match.group(1))
    if number <= 0 or number >= 10**width:
        raise ValueError(f"{prefix} identifier is outside the supported range")
    return f"{prefix}{number:0{width}d}"


def normalize_segment_id(value: Any) -> str:
    return _normalize_numeric_id(value, r"(?:(?:SEG)_?|S)?0*(\d+)", "S", 3)


def normalize_worker_id(value: Any) -> str:
    normalized = _normalize_numeric_id(value, r"(?:WORKER_?|W)?0*(\d+)", "WORKER_", 2)
    return normalized


def normalize_tag_id(value: Any) -> str:
    return _normalize_numeric_id(value, r"(?:TAG_?|T)?0*(\d+)", "TAG_", 3)


def normalize_anchor_id(value: Any) -> str:
    return _normalize_numeric_id(value, r"(?:A)?0*(\d+)", "A", 3)


def normalize_cable_id(value: Any) -> str:
    return _normalize_numeric_id(value, r"(?:C)?0*(\d+)", "C", 3)


def distance_2d(p1: Any, p2: Any) -> float:
    first, second = Point3D.from_any(p1), Point3D.from_any(p2)
    return sqrt((second.x - first.x) ** 2 + (second.y - first.y) ** 2)


def distance_3d(p1: Any, p2: Any) -> float:
    first, second = Point3D.from_any(p1), Point3D.from_any(p2)
    return sqrt(
        (second.x - first.x) ** 2
        + (second.y - first.y) ** 2
        + (second.z - first.z) ** 2
    )


def vector_between(p1: Point3D, p2: Point3D) -> tuple[float, float, float]:
    return (p2.x - p1.x, p2.y - p1.y, p2.z - p1.z)


def _finite_vector(vector: Iterable[float]) -> tuple[float, ...]:
    values = tuple(ensure_finite_number(value, "vector component") for value in vector)
    if not values:
        raise ValueError("vector must not be empty")
    return values


def dot(v1: Iterable[float], v2: Iterable[float]) -> float:
    first, second = _finite_vector(v1), _finite_vector(v2)
    if len(first) != len(second):
        raise ValueError("vectors must have equal dimensions")
    return sum(a * b for a, b in zip(first, second))


def magnitude(vector: Iterable[float]) -> float:
    values = _finite_vector(vector)
    return sqrt(sum(value * value for value in values))


def angle_between_vectors_deg(v1: Iterable[float], v2: Iterable[float]) -> float:
    first, second = _finite_vector(v1), _finite_vector(v2)
    if len(first) != len(second):
        raise ValueError("vectors must have equal dimensions")
    denominator = magnitude(first) * magnitude(second)
    if denominator == 0.0:
        return 0.0
    cosine = clamp(dot(first, second) / denominator, -1.0, 1.0)
    return degrees(acos(cosine))


def point_to_segment_distance_2d(point: Any, start: Any, end: Any) -> float:
    candidate = Point3D.from_any(point)
    first, second = Point3D.from_any(start), Point3D.from_any(end)
    dx, dy = second.x - first.x, second.y - first.y
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return distance_2d(candidate, first)
    projection = clamp(
        ((candidate.x - first.x) * dx + (candidate.y - first.y) * dy) / length_squared
    )
    closest = Point3D(first.x + projection * dx, first.y + projection * dy)
    return distance_2d(candidate, closest)


def polyline_length(points: Iterable[Any]) -> float:
    normalized = [Point3D.from_any(point) for point in points]
    return sum(distance_3d(a, b) for a, b in zip(normalized, normalized[1:]))


def interpolate_polyline(points: Iterable[Any], spacing_m: float) -> list[Point3D]:
    normalized = [Point3D.from_any(point) for point in points]
    spacing = ensure_finite_number(spacing_m, "spacing_m")
    if spacing <= 0.0:
        raise ValueError("spacing_m must be greater than zero")
    if len(normalized) < 2:
        return normalized

    segment_lengths = [distance_3d(a, b) for a, b in zip(normalized, normalized[1:])]
    total_length = sum(segment_lengths)
    if total_length == 0.0:
        return [normalized[0]]

    targets: list[float] = []
    target = spacing
    while target < total_length:
        targets.append(target)
        target += spacing

    result = [normalized[0]]
    segment_index = 0
    traversed = 0.0
    for target in targets:
        while (
            segment_index < len(segment_lengths) - 1
            and traversed + segment_lengths[segment_index] < target
        ):
            traversed += segment_lengths[segment_index]
            segment_index += 1
        segment_length = segment_lengths[segment_index]
        if segment_length == 0.0:
            continue
        ratio = (target - traversed) / segment_length
        start, end = normalized[segment_index], normalized[segment_index + 1]
        candidate = Point3D(
            start.x + ratio * (end.x - start.x),
            start.y + ratio * (end.y - start.y),
            start.z + ratio * (end.z - start.z),
        )
        if candidate != result[-1]:
            result.append(candidate)
    if normalized[-1] != result[-1]:
        result.append(normalized[-1])
    return result


def signal_quality_from_distance(distance_m: float, coverage_radius_m: float) -> float:
    distance = ensure_finite_number(distance_m, "distance_m")
    radius = ensure_finite_number(coverage_radius_m, "coverage_radius_m")
    if radius <= 0.0:
        return 0.0
    return clamp(1.0 - distance / radius)


def tracking_status_from_visible_count(count: int, min_visible_anchors: int = 3) -> str:
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("count must be an integer")
    if isinstance(min_visible_anchors, bool) or not isinstance(min_visible_anchors, int):
        raise ValueError("min_visible_anchors must be an integer")
    if min_visible_anchors <= 0:
        raise ValueError("min_visible_anchors must be greater than zero")
    if count >= min_visible_anchors:
        return "full_tracking"
    if count == 2:
        return "degraded_tracking"
    if count == 1:
        return "weak_tracking"
    return "no_tracking"


def reliability_status(value: float) -> str:
    score = clamp(value)
    if score >= 0.80:
        return "good"
    if score >= 0.60:
        return "degraded"
    return "poor"


def compute_position_reliability(
    flight_signal_reliability: float,
    visible_anchor_count: int,
    min_visible_anchors: int,
    mean_signal_quality_est: float,
    mapping_confidence: float = 1.0,
    continuity_score: float = 1.0,
    weights: dict[str, float] | None = None,
) -> float:
    if isinstance(visible_anchor_count, bool) or not isinstance(visible_anchor_count, int):
        raise ValueError("visible_anchor_count must be an integer")
    if isinstance(min_visible_anchors, bool) or not isinstance(min_visible_anchors, int):
        raise ValueError("min_visible_anchors must be an integer")
    if min_visible_anchors <= 0:
        raise ValueError("min_visible_anchors must be greater than zero")

    configured_weights = weights or {
        "flight_signal": 0.30,
        "visible_anchor": 0.30,
        "signal_quality": 0.20,
        "mapping_confidence": 0.10,
        "continuity": 0.10,
    }
    names = (
        "flight_signal", "visible_anchor", "signal_quality",
        "mapping_confidence", "continuity",
    )
    if any(name not in configured_weights for name in names):
        raise ValueError("weights must define all reliability components")
    normalized_weights = {
        name: clamp(configured_weights[name], 0.0, 1.0) for name in names
    }
    visible_score = clamp(max(visible_anchor_count, 0) / min_visible_anchors)
    score = (
        normalized_weights["flight_signal"] * clamp(flight_signal_reliability)
        + normalized_weights["visible_anchor"] * visible_score
        + normalized_weights["signal_quality"] * clamp(mean_signal_quality_est)
        + normalized_weights["mapping_confidence"] * clamp(mapping_confidence)
        + normalized_weights["continuity"] * clamp(continuity_score)
    )
    score = clamp(score)
    if visible_anchor_count <= 0:
        score = min(score, 0.3)
    return round_float(score, 4)


def tracking_risk_score_from_reliability(position_reliability: float) -> float:
    return round_float((1.0 - clamp(position_reliability)) * 100.0, 4)


def build_worker_exposure_record(
    worker_id: str,
    tag_id: str,
    segment_id: str | None,
    time_step: int,
    position: Any,
    position_reliability: float,
    visible_anchor_count: int,
    tracking_status: str,
    dwell_time_s: float = 0.0,
    status: str = "present",
    source: str = "uwb_tracking",
) -> dict[str, Any]:
    normalized_segment = normalize_segment_id(segment_id) if segment_id is not None else None
    reliability = round_float(clamp(position_reliability), 4)
    exposure = 100.0 if normalized_segment is not None else 0.0
    record_status = status if normalized_segment is not None or status != "present" else "unknown"
    return {
        "worker_id": normalize_worker_id(worker_id),
        "tag_id": normalize_tag_id(tag_id),
        "segment_id": normalized_segment,
        "time_step": int(time_step),
        "position": Point3D.from_any(position).to_dict(),
        "worker_exposure_risk": exposure,
        "tracking_risk_score": tracking_risk_score_from_reliability(reliability),
        "position_reliability": reliability,
        "visible_anchor_count": int(visible_anchor_count),
        "tracking_status": tracking_status,
        "dwell_time_s": ensure_finite_number(dwell_time_s, "dwell_time_s"),
        "risk_level": "critical" if normalized_segment is not None else "low",
        "status": record_status,
        "source": source,
    }


def to_jsonable(value: Any) -> Any:
    """Recursively convert supported dataclasses and containers to JSON values."""
    if isinstance(value, Point3D):
        return value.to_dict()
    if isinstance(value, Bounds3D):
        return value.to_dict()
    if is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_jsonable(item) for item in value]
    return value


def _self_check() -> None:
    """Run minimal executable checks for canonical IDs and tracking states."""
    assert normalize_segment_id("SEG_047") == "S047"
    assert normalize_worker_id("W01") == "WORKER_01"
    assert normalize_tag_id("T1") == "TAG_001"
    assert normalize_anchor_id("A1") == "A001"
    assert normalize_cable_id("C1") == "C001"
    assert tracking_status_from_visible_count(3) == "full_tracking"
    assert tracking_status_from_visible_count(2) == "degraded_tracking"
    assert tracking_status_from_visible_count(1) == "weak_tracking"
    assert tracking_status_from_visible_count(0) == "no_tracking"


if __name__ == "__main__":
    _self_check()
    print("core.py self-check passed")
