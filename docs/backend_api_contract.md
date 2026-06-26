# Backend API Contract

Base URL for local development:

```text
http://localhost:8000
```

Selim can set:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Common Rules

- `segment_id` is canonicalized as `S001`, `S002`, `S047`.
- Legacy `SEG_047` input is accepted and returned as `S047`.
- `risk_level` is returned lowercase: `low`, `medium`, `high`, `critical`.
- Time series endpoints accept `?time_step=0`.
- Use `?time_step=all` only for debugging; frontend should usually request one step.

## Endpoints

### `GET /api/health`

Returns backend status and available JSON files.

### `GET /api/digital-twin/segments`

Returns segment list from Haki's processed digital twin output.

Current integration source:

```text
backend/data_processed/sample/haki_lidar/segments/map_segments.json
```

Current record count: `143`.

Required fields:

```json
{
  "segment_id": "S047",
  "from_node": "1",
  "to_node": "2",
  "length": 20.5,
  "is_chokepoint": false
}
```

### `GET /api/digital-twin/graph`

Returns graph nodes and edges derived from segment data.

Current integration source:

```text
backend/data_processed/sample/haki_lidar/graph/mine_graph.json
```

The current graph is segment-to-segment:

```json
{
  "source": "S001",
  "target": "S011",
  "weight": 17.383
}
```

### `GET /api/digital-twin/pointcloud`

Returns local viewer metadata for the frontend LiDAR layer.

```json
{
  "preview_url": "/models/tunnel_preview_500k.ply",
  "downsampled_url": "/models/tunnel_downsampled.ply"
}
```

### `GET /api/workers?time_step=0`

Returns worker state for one timestep.

Required fields:

```json
{
  "worker_id": "WORKER_01",
  "time_step": 0,
  "current_segment": "S047",
  "position": {"x": 0.0, "y": 0.0, "z": 0.0},
  "position_reliability": 0.86,
  "status": "safe"
}
```

### `GET /api/risk/segments?time_step=0`

Returns final segment risk for one timestep.

Current integration behavior:

- Reads Haki geometry risk from `haki_lidar/risk/geometry_risk.json`.
- Reads Recep environmental risk from `risk/environmental_risk.json`.
- Reads Huseyin worker occupancy/tracking state from `workers/workers.json` for current snapshots.
- Returns one integrated risk record per Haki segment.

This is the integration adapter, not the final advanced Enes risk model yet.

Required fields:

```json
{
  "segment_id": "S047",
  "final_risk_score": 58.5,
  "risk_level": "medium",
  "geometry_risk": 54.7,
  "environmental_risk": 52.8,
  "worker_exposure_risk": 100.0,
  "route_blockage_risk": 44.7,
  "active_reasons": ["LiDAR geometry risk 54.7"]
}
```

### `GET /api/gas-sensors?time_step=0`

Returns gas/methane sensor state for one timestep.

### `GET /api/risk/environmental?time_step=0`

Returns Recep's environmental/methane risk records for one timestep.

### `GET /api/risk/geometry`

Returns Haki's geometry risk records.

### `GET /api/scenarios/collapse`

Returns the current collapse scenario result.

### `GET /api/routes/emergency`

Query examples:

```text
/api/routes/emergency?worker_id=WORKER_01&time_step=6
/api/routes/emergency?segment_id=S047&blocked_segment=S004&exit_node=3
```

Returns:

```json
{
  "reachable": true,
  "trapped": false,
  "route_segments": ["S001", "S002"],
  "route_nodes": ["35", "3"],
  "cost_policy": "length + final_risk_score * 0.20"
}
```
