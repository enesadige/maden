# Team Output Contracts

This file defines what each teammate should put into the backend handoff area.

Canonical handoff root:

```text
backend/data_processed/sample/
```

## Haki - LiDAR / Digital Twin

Target files:

```text
digital_twin/segments.json
graph/mine_graph.json
risk/geometry_risk.json
```

Segment fields:

```json
{
  "segment_id": "S001",
  "from_node": "3",
  "to_node": "35",
  "length": 14.6,
  "is_chokepoint": false,
  "geometry_risk": 25.6,
  "risk_reason": "normal geometry"
}
```

Notes:

- Do not create a second segment ID standard.
- Use `S001` format. Backend can temporarily normalize `SEG_001`, but final files should use `S001`.
- Do not commit raw LAS/LAZ.

## Recep - Gas / Methane Sensors

Target files:

```text
sensors/gas_sensors.json
risk/environmental_risk.json
```

Sensor fields:

```json
{
  "time_step": 0,
  "sensor_id": "GAS_SENSOR_01",
  "segment_id": "S004",
  "methane_value": 0.2,
  "methane_risk_score": 87.5,
  "anomaly_score": 0.91,
  "status": "critical"
}
```

Notes:

- MVP AI/ML method: threshold + z-score + rolling change.
- Optional ML: Isolation Forest for anomaly score.
- Include sensor confidence if drift/reliability is calculated.

## Huseyin - UWB / Worker Tracking

Target files:

```text
workers/workers.json
workers/worker_segment_timeline.json
risk/worker_exposure_risk.json
```

Worker fields:

```json
{
  "time_step": 0,
  "worker_id": "WORKER_01",
  "current_segment": "S047",
  "position": {"x": 1.2, "y": 0.4, "z": 1.5},
  "position_reliability": 0.86,
  "status": "safe"
}
```

Notes:

- Do not generate an independent tunnel map.
- Map worker position onto Haki's `segment_id` values.
- Optional ML: LOS/NLOS confidence and movement anomaly detection.

## Enes - Backend / Fusion / Routing

Backend-owned outputs:

```text
risk/risk_segments.json
scenarios/collapse_result.json
```

Final risk fields:

```json
{
  "time_step": 0,
  "segment_id": "S047",
  "final_risk_score": 58.5,
  "risk_level": "medium",
  "geometry_risk": 54.7,
  "environmental_risk": 52.8,
  "worker_exposure_risk": 100.0,
  "route_blockage_risk": 44.7,
  "active_reasons": ["worker is inside this segment"]
}
```

Notes:

- Backend is the source of truth for final risk score.
- Route engine should consider both graph distance and risk cost.
- Frontend should not recompute risk.

## Selim - Frontend

Selim consumes:

```text
GET /api/digital-twin/segments
GET /api/workers
GET /api/risk/segments
GET /api/gas-sensors
GET /api/routes/emergency
```

Notes:

- No raw LAS, no raw big CSV in frontend.
- Frontend displays risk scores, reasons, worker state, and emergency route result from API.
