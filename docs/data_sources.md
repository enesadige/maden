# Data Sources

Large source data stays outside the git repository.

Current local paths:

```text
MediumRes LAS:
/Volumes/enes/Tunnel_Circuit_MediumRes_Scan_EX_Frame.las

DARPA graph:
/Users/enesdasci/Downloads/drive-download-20260619T202713Z-3-001/ground_truth_repo/systems_tunnel_ground_truth/network/data/ex_edgelist.csv

Methane CSV:
/Volumes/enes/MadenGuardAI/Mendeley_Methane_CoalMine-20260619T175740Z-3-001/Mendeley_Methane_CoalMine/openml_mirror/methane_openml_42701.csv

UTIL UWB CSV:
/Volumes/enes/UTIL_UWB-20260619T173659Z-3-003/UTIL_UWB/original_dataset/extracted_dataset/dataset/flight-dataset/csv-data/const1/const1-trial5-tdoa2.csv

UCI Gas Drift:
/Volumes/enes/UCI_Gas_Sensor_Drift-20260619T175738Z-3-001/UCI_Gas_Sensor_Drift/extracted_dataset
```

Rules:

- Do not copy raw LAS/LAZ into the repo.
- Do not commit huge raw CSV/parquet/archive files.
- Commit small processed JSON samples needed by backend/frontend integration.
