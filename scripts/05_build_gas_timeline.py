from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.methane_processing.run_pipeline import run  # noqa: E402


def main() -> None:
    run()


if __name__ == "__main__":
    main()
