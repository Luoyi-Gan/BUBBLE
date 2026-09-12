"""Sequential Q4-2 / Q4-3 campaigns with streamed daily outputs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import E_INITIAL_KWH
from q3.config import PILOT_DATES
from q4.bundle import Q4Bundle
from q4.config import (
    FIXED_SCENARIO_K,
    OUTPUT_DIR,
    PAM_SEED,
    Q4_2_DISPATCH_DIR,
    Q4_3_DISPATCH_DIR,
    RISK_CALIBRATION_DAYS,
    RISK_WARMUP_DAYS,
)
from q4.q4_2 import alpha_for_day, run_q4_2_day, select_risk_alpha
from q4.q4_3 import run_q4_3_day


def _append_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists() or path.stat().st_size == 0
    frame.to_csv(path, mode="a", header=header, index=False)


def last_index_for_dates(bundle: Q4Bundle, dates: tuple[str, ...]) -> int:
    return max(bundle.date_index(date) for date in dates)


def run_q4_2_campaign(
    bundle: Q4Bundle,
    end_index: int,
    detail_dates: tuple[str, ...] = PILOT_DATES,
    out_dir: Path = OUTPUT_DIR,
) -> dict:
    Q4_2_DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    daily_path = out_dir / "q4_2_warmup_daily.csv"
    ahead_path = out_dir / "q4_2_day_ahead_audit.csv"
    scen_path = out_dir / "q4_2_scenario_audit.csv"
    ledger_path = out_dir / "q4_2_cost_ledger.csv"
    for path in (daily_path, ahead_path, scen_path, ledger_path):
        if path.exists():
            path.unlink()
    soc = E_INITIAL_KWH
    start_soc = np.full(bundle.n_days(), np.nan)
    calibrated: dict[int, float | None] = {}
    alpha_rows: list[dict] = []
    detail = {}
    for i in range(end_index + 1):
        start_soc[i] = soc
        cal = (i // RISK_CALIBRATION_DAYS) * RISK_CALIBRATION_DAYS
        if i >= RISK_WARMUP_DAYS and cal not in calibrated and i == cal:
            alpha, records = select_risk_alpha(bundle, start_soc, i, FIXED_SCENARIO_K)
            calibrated[cal] = alpha
            for row in records:
                alpha_rows.append({"calibration_date": bundle.prices.dates[i].strftime("%Y-%m-%d"), **row})
            print(f"Q4-2 calibrated alpha={alpha} at {bundle.prices.dates[i].strftime('%Y-%m-%d')}", flush=True)
        elif i < RISK_WARMUP_DAYS:
            calibrated.setdefault(cal, None)
        alpha = alpha_for_day(i, calibrated)
        date = bundle.prices.dates[i].strftime("%Y-%m-%d")
        write_path = Q4_2_DISPATCH_DIR / f"dispatch_{date}.csv" if date in detail_dates else None
        result = run_q4_2_day(bundle, i, soc, alpha, write_dispatch=write_path)
        soc = float(result.summary["soc_end_kwh"])
        _append_csv(daily_path, pd.DataFrame([result.summary]))
        _append_csv(ahead_path, pd.DataFrame([result.day_ahead_audit]))
        if result.scenario_rows:
            _append_csv(scen_path, pd.DataFrame(result.scenario_rows))
        if date in detail_dates:
            nrm = result.dispatch["actual_price"] * result.dispatch["q_or_g0_kwh"]
            emg = 5.0 * result.dispatch["actual_price"] * result.dispatch["emergency_kwh"]
            _append_csv(
                ledger_path,
                pd.DataFrame(
                    {
                        "date": result.dispatch["date"],
                        "period_index": result.dispatch["period_index"],
                        "normal_cost_yuan": nrm,
                        "adjustment_cost_yuan": 0.0,
                        "emergency_cost_yuan": emg,
                        "total_cost_yuan": nrm + emg,
                    }
                ),
            )
            detail[date] = result
        print(
            f"Q4-2 [{i+1}/{end_index+1}] {date} cost={result.summary['total_cost_yuan']:.2f} "
            f"soc={soc:.2f} K={result.summary['k_effective']} alpha={alpha}",
            flush=True,
        )
        del result
    if alpha_rows:
        pd.DataFrame(alpha_rows).to_csv(out_dir / "q4_2_alpha_selection.csv", index=False)
    return {"detail": detail, "end_soc": soc, "calibrated_alpha": calibrated}


def run_q4_3_campaign(
    bundle: Q4Bundle,
    end_index: int,
    detail_dates: tuple[str, ...] = PILOT_DATES,
    out_dir: Path = OUTPUT_DIR,
) -> dict:
    Q4_3_DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    daily_path = out_dir / "q4_3_warmup_daily.csv"
    update_path = out_dir / "q4_3_update_log.csv"
    ledger_path = out_dir / "q4_3_cost_ledger.csv"
    for path in (daily_path, update_path, ledger_path):
        if path.exists():
            path.unlink()
    soc = E_INITIAL_KWH
    cache: dict = {}
    detail = {}
    for i in range(end_index + 1):
        date = bundle.prices.dates[i].strftime("%Y-%m-%d")
        result = run_q4_3_day(bundle, i, soc, value_cut_cache=cache)
        soc = float(result.summary["soc_end_kwh"])
        _append_csv(daily_path, pd.DataFrame([result.summary]))
        _append_csv(update_path, result.update_log)
        if date in detail_dates:
            result.dispatch.to_csv(Q4_3_DISPATCH_DIR / f"dispatch_{date}.csv", index=False)
            pd.DataFrame(
                {
                    "date": date,
                    "period_index": np.arange(len(result.g0)),
                    "g0_kwh": result.g0,
                    "g_final_kwh": result.g_final,
                }
            ).to_csv(out_dir / f"q4_3_commitment_versions_{date}.csv", index=False)
            ledger = result.dispatch[
                ["date", "period_index", "normal_cost_yuan", "adjustment_cost_yuan", "emergency_cost_yuan"]
            ].copy()
            ledger["total_cost_yuan"] = (
                ledger["normal_cost_yuan"]
                + ledger["adjustment_cost_yuan"]
                + ledger["emergency_cost_yuan"]
            )
            _append_csv(ledger_path, ledger)
            detail[date] = result
        print(
            f"Q4-3 [{i+1}/{end_index+1}] {date} cost={result.summary['total_cost_yuan']:.2f} "
            f"soc={soc:.2f} adj={result.summary['adjustment_count']}",
            flush=True,
        )
        del result
    return {"detail": detail, "end_soc": soc, "pam_seed": PAM_SEED}


def load_q42_detail_from_disk(
    out_dir: Path = OUTPUT_DIR,
    detail_dates: tuple[str, ...] = PILOT_DATES,
) -> dict:
    """Rebuild the in-memory Q4-2 pilot detail from streamed CSVs."""
    from q4.q4_2 import Q42DayResult

    daily = pd.read_csv(out_dir / "q4_2_warmup_daily.csv")
    detail = {}
    for date in detail_dates:
        path = Q4_2_DISPATCH_DIR / f"dispatch_{date}.csv"
        dispatch = pd.read_csv(path)
        row = daily.loc[daily["date"] == date].iloc[0].to_dict()
        alpha = row.get("risk_alpha")
        if alpha is None or (isinstance(alpha, float) and not np.isfinite(alpha)):
            row["risk_alpha"] = None
        detail[date] = Q42DayResult(
            date=date,
            day_index=int(row["day_index"]),
            q=dispatch["q_or_g0_kwh"].to_numpy(float),
            dispatch=dispatch,
            summary=row,
            day_ahead_audit={},
        )
    return {"detail": detail, "end_soc": float(daily["soc_end_kwh"].iloc[-1]), "from_disk": True}
