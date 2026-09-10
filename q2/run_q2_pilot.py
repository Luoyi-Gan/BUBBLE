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
    run_perfect_information,
    run_posterior_mpc,
    select_dynamic_k,
    write_k_audit,
    write_pilot_figures,
    write_validation_report,
)
from q2.scenarios import write_scenarios_csv  # noqa: E402


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

    choices = []
    scenario_rows = []
    for date_text in PILOT_DATES:
        i = int(data.dates.get_loc(pd.Timestamp(date_text)))
        choice = select_dynamic_k(data, archive, day_start_soc, i)
        choices.append(choice)
        scenario_rows.extend(choice.rows)
        write_scenarios_csv(
            OUTPUT_DIR / f"scenarios_{date_text}.csv", data, choice.scenarios
        )
        print(f"P3 {date_text}: selected K={choice.selected_k}")
    pd.DataFrame(scenario_rows).to_csv(OUTPUT_DIR / "scenario_selection.csv", index=False)
    write_k_audit(OUTPUT_DIR / "k_selection_validation.md", choices, data)

    summaries = []
    for choice in choices:
        date_text = data.dates[choice.target_index].strftime("%Y-%m-%d")
        summary = run_posterior_mpc(
            data,
            archive,
            choice,
            float(day_start_soc[choice.target_index]),
            OUTPUT_DIR / f"q2_pilot_dispatch_{date_text}.csv",
        )
        summaries.append(summary)
        print(f"P4 {date_text}: pass={summary['pass']}")
    pd.DataFrame(summaries).to_csv(OUTPUT_DIR / "pilot_day_summary.csv", index=False)
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

