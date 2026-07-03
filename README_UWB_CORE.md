# MadenGuard UWB Worker Tracking MVP

## Scope

This module will plan UWB anchors and graph-following cables, extract configured UTIL movement proxies, map workers onto Haki segment IDs, estimate anchor visibility and tracking reliability, and produce UWB-owned handoff outputs.

## Out of Scope

- Frontend and dashboard changes
- Backend final-risk fusion
- Emergency route planning
- Gas and sensor processing
- A separate tunnel or segment map
- Modifying or copying Haki handoff files

## Read-only Haki Inputs

The paths below are configuration-driven, read-only inputs:

```text
backend/data_processed/sample/haki_lidar/segments/map_segments.json
backend/data_processed/sample/haki_lidar/segments/segment_metadata.json
backend/data_processed/sample/haki_lidar/graph/mine_graph.json
backend/data_processed/sample/haki_lidar/risk/geometry_risk.json
```

## External UTIL UWB Dataset

The raw UTIL dataset remains outside the repository. Raw CSV, bag and archive files must not be copied or committed.

## Generated Outputs

Only approved small handoff files will be written beneath:

```text
backend/data_processed/sample/anchors/
backend/data_processed/sample/workers/
backend/data_processed/sample/risk/
```

## API Testing Output Location

For local Django API testing, the UWB pipeline publishes API-ready files under:

```text
backend/data_processed/sample/
```

This matches the current Django JSON loader root. Haki's files remain under `sample/haki_lidar` and are read-only. UWB outputs are written to sibling folders `sample/workers`, `sample/anchors` and `sample/risk`.

`workers.json` includes both the new UWB fields and legacy backend compatibility fields so the current `apps.workers` loader can read it without immediate backend changes. In each snapshot, `mapped_segment_id` equals `current_segment`, `uwb_pose` equals `position`, and `motion_status` equals `status`.

## Geometry Limitation

The current Haki handoff provides bounds-center geometry. Dynamic anchor planning is performed at segment/graph level using segment centers, bounds, graph edges and edge weights. Exact centerline-based tunnel curve placement is not available until Haki provides centerline/start-end geometry.

## Worker Movement Limitation

UTIL UWB pose_x, pose_y and pose_z values are motion-capture ground-truth proxy positions, not real UWB-estimated miner positions. In this MVP they are used only as worker movement proxies.

## Gerçek UWB Position Solver Genişletmesi

The existing MVP mode is `position_source_mode = "mocap_proxy"`. In this mode, `pose_x/y/z` values are used as motion-capture proxy worker positions, and anchor distance/reliability calculations are derived from those proxy positions.

The experimental solver mode is `position_source_mode = "tdoa_solver"`. In tdoa_solver mode, worker position is estimated from UWB measurements. The UTIL pose_x/y/z values are used only as motion-capture ground-truth proxy references for validation metrics, not as the primary position source.

This extension supports the plumbing for calibrated anchor coordinates plus TDoA/ToF measurements to produce estimated worker positions and validation error metrics. Solver outputs are optional and must not replace `workers.json` unless explicitly enabled by config.

Real field deployment requires measured anchor coordinates, clock synchronization, TDoA/ToF calibration, NLOS/multipath validation, and certified/ex-proof hardware for mine use.

Bu genişletme, gerçek UWB sinyalinden konum hesaplama altyapısını ekler. Ancak gerçek saha doğruluğu, anchor kalibrasyonu ve donanım doğrulaması yapılmadan sertifikalı lokalizasyon iddiası taşımaz.

## Anchor Planning Policy

Anchor planning will use segment length, bounds, graph degree, exits, geometry risk, neighbor-center turns and long graph edges. IDs use `A001` format, and positions will be clamped or validated against segment bounds when possible.

## Cable Topology Policy

Primary cables will follow Haki graph adjacency from an exit-adjacent head end. Cross-links provide infrastructure redundancy only. Cable topology does not modify Haki's graph and is not emergency routing.

## Worker Timeline Policy

Worker count and explicit source-trial assignments come from configuration. Positions will be resampled, transformed into the Haki frame, and mapped by bounds containment, center distance and graph continuity.

## Reliability Policy

Tracking status will be based on visible-anchor count. Position reliability will combine flight-signal reliability, anchor visibility, estimated signal quality, mapping confidence and continuity, with results constrained to `[0, 1]`.

## Exposure Policy

Worker occupancy contributes `worker_exposure_risk = 100.0`. Low position reliability does not reduce occupancy exposure; it increases a separate tracking-risk score. Final risk fusion remains backend-owned.

## Validation Policy

Validation will cover canonical IDs, Haki segment references, finite positions, score bounds, visibility consistency, tracking states, exposure invariants and configured worker count. Failed validation will prevent output publication.

## Run Order

Implementation order is `core`, config loading, Haki loading, anchor planning, cable planning, dataset reading, position extraction, coordinate mapping, segment mapping, timeline building, distance calculation, enrichment, exposure, validation, then orchestration. The pipeline is not implemented or runnable in this scaffold.

## Git Push Rules

Commit only source, documentation, example configuration, and approved small handoff outputs. Never commit raw datasets, local configuration, LAS/LAZ files, archives, cache files or large generated artifacts.

## 2026-07 Worker Count and Behavior Anomaly Update

Default worker count is now 10. Worker count remains config-driven in the UWB config/pipeline layer:

- If `workers` is explicitly filled, that list is used exactly as the active worker source of truth.
- If `workers` is empty or missing and `worker_defaults.allow_auto_generate_workers=true`, `worker_defaults.default_worker_count` generates worker identities such as `WORKER_01` to `WORKER_10` with `TAG_001` to `TAG_010`.
- Worker count can be increased or decreased by config only; no Django code change is required.
- Django does not generate workers. Django only reads generated JSON outputs such as `backend/data_processed/sample/workers/workers.json` and `backend/data_processed/sample/workers/worker_segment_timeline.json`.

Current generated result:

```text
workers count: 10
timeline record count: 1308
anomaly event count: 1640
```

New UWB behavior anomaly outputs:

```text
backend/data_processed/sample/workers/behavior_anomaly_events.json
backend/data_processed/sample/workers/behavior_anomaly_summary.json
```

Allowed behavior anomaly event types:

```text
stationary_too_long
low_position_reliability
tracking_lost_in_risky_segment
entered_high_risk_segment
near_blocked_segment
route_deviation
```

Behavior anomaly events are rule-based MVP analytics only. They are not certified safety decisions.

LOS/NLOS limitation: LOS/NLOS classifier is not implemented. Current anchor visibility is heuristic and based on distance/graph visibility assumptions. A real LOS/NLOS classifier requires labeled LOS/NLOS data before it can be trained, validated, and used for safety-relevant interpretation.

MVP'de UTIL pose verisi worker hareket proxy'si olarak kullanılır. Gerçek UWB TDoA solver deneysel altyapıdır; saha kalibrasyonu ve ölçüm birimi doğrulaması olmadan gerçek konum doğruluğu iddiası taşımaz.

Worker trapped durumu UWB modülünde nihai olarak üretilmez. UWB modülü worker konumu, güvenilirlik, exposure ve davranış anomaly sinyalleri üretir; trapped kararı backend route/simulation katmanında verilmelidir.
