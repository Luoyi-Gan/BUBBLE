#!/usr/bin/env python3
"""Rerun only A_q2_aligned + M1_M6, stream 10-minute trajectories, write result3.xlsx."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import (  # noqa: E402
    ANNUAL_OUTPUT_DIR,
    ATTACH1,
    ATTACH2,
    ATTACH3,
    E_INITIAL_KWH,
    LOAD_INFORMATION_MAIN,
    PV_MAPPING_LINEAR,
    RESULT3_ANNUAL_COST_YUAN,
    RESULT3_EXPORT_AUDIT,
    RESULT3_EXPORT_START,
    RESULT3_OFFICIAL_STRATEGY,
    RESULT3_TEMPLATE,
    RESULT3_XLSX,
    SETTLEMENT_MAIN,
    YEAR_END_BOUNDARY_A,
    YEAR_END_SOC_A_KWH,
)
from q3.data import load_q3_data  # noqa: E402
from q3.export_result3 import (  # noqa: E402
    compare_to_annual_summary,
    dispatch_path,
    enrich_dispatch,
    export_dates,
    git_hash,
    has_required_trajectory,
    inspect_result3_workbook,
    load_daily_trajectory,
    summarize_trajectory,
    write_daily_trajectory,
    write_export_audit,
    write_result3_xlsx,
)
from q3.full_annual import annual_dates  # noqa: E402
from q3.pilot import ValueCutCache, run_day  # noqa: E402

RERUN_DAILY_CSV = "result3_rerun_daily.csv"
PROGRESS_JSON = "result3_export_progress.json"


def _usable_existing(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        frame = pd.read_csv(path)
        return has_required_trajectory(frame) and "phi_yuan" in frame.columns
    except (OSError, ValueError):
        return False


def run_main_path(export_only: bool = False) -> dict:
    data = load_q3_data()
    dates = annual_dates(data)
    dispatch_dir = ANNUAL_OUTPUT_DIR / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    daily_path = ANNUAL_OUTPUT_DIR / RERUN_DAILY_CSV
    cache: ValueCutCache = {}
    started = perf_counter()
    soc = E_INITIAL_KWH
    n_solved = 0
    n_skipped = 0
    by_date: dict[str, pd.DataFrame] = {}

    for i, date in enumerate(dates, start=1):
        path = dispatch_path(date, dispatch_dir)
        if _usable_existing(path):
            frame = load_daily_trajectory(path)
            soc = float(frame["soc_end_kwh"].iloc[-1])
            by_date[date] = frame
            n_skipped += 1
            print(f"[{i}/{len(dates)}] skip {date} soc_end={soc:.4f}", flush=True)
            continue
        if export_only:
            raise FileNotFoundError(f"export-only missing trajectory {path}")
        day_index = data.date_index(date)
        run = run_day(
            data,
            day_index,
            RESULT3_OFFICIAL_STRATEGY,
            soc,
            with_terminal_value=True,
            load_information_case=LOAD_INFORMATION_MAIN,
            pv_mapping_mode=PV_MAPPING_LINEAR,
            settlement_mode=SETTLEMENT_MAIN,
            value_cut_cache=cache,
            year_end_soc_kwh=YEAR_END_SOC_A_KWH,
        )
        frame = enrich_dispatch(run)
        write_daily_trajectory(frame, path)
        soc = float(run.summary["soc_end_kwh"])
        by_date[date] = frame
        n_solved += 1
        print(
            f"[{i}/{len(dates)}] solved {run.run_id} "
            f"cost={run.summary['total_cost_yuan']:.2f} soc_end={soc:.4f}",
            flush=True,
        )
        del run

    rerun_daily = pd.DataFrame([summarize_trajectory(by_date[date]) for date in dates])
    rerun_daily.to_csv(daily_path, index=False)
    export_frames = {date: by_date[date] for date in export_dates()}
    xlsx_meta = write_result3_xlsx(export_frames, source_commit=git_hash())
    workbook = inspect_result3_workbook(RESULT3_XLSX)
    comparison = compare_to_annual_summary(
        rerun_daily, ANNUAL_OUTPUT_DIR / "q3_annual_daily_summary.csv"
    )
    jan_mask = pd.to_datetime(rerun_daily["date"]) < pd.Timestamp(RESULT3_EXPORT_START)
    jan_cost = float(rerun_daily.loc[jan_mask, "total_cost_yuan"].sum())
    annual_cost = float(rerun_daily["total_cost_yuan"].sum())
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "template": str(RESULT3_TEMPLATE),
        "result3_xlsx": str(RESULT3_XLSX),
        "dispatch_dir": str(dispatch_dir),
        "rerun_daily_csv": str(daily_path),
        "strategy": RESULT3_OFFICIAL_STRATEGY,
        "year_end_boundary": YEAR_END_BOUNDARY_A,
        "year_end_soc_kwh": YEAR_END_SOC_A_KWH,
        "load_information_case": LOAD_INFORMATION_MAIN,
        "pv_mapping_mode": PV_MAPPING_LINEAR,
        "settlement_mode": SETTLEMENT_MAIN,
        "jan01_soc_kwh": E_INITIAL_KWH,
        "n_calendar_days": len(dates),
        "n_export_days": len(export_dates()),
        "export_start": export_dates()[0],
        "export_end": export_dates()[-1],
        "n_periods": 144,
        "n_solved_days": n_solved,
        "n_skipped_existing_days": n_skipped,
        "elapsed_seconds": float(perf_counter() - started),
        "git_commit": git_hash(),
        "xlsx": xlsx_meta,
        "workbook_inspect": workbook,
        "annual_summary_comparison": comparison,
        "rerun_annual_cost_yuan": annual_cost,
        "rerun_january_cost_yuan": jan_cost,
        "rerun_export_window_cost_yuan": float(xlsx_meta["export_window_cost_yuan"]),
        "official_annual_cost_yuan": RESULT3_ANNUAL_COST_YUAN,
        "export_window_is_not_annual_total": True,
        "note": (
            "Only A_q2_aligned + M1_M6 was rerun. Trajectories are streamed 10-minute "
            "solver output, not reconstructed from q3_annual_daily_summary.csv. "
            "February–December workbook totals are not the 365-day official cost."
        ),
        "all_pass": bool(
            comparison.get("all_match", False)
            and workbook.get("n_anomalies", 1) == 0
            and abs(float(by_date[dates[-1]]["soc_end_kwh"].iloc[-1]) - YEAR_END_SOC_A_KWH)
            < 1e-3
        ),
    }
    write_export_audit(payload)
    (ANNUAL_OUTPUT_DIR / PROGRESS_JSON).write_text(
        json.dumps(
            {
                "last_date": dates[-1],
                "soc_end_kwh": float(by_date[dates[-1]]["soc_end_kwh"].iloc[-1]),
                "n_solved_days": n_solved,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Export official result3.xlsx from A+M1_M6")
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Do not solve; rebuild the workbook from already streamed trajectories.",
    )
    args = parser.parse_args()
    payload = run_main_path(export_only=args.export_only)
    print(
        json.dumps(
            {
                "elapsed_seconds": payload["elapsed_seconds"],
                "n_solved_days": payload["n_solved_days"],
                "n_skipped_existing_days": payload["n_skipped_existing_days"],
                "result3_xlsx": payload["result3_xlsx"],
                "export_window_cost_yuan": payload["rerun_export_window_cost_yuan"],
                "annual_cost_yuan": payload["rerun_annual_cost_yuan"],
                "all_pass": payload["all_pass"],
                "audit": str(RESULT3_EXPORT_AUDIT),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
