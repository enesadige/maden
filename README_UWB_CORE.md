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
