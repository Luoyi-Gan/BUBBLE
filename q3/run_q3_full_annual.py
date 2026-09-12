#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from time import perf_counter

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import ATTACH1, ATTACH2, ATTACH3, ANNUAL_OUTPUT_DIR  # noqa: E402
from q3.data import load_q3_data  # noqa: E402
from q3.full_annual import parse_boundaries, run_q3_full_annual  # noqa: E402


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Q3 full-year continuous SOC for year-end A and/or B")
    parser.add_argument(
        "--boundary",
        default="both",
        help="A, B, or both (default both). A then B are independent 365-day campaigns.",
    )
    args = parser.parse_args()
    selected = parse_boundaries(args.boundary)
    started = perf_counter()
    data = load_q3_data()
    result = run_q3_full_annual(data, boundaries=selected)
    elapsed = perf_counter() - started
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "output_dir": str(ANNUAL_OUTPUT_DIR),
        "elapsed_seconds": elapsed,
        "n_runs": result["n_runs"],
        "all_physical_pass": result["audit"]["all_pass"],
        "load_treatment": "causal_load_main",
        "pv_mapping_mode": "linear_anchor_main",
        "settlement_mode": "anchor_final_main",
        "jan01_soc_kwh": 6000.0,
        "boundaries": {name: target for name, target in selected},
        "git_commit": _git_hash(),
        "solver": "HIGHS",
        "dependency_versions": {
            "python": sys.version.split()[0],
            "numpy": __import__("numpy").__version__,
            "pandas": __import__("pandas").__version__,
            "cvxpy": __import__("cvxpy").__version__,
            "matplotlib": __import__("matplotlib").__version__,
        },
        "run_command": ".venv/bin/python q3/run_q3_full_annual.py --boundary both",
        "note": (
            "Independent 365-day campaigns for year-end A=1200 and/or B=6000. "
            "Does not choose a single official boundary and does not write result3.xlsx."
        ),
        "totals": result["totals"].to_dict(orient="records"),
        "delta": result["delta"].to_dict(orient="records") if len(result["delta"]) else [],
    }
    ANNUAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (ANNUAL_OUTPUT_DIR / "run_meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: payload[k] for k in ("elapsed_seconds", "n_runs", "all_physical_pass", "git_commit")}, indent=2))
    print(result["totals"].to_string(index=False))
    if len(result["delta"]):
        print(result["delta"].to_string(index=False))


if __name__ == "__main__":
    main()
