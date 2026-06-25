# MadenGuard Methane Processing

This module generates Recep-owned methane / gas sensor handoff outputs for the MadenGuard AI backend.

## Scope

This module produces:

- backend/data_processed/sample/sensors/gas_sensors.json
- backend/data_processed/sample/risk/environmental_risk.json
- processed/timelines/gas_sensors_timeline.json
- simulation_ready/gas_sensors_timeline.json

It does not produce final segment risk, worker tracking, LiDAR segments, digital twin geometry, or emergency routes.

## Method

- Reads OpenML methane CSV from MADENGUARD_METHANE_CSV or config/paths.json.
- Uses MM263, MM264, MM256 as independent methane sensor channels.
- Places gas sensors onto Haki LiDAR segment IDs.
- Calculates rolling z-score anomaly scores per sensor.
- Calculates methane risk from robust methane value score and anomaly score.
- Writes backend-compatible JSON outputs.

## Run

Set local methane CSV path:

export MADENGUARD_METHANE_CSV="/path/to/methane_openml_42701.csv"

Then run:

python scripts/05_build_gas_timeline.py

## Important

Raw methane CSV must not be committed.
