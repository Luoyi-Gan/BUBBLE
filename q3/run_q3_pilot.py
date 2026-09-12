#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import ATTACH1, ATTACH2, ATTACH3, OUTPUT_DIR  # noqa: E402
from q3.data import load_q3_data  # noqa: E402
from q3.pilot import run_q3_pilot  # noqa: E402


def main() -> None:
    started = perf_counter()
    data = load_q3_data()
    result = run_q3_pilot(data)
    elapsed = perf_counter() - started
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "output_dir": str(OUTPUT_DIR),
        "elapsed_seconds": elapsed,
        "initial_soc": result["initial_soc"],
        "n_runs": result["n_runs"],
        "load_treatment": result.get("load_treatment"),
        "all_physical_pass": result["audit"]["all_pass"],
        "causality_all_pass": result["causality"]["all_pass"],
        "solver": "HIGHS",
        "dependency_versions": {
            "python": sys.version.split()[0],
            "numpy": __import__("numpy").__version__,
            "pandas": __import__("pandas").__version__,
            "cvxpy": __import__("cvxpy").__version__,
            "matplotlib": __import__("matplotlib").__version__,
        },
        "comparison": result["comparison"].to_dict(orient="records"),
    }
    (OUTPUT_DIR / "run_meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                k: payload[k]
                for k in (
                    "elapsed_seconds",
                    "initial_soc",
                    "all_physical_pass",
                    "causality_all_pass",
                    "n_runs",
                    "load_treatment",
                    "dependency_versions",
                )
            },
            indent=2,
        )
    )
    print(
        result["comparison"][
            [
                "date",
                "strategy",
                "load_information_case",
                "with_terminal_value",
                "total_cost_yuan",
                "adjustment_count",
            ]
        ]
    )


if __name__ == "__main__":
    main()
