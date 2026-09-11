#!/usr/bin/env python3
"""Independent checks over C2-R1 policy-consistent artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    E_MAX_KWH,
    E_MIN_KWH,
    NUMERIC_TOL,
    PILOT_DATES,
    POLICY_CONSISTENT_OUTPUT_DIR,
    POWER_LIMIT_KWH,
    SIMULTANEOUS_CD_TOL,
    T,
)
from q2.data import load_q2_data  # noqa: E402
from q2.pilot import planned_q_hash  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    output = POLICY_CONSISTENT_OUTPUT_DIR
    data = load_q2_data()
    forecast = pd.read_csv(output / "forecast_policy_audit.csv")
    physical = pd.read_csv(output / "physical_audit.csv")
    diagnostics = pd.read_csv(output / "forecast_diagnostics.csv")
    consistency = json.loads((output / "policy_consistency_audit.json").read_text(encoding="utf-8"))
    report = json.loads((output / "validation.json").read_text(encoding="utf-8"))

    require(list(forecast["date"]) == list(PILOT_DATES), "R1 dates")
    require(report["status"] == "PASS", "R1 validation status")
    require(report["candidate_result2_xlsx"] is False, "no candidate result2")
    require(consistency["annual_run"] is False, "R1 must not run the year")
    require(consistency["validation_uses_full_day_actual_lp"] is False, "no full-day actual LP")
    require(consistency["k_used_for"] == ["risk_reserve_R", "intra_day_residual_weights"], "K uses")
    require(not consistency["has_scenario_specific_battery"] if "has_scenario_specific_battery" in consistency else True, "battery")

    for row in forecast.itertuples():
        target = pd.Timestamp(row.date)
        for field in ("load_source_dates", "pv_source_dates"):
            sources = str(getattr(row, field)).split(";")
            if sources != ["attachment1_fallback"]:
                require(
                    all(pd.Timestamp(source) < target for source in sources),
                    f"forecast leakage in {field} on {row.date}",
                )
        if str(row.residual_pool_end_date) != "none":
            require(
                pd.Timestamp(row.residual_pool_end_date) < target,
                f"residual pool leakage on {row.date}",
            )
        if str(row.medoid_dates) != "none":
            require(
                all(pd.Timestamp(item) < target for item in str(row.medoid_dates).split(";")),
                f"medoid leakage on {row.date}",
            )
        shapes = json.loads(row.day_ahead_variable_shapes)
        for name in ("charge", "discharge", "soc"):
            require(name in shapes, f"missing {name}")
            require(len(shapes[name]) == 1, f"{name} must be 1-D, got {shapes[name]}")
        require(not bool(row.has_scenario_specific_battery), "scenario battery flag")

    require(physical["pass"].all(), "physical pass")
    require(not physical["used_full_day_actual_lp"].any(), "artifact used full-day LP")
    require(diagnostics["selection_role"].eq("diagnostic_only").all(), "MAE must stay diagnostic")

    for date_text in PILOT_DATES:
        i = int(data.dates.get_loc(pd.Timestamp(date_text)))
        frame = pd.read_csv(output / "dispatch_daily" / f"dispatch_{date_text}.csv")
        require(len(frame) == T, f"{date_text} dispatch length")
        q = frame["planned_q_kwh"].to_numpy()
        x = frame["actual_x_kwh"].to_numpy()
        require(planned_q_hash(q) == physical.loc[physical["date"] == date_text, "planned_q_sha256"].iloc[0], "q hash")
        require(np.max(x - q) < NUMERIC_TOL, f"{date_text} x<=q")
        residual = (
            frame["actual_x_kwh"]
            + frame["emergency_kwh"]
            + frame["pv_kwh"]
            - frame["curtailment_kwh"]
            + frame["discharge_kwh"]
            - frame["load_kwh"]
            - frame["charge_kwh"]
        )
        require(float(residual.abs().max()) < NUMERIC_TOL, f"{date_text} balance")
        require(frame["soc_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL, f"{date_text} SOC min")
        require(frame["soc_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL, f"{date_text} SOC max")
        require(
            float((frame["charge_kwh"] * frame["discharge_kwh"]).max()) <= SIMULTANEOUS_CD_TOL,
            f"{date_text} simultaneous charge/discharge",
        )
        require(frame["charge_kwh"].max() <= POWER_LIMIT_KWH + NUMERIC_TOL, f"{date_text} charge limit")
        require(np.allclose(frame["load_kwh"].to_numpy(), data.load[i], atol=1e-12), "dispatch load")
        _ = i

    print("C2-R1 artifact validation passed")


if __name__ == "__main__":
    main()
