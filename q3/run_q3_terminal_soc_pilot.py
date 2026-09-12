#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from time import perf_counter

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import ATTACH1, ATTACH2, ATTACH3, TERMINAL_SOC_OUTPUT_DIR  # noqa: E402
from q3.data import load_q3_data  # noqa: E402
from q3.terminal_soc_pilot import run_q3_terminal_soc_pilot  # noqa: E402


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
    result = run_q3_terminal_soc_pilot(data)
    elapsed = perf_counter() - started
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "output_dir": str(TERMINAL_SOC_OUTPUT_DIR),
        "elapsed_seconds": elapsed,
        "n_runs": result["n_runs"],
        "all_physical_pass": result["audit"]["all_pass"],
        "load_treatment": "causal_load_main",
        "pv_mapping_mode": "linear_anchor_main",
        "settlement_mode": "anchor_final_main",
        "isolated_dec01_soc_kwh": 6000.0,
        "boundaries": {"A_q2_aligned": 1200.0, "B_energy_neutral": 6000.0},
        "git_commit": _git_hash(),
        "solver": "HIGHS",
        "dependency_versions": {
            "python": sys.version.split()[0],
            "numpy": __import__("numpy").__version__,
            "pandas": __import__("pandas").__version__,
            "cvxpy": __import__("cvxpy").__version__,
            "matplotlib": __import__("matplotlib").__version__,
        },
        "run_command": ".venv/bin/python q3/run_q3_terminal_soc_pilot.py",
        "note": (
            "December A/B terminal-SOC decision trial only. "
            "Does not choose the official year-end boundary and does not write result3.xlsx."
        ),
        "totals": result["totals"].to_dict(orient="records"),
        "delta": result["delta"].to_dict(orient="records"),
    }
    TERMINAL_SOC_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (TERMINAL_SOC_OUTPUT_DIR / "run_meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "elapsed_seconds": elapsed,
                "n_runs": result["n_runs"],
                "all_physical_pass": result["audit"]["all_pass"],
                "git_commit": payload["git_commit"],
            },
            indent=2,
        )
    )
    print(result["totals"].to_string(index=False))
    print(result["delta"].to_string(index=False))


if __name__ == "__main__":
    main()
