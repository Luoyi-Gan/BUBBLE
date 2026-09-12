#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from time import perf_counter

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import ATTACH1, ATTACH2, ATTACH3, SENSITIVITY_OUTPUT_DIR  # noqa: E402
from q3.data import load_q3_data  # noqa: E402
from q3.sensitivity import run_q3_sensitivity  # noqa: E402


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    started = perf_counter()
    data = load_q3_data()
    result = run_q3_sensitivity(data)
    elapsed = perf_counter() - started
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "output_dir": str(SENSITIVITY_OUTPUT_DIR),
        "elapsed_seconds": elapsed,
        "initial_soc": result["initial_soc"],
        "n_runs": result["n_runs"],
        "all_physical_pass": result["audit"]["all_pass"],
        "load_treatment": "causal_load_main",
        "git_commit": _git_hash(),
        "solver": "HIGHS",
        "dependency_versions": {
            "python": sys.version.split()[0],
            "numpy": __import__("numpy").__version__,
            "pandas": __import__("pandas").__version__,
            "cvxpy": __import__("cvxpy").__version__,
            "matplotlib": __import__("matplotlib").__version__,
        },
        "run_command": ".venv/bin/python q3/run_q3_sensitivity.py",
        "comparison": result["comparison"].to_dict(orient="records"),
    }
    SENSITIVITY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (SENSITIVITY_OUTPUT_DIR / "run_meta.json").write_text(
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
                    "n_runs",
                    "git_commit",
                    "dependency_versions",
                )
            },
            indent=2,
        )
    )
    cols = [
        "date",
        "strategy",
        "pv_mapping_mode",
        "settlement_mode",
        "total_cost_yuan",
        "delta_total_vs_baseline_yuan",
    ]
    print(result["comparison"][cols].to_string(index=False))


if __name__ == "__main__":
    main()
