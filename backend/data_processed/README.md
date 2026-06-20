# Backend Processed Data

This directory is the canonical handoff area for small processed files.

Do not put raw LAS/LAZ, full raw CSV, large archives, or cache files here.
Those stay on external disks or in Downloads and are documented by path.

## Expected Layout

```text
data_processed/
  sample/
    digital_twin/segments.json
    graph/mine_graph.json
    sensors/gas_sensors.json
    workers/workers.json
    risk/risk_segments.json
    scenarios/collapse_result.json
```

`sample/` is safe to commit. Future large or private live outputs should go
under `raw/`, `live/`, or `cache/`, which are ignored by git.
