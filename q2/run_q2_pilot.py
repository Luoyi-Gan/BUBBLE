#!/usr/bin/env python3
"""Run Q2 P0-P4 pilot outputs; never creates result2.xlsx."""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import OUTPUT_DIR, PILOT_DATES  # noqa: E402
from q2.data import load_q2_data, write_input_audit  # noqa: E402
from q2.forecast import (  # noqa: E402
    assert_no_forecast_leakage,
    build_forecast_archive,
    write_forecast_archive,
)
from q2.pilot import (  # noqa: E402
    KChoice,
    build_k_freeze_calendar,
    build_next_day_value_cuts,
    run_linked_warmup,
    run_perfect_information,
    run_posterior_mpc,
    write_k_freeze_calendar,
    write_k_audit,
    write_pilot_figures,
    write_validation_report,
)
from q2.scenarios import build_scenarios, write_scenarios_csv  # noqa: E402


def main() -> None:
    started = perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    forbidden = ROOT / "output" / "result2.xlsx"
    forbidden_before = forbidden.stat().st_mtime_ns if forbidden.exists() else None

    data = load_q2_data()
    write_input_audit(data, OUTPUT_DIR / "input_audit.json")
    print("P0 complete: input audit")

    perfect_path = OUTPUT_DIR / "perfect_information_daily.csv"
    day_start_soc = run_perfect_information(data, perfect_path)
    print("P1 complete: 365-day sequential perfect-information comparator")

    archive = build_forecast_archive(data)
    assert_no_forecast_leakage(archive)
    write_forecast_archive(
        data,
        archive,
        OUTPUT_DIR / "forecast_archive.csv",
        OUTPUT_DIR / "forecast_audit.md",
    )
    print("P2 complete: causal forecast archive")

    calendar = build_k_freeze_calendar(data, archive, day_start_soc)
    write_k_freeze_calendar(OUTPUT_DIR / "k_freeze_calendar.csv", calendar)
    print("R4 complete: 14-day K freeze calendar")

    warmup, warmup_value_audit = run_linked_warmup(
        data, archive, calendar, OUTPUT_DIR / "linked_warmup_daily.csv"
    )
    print("R2 complete: January linked-policy warmup")

    choices = []
    scenario_rows = []
    for date_text in PILOT_DATES:
        i = int(data.dates.get_loc(pd.Timestamp(date_text)))
        k = int(calendar.daily_k[i])
        choice = KChoice(i, k, build_scenarios(i, data, archive, k), ())
        choices.append(choice)
        calibration_index = (i // 14) * 14
        scenario_rows.extend(
            row
            for row in calendar.rows
            if row["calibration_date"]
            == data.dates[calibration_index].strftime("%Y-%m-%d")
        )
        write_scenarios_csv(
            OUTPUT_DIR / f"scenarios_{date_text}.csv", data, choice.scenarios
        )
        print(f"P3 {date_text}: selected K={choice.selected_k}")
    pd.DataFrame(scenario_rows).to_csv(OUTPUT_DIR / "scenario_selection.csv", index=False)
    write_k_audit(OUTPUT_DIR / "k_selection_validation.md", choices, data)

    summaries = []
    value_comparisons = []
    all_value_audits = list(warmup_value_audit)
    for choice in choices:
        date_text = data.dates[choice.target_index].strftime("%Y-%m-%d")
        if date_text == "2025-02-01":
            initial_soc = float(warmup["soc_end_kwh"].iloc[-1])
        else:
            initial_soc = float(day_start_soc[choice.target_index])
        cuts, cut_rows = build_next_day_value_cuts(
            data, archive, choice.target_index, choice.selected_k
        )
        all_value_audits.extend(
            {"decision_date": date_text, **row} for row in cut_rows
        )
        without_value = run_posterior_mpc(
            data,
            archive,
            choice,
            initial_soc,
            OUTPUT_DIR / f"q2_pilot_dispatch_{date_text}_no48h.csv",
            terminal_value_cuts=None,
            variant="without_48h_value",
        )
        summary = run_posterior_mpc(
            data,
            archive,
            choice,
            initial_soc,
            OUTPUT_DIR / f"q2_pilot_dispatch_{date_text}.csv",
            terminal_value_cuts=cuts,
            variant="with_48h_value",
        )
        summaries.append(summary)
        next_index = choice.target_index + 1
        next_k = int(calendar.daily_k[next_index])
        next_choice = KChoice(
            next_index,
            next_k,
            build_scenarios(next_index, data, archive, next_k),
            (),
        )
        next_cuts, next_cut_rows = build_next_day_value_cuts(
            data, archive, next_index, next_k
        )
        all_value_audits.extend(
            {
                "decision_date": data.dates[next_index].strftime("%Y-%m-%d"),
                **row,
            }
            for row in next_cut_rows
        )
        next_after_without = run_posterior_mpc(
            data,
            archive,
            next_choice,
            float(without_value["soc_end_kwh"]),
            path=None,
            terminal_value_cuts=next_cuts,
            variant="next_day_after_without_48h_today",
        )
        next_after_with = run_posterior_mpc(
            data,
            archive,
            next_choice,
            float(summary["soc_end_kwh"]),
            path=None,
            terminal_value_cuts=next_cuts,
            variant="next_day_after_with_48h_today",
        )
        value_comparisons.append(
            {
                "date": date_text,
                "initial_soc_kwh": initial_soc,
                "cost_without_48h_yuan": without_value["total_cost_yuan"],
                "cost_with_48h_yuan": summary["total_cost_yuan"],
                "cost_difference_yuan": (
                    summary["total_cost_yuan"] - without_value["total_cost_yuan"]
                ),
                "emergency_without_48h_kwh": without_value["emergency_kwh"],
                "emergency_with_48h_kwh": summary["emergency_kwh"],
                "emergency_difference_kwh": (
                    summary["emergency_kwh"] - without_value["emergency_kwh"]
                ),
                "soc_end_without_48h_kwh": without_value["soc_end_kwh"],
                "soc_end_with_48h_kwh": summary["soc_end_kwh"],
                "soc_end_difference_kwh": (
                    summary["soc_end_kwh"] - without_value["soc_end_kwh"]
                ),
                "virtual_next_day_value_billed_today": False,
                "next_day_cost_after_without_48h_yuan": next_after_without[
                    "total_cost_yuan"
                ],
                "next_day_cost_after_with_48h_yuan": next_after_with[
                    "total_cost_yuan"
                ],
                "realized_two_day_cost_without_48h_today_yuan": (
                    without_value["total_cost_yuan"]
                    + next_after_without["total_cost_yuan"]
                ),
                "realized_two_day_cost_with_48h_today_yuan": (
                    summary["total_cost_yuan"] + next_after_with["total_cost_yuan"]
                ),
                "realized_two_day_cost_difference_yuan": (
                    summary["total_cost_yuan"]
                    + next_after_with["total_cost_yuan"]
                    - without_value["total_cost_yuan"]
                    - next_after_without["total_cost_yuan"]
                ),
                "next_day_plan_recomputed_and_billed_once": True,
            }
        )
        print(f"P4 {date_text}: pass={summary['pass']}")
    pd.DataFrame(summaries).to_csv(OUTPUT_DIR / "pilot_day_summary.csv", index=False)
    pd.DataFrame(value_comparisons).to_csv(
        OUTPUT_DIR / "next_day_value_comparison.csv", index=False
    )
    pd.DataFrame(all_value_audits).to_csv(
        OUTPUT_DIR / "next_day_value_audit.csv", index=False
    )
    write_pilot_figures(data, summaries)
    write_validation_report(
        OUTPUT_DIR / "validation.json",
        OUTPUT_DIR / "validation.md",
        perfect_path,
        summaries,
    )

    forbidden_after = forbidden.stat().st_mtime_ns if forbidden.exists() else None
    if forbidden_after != forbidden_before:
        raise RuntimeError("Forbidden output/result2.xlsx was created or modified")
    print(f"Q2 P0-P4 pilot complete in {perf_counter() - started:.2f} s")
    print(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

