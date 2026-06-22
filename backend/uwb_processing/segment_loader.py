"""Load Haki's read-only segment, metadata, graph, and risk handoffs.

The current Haki handoff provides bounds-center geometry. Dynamic anchor planning is performed at segment/graph level using segment centers, bounds, graph edges and edge weights. Exact centerline-based tunnel curve placement is not available until Haki provides centerline/start-end geometry.

Haki remains the source of truth for segment IDs and graph connectivity. This
module normalizes and joins those records in memory and never writes inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

try:
    from .config_loader import load_config
    from .core import (
        Bounds3D,
        GraphEdge,
        Point3D,
        Segment,
        ensure_finite_number,
        normalize_segment_id,
    )
except ImportError:  # Supports ``python backend/uwb_processing/segment_loader.py``.
    from config_loader import load_config  # type: ignore
    from core import (  # type: ignore
        Bounds3D,
        GraphEdge,
        Point3D,
        Segment,
        ensure_finite_number,
        normalize_segment_id,
    )


@dataclass(frozen=True)
class SegmentDataset:
    segments: dict[str, Segment]
    adjacency: dict[str, tuple[str, ...]]
    edge_weights: dict[tuple[str, str], float]
    edges: tuple[GraphEdge, ...]
    exits: tuple[str, ...]
    blocked_segments: tuple[str, ...]
    risky_segments: tuple[str, ...]
    geometry_risk_by_segment: dict[str, float]
    raw_counts: dict[str, int] = field(default_factory=dict)

    def get_segment(self, segment_id: str) -> Segment:
        canonical = normalize_segment_id(segment_id)
        try:
            return self.segments[canonical]
        except KeyError as exc:
            raise KeyError(f"Unknown segment_id: {canonical}") from exc

    def has_segment(self, segment_id: str) -> bool:
        try:
            canonical = normalize_segment_id(segment_id)
        except ValueError:
            return False
        return canonical in self.segments

    def neighbors(self, segment_id: str) -> tuple[str, ...]:
        canonical = normalize_segment_id(segment_id)
        if canonical not in self.segments:
            raise KeyError(f"Unknown segment_id: {canonical}")
        return self.adjacency.get(canonical, ())

    def degree(self, segment_id: str) -> int:
        return len(self.neighbors(segment_id))

    def edge_weight(
        self, source: str, target: str, default: float | None = None
    ) -> float | None:
        key = tuple(sorted((normalize_segment_id(source), normalize_segment_id(target))))
        return self.edge_weights.get(key, default)

    def is_graph_adjacent(self, source: str, target: str) -> bool:
        return normalize_segment_id(target) in self.neighbors(source)

    def to_summary(self) -> dict[str, Any]:
        ids = sorted(self.segments)
        center_count = sum(segment.center is not None for segment in self.segments.values())
        bounds_count = sum(segment.bounds is not None for segment in self.segments.values())
        length_count = sum(segment.length_m is not None for segment in self.segments.values())
        segment_count = len(self.segments)
        if segment_count and center_count >= segment_count / 2 and bounds_count >= segment_count / 2:
            geometry_mode = "bounds_center"
        elif center_count:
            geometry_mode = "center_only"
        elif self.edges:
            geometry_mode = "graph_only"
        else:
            geometry_mode = "unknown"

        warnings: list[str] = []
        if not any(
            self.raw_counts.get(key, 0)
            for key in ("start_count", "end_count", "centerline_count")
        ):
            warnings.append(
                "centerline/start/end not available; using bounds-center graph geometry"
            )
        missing_centers = segment_count - center_count
        missing_bounds = segment_count - bounds_count
        if missing_centers:
            warnings.append(f"{missing_centers} segment(s) lack center geometry")
        if missing_bounds:
            warnings.append(f"{missing_bounds} segment(s) lack bounds geometry")

        return {
            "segment_count": segment_count,
            "edge_count": len(self.edges),
            "graph_node_count": len(self.adjacency),
            "exit_count": len(self.exits),
            "blocked_count": len(self.blocked_segments),
            "risky_count": len(self.risky_segments),
            "ids_min": ids[0] if ids else None,
            "ids_max": ids[-1] if ids else None,
            "has_center_count": center_count,
            "has_bounds_count": bounds_count,
            "has_length_count": length_count,
            "geometry_mode": geometry_mode,
            "warnings": warnings,
        }


def load_json(path: str | Path) -> Any:
    """Read a UTF-8 JSON file without modifying it."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Haki input file does not exist: {resolved}")
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {resolved} at line {exc.lineno}, column {exc.colno}"
        ) from exc


