#!/usr/bin/env python3
"""Annual Q2 re-run: fixed K=8 plus causal rolling risk-quantile reserve."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    E_INITIAL_KWH,
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    NUMERIC_TOL,
)
from q2.data import load_q2_data, write_input_audit  # noqa: E402
from q2.forecast import assert_no_forecast_leakage, build_forecast_archive, write_forecast_archive  # noqa: E402
from q2.pilot import KChoice, build_next_day_value_cuts, run_posterior_mpc, select_risk_alpha  # noqa: E402
from q2.scenarios import build_scenarios  # noqa: E402


def main() -> None:
    started = perf_counter()
    output = FULL_K8_RISK_OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    dispatch_dir = output / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    forbidden = ROOT / "output" / "result2.xlsx"
    before = forbidden.stat().st_mtime_ns if forbidden.exists() else None

    data = load_q2_data()
    archive = build_forecast_archive(data)
    assert_no_forecast_leakage(archive)
    write_input_audit(data, output / "input_audit.json")
    write_forecast_archive(data, archive, output / "forecast_archive.csv", output / "forecast_audit.md")

    policy_start_soc = np.full(len(data.dates), np.nan)
    daily_rows: list[dict] = []
    calibration_rows: list[dict] = []
    value_rows: list[dict] = []
    soc = E_INITIAL_KWH

    for calibration in range(0, len(data.dates), 14):
        effective_end = min(calibration + 13, len(data.dates) - 1)
        if calibration < 28:
            # A K=8 distribution and an empirical risk quantile both need the
            # complete 28-day residual pool.  Before then, use the same causal
            # K=1/no-reserve warmup rather than inventing an unsupported tail.
            alpha = None
            active_k = 1
            candidates = [
                {
                    "risk_alpha": alpha,
                    "validation_days": 0,
                    "mean_validation_cost_yuan": np.nan,
                    "standard_error_yuan": np.nan,
                    "emergency_purchase_kwh": np.nan,
                    "mean_solve_seconds": np.nan,
                    "within_time_limit": True,
                    "selected": True,
                    "fallback_reason": "K=1_no_risk_reserve_before_28_day_pool",
                }
            ]
        else:
            risk_choice = select_risk_alpha(
                data, archive, policy_start_soc, calibration, FIXED_SCENARIO_K
            )
            alpha = risk_choice.selected_alpha
            active_k = FIXED_SCENARIO_K
            candidates = [
                {**row, "fallback_reason": ""} for row in risk_choice.rows
            ]
        for candidate in candidates:
            calibration_rows.append(
                {
                    "calibration_date": data.dates[calibration].strftime("%Y-%m-%d"),
                    "history_cutoff_date": (
                        data.dates[calibration - 1].strftime("%Y-%m-%d")
                        if calibration else "none"
                    ),
                    "fixed_k": active_k,
                    "effective_start_date": data.dates[calibration].strftime("%Y-%m-%d"),
                    "effective_end_date": data.dates[effective_end].strftime("%Y-%m-%d"),
                    **candidate,
                }
            )
        for i in range(calibration, effective_end + 1):
            policy_start_soc[i] = soc
            if i == 0:
                choice = None
            else:
                choice = KChoice(
                    i,
                    active_k,
                    build_scenarios(i, data, archive, active_k),
                    (),
                )
            cuts, cut_audit = build_next_day_value_cuts(
                data, archive, i, active_k, risk_alpha=alpha
            )
            value_rows.extend(
                {"decision_date": data.dates[i].strftime("%Y-%m-%d"), **row}
                for row in cut_audit
            )
            result = run_posterior_mpc(
                data,
                archive,
                choice,
                soc,
                dispatch_dir / f"dispatch_{data.dates[i].strftime('%Y-%m-%d')}.csv",
                terminal_value_cuts=cuts,
                variant="fixed_k8_rolling_risk_quantile",
                risk_alpha=alpha,
            )
            if not result["pass"]:
                raise AssertionError(f"physical validation failed on {result['date']}")
            result["effective_scenario_count"] = (
                1 if choice is None else len(choice.scenarios.probabilities)
            )
            daily_rows.append(result)
            soc = float(result["soc_end_kwh"])

    daily = pd.DataFrame(daily_rows)
    calibration_frame = pd.DataFrame(calibration_rows)
    value_audit = pd.DataFrame(value_rows)
    continuity = float(
        np.max(
            np.abs(
                daily["soc_start_kwh"].to_numpy()[1:]
                - daily["soc_end_kwh"].to_numpy()[:-1]
            )
        )
    )
    if (
        len(daily) != len(data.dates)
        or not daily["pass"].all()
        or continuity >= NUMERIC_TOL
        or not calibration_frame["within_time_limit"].all()
    ):
        raise AssertionError("annual K=8 risk-quantile validation failed")
    daily.to_csv(output / "daily_summary.csv", index=False)
    calibration_frame.to_csv(output / "risk_calibration.csv", index=False)
    value_audit.to_csv(output / "next_day_value_audit.csv", index=False)
    report = {
        "status": "PASS",
        "policy": "fixed K=8 plus 14-day causal rolling risk-quantile reserve",
        "days": len(daily),
        "total_cost_yuan": float(daily["total_cost_yuan"].sum()),
        "planned_cost_yuan": float(daily["planned_cost_yuan"].sum()),
        "emergency_cost_yuan": float(daily["emergency_cost_yuan"].sum()),
        "emergency_kwh": float(daily["emergency_kwh"].sum()),
        "unused_plan_kwh": float(daily["unused_plan_kwh"].sum()),
        "curtailment_kwh": float(daily["curtailment_kwh"].sum()),
        "max_balance_residual_kwh": float(daily["max_balance_residual_kwh"].max()),
        "max_simultaneous_cd_kwh2": float(daily["max_simultaneous_cd_kwh2"].max()),
        "max_x_minus_q_kwh": float(daily["max_x_minus_q_kwh"].max()),
        "max_cross_day_soc_gap_kwh": continuity,
        "selected_alpha_periods": {
            str(alpha): int(count)
            for alpha, count in daily["risk_alpha"].fillna("no_reserve").groupby(
                daily["risk_alpha"].fillna("no_reserve")
            ).size().items()
        },
        "max_value_cut_gap_yuan": float(value_audit["certified_max_gap_yuan"].max()),
        "elapsed_seconds": perf_counter() - started,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    after = forbidden.stat().st_mtime_ns if forbidden.exists() else None
    if after != before:
        raise RuntimeError("Forbidden output/result2.xlsx was created or modified")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
