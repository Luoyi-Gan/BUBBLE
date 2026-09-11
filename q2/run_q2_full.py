#!/usr/bin/env python3
"""Run the Q2 annual causal linked-policy calculation; no result2.xlsx export."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import FULL_OUTPUT_DIR, NUMERIC_TOL  # noqa: E402
from q2.data import load_q2_data, write_input_audit  # noqa: E402
from q2.forecast import assert_no_forecast_leakage, build_forecast_archive, write_forecast_archive  # noqa: E402
from q2.pilot import run_full_linked_policy  # noqa: E402


def main() -> None:
    started = perf_counter()
    forbidden = ROOT / "output" / "result2.xlsx"
    forbidden_before = forbidden.stat().st_mtime_ns if forbidden.exists() else None
    data = load_q2_data()
    FULL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_input_audit(data, FULL_OUTPUT_DIR / "input_audit.json")
    archive = build_forecast_archive(data)
    assert_no_forecast_leakage(archive)
    write_forecast_archive(
        data,
        archive,
        FULL_OUTPUT_DIR / "forecast_archive.csv",
        FULL_OUTPUT_DIR / "forecast_audit.md",
    )
    daily, calendar, value_audit = run_full_linked_policy(data, archive, FULL_OUTPUT_DIR)
    soc_gap = float(
        np.max(
            np.abs(
                daily["soc_start_kwh"].to_numpy()[1:]
                - daily["soc_end_kwh"].to_numpy()[:-1]
            )
        )
    )
    report = {
        "status": "PASS",
        "days": int(len(daily)),
        "total_cost_yuan": float(daily["total_cost_yuan"].sum()),
        "planned_cost_yuan": float(daily["planned_cost_yuan"].sum()),
        "emergency_cost_yuan": float(daily["emergency_cost_yuan"].sum()),
        "planned_q_kwh": float(daily["planned_q_kwh"].sum()),
        "actual_x_kwh": float(daily["actual_x_kwh"].sum()),
        "unused_plan_kwh": float(daily["unused_plan_kwh"].sum()),
        "emergency_kwh": float(daily["emergency_kwh"].sum()),
        "curtailment_kwh": float(daily["curtailment_kwh"].sum()),
        "soc_start_kwh": float(daily["soc_start_kwh"].iloc[0]),
        "soc_end_kwh": float(daily["soc_end_kwh"].iloc[-1]),
        "max_balance_residual_kwh": float(daily["max_balance_residual_kwh"].max()),
        "max_simultaneous_cd_kwh2": float(daily["max_simultaneous_cd_kwh2"].max()),
        "max_x_minus_q_kwh": float(daily["max_x_minus_q_kwh"].max()),
        "max_cross_day_soc_gap_kwh": soc_gap,
        "calendar_periods": int(calendar["calibration_date"].nunique()),
        "all_within_time_limit": bool(calendar["within_time_limit"].all()),
        "max_value_cut_gap_yuan": float(value_audit["certified_max_gap_yuan"].max()),
        "elapsed_seconds": perf_counter() - started,
    }
    if (
        report["max_balance_residual_kwh"] >= NUMERIC_TOL
        or report["max_cross_day_soc_gap_kwh"] >= NUMERIC_TOL
        or report["max_x_minus_q_kwh"] >= NUMERIC_TOL
    ):
        raise AssertionError("annual physical validation failed")
    (FULL_OUTPUT_DIR / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    forbidden_after = forbidden.stat().st_mtime_ns if forbidden.exists() else None
    if forbidden_after != forbidden_before:
        raise RuntimeError("Forbidden output/result2.xlsx was created or modified")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