def as_record_list(raw: Any, label: str) -> list[dict[str, Any]]:
    """Extract a non-empty record list from common handoff container shapes."""
    candidate: Any = raw
    if isinstance(raw, dict):
        candidate = None
        for key in ("segments", "data", "records"):
            value = raw.get(key)
            if isinstance(value, list):
                candidate = value
                break
        if candidate is None:
            candidate = next(
                (
                    value
                    for value in raw.values()
                    if isinstance(value, list)
                    and value
                    and all(isinstance(item, dict) for item in value)
                ),
                None,
            )
    if not isinstance(candidate, list) or not candidate:
        raise ValueError(f"{label} does not contain a non-empty record list")
    if not all(isinstance(item, dict) for item in candidate):
        raise ValueError(f"{label} records must all be objects")
    return candidate


def parse_point(value: Any, field_name: str) -> Point3D | None:
    if value is None or value == "" or value == [] or value == {}:
        return None
    try:
        return Point3D.from_any(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid point for {field_name}: {value!r}") from exc


def parse_bounds(value: Any, field_name: str) -> Bounds3D | None:
    if value is None or value == "" or value == [] or value == {}:
        return None
    try:
        return Bounds3D.from_any(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid bounds for {field_name}: {value!r}") from exc


def _build_index(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for position, record in enumerate(records):
        if "segment_id" not in record:
            raise ValueError(f"{label}[{position}] is missing segment_id")
        segment_id = normalize_segment_id(record["segment_id"])
        if segment_id in index:
            raise ValueError(f"Duplicate segment_id in {label}: {segment_id}")
        normalized = dict(record)
        normalized["segment_id"] = segment_id
        index[segment_id] = normalized
    return index


def build_map_index(map_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _build_index(map_records, "map_records")


def build_metadata_index(
    metadata_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return _build_index(metadata_records, "metadata_records")


def build_risk_index(risk_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index = _build_index(risk_records, "risk_records")
    aliases = ("geometry_risk", "risk_score", "score", "normalized_risk")
    for segment_id, record in index.items():
        for key in aliases:
            if record.get(key) is not None:
                record["geometry_risk"] = ensure_finite_number(
                    record[key], f"risk_records[{segment_id}].{key}"
                )
                break
    return index


def _edge_value(record: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        if key in record and record[key] is not None:
            return record[key]
    return None


def extract_graph_edges(raw_graph: Any) -> list[GraphEdge]:
    """Extract normalized, deduplicated undirected edges from common graph shapes."""
    records: list[dict[str, Any]] = []
    if isinstance(raw_graph, list):
        if not all(isinstance(item, dict) for item in raw_graph):
            raise ValueError("graph edge list must contain objects")
        records = raw_graph
    elif isinstance(raw_graph, dict):
        container = raw_graph.get("edges", raw_graph.get("links"))
        if container is not None:
            if not isinstance(container, list) or not all(
                isinstance(item, dict) for item in container
            ):
                raise ValueError("graph edges/links must be a list of objects")
            records = container
        else:
            for source, targets in raw_graph.items():
                if not isinstance(targets, list):
                    continue
                for target in targets:
                    if isinstance(target, dict):
                        target_value = _edge_value(
                            target, ("target", "to", "to_segment", "segment_b", "v")
                        )
                        record = dict(target)
                        record.setdefault("source", source)
                        if target_value is not None:
                            record.setdefault("target", target_value)
                        records.append(record)
                    else:
                        records.append({"source": source, "target": target})
    else:
        raise ValueError("graph root must be an object or edge list")

    source_aliases = ("source", "from", "from_segment", "segment_a", "u")
    target_aliases = ("target", "to", "to_segment", "segment_b", "v")
    weight_aliases = ("weight", "length", "length_m", "distance", "distance_m")
    deduplicated: dict[tuple[str, str], GraphEdge] = {}
    for position, record in enumerate(records):
        source_value = _edge_value(record, source_aliases)
        target_value = _edge_value(record, target_aliases)
        if source_value is None or target_value is None:
            raise ValueError(f"graph edge {position} is missing source or target")
        source = normalize_segment_id(source_value)
        target = normalize_segment_id(target_value)
        if source == target:
            raise ValueError(f"self-loop graph edge is not allowed: {source}")
        raw_weight = _edge_value(record, weight_aliases)
        weight = 1.0 if raw_weight is None else ensure_finite_number(
            raw_weight, f"graph edge {source}-{target} weight"
        )
        blocked = bool(record.get("is_blocked", record.get("blocked", False)))
        edge = GraphEdge(source, target, weight, blocked)
        key = edge.key()
        existing = deduplicated.get(key)
        if existing is None or edge.weight < existing.weight:
            deduplicated[key] = GraphEdge(
                key[0], key[1], edge.weight, edge.is_blocked or bool(existing and existing.is_blocked)
            )
        elif edge.is_blocked and not existing.is_blocked:
            deduplicated[key] = GraphEdge(
                existing.source, existing.target, existing.weight, True
            )
    return [deduplicated[key] for key in sorted(deduplicated)]


def build_adjacency(
    edges: list[GraphEdge], segment_ids: set[str]
) -> tuple[dict[str, tuple[str, ...]], dict[tuple[str, str], float]]:
    neighbors: dict[str, set[str]] = {segment_id: set() for segment_id in segment_ids}
    weights: dict[tuple[str, str], float] = {}
    for edge in edges:
        if edge.source not in segment_ids or edge.target not in segment_ids:
            raise ValueError(
                f"graph edge references unknown segment: {edge.source}-{edge.target}"
            )
        neighbors[edge.source].add(edge.target)
        neighbors[edge.target].add(edge.source)
        weights[edge.key()] = edge.weight
    return (
        {segment_id: tuple(sorted(values)) for segment_id, values in sorted(neighbors.items())},
        weights,
    )


def _first_value(*sources: tuple[dict[str, Any] | None, tuple[str, ...]]) -> Any:
    for record, keys in sources:
        if not record:
            continue
        for key in keys:
            if key in record and record[key] is not None:
                return record[key]
    return None


def merge_segment_record(
    segment_id: str,
    map_record: dict[str, Any],
    metadata_record: dict[str, Any] | None,
    risk_record: dict[str, Any] | None,
    adjacency: dict[str, tuple[str, ...]],
) -> Segment:
    """Merge one map-authoritative segment with metadata, risk, and graph data."""
    canonical = normalize_segment_id(segment_id)
    bounds = parse_bounds(
        _first_value((map_record, ("bounds",)), (metadata_record, ("bounds",))),
        f"{canonical}.bounds",
    )
    center = parse_point(
        _first_value(
            (map_record, ("center", "center_position")),
            (metadata_record, ("center", "center_position")),
        ),
        f"{canonical}.center",
    )
    if center is None and bounds is not None:
        center = bounds.center()

    connected: set[str] = set(adjacency.get(canonical, ()))
    raw_connected = map_record.get("connected_segments") or ()
    if not isinstance(raw_connected, (list, tuple, set)):
        raise ValueError(f"{canonical}.connected_segments must be a sequence")
    connected.update(normalize_segment_id(item) for item in raw_connected)
    connected.discard(canonical)

    length_value = _first_value(
        (map_record, ("length_m", "length")),
        (metadata_record, ("length_m", "length")),
    )
    length = (
        ensure_finite_number(length_value, f"{canonical}.length_m")
        if length_value is not None
        else None
    )
    risk_value = _first_value(
        (map_record, ("geometry_risk",)),
        (risk_record, ("geometry_risk", "risk_score", "score", "normalized_risk")),
        (metadata_record, ("geometry_risk", "base_geometry_risk")),
    )
    geometry_risk = (
        ensure_finite_number(risk_value, f"{canonical}.geometry_risk")
        if risk_value is not None
        else None
    )
    return Segment(
        segment_id=canonical,
        name=str(_first_value((map_record, ("name",)), (metadata_record, ("name", "segment_name"))) or ""),
        type=str(_first_value((map_record, ("type",)), (metadata_record, ("type", "segment_type"))) or ""),
        role=str(_first_value((map_record, ("role",)), (metadata_record, ("role",))) or ""),
        center=center,
        bounds=bounds,
        length_m=length,
        connected_segments=tuple(sorted(connected)),
        is_exit=bool(_first_value((metadata_record, ("is_exit",)), (map_record, ("is_exit",))) or False),
        is_exit_candidate=bool(map_record.get("is_exit_candidate", False)),
        is_blocked=bool(_first_value((metadata_record, ("is_blocked",)), (map_record, ("is_blocked",))) or False),
        is_risky=bool(_first_value((map_record, ("is_risky",)), (risk_record, ("is_risky",))) or False),
        geometry_risk=geometry_risk,
    )


def load_segment_dataset(config: dict[str, Any] | None = None) -> SegmentDataset:
    """Load and normalize the configured Haki handoff entirely in memory."""
    normalized_config = load_config() if config is None else config
    sources = normalized_config.get("segment_source")
    if not isinstance(sources, dict):
        raise ValueError("config.segment_source must be an object")
    missing_sources = [key for key in (
        "map_segments_path", "segment_metadata_path", "mine_graph_path", "geometry_risk_path"
    ) if key not in sources]
    if missing_sources:
        raise ValueError(f"config.segment_source missing: {', '.join(missing_sources)}")

    map_records = as_record_list(load_json(sources["map_segments_path"]), "map_segments")
    metadata_records = as_record_list(
        load_json(sources["segment_metadata_path"]), "segment_metadata"
    )
    risk_records = as_record_list(load_json(sources["geometry_risk_path"]), "geometry_risk")
    raw_graph = load_json(sources["mine_graph_path"])

    map_index = build_map_index(map_records)
    metadata_index = build_metadata_index(metadata_records)
    risk_index = build_risk_index(risk_records)
    segment_ids = set(map_index)
    unknown_metadata = set(metadata_index) - segment_ids
    unknown_risk = set(risk_index) - segment_ids
    if unknown_metadata:
        raise ValueError(f"metadata references unknown segments: {sorted(unknown_metadata)}")
    if unknown_risk:
        raise ValueError(f"risk records reference unknown segments: {sorted(unknown_risk)}")

    edges = extract_graph_edges(raw_graph)
    adjacency, edge_weights = build_adjacency(edges, segment_ids)
    segments = {
        segment_id: merge_segment_record(
            segment_id,
            map_index[segment_id],
            metadata_index.get(segment_id),
            risk_index.get(segment_id),
            adjacency,
        )
        for segment_id in sorted(segment_ids)
    }
    exits = tuple(sorted(
        segment_id for segment_id, segment in segments.items()
        if segment.is_exit or segment.is_exit_candidate
    ))
    blocked = tuple(sorted(
        segment_id for segment_id, segment in segments.items() if segment.is_blocked
    ))
    risky = tuple(sorted(
        segment_id for segment_id, segment in segments.items() if segment.is_risky
    ))
    risks = {
        segment_id: segment.geometry_risk
        for segment_id, segment in segments.items()
        if segment.geometry_risk is not None
    }
    raw_counts = {
        "map_record_count": len(map_records),
        "metadata_record_count": len(metadata_records),
        "risk_record_count": len(risk_records),
        "graph_edge_count": len(edges),
        "start_count": sum(record.get("start") is not None for record in map_records),
        "end_count": sum(record.get("end") is not None for record in map_records),
        "centerline_count": sum(record.get("centerline") is not None for record in map_records),
    }
    dataset = SegmentDataset(
        segments=segments,
        adjacency=adjacency,
        edge_weights=edge_weights,
        edges=tuple(edges),
        exits=exits,
        blocked_segments=blocked,
        risky_segments=risky,
        geometry_risk_by_segment=risks,
        raw_counts=raw_counts,
    )
    validate_segment_dataset(dataset)
    return dataset


def validate_segment_dataset(dataset: SegmentDataset) -> None:
    """Validate segment IDs, references, and positive finite graph weights."""
    if not dataset.segments:
        raise ValueError("segment dataset must contain at least one segment")
    ids = set(dataset.segments)
    for key, segment in dataset.segments.items():
        if key != segment.segment_id:
            raise ValueError(f"segment key does not match record ID: {key}")
        if not re.fullmatch(r"S\d{3}", key):
            raise ValueError(f"non-canonical segment ID: {key}")
        unknown_connected = set(segment.connected_segments) - ids
        if unknown_connected:
            raise ValueError(f"{key} references unknown connected segments: {unknown_connected}")
    if set(dataset.adjacency) != ids:
        raise ValueError("adjacency must contain every segment exactly once")
    for source, neighbors in dataset.adjacency.items():
        unknown = set(neighbors) - ids
        if unknown:
            raise ValueError(f"adjacency for {source} references unknown segments: {unknown}")
    for edge in dataset.edges:
        if edge.source not in ids or edge.target not in ids:
            raise ValueError(f"edge references unknown segment: {edge.key()}")
        weight = ensure_finite_number(edge.weight, f"edge {edge.key()} weight")
        if weight <= 0.0:
            raise ValueError(f"edge weight must be positive: {edge.key()}")
    for label, values in (
        ("exits", dataset.exits),
        ("blocked_segments", dataset.blocked_segments),
        ("risky_segments", dataset.risky_segments),
    ):
        unknown = set(values) - ids
        if unknown:
            raise ValueError(f"{label} contain unknown segments: {unknown}")


def _self_check() -> None:
    config = load_config()
    dataset = load_segment_dataset(config)
    validate_segment_dataset(dataset)
    assert dataset.segments
    assert dataset.edges
    if "S001" in dataset.segments:
        assert dataset.has_segment("S001")
    assert all(segment_id.startswith("S") for segment_id in dataset.segments)
    assert all(
        neighbor in dataset.segments
        for neighbors in dataset.adjacency.values()
        for neighbor in neighbors
    )
    print(json.dumps(dataset.to_summary(), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    _self_check()
    print("segment_loader.py self-check passed")
