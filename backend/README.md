# MadenGuard Backend

Backend foundation for the MadenGuard AI MVP.

This first version is a lightweight Django JSON API. It reads small processed
JSON outputs from `backend/data_processed/sample` and exposes stable endpoints
for the frontend and team modules.

## Run Locally

```bash
cd /Users/enesdasci/Desktop/madenguard/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver
```

Open:

```text
http://localhost:8000/api/health
```

## Endpoints

```text
GET /api/health
GET /api/digital-twin/segments
GET /api/digital-twin/graph
GET /api/digital-twin/pointcloud
GET /api/workers?time_step=0
GET /api/risk/segments?time_step=0
GET /api/risk/environmental?time_step=0
GET /api/risk/geometry
GET /api/gas-sensors?time_step=0
GET /api/simulation/state?time_step=0
GET /api/simulation/scenario?scenario_id=collapse_s004&time_step=27
GET /api/simulation/trapped?time_step=27
GET /api/integration/status?time_step=27&scenario_id=collapse_s004
GET /api/scenarios/collapse
GET /api/routes/emergency?worker_id=WORKER_01&time_step=6
```

## Team Handoff

- Haki writes LiDAR/geometric outputs under `data_processed/sample/digital_twin` and `data_processed/sample/graph`.
- Recep writes gas/methane outputs under `data_processed/sample/sensors` and risk outputs under `data_processed/sample/risk`.
- Huseyin writes worker/UWB outputs under `data_processed/sample/workers`.
- Enes owns backend fusion, routing, scenario logic, integration status checks, and the public API contract.
- Selim consumes only these API endpoints; no raw LAS or raw large CSV in frontend.

## Current Integrated Sources

- Haki LiDAR source of truth: `data_processed/sample/haki_lidar/`
- Huseyin worker/UWB source: `data_processed/sample/workers/`
- Recep methane/gas source: `data_processed/sample/sensors/` and `data_processed/sample/risk/environmental_risk.json`
- Integrated risk endpoint: `GET /api/risk/segments`
- Joined simulation state: `GET /api/simulation/state`
- Scenario motor: `GET /api/simulation/scenario`
- Trapped analysis: `GET /api/simulation/trapped`
- Contract health: `GET /api/integration/status`

## Backend Contract Notes

- Canonical segment IDs are `S001`, `S002`, `S047`.
- `segment_id` is the shared join key across LiDAR, gas, worker, risk, and scenario outputs.
- `time_step=0` is the latest snapshot for worker APIs, but the simulation endpoints can also replay historical steps.
- `GET /api/routes/emergency` accepts `worker_id`, `time_step`, `segment_id`, `blocked_segment`, and `scenario`.
- `GET /api/simulation/scenario` is the backend-owned story/sim state generator for collapse, methane spike, worker-at-risk, and route preview flows.
- `GET /api/integration/status` is the quick sanity endpoint for contract drift checks.

## Segment ID Rule

Canonical segment IDs are `S001`, `S002`, `S047`.
Legacy IDs like `SEG_047` are normalized by the backend.
