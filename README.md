# MadenGuard AI

Local, data-backed prototype for underground mine digital twin risk analysis.

The project now has two layers:

- `scripts/`, `src/`, `processed/`, `simulation_ready/`: local data processing and demo generation.
- `backend/`: Django JSON API foundation for team integration and frontend consumption.

## Purpose

MadenGuard AI combines tunnel point-cloud geometry, DARPA tunnel graph topology, UWB-like worker movement, methane time series, and gas sensor drift data to produce explainable segment risk and emergency route analysis.

This is not a raw data mirror. Large source files stay in their original locations and are read safely.

## Raw Data Locations

- MediumRes LAS: `/Volumes/enes/Tunnel_Circuit_MediumRes_Scan_EX_Frame.las`
- DARPA graph: `/Users/enesdasci/Downloads/drive-download-20260619T202713Z-3-001/ground_truth_repo/systems_tunnel_ground_truth/network/data/ex_edgelist.csv`
- Methane CSV: `/Volumes/enes/MadenGuardAI/Mendeley_Methane_CoalMine-20260619T175740Z-3-001/Mendeley_Methane_CoalMine/openml_mirror/methane_openml_42701.csv`
- UTIL UWB CSV: `/Volumes/enes/UTIL_UWB-20260619T173659Z-3-003/UTIL_UWB/original_dataset/extracted_dataset/dataset/flight-dataset/csv-data/const1/const1-trial5-tdoa2.csv`
- UCI Gas Drift: `/Volumes/enes/UCI_Gas_Sensor_Drift-20260619T175738Z-3-001/UCI_Gas_Sensor_Drift/extracted_dataset`

## Safety Rules

- Do not copy the 10 GB LAS into this project.
- Do not call `las.read()` or load all points into memory.
- The first local pipeline uses a lightweight LAS reader that reads header bytes and samples selected point records only.
- Browser/dashboard output embeds only a small sampled point layer.

## Run

The initial safe pipeline uses Python stdlib only.

```bash
cd /Users/enesdasci/Desktop/madenguard
python3 scripts/run_all.py
```

Individual steps:

```bash
python3 scripts/00_inventory.py
python3 scripts/01_build_segments.py
python3 scripts/02_sample_lidar.py
python3 scripts/03_lidar_geometry_features.py
python3 scripts/04_build_uwb_worker_timeline.py
python3 scripts/05_build_gas_timeline.py
python3 scripts/05b_sensor_drift_reliability.py
python3 scripts/06_graph_risk_analysis.py
python3 scripts/07_fuse_risk_timeline.py
python3 scripts/08_emergency_route_analysis.py
python3 scripts/09_generate_dashboard.py
```

## Outputs

- `reports/data_inventory.md`
- `reports/lidar_geometry_analysis.md`
- `reports/graph_risk_analysis.md`
- `reports/uwb_worker_timeline_report.md`
- `reports/gas_risk_report.md`
- `reports/sensor_drift_report.md`
- `reports/final_risk_fusion_report.md`
- `reports/emergency_scenario_report.md`
- `processed/features/segments.json`
- `processed/features/lidar_geometry_features.csv`
- `processed/features/graph_risk_scores.csv`
- `processed/timelines/workers_timeline.json`
- `processed/timelines/gas_sensors_timeline.json`
- `processed/timelines/combined_simulation_timeline.json`
- `simulation_ready/final_segment_risk_timeline.json`
- `simulation_ready/emergency_result.json`
- `dashboards/madenguard_dashboard.html`

## Current Limitations

- FullRes LAS is not present and is not required for this MVP.
- LiDAR slice-to-graph segment matching is approximate in the first pass.
- UTIL UWB raw TDOA solving is not performed yet; pose columns are normalized onto tunnel segments.
- Methane processing scans a configurable local-safe row limit first. Increase `max_methane_rows` in `config/paths.json` for heavier processing.

## Next Improvements

- Add optional `laspy` chunk iterator path when dependencies are installed.
- Add PDAL decimation pipeline for CloudCompare-ready LAS samples.
- Replace approximate LiDAR slice mapping with stronger graph/centerline registration.
- Build a richer Three.js or Potree digital twin viewer when a small web-ready point cloud artifact is available.

## Backend API

The backend is the shared integration layer for Haki, Recep, Huseyin, Enes, and Selim.

```bash
cd /Users/enesdasci/Desktop/madenguard/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver
```

Local API:

```text
http://localhost:8000/api/health
```

Frontend can use:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Important docs:

- `docs/backend_api_contract.md`
- `docs/team_output_contracts.md`
- `docs/data_sources.md`

Private repo policy:

- Commit backend code, docs, small processed JSON samples, contracts, and examples.
- Do not commit raw LAS/LAZ, huge raw CSVs, local virtualenvs, `.env`, caches, or archives.
