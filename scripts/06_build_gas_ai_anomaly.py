from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.methane_processing.gas_ai_anomaly_model import build_gas_ai_anomaly  # noqa: E402


def main() -> None:
    result = build_gas_ai_anomaly()

    print(f"[gas-ai] model: {result['model_name']}@{result['model_version']}")
    print(f"[gas-ai] input: {result['input_path']}")
    print(f"[gas-ai] output: {result['output_path']}")
    print(f"[gas-ai] model params: {result['model_params_path']}")
    print(f"[gas-ai] report: {result['report_path']}")
    print(f"[gas-ai] records: {result['record_count']}")
    print(f"[gas-ai] level counts: {result['level_counts']}")
    print("[gas-ai] validation: OK")


if __name__ == "__main__":
    main()