#!/usr/bin/env python3
"""Independent checks over C2-R1 / R2 / R3 / R4 policy-consistent artifacts."""

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
    CANDIDATE_RESULT2,
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    FIG_POLICY_CONSISTENT_DIR,
    FIG_Q2_FINAL_DIR,
    FIXED_SCENARIO_K,
    K_SENSITIVITY_CANDIDATES,
    NUMERIC_TOL,
    OFFICIAL_OUTPUT_START,
    PILOT_DATES,
    POLICY_CONSISTENT_OUTPUT_DIR,
    POWER_LIMIT_KWH,
    RESULT2_SIGNED_OFF_BACKUP,
    SIGNED_OFF_RESULT2,
    SIGNED_OFF_RESULT2_SHA256,
    SIMULTANEOUS_CD_TOL,
    T,
)
from q2.data import load_q2_data  # noqa: E402
from q2.export_result2 import (  # noqa: E402
    N_OUTPUT_DAYS,
    audit_candidate_result2,
    file_sha256,
)
from q2.pilot import planned_q_hash  # noqa: E402
from q2.policy_consistent import PERIOD_FEB_DEC_OUTPUT, PERIOD_JANUARY_WARMUP  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_no_forecast_leakage(forecast: pd.DataFrame) -> None:
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


def assert_dispatch_physics(path: Path, data, physical_row: pd.Series, date_text: str) -> None:
    i = int(data.dates.get_loc(pd.Timestamp(date_text)))
    frame = pd.read_csv(path)
    require(len(frame) == T, f"{date_text} dispatch length")
    q = frame["planned_q_kwh"].to_numpy()
    x = frame["actual_x_kwh"].to_numpy()
    require(planned_q_hash(q) == physical_row["planned_q_sha256"], "q hash")
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
    require(
        frame["discharge_kwh"].max() <= POWER_LIMIT_KWH + NUMERIC_TOL,
        f"{date_text} discharge limit",
    )
    require(np.allclose(frame["load_kwh"].to_numpy(), data.load[i], atol=1e-12), "dispatch load")


def validate_r1(output: Path, data, consistency: dict, report: dict) -> None:
    r1_forecast = output / "r1_forecast_policy_audit.csv"
    if r1_forecast.exists():
        forecast = pd.read_csv(r1_forecast)
        physical = pd.read_csv(output / "r1_physical_audit.csv")
        value_audit = pd.read_csv(output / "r1_next_day_value_audit.csv")
        dispatch_dir = output / "r1_dispatch_daily"
    else:
        forecast = pd.read_csv(output / "forecast_policy_audit.csv")
        physical = pd.read_csv(output / "physical_audit.csv")
        value_audit = pd.read_csv(output / "next_day_value_audit.csv")
        dispatch_dir = output / "dispatch_daily"
        require(consistency["annual_run"] is False, "R1 must not run the year")

    require(list(forecast["date"]) == list(PILOT_DATES), "R1 dates")
    require(report["status"] == "PASS", "validation status")
    if not r1_forecast.exists():
        require(report["candidate_result2_xlsx"] is False, "no candidate result2")
    require(consistency["validation_uses_full_day_actual_lp"] is False, "no full-day actual LP")
    require(consistency["k_used_for"] == ["risk_reserve_R", "intra_day_residual_weights"], "K uses")
    assert_no_forecast_leakage(forecast)
    require(physical["pass"].all(), "physical pass")
    require(not physical["used_full_day_actual_lp"].any(), "artifact used full-day LP")
    require(set(value_audit["decision_date"]) == set(PILOT_DATES), "value-cut decision dates")
    for row in value_audit.itertuples():
        decision = pd.Timestamp(row.decision_date)
        cutoff = pd.Timestamp(row.history_cutoff_date)
        target = pd.Timestamp(row.target_date)
        require(cutoff == decision - pd.Timedelta(days=1), f"cutoff is last history day for {row.decision_date}")
        require(cutoff < decision, f"cutoff precedes decision {row.decision_date}")
        require(target == decision + pd.Timedelta(days=1), f"target is next day for {row.decision_date}")
    for date_text in PILOT_DATES:
        physical_row = physical.loc[physical["date"] == date_text].iloc[0]
        assert_dispatch_physics(
            dispatch_dir / f"dispatch_{date_text}.csv",
            data,
            physical_row,
            date_text,
        )
    print("C2-R1 artifact validation passed")


def validate_r2(
    output: Path,
    data,
    diagnostics: pd.DataFrame,
    consistency: dict,
    report: dict,
) -> None:
    from q2.config import RISK_ALPHA_CANDIDATES
    from q2.policy_consistent import FORECAST_MODES

    calibration = pd.read_csv(output / "closed_loop_calibration.csv")
    deployed = pd.read_csv(output / "r2_deployed_daily.csv")
    n_candidates = len(FORECAST_MODES) * len(RISK_ALPHA_CANDIDATES)
    stage = consistency["stage"]
    require(n_candidates == 12, "12 (m, alpha) pairs")
    if stage in ("C2-R3", "C2-R4"):
        require(consistency["annual_run"] is True, "R3 annual run flag")
    elif stage == "C2-R2":
        require(consistency["annual_run"] is False, "R3 annual run not started")
    else:
        raise AssertionError(f"unexpected stage {stage}")
    require(consistency["calibration_closed_loop"] is True, "closed-loop calibration")
    require(consistency["mae_is_diagnostic_only"] is True, "MAE diagnostic flag")
    require(consistency["mae_used_for_selection"] is False, "MAE not used to select")
    require(consistency["validation_uses_full_day_actual_lp"] is False, "R2 no full-day LP")
    require(consistency["formal_execution_uses_full_day_actual_lp"] is False, "deploy no full-day LP")
    require(consistency["calibration_and_execution_exclude_future_actuals"] is True, "no future actuals")
    require(consistency["calibration_include_value_cuts"] is True, "calibration value cuts")
    require(consistency["deployment_include_value_cuts"] is True, "deployment value cuts")
    require(consistency["include_value_cuts"] is True, "include_value_cuts flag")
    require(consistency["include_value_cuts_consistent"] is True, "value-cut consistency")
    if stage != "C2-R4":
        require(report["candidate_result2_xlsx"] is False, "no candidate result2")
    require(diagnostics["selection_role"].eq("diagnostic_only").all(), "R2 MAE diagnostic")
    require(len(deployed) == len(data.dates), "deployed path covers the year for SOC")
    require(deployed["pass"].all(), "deployed physical pass")
    require(not deployed["used_full_day_actual_lp"].any(), "deployed used full-day LP")
    require(not deployed["future_actuals_in_optimizer"].any(), "deployed future actuals")
    require(deployed["include_value_cuts"].all(), "deployed value cuts")
    require(calibration["include_value_cuts"].all(), "calibration value cuts column")
    require(
        np.max(np.abs(deployed["soc_start_kwh"].to_numpy()[1:] - deployed["soc_end_kwh"].to_numpy()[:-1]))
        < NUMERIC_TOL,
        "deployed SOC continuity",
    )

    scored = calibration.loc[calibration["fallback_reason"].fillna("") == ""]
    require((scored.groupby("calibration_date").size() == n_candidates).all(), "12 candidates per scored block")
    require(
        calibration.loc[calibration["selected"].astype(bool)].groupby("calibration_date").size().eq(1).all(),
        "one selected pair per block",
    )
    require(not scored["used_full_day_actual_lp"].any(), "candidate used full-day LP")
    require(not scored["future_actuals_in_optimizer"].any(), "candidate future actuals")
    for _, block in scored.groupby("calibration_date"):
        best = block["mean_actual_cost_yuan"].min()
        selected_row = block.loc[block["selected"].astype(bool)].iloc[0]
        threshold = float(selected_row["one_se_threshold_yuan"])
        require(float(selected_row["mean_actual_cost_yuan"]) <= threshold + 1e-8, "selected within 1-SE")
        require(best <= float(selected_row["mean_actual_cost_yuan"]) + 1e-8, "best cost not worse than selected")
        require(
            pd.Timestamp(selected_row["history_cutoff_date"])
            == pd.Timestamp(selected_row["calibration_date"]) - pd.Timedelta(days=1),
            "calibration cutoff is last history day",
        )
        window_start = pd.Timestamp(selected_row["validation_start_date"])
        deployed_start = deployed.loc[deployed["date"] == window_start.strftime("%Y-%m-%d"), "soc_start_kwh"]
        require(len(deployed_start) == 1, "window start date in deployed path")
        require(
            abs(float(selected_row["window_start_soc_kwh"]) - float(deployed_start.iloc[0])) < 1e-6,
            "window SOC comes from deployed policy",
        )
    print("C2-R2 artifact validation passed")


def validate_r3(output: Path, data, consistency: dict, report: dict) -> None:
    daily = pd.read_csv(output / "q2_redesign_daily_summary.csv")
    january = pd.read_csv(output / "january_warmup_summary.csv")
    feb_dec = pd.read_csv(output / "feb_dec_daily_summary.csv")
    forecast = pd.read_csv(output / "forecast_policy_audit.csv")
    physical = pd.read_csv(output / "physical_audit.csv")
    value_audit = pd.read_csv(output / "next_day_value_audit.csv")
    k_table = pd.read_csv(output / "k_sensitivity.csv")
    soc_table = pd.read_csv(output / "feb_soc_sensitivity.csv")
    alt = pd.read_csv(output / "feb_soc_sensitivity_daily.csv")
    calendar = pd.read_csv(output / "frozen_policy_calendar.csv")

    require(consistency["stage"] in ("C2-R3", "C2-R4"), "R3/R4 stage")
    require(consistency["annual_run"] is True, "annual run")
    if consistency["stage"] == "C2-R3":
        require(report["candidate_result2_xlsx"] is False, "no candidate result2")
    require(consistency["main_path_initial_rule_unchanged"] is True, "initial rule frozen")
    require(consistency["calibration_include_value_cuts"] is True, "R3 calibration value cuts")
    require(consistency["deployment_include_value_cuts"] is True, "R3 deployment value cuts")
    require(consistency["annual_run_include_value_cuts"] is True, "R3 annual value cuts")
    require(consistency["include_value_cuts_consistent"] is True, "R3 value-cut consistency")
    require(daily["include_value_cuts"].all(), "annual daily value cuts")
    require(len(daily) == len(data.dates), "full-year daily summary")
    require(list(daily["date"]) == [stamp.strftime("%Y-%m-%d") for stamp in data.dates], "date order")
    require(abs(float(daily["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) < NUMERIC_TOL, "Jan 1 SOC 6000")
    require(len(january) == 31, "January warmup days")
    require(len(feb_dec) == 334, "Feb-Dec days")
    require((january["period"] == PERIOD_JANUARY_WARMUP).all(), "January period label")
    require((feb_dec["period"] == PERIOD_FEB_DEC_OUTPUT).all(), "Feb-Dec period label")
    require(january["date"].iloc[0] == "2025-01-01", "January start")
    require(january["date"].iloc[-1] == "2025-01-31", "January end")
    require(feb_dec["date"].iloc[0] == OFFICIAL_OUTPUT_START, "Feb-Dec start")
    require(feb_dec["date"].iloc[-1] == "2025-12-31", "Feb-Dec end")
    require(
        np.max(np.abs(daily["soc_start_kwh"].to_numpy()[1:] - daily["soc_end_kwh"].to_numpy()[:-1]))
        < NUMERIC_TOL,
        "main-path SOC continuity",
    )
    inherited = float(january["soc_end_kwh"].iloc[-1])
    require(abs(float(feb_dec["soc_start_kwh"].iloc[0]) - inherited) < NUMERIC_TOL, "Feb 1 inherits warmup")
    require(daily["pass"].all(), "annual physical pass")
    require(not daily["used_full_day_actual_lp"].any(), "annual full-day LP")
    require(not daily["future_actuals_in_optimizer"].any(), "annual future actuals")
    require(len(forecast) == len(data.dates), "annual forecast audit")
    assert_no_forecast_leakage(forecast)
    require(physical["pass"].all(), "physical audit pass")
    require((physical["period"] == daily["period"]).all(), "physical period labels")

    decisions = set(pd.to_datetime(value_audit["decision_date"]).dt.strftime("%Y-%m-%d"))
    require("2025-12-31" not in decisions, "no next-day cuts on Dec 31")
    require(len(decisions) == 364, "value cuts on 364 decision days")
    for row in value_audit.itertuples():
        decision = pd.Timestamp(row.decision_date)
        cutoff_raw = row.history_cutoff_date
        target = pd.Timestamp(row.target_date)
        if str(cutoff_raw) == "attachment1_fallback":
            require(decision == pd.Timestamp("2025-01-01"), "fallback cutoff only on Jan 1")
        else:
            require(
                pd.Timestamp(cutoff_raw) == decision - pd.Timedelta(days=1),
                f"cutoff is last history day for {row.decision_date}",
            )
        require(target == decision + pd.Timedelta(days=1), f"target is next day for {row.decision_date}")

    require(set(k_table["scenario_k"].astype(int)) == set(K_SENSITIVITY_CANDIDATES), "K=4,8,12")
    require((k_table["period"] == PERIOD_FEB_DEC_OUTPUT).all(), "K table is Feb-Dec")
    require(bool(k_table["calendar_frozen_from_r2"].all()), "K uses frozen calendar")
    k8 = k_table.loc[k_table["scenario_k"].astype(int) == FIXED_SCENARIO_K].iloc[0]
    require(abs(float(k8["total_cost_yuan"]) - float(feb_dec["total_cost_yuan"].sum())) < 1e-4, "K=8 matches main")

    require(len(soc_table) == 2, "two Feb SOC rows")
    inherited_row = soc_table.loc[soc_table["soc_source"] == "inherited_january_warmup"].iloc[0]
    boundary_row = soc_table.loc[soc_table["soc_source"] == "registered_boundary_E_INITIAL_6000"].iloc[0]
    require(abs(float(inherited_row["feb1_soc_start_kwh"]) - inherited) < NUMERIC_TOL, "inherited SOC table")
    require(abs(float(boundary_row["feb1_soc_start_kwh"]) - E_INITIAL_KWH) < NUMERIC_TOL, "boundary SOC table")
    require(bool(boundary_row["only_registered_boundary_changed"]), "boundary-only flag")
    require(list(alt["date"]) == list(feb_dec["date"]), "SOC sensitivity dates")
    require(list(alt["forecast_mode"]) == list(feb_dec["forecast_mode"]), "SOC sensitivity forecast mode")
    require(
        np.allclose(
            alt["risk_alpha"].to_numpy(dtype=float),
            feb_dec["risk_alpha"].to_numpy(dtype=float),
            equal_nan=True,
        ),
        "SOC sensitivity alpha",
    )
    require(abs(float(alt["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) < NUMERIC_TOL, "alt Feb 1 SOC")
    require(not np.isclose(float(alt["soc_start_kwh"].iloc[0]), inherited), "alt SOC differs from inherited")

    require(len(calendar) == len(data.dates), "frozen calendar coverage")
    require(calendar["forecast_mode"].isin(["m1", "m2", "m3"]).all(), "calendar modes")

    for date_text in ("2025-01-01", OFFICIAL_OUTPUT_START, "2025-06-21", "2025-12-31"):
        physical_row = physical.loc[physical["date"] == date_text].iloc[0]
        assert_dispatch_physics(
            output / "dispatch_daily" / f"dispatch_{date_text}.csv",
            data,
            physical_row,
            date_text,
        )

    for stem in (
        "fig_q2_pc_cost_comparison",
        "fig_q2_pc_emergency_curtailment",
        "fig_q2_pc_soc",
        "fig_q2_pc_cumulative_cost",
    ):
        require((FIG_POLICY_CONSISTENT_DIR / f"{stem}.pdf").exists(), f"missing {stem}.pdf")
        require((FIG_POLICY_CONSISTENT_DIR / f"{stem}.png").exists(), f"missing {stem}.png")
    print("C2-R3 artifact validation passed")


def validate_r4(output: Path, data, consistency: dict, report: dict) -> None:
    require(consistency["stage"] == "C2-R4", "R4 stage")
    require(report["stage"] == "C2-R4", "R4 report stage")
    require(report["status"] == "PASS", "R4 status")
    require(report["candidate_result2_xlsx"] is True, "candidate result2 flag")
    require(consistency["candidate_result2_xlsx"] is True, "audit candidate flag")
    require(consistency["k8_not_cost_optimal"] is True, "K=8 not cost-optimal")
    require(consistency["k8_paper_language"] == "预注册且对 K=4/12 稳定的简洁主方案", "K=8 paper language")
    require(consistency["old_full_path_role"] == "信息更强的近似对照", "old path role")
    require(CANDIDATE_RESULT2.exists(), "candidate workbook missing")
    require(CANDIDATE_RESULT2.resolve() != SIGNED_OFF_RESULT2.resolve(), "candidate overwrote signed-off file")
    require(CANDIDATE_RESULT2.parent.resolve() == output.resolve(), "candidate not in policy-consistent dir")
    require(file_sha256(SIGNED_OFF_RESULT2) == SIGNED_OFF_RESULT2_SHA256, "signed-off result2 hash")
    require(RESULT2_SIGNED_OFF_BACKUP.exists(), "signed-off backup missing")
    require(file_sha256(RESULT2_SIGNED_OFF_BACKUP) == SIGNED_OFF_RESULT2_SHA256, "backup hash")
    require(FIG_Q2_FINAL_DIR.resolve() != FIG_POLICY_CONSISTENT_DIR.resolve(), "figure dirs collapsed")

    january = pd.read_csv(output / "january_warmup_summary.csv")
    feb_dec = pd.read_csv(output / "feb_dec_daily_summary.csv")
    inherited = float(january["soc_end_kwh"].iloc[-1])
    audit = audit_candidate_result2(
        CANDIDATE_RESULT2,
        output / "dispatch_daily",
        feb_dec,
        data,
        inherited,
    )
    require(audit["summary"]["pass"] is True, "cell audit pass")
    require(audit["summary"]["n_days"] == N_OUTPUT_DAYS, "334 official days")
    require(audit["summary"]["n_periods"] == T, "144 periods")
    require(report["result2_cell_audit_pass"] is True, "report cell audit flag")
    require(
        abs(float(feb_dec["soc_start_kwh"].iloc[0]) - inherited) < NUMERIC_TOL,
        "R4 Feb 1 inherited SOC",
    )
    for stem in (
        "fig_q2_pc_closed_loop",
        "fig_q2_pc_representative_day",
        "fig_q2_pc_forecast_calendar",
        "fig_q2_pc_cost_comparison",
    ):
        require((FIG_POLICY_CONSISTENT_DIR / f"{stem}.pdf").exists(), f"missing {stem}.pdf")
        require((FIG_POLICY_CONSISTENT_DIR / f"{stem}.png").exists(), f"missing {stem}.png")
    print("C2-R4 artifact validation passed")


def main() -> None:
    output = POLICY_CONSISTENT_OUTPUT_DIR
    data = load_q2_data()
    diagnostics = pd.read_csv(output / "forecast_diagnostics.csv")
    consistency = json.loads((output / "policy_consistency_audit.json").read_text(encoding="utf-8"))
    report = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    require(diagnostics["selection_role"].eq("diagnostic_only").all(), "MAE must stay diagnostic")

    if (output / "r1_forecast_policy_audit.csv").exists() or list(
        pd.read_csv(output / "forecast_policy_audit.csv")["date"]
    ) == list(PILOT_DATES):
        validate_r1(output, data, consistency, report)
    if (output / "closed_loop_calibration.csv").exists():
        validate_r2(output, data, diagnostics, consistency, report)
    if consistency.get("stage") in ("C2-R3", "C2-R4") and (output / "q2_redesign_daily_summary.csv").exists():
        validate_r3(output, data, consistency, report)
    if consistency.get("stage") == "C2-R4":
        validate_r4(output, data, consistency, report)


if __name__ == "__main__":
    main()
