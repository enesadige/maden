from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "00_inventory.py",
    "01_build_segments.py",
    "02_sample_lidar.py",
    "03_lidar_geometry_features.py",
    "04_build_uwb_worker_timeline.py",
    "05_build_gas_timeline.py",
    "05b_sensor_drift_reliability.py",
    "06_graph_risk_analysis.py",
    "07_fuse_risk_timeline.py",
    "08_emergency_route_analysis.py",
    "09_generate_dashboard.py",
]


def main() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    for script in SCRIPTS:
        path = ROOT / "scripts" / script
        print(f"\n==> {script}")
        subprocess.run([sys.executable, str(path)], cwd=str(ROOT), env=env, check=True)


if __name__ == "__main__":
    main()

