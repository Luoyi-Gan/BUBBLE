"""Physical, ledger, and information-set audits for Q4-2/Q4-3."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import E_MAX_KWH, E_MIN_KWH, NUMERIC_TOL, SIMULTANEOUS_CD_TOL, T
from q3.optimization import settlement_cost


def ledger_from_dispatch_q42(dispatch: pd.DataFrame) -> pd.DataFrame:
    out = dispatch.copy()
    out["normal_cost_yuan"] = out["actual_price"] * out["q_or_g0_kwh"]
    out["adjustment_cost_yuan"] = 0.0
    out["emergency_cost_yuan"] = 5.0 * out["actual_price"] * out["emergency_kwh"]
    out["total_cost_yuan"] = (
        out["normal_cost_yuan"] + out["adjustment_cost_yuan"] + out["emergency_cost_yuan"]
    )
    return out


def ledger_from_dispatch_q43(dispatch: pd.DataFrame) -> pd.DataFrame:
    phi = settlement_cost(
        dispatch["actual_price"].to_numpy(),
        dispatch["q_or_g0_kwh"].to_numpy(),
        dispatch["g_final_kwh"].to_numpy(),
    )
    out = dispatch.copy()
    out["normal_cost_yuan"] = dispatch["actual_price"] * dispatch["g_final_kwh"]
    out["adjustment_cost_yuan"] = phi - out["normal_cost_yuan"].to_numpy()
    out["emergency_cost_yuan"] = 5.0 * dispatch["actual_price"] * dispatch["emergency_kwh"]
    out["total_cost_yuan"] = (
        out["normal_cost_yuan"] + out["adjustment_cost_yuan"] + out["emergency_cost_yuan"]
    )
    return out


def physical_from_dispatch(dispatch: pd.DataFrame, q4_3: bool) -> dict:
    x = dispatch["x_kwh"].to_numpy()
    cap = dispatch["g_final_kwh"].to_numpy() if q4_3 else dispatch["q_or_g0_kwh"].to_numpy()
    cd = dispatch["charge_kwh"].to_numpy() * dispatch["discharge_kwh"].to_numpy()
    return {
        "n_periods": int(len(dispatch)),
        "max_balance_residual_kwh": float(dispatch["balance_residual_kwh"].abs().max()),
        "soc_min_kwh": float(dispatch["soc_end_kwh"].min()),
        "soc_max_kwh": float(dispatch["soc_end_kwh"].max()),
        "max_x_minus_cap_kwh": float(np.max(x - cap)),
        "max_simultaneous_cd_kwh2": float(np.max(cd)),
        "n_rows": int(len(dispatch)),
        "pass": bool(
            len(dispatch) == T
            and dispatch["balance_residual_kwh"].abs().max() < 1e-5
            and dispatch["soc_end_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL
            and dispatch["soc_end_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL
            and np.max(x - cap) < NUMERIC_TOL
            and np.max(cd) <= SIMULTANEOUS_CD_TOL
        ),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def q_unchanged_probe(result_q: np.ndarray, dispatch: pd.DataFrame) -> bool:
    return bool(np.allclose(result_q, dispatch["q_or_g0_kwh"].to_numpy(), atol=1e-9))


def prefix_lock_probe(update_log: pd.DataFrame) -> bool:
    if update_log.empty:
        return True
    return bool(update_log["prefix_lock_ok"].all())


def warmup_soc_continuity(daily: pd.DataFrame) -> dict:
    if daily.empty or len(daily) < 2:
        return {"n_days": int(len(daily)), "max_soc_gap_kwh": 0.0, "pass": True}
    end_vals = daily["soc_end_kwh"].to_numpy()[:-1]
    start_vals = daily["soc_start_kwh"].to_numpy()[1:]
    gap = float(np.max(np.abs(end_vals - start_vals)))
    return {"n_days": int(len(daily)), "max_soc_gap_kwh": gap, "pass": bool(gap < 1e-6)}
