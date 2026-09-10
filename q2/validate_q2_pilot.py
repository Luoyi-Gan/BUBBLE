#!/usr/bin/env python3
"""Independent checks over generated Q2 pilot artifacts."""

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
    EMERGENCY_PRICE_MULTIPLIER,
    E_MAX_KWH,
    E_MIN_KWH,
    NUMERIC_TOL,
    OUTPUT_DIR,
    PILOT_DATES,
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
    data = load_q2_data()
    audit = json.loads((OUTPUT_DIR / "input_audit.json").read_text(encoding="utf-8"))
    require(audit["shape"] == {"days": 365, "periods_per_day": 144}, "P0 shape")
    require(audit["missing_count"] == 0, "P0 missing data")

    perfect = pd.read_csv(OUTPUT_DIR / "perfect_information_daily.csv")
    require(len(perfect) == 365 and perfect["pass"].all(), "P1 daily status")
    require(float(perfect["emergency_kwh"].sum()) < NUMERIC_TOL, "P1 emergency")
    require(
        np.max(
            np.abs(
                perfect["soc_start_kwh"].to_numpy()[1:]
                - perfect["soc_end_kwh"].to_numpy()[:-1]
            )
        )
        < NUMERIC_TOL,
        "P1 cross-day SOC",
    )

    forecast = pd.read_csv(OUTPUT_DIR / "forecast_archive.csv")
    require(len(forecast) == 365 * T, "P2 archive rows")
    require(forecast[["load_hat_kwh", "pv_hat_kwh"]].notna().all().all(), "P2 finite")
    for row in forecast.groupby("date", sort=False).first().reset_index().itertuples():
        for field in ("load_source_dates", "pv_source_dates"):
            sources = str(getattr(row, field)).split(";")
            if sources != ["attachment1_fallback"]:
                require(
                    all(pd.Timestamp(source) < pd.Timestamp(row.date) for source in sources),
                    f"P2 future source in {field} for {row.date}",
                )

    selected = pd.read_csv(OUTPUT_DIR / "scenario_selection.csv")
    require(selected.groupby("calibration_date")["selected"].sum().eq(1).all(), "P3 K choice")
    for date_text in PILOT_DATES:
        scenarios = pd.read_csv(OUTPUT_DIR / f"scenarios_{date_text}.csv")
        require(abs(float(scenarios["probability"].sum()) - 1.0) < 1e-12, "P3 probability")
        require((pd.to_datetime(scenarios["medoid_date"]) < pd.Timestamp(date_text)).all(), "P3 future medoid")

        dispatch = pd.read_csv(OUTPUT_DIR / f"q2_pilot_dispatch_{date_text}.csv")
        summary = pd.read_csv(OUTPUT_DIR / "pilot_day_summary.csv")
        summary = summary.loc[summary["date"] == date_text].iloc[0]
        require(len(dispatch) == T, "P4 row count")
        require(float(dispatch["balance_residual_kwh"].abs().max()) < NUMERIC_TOL, "P4 balance")
        require(float((dispatch["actual_x_kwh"] - dispatch["planned_q_kwh"]).max()) < NUMERIC_TOL, "P4 x<=q")
        require(float(dispatch["charge_kwh"].max()) <= POWER_LIMIT_KWH + NUMERIC_TOL, "P4 charge bound")
        require(float(dispatch["discharge_kwh"].max()) <= POWER_LIMIT_KWH + NUMERIC_TOL, "P4 discharge bound")
        require(float((dispatch["curtailment_kwh"] - dispatch["pv_kwh"]).max()) < NUMERIC_TOL, "P4 curtailment")
        require(float(dispatch["soc_kwh"].min()) >= E_MIN_KWH - NUMERIC_TOL, "P4 SOC min")
        require(float(dispatch["soc_kwh"].max()) <= E_MAX_KWH + NUMERIC_TOL, "P4 SOC max")
        require(
            float((dispatch["charge_kwh"] * dispatch["discharge_kwh"]).max())
            <= SIMULTANEOUS_CD_TOL,
            "P4 simultaneous c/d",
        )
        planned_cost = float(data.price @ dispatch["planned_q_kwh"].to_numpy())
        emergency_cost = float(
            EMERGENCY_PRICE_MULTIPLIER
            * data.price
            @ dispatch["emergency_kwh"].to_numpy()
        )
        require(abs(planned_cost - summary["planned_cost_yuan"]) < 1e-6, "P4 q cost")
        require(abs(emergency_cost - summary["emergency_cost_yuan"]) < 1e-6, "P4 e cost")
        require(
            planned_q_hash(dispatch["planned_q_kwh"].to_numpy())
            == summary["planned_q_sha256"],
            "P4 locked q hash",
        )

    require(not (ROOT / "output" / "result2.xlsx").exists(), "result2.xlsx forbidden")
    print("Q2 pilot independent validation: PASS")


if __name__ == "__main__":
    main()

