"""Q4-3 off-main sensitivities: update-time adjustment fees and a price oracle.

Neither path replaces the official M1_M6 delivery-time scheme or result4-3.xlsx.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from q3.config import ADJUST_ABS_COEFF, PILOT_DATES
from q4.audit import ledger_from_dispatch_q43, write_json
from q4.config import (
    OUTPUT_DIR,
    Q4_3_DISPATCH_DIR,
    Q4_3_ORACLE_DAILY_CSV,
    Q4_3_ORACLE_DISPATCH_DIR,
    Q4_3_SENSITIVITY_SUMMARY_JSON,
    Q4_3_SETTLEMENT_SENSITIVITY_CSV,
    Q4_3_SETTLEMENT_SENSITIVITY_JSON,
)

UPDATE_CLOCKS = ("06:00", "12:00", "18:00")


def clock_price_map(frame: pd.DataFrame) -> dict[str, float]:
    labels = frame["time_label"].astype(str)
    out: dict[str, float] = {}
    for clock in UPDATE_CLOCKS:
        hit = frame.loc[labels == clock]
        if not hit.empty:
            out[clock] = float(hit["actual_price"].iloc[0])
    return out


def adjustment_at_update_clock(frame: pd.DataFrame) -> pd.DataFrame:
    """Rebook 0.5 |gF-g0| at the last update clock price; keep p_t gF and 5 p_t e."""
    work = frame.copy()
    g0 = work["q_or_g0_kwh"].to_numpy(float)
    gf = work["g_final_kwh"].to_numpy(float)
    p = work["actual_price"].to_numpy(float)
    last = work["last_update_time"].astype(str).to_numpy()
    clocks = clock_price_map(work)
    p_tau = np.array(
        [clocks[t] if t in clocks else float(p[i]) for i, t in enumerate(last)],
        dtype=float,
    )
    delta = np.abs(gf - g0)
    adj_delivery = ADJUST_ABS_COEFF * p * delta
    adj_update = ADJUST_ABS_COEFF * p_tau * delta
    emergency = 5.0 * p * work["emergency_kwh"].to_numpy(float)
    normal = p * gf
    work["adjustment_delivery_yuan"] = adj_delivery
    work["adjustment_update_clock_yuan"] = adj_update
    work["update_clock_price"] = p_tau
    work["normal_cost_yuan"] = normal
    work["emergency_cost_yuan"] = emergency
    work["total_delivery_yuan"] = normal + adj_delivery + emergency
    work["total_update_clock_yuan"] = normal + adj_update + emergency
    return work


def summarize_settlement_day(frame: pd.DataFrame) -> dict:
    billed = ledger_from_dispatch_q43(frame)
    alt = adjustment_at_update_clock(frame)
    delivery_adj = float(alt["adjustment_delivery_yuan"].sum())
    ledger_adj = float(billed["adjustment_cost_yuan"].sum())
    return {
        "date": str(frame["date"].iloc[0]),
        "n_adjusted_periods": int(np.sum(np.abs(
            frame["g_final_kwh"].to_numpy(float) - frame["q_or_g0_kwh"].to_numpy(float)
        ) > 1e-9)),
        "normal_cost_yuan": float(alt["normal_cost_yuan"].sum()),
        "emergency_cost_yuan": float(alt["emergency_cost_yuan"].sum()),
        "adjustment_delivery_yuan": delivery_adj,
        "adjustment_update_clock_yuan": float(alt["adjustment_update_clock_yuan"].sum()),
        "total_delivery_yuan": float(alt["total_delivery_yuan"].sum()),
        "total_update_clock_yuan": float(alt["total_update_clock_yuan"].sum()),
        "adjustment_gap_yuan": float(alt["adjustment_update_clock_yuan"].sum() - delivery_adj),
        "ledger_matches_delivery": bool(abs(delivery_adj - ledger_adj) < 1e-6),
    }


def run_settlement_sensitivity(dispatch_dir: Path = Q4_3_DISPATCH_DIR) -> dict:
    paths = sorted(dispatch_dir.glob("dispatch_*.csv"))
    if not paths:
        raise FileNotFoundError(f"no Q4-3 dispatch files in {dispatch_dir}")
    rows = [summarize_settlement_day(pd.read_csv(path)) for path in paths]
    daily = pd.DataFrame(rows)
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date").reset_index(drop=True)
    export = daily.loc[daily["date"] >= pd.Timestamp("2025-02-01")]
    summary = {
        "policy": "official_q4_3_dispatch_rebooked_only",
        "changes_main_scheme": False,
        "n_days": int(len(daily)),
        "n_export_days": int(len(export)),
        "annual_delivery_yuan": float(daily["total_delivery_yuan"].sum()),
        "annual_update_clock_yuan": float(daily["total_update_clock_yuan"].sum()),
        "annual_adjustment_delivery_yuan": float(daily["adjustment_delivery_yuan"].sum()),
        "annual_adjustment_update_clock_yuan": float(daily["adjustment_update_clock_yuan"].sum()),
        "annual_adjustment_gap_yuan": float(daily["adjustment_gap_yuan"].sum()),
        "export_delivery_yuan": float(export["total_delivery_yuan"].sum()),
        "export_update_clock_yuan": float(export["total_update_clock_yuan"].sum()),
        "all_ledger_match": bool(daily["ledger_matches_delivery"].all()),
        "note": (
            "Main phi uses delivery-time p_t. The sensitivity keeps the same "
            "(g0, gF, e) and charges 0.5 |gF-g0| at the last update clock price "
            "p_{d,tau} (06:00/12:00/18:00 period ending at that clock)."
        ),
    }
    out = daily.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    Q4_3_SETTLEMENT_SENSITIVITY_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(Q4_3_SETTLEMENT_SENSITIVITY_CSV, index=False)
    write_json(Q4_3_SETTLEMENT_SENSITIVITY_JSON, summary)
    return {"daily": out, "summary": summary}


def write_sensitivity_summary(settlement: dict, oracle_daily: pd.DataFrame | None) -> dict:
    main = pd.read_csv(OUTPUT_DIR / "q4_3_warmup_daily.csv")
    q42 = pd.read_csv(OUTPUT_DIR / "q4_2_warmup_daily.csv")
    main["date"] = pd.to_datetime(main["date"])
    q42["date"] = pd.to_datetime(q42["date"])
    payload = {
        "main_scheme": "Q4-3 M1_M6 causal prices, delivery-time phi+5pe",
        "changes_main_scheme": False,
        "q4_3_main": {
            "annual_yuan": float(main["total_cost_yuan"].sum()),
            "export_yuan": float(main.loc[main["date"] >= "2025-02-01", "total_cost_yuan"].sum()),
            "end_soc_kwh": float(main["soc_end_kwh"].iloc[-1]),
        },
        "q4_2_main": {
            "annual_yuan": float(q42["total_cost_yuan"].sum()),
            "export_yuan": float(q42.loc[q42["date"] >= "2025-02-01", "total_cost_yuan"].sum()),
        },
        "settlement_update_clock": settlement["summary"],
        "pilot_dates": list(PILOT_DATES),
    }
    if oracle_daily is not None and not oracle_daily.empty:
        oracle_daily = oracle_daily.copy()
        oracle_daily["date"] = pd.to_datetime(oracle_daily["date"])
        payload["price_oracle"] = {
            "annual_yuan": float(oracle_daily["total_cost_yuan"].sum()),
            "export_yuan": float(
                oracle_daily.loc[oracle_daily["date"] >= "2025-02-01", "total_cost_yuan"].sum()
            ),
            "end_soc_kwh": float(oracle_daily["soc_end_kwh"].iloc[-1]),
            "gap_vs_main_annual_yuan": float(
                oracle_daily["total_cost_yuan"].sum() - main["total_cost_yuan"].sum()
            ),
            "note": (
                "Offline reference only: midnight and remaining-horizon prices are "
                "today's actual path. Next-day value cuts stay causal. Not executable."
            ),
        }
        for date in PILOT_DATES:
            main_hit = main.loc[main["date"] == date]
            ora_hit = oracle_daily.loc[oracle_daily["date"] == date]
            if not main_hit.empty and not ora_hit.empty:
                payload.setdefault("two_day", {})[date] = {
                    "main_yuan": float(main_hit.iloc[0]["total_cost_yuan"]),
                    "oracle_yuan": float(ora_hit.iloc[0]["total_cost_yuan"]),
                }
    write_json(Q4_3_SENSITIVITY_SUMMARY_JSON, payload)
    return payload
