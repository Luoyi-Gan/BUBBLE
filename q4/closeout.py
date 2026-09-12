"""Reporting-only Q4 closeout: tails, fair windows, physical year scan, residual correlation.

Does not change decisions, workbooks, or official dispatch archives.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import E_MAX_KWH, E_MIN_KWH, NUMERIC_TOL, POWER_LIMIT_KWH, SIMULTANEOUS_CD_TOL, T
from q3.config import HOUR_TO_FIRST_MUTABLE, RESULT3_OFFICIAL_STRATEGY, YEAR_END_BOUNDARY_A
from q4.audit import (
    ledger_from_dispatch_q42,
    ledger_from_dispatch_q43,
    physical_from_dispatch,
    warmup_soc_continuity,
)
from q4.config import (
    EXPECTED_Q2_K8_EXPORT_YUAN,
    EXPECTED_Q3_ANNUAL_YUAN,
    EXPECTED_Q4_2_ALPHA070_END,
    EXPECTED_Q4_2_ALPHA070_START,
    EXPECTED_Q4_2_ANNUAL_YUAN,
    EXPECTED_Q4_2_EXPORT_YUAN,
    EXPECTED_Q4_3_ANNUAL_YUAN,
    EXPECTED_Q4_3_EXPORT_YUAN,
    EXPORT_END,
    EXPORT_N_DAYS,
    EXPORT_START,
    LOAD_INFORMATION_CASE,
    Q2_K8_DAILY_CSV,
    Q3_ANNUAL_DAILY_CSV,
    Q4_2_ALPHA_SELECTION_CSV,
    Q4_2_DAILY_CSV,
    Q4_2_DISPATCH_DIR,
    Q4_2_SCENARIO_AUDIT_CSV,
    Q4_3_DAILY_CSV,
    Q4_3_DISPATCH_DIR,
    YEAR_N_DAYS,
)

ALLOWED_Q43_UPDATE_CLOCKS = ("00:00", "06:00", "12:00", "18:00")
PRICE_NOTE = (
    "公平对比窗口为 2025-02-01 至 2025-12-31（334 日），设备、SOC 规则与负荷/光伏主案例相同；"
    "Q2/Q3 使用附件1 分时电价，Q4 使用附件4 变动电价。对比解释为同一套储能在不同价格信息下的运行结果，"
    "不是同一电价序列下的会计差额。"
)


def output_interval(
    frame: pd.DataFrame,
    start: str = EXPORT_START,
    end: str = EXPORT_END,
    n_days: int = EXPORT_N_DAYS,
) -> pd.DataFrame:
    if "date" not in frame.columns:
        raise AssertionError("daily frame lacks date column")
    dates = pd.to_datetime(frame["date"])
    selected = frame.loc[dates.between(pd.Timestamp(start), pd.Timestamp(end))].copy()
    selected = selected.sort_values("date").reset_index(drop=True)
    if len(selected) != n_days:
        raise AssertionError(f"Expected {n_days} output days, got {len(selected)}")
    return selected


def empirical_var(values: np.ndarray, alpha: float) -> float:
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values must be non-empty")
    return float(np.quantile(arr, alpha, method="linear"))


def empirical_cvar(values: np.ndarray, alpha: float) -> float:
    """Mean of the worst ceil((1-alpha)*n) observations (higher cost is worse)."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    arr = np.sort(np.asarray(values, dtype=float))
    if arr.size == 0:
        raise ValueError("values must be non-empty")
    k = max(1, int(np.ceil((1.0 - alpha) * arr.size)))
    return float(arr[-k:].mean())


def tail_bundle(values: np.ndarray, prefix: str = "") -> dict:
    arr = np.asarray(values, dtype=float)
    key = f"{prefix}_" if prefix else ""
    return {
        f"{key}n_days": int(arr.size),
        f"{key}mean_yuan": float(arr.mean()),
        f"{key}max_yuan": float(arr.max()),
        f"{key}p90_yuan": empirical_var(arr, 0.90),
        f"{key}p95_yuan": empirical_var(arr, 0.95),
        f"{key}cvar_0_90_yuan": empirical_cvar(arr, 0.90),
        f"{key}cvar_n_tail_0_90": int(max(1, int(np.ceil(0.10 * arr.size)))),
    }


def _require_close(actual: float, expected: float, label: str, atol: float = 0.01) -> None:
    if abs(actual - expected) >= atol:
        raise AssertionError(f"{label} mismatch: {actual:.6f} vs signed-off {expected:.2f}")


def load_q4_2_daily() -> pd.DataFrame:
    return pd.read_csv(Q4_2_DAILY_CSV)


def load_q4_3_daily() -> pd.DataFrame:
    return pd.read_csv(Q4_3_DAILY_CSV)


def load_q2_k8_daily() -> pd.DataFrame:
    return pd.read_csv(Q2_K8_DAILY_CSV)


def load_q3_official_daily() -> pd.DataFrame:
    raw = pd.read_csv(Q3_ANNUAL_DAILY_CSV)
    selected = raw.loc[
        (raw["strategy"] == RESULT3_OFFICIAL_STRATEGY)
        & (raw["year_end_boundary"] == YEAR_END_BOUNDARY_A)
        & (raw["load_information_case"] == LOAD_INFORMATION_CASE)
    ].copy()
    selected = selected.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if len(selected) != YEAR_N_DAYS:
        raise AssertionError(f"Q3 official daily expected {YEAR_N_DAYS} days, got {len(selected)}")
    annual = float(selected["total_cost_yuan"].sum())
    _require_close(annual, EXPECTED_Q3_ANNUAL_YUAN, "Q3 official annual")
    return selected


def cost_components(frame: pd.DataFrame, scheme: str) -> dict:
    if scheme == "q4_2":
        normal = float(frame["normal_cost_yuan"].sum())
        adjustment = float(frame["adjustment_cost_yuan"].sum()) if "adjustment_cost_yuan" in frame else 0.0
        emergency = float(frame["emergency_cost_yuan"].sum())
        total = float(frame["total_cost_yuan"].sum())
        planned_kwh = float(frame["planned_q_kwh"].sum()) if "planned_q_kwh" in frame else float("nan")
    elif scheme == "q4_3":
        normal = float(frame["normal_cost_yuan"].sum())
        adjustment = float(frame["adjustment_cost_yuan"].sum())
        emergency = float(frame["emergency_cost_yuan"].sum())
        total = float(frame["total_cost_yuan"].sum())
        planned_kwh = float(frame["g0_kwh"].sum()) if "g0_kwh" in frame else float("nan")
    elif scheme == "q2":
        normal = float(frame["planned_cost_yuan"].sum())
        adjustment = 0.0
        emergency = float(frame["emergency_cost_yuan"].sum())
        total = float(frame["total_cost_yuan"].sum())
        planned_kwh = float("nan")
    elif scheme == "q3":
        normal = float(frame["settlement_cost_yuan"].sum())
        adjustment = 0.0
        emergency = float(frame["emergency_cost_yuan"].sum())
        total = float(frame["total_cost_yuan"].sum())
        planned_kwh = float("nan")
    else:
        raise ValueError(scheme)
    if abs(total - (normal + adjustment + emergency)) >= 0.05:
        raise AssertionError(f"{scheme} components do not sum to total")
    return {
        "scheme": scheme,
        "n_days": int(len(frame)),
        "normal_or_settlement_yuan": normal,
        "adjustment_yuan": adjustment,
        "emergency_cost_yuan": emergency,
        "total_cost_yuan": total,
        "emergency_kwh": float(frame["emergency_kwh"].sum()),
        "planned_kwh": planned_kwh,
        "max_day_cost_yuan": float(frame["total_cost_yuan"].max()),
        "max_day_cost_date": str(
            pd.Timestamp(frame.loc[frame["total_cost_yuan"].idxmax(), "date"]).date()
        ),
        "max_emergency_cost_yuan": float(frame["emergency_cost_yuan"].max()),
        "max_emergency_cost_date": str(
            pd.Timestamp(frame.loc[frame["emergency_cost_yuan"].idxmax(), "date"]).date()
        ),
        **tail_bundle(frame["total_cost_yuan"].to_numpy(float), prefix="daily_cost"),
    }


def price_error_stats(audit: pd.DataFrame, start: str, end: str) -> dict:
    dates = pd.to_datetime(audit["date"])
    window = audit.loc[dates.between(pd.Timestamp(start), pd.Timestamp(end))].copy()
    ahead = window.loc[np.isfinite(window["day_ahead_mae"].to_numpy(float))].copy()
    if ahead.empty:
        raise AssertionError("no finite day-ahead price errors in window")
    mae = float(ahead["day_ahead_mae"].mean())
    rmse = float(np.sqrt(np.mean(np.square(ahead["day_ahead_rmse"].to_numpy(float)))))
    return {
        "start": start,
        "end": end,
        "n_days": int(len(window)),
        "n_days_with_day_ahead": int(len(ahead)),
        "day_ahead_mae": mae,
        "day_ahead_rmse_pooled": rmse,
        "day_ahead_rmse_mean_daily": float(ahead["day_ahead_rmse"].mean()),
        "intraday_06_mae": float(ahead["intraday_06_mae"].mean()),
        "intraday_12_mae": float(ahead["intraday_12_mae"].mean()),
        "intraday_18_mae": float(ahead["intraday_18_mae"].mean()),
        "aggregation": (
            "MAE = mean of daily MAE; pooled RMSE = sqrt(mean of daily RMSE squared); "
            "equal slot count per day with a finite day-ahead forecast"
        ),
    }


def build_fair_comparison(
    q42: pd.DataFrame,
    q43: pd.DataFrame,
    q2: pd.DataFrame,
    q3: pd.DataFrame,
) -> dict:
    q42_year = cost_components(q42, "q4_2")
    q43_year = cost_components(q43, "q4_3")
    q42_export = cost_components(output_interval(q42), "q4_2")
    q43_export = cost_components(output_interval(q43), "q4_3")
    q2_export = cost_components(output_interval(q2), "q2")
    q3_export = cost_components(output_interval(q3), "q3")
    q3_year = cost_components(q3, "q3")
    _require_close(q42_year["total_cost_yuan"], EXPECTED_Q4_2_ANNUAL_YUAN, "Q4-2 annual")
    _require_close(q42_export["total_cost_yuan"], EXPECTED_Q4_2_EXPORT_YUAN, "Q4-2 2-12")
    _require_close(q43_year["total_cost_yuan"], EXPECTED_Q4_3_ANNUAL_YUAN, "Q4-3 annual")
    _require_close(q43_export["total_cost_yuan"], EXPECTED_Q4_3_EXPORT_YUAN, "Q4-3 2-12")
    _require_close(q2_export["total_cost_yuan"], EXPECTED_Q2_K8_EXPORT_YUAN, "Q2 K=8 2-12")
    _require_close(q3_year["total_cost_yuan"], EXPECTED_Q3_ANNUAL_YUAN, "Q3 official annual")
    return {
        "price_note": PRICE_NOTE,
        "export_window": {"start": EXPORT_START, "end": EXPORT_END, "n_days": EXPORT_N_DAYS},
        "annual_window": {"start": "2025-01-01", "end": "2025-12-31", "n_days": YEAR_N_DAYS},
        "q4_2_annual": q42_year,
        "q4_3_annual": q43_year,
        "q3_annual": q3_year,
        "export": {
            "q4_2": q42_export,
            "q4_3": q43_export,
            "q2_k8": q2_export,
            "q3_m1_m6": q3_export,
        },
        "pairs": {
            "q4_2_minus_q2_k8_export_yuan": q42_export["total_cost_yuan"] - q2_export["total_cost_yuan"],
            "q4_2_minus_q2_k8_emergency_kwh": q42_export["emergency_kwh"] - q2_export["emergency_kwh"],
            "q4_3_minus_q3_m1_m6_export_yuan": q43_export["total_cost_yuan"] - q3_export["total_cost_yuan"],
            "q4_3_minus_q3_m1_m6_emergency_kwh": q43_export["emergency_kwh"] - q3_export["emergency_kwh"],
        },
    }


def expected_q43_last_update(period_index: np.ndarray) -> np.ndarray:
    clocks = np.full(len(period_index), "00:00", dtype=object)
    clocks[period_index >= HOUR_TO_FIRST_MUTABLE[6]] = "06:00"
    clocks[period_index >= HOUR_TO_FIRST_MUTABLE[12]] = "12:00"
    clocks[period_index >= HOUR_TO_FIRST_MUTABLE[18]] = "18:00"
    return clocks


def _intra_day_soc_gap(dispatch: pd.DataFrame) -> float:
    if len(dispatch) < 2:
        return 0.0
    return float(
        np.max(
            np.abs(
                dispatch["soc_start_kwh"].to_numpy(float)[1:]
                - dispatch["soc_end_kwh"].to_numpy(float)[:-1]
            )
        )
    )


def _energy_balance_gap(dispatch: pd.DataFrame) -> float:
    x = dispatch["x_kwh"].to_numpy(float)
    e = dispatch["emergency_kwh"].to_numpy(float)
    pv = dispatch["actual_pv_kwh"].to_numpy(float)
    curt = dispatch["curtailment_kwh"].to_numpy(float)
    d = dispatch["discharge_kwh"].to_numpy(float)
    load = dispatch["actual_load_kwh"].to_numpy(float)
    c = dispatch["charge_kwh"].to_numpy(float)
    residual = x + e + pv - curt + d - load - c
    stored = dispatch["balance_residual_kwh"].to_numpy(float)
    return float(max(np.max(np.abs(residual)), np.max(np.abs(residual - stored))))


def scan_dispatch_year(
    dispatch_dir: Path,
    daily: pd.DataFrame,
    *,
    q4_3: bool,
) -> dict:
    paths = sorted(dispatch_dir.glob("dispatch_*.csv"))
    if len(paths) != YEAR_N_DAYS:
        raise AssertionError(f"Expected {YEAR_N_DAYS} dispatch files in {dispatch_dir}, got {len(paths)}")
    daily = daily.sort_values("date").reset_index(drop=True)
    if len(daily) != YEAR_N_DAYS:
        raise AssertionError(f"Expected {YEAR_N_DAYS} daily rows, got {len(daily)}")
    by_date = {str(row.date): row for row in daily.itertuples()}
    max_balance = 0.0
    max_x_minus_cap = 0.0
    max_cd = 0.0
    max_power = 0.0
    max_soc_chain = 0.0
    soc_min = float("inf")
    soc_max = float("-inf")
    max_ledger_gap = 0.0
    n_physical_pass = 0
    info_fail = 0
    prefix_fail = 0
    first_intraday = HOUR_TO_FIRST_MUTABLE[6]
    for path in paths:
        date = path.stem.replace("dispatch_", "")
        frame = pd.read_csv(path)
        if len(frame) != T:
            raise AssertionError(f"{path.name} has {len(frame)} rows")
        phys = physical_from_dispatch(frame, q4_3=q4_3)
        max_balance = max(max_balance, phys["max_balance_residual_kwh"], _energy_balance_gap(frame))
        max_x_minus_cap = max(max_x_minus_cap, phys["max_x_minus_cap_kwh"])
        max_cd = max(max_cd, phys["max_simultaneous_cd_kwh2"])
        max_power = max(
            max_power,
            float(frame["charge_kwh"].max()),
            float(frame["discharge_kwh"].max()),
        )
        max_soc_chain = max(max_soc_chain, _intra_day_soc_gap(frame))
        soc_min = min(soc_min, phys["soc_min_kwh"])
        soc_max = max(soc_max, phys["soc_max_kwh"])
        n_physical_pass += int(phys["pass"])
        row = by_date[date]
        if q4_3:
            ledger = ledger_from_dispatch_q43(frame)
            expected_clock = expected_q43_last_update(frame["period_index"].to_numpy(int))
            clocks = frame["last_update_time"].astype(str).to_numpy()
            if not np.array_equal(clocks, expected_clock):
                info_fail += 1
            if not set(clocks).issubset(ALLOWED_Q43_UPDATE_CLOCKS):
                info_fail += 1
            g0 = frame["q_or_g0_kwh"].to_numpy(float)
            gf = frame["g_final_kwh"].to_numpy(float)
            if np.max(np.abs(gf[:first_intraday] - g0[:first_intraday])) > NUMERIC_TOL:
                prefix_fail += 1
        else:
            ledger = ledger_from_dispatch_q42(frame)
            if not (frame["last_update_time"].astype(str) == "00:00").all():
                info_fail += 1
        ledger_total = float(ledger["total_cost_yuan"].sum())
        max_ledger_gap = max(max_ledger_gap, abs(ledger_total - float(row.total_cost_yuan)))
    soc = warmup_soc_continuity(daily)
    physical_pass = (
        n_physical_pass == YEAR_N_DAYS
        and max_balance < 1e-5
        and max_x_minus_cap < NUMERIC_TOL
        and max_cd <= SIMULTANEOUS_CD_TOL
        and max_power <= POWER_LIMIT_KWH + NUMERIC_TOL
        and max_soc_chain < 1e-6
        and soc_min >= E_MIN_KWH - NUMERIC_TOL
        and soc_max <= E_MAX_KWH + NUMERIC_TOL
        and info_fail == 0
        and prefix_fail == 0
        and max_ledger_gap < 0.01
        and soc["pass"]
    )
    return {
        "system": "q4_3" if q4_3 else "q4_2",
        "n_dispatch_files": len(paths),
        "n_days": int(len(daily)),
        "n_physical_pass": n_physical_pass,
        "soc_continuity": soc,
        "max_balance_residual_kwh": max_balance,
        "max_x_minus_cap_kwh": max_x_minus_cap,
        "max_simultaneous_cd_kwh2": max_cd,
        "max_charge_or_discharge_kwh": max_power,
        "power_limit_kwh": float(POWER_LIMIT_KWH),
        "max_intraday_soc_chain_gap_kwh": max_soc_chain,
        "soc_min_kwh": float(soc_min),
        "soc_max_kwh": float(soc_max),
        "max_ledger_vs_daily_gap_yuan": max_ledger_gap,
        "info_cutoff_failures": info_fail,
        "prefix_lock_failures": prefix_fail,
        "dec31_soc_kwh": float(daily.iloc[-1]["soc_end_kwh"]),
        "pass": bool(physical_pass),
    }


def q4_2_policy_windows(daily: pd.DataFrame) -> pd.DataFrame:
    """14-day calibration calendar, including the 28-day warmup with no alpha."""
    from q4.config import RISK_CALIBRATION_DAYS, RISK_WARMUP_DAYS
    from q4.q4_2 import q2_aligned_calibration_indices

    work = daily.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)
    if len(work) != YEAR_N_DAYS:
        raise AssertionError(f"Q4-2 daily expected {YEAR_N_DAYS} days, got {len(work)}")
    rows = [
        {
            "effective_start_date": work.loc[0, "date"],
            "effective_end_date": work.loc[RISK_WARMUP_DAYS - 1, "date"],
            "n_days": RISK_WARMUP_DAYS,
            "risk_alpha": None,
            "kind": "warmup",
        }
    ]
    for start in q2_aligned_calibration_indices(len(work)):
        end = min(start + RISK_CALIBRATION_DAYS - 1, len(work) - 1)
        chunk = work.iloc[start : end + 1]
        alphas = chunk["risk_alpha"]
        if alphas.isna().any() or alphas.nunique() != 1:
            raise AssertionError(
                f"alpha is not constant on {chunk.iloc[0]['date']}–{chunk.iloc[-1]['date']}"
            )
        rows.append(
            {
                "effective_start_date": chunk.iloc[0]["date"],
                "effective_end_date": chunk.iloc[-1]["date"],
                "n_days": int(len(chunk)),
                "risk_alpha": round(float(chunk.iloc[0]["risk_alpha"]), 2),
                "kind": "calibrated",
            }
        )
    frame = pd.DataFrame(rows)
    if len(frame) != 26:
        raise AssertionError(f"expected 1 warmup + 25 calibrated windows, got {len(frame)}")
    hot = frame.loc[frame["risk_alpha"] == 0.70]
    if len(hot) != 1:
        raise AssertionError("expected exactly one α=0.70 window")
    if hot.iloc[0]["effective_start_date"] != pd.Timestamp(EXPECTED_Q4_2_ALPHA070_START):
        raise AssertionError("α=0.70 start mismatch")
    if hot.iloc[0]["effective_end_date"] != pd.Timestamp(EXPECTED_Q4_2_ALPHA070_END):
        raise AssertionError("α=0.70 end mismatch")
    return frame


def selected_alpha_blocks(daily: pd.DataFrame, selection: pd.DataFrame) -> pd.DataFrame:
    work = daily.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)
    blocks = []
    start_idx = 0
    for i in range(1, len(work) + 1):
        same = False
        if i < len(work):
            prev = work.loc[start_idx, "risk_alpha"]
            cur = work.loc[i, "risk_alpha"]
            same = (pd.isna(prev) and pd.isna(cur)) or (
                pd.notna(prev) and pd.notna(cur) and abs(float(prev) - float(cur)) < 1e-12
            )
        if same:
            continue
        chunk = work.iloc[start_idx:i]
        alpha = chunk.iloc[0]["risk_alpha"]
        blocks.append(
            {
                "effective_start_date": chunk.iloc[0]["date"],
                "effective_end_date": chunk.iloc[-1]["date"],
                "n_days": int(len(chunk)),
                "risk_alpha": None if pd.isna(alpha) else round(float(alpha), 2),
            }
        )
        start_idx = i
    frame = pd.DataFrame(blocks)
    selected = selection.loc[selection["selected"].astype(str).str.lower().isin(("true", "1"))].copy()
    selected["calibration_date"] = pd.to_datetime(selected["calibration_date"])
    if int(selected["calibration_date"].nunique()) != 25:
        raise AssertionError(f"expected 25 Q4-2 calibration windows, got {selected['calibration_date'].nunique()}")
    return frame


def pearson_corrcoef(a: np.ndarray, b: np.ndarray) -> float:
    x = np.asarray(a, dtype=float).ravel()
    y = np.asarray(b, dtype=float).ravel()
    if x.size != y.size or x.size < 3:
        raise ValueError("correlation requires aligned arrays with length >= 3")
    if np.std(x) < 1e-18 or np.std(y) < 1e-18:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def residual_correlation_report(
    load_r: np.ndarray, pv_r: np.ndarray, price_r: np.ndarray, dates: list[str]
) -> dict:
    load_r = np.asarray(load_r, dtype=float)
    pv_r = np.asarray(pv_r, dtype=float)
    price_r = np.asarray(price_r, dtype=float)
    if load_r.shape != pv_r.shape or load_r.shape != price_r.shape:
        raise AssertionError("residual stacks must share shape")
    if load_r.ndim != 2 or load_r.shape[1] != T:
        raise AssertionError(f"expected (n_days, {T}) residual stacks")
    names = ("load", "pv", "price")
    stacks = {"load": load_r, "pv": pv_r, "price": price_r}
    flat = {name: stacks[name].ravel() for name in names}
    daily_mean = {name: stacks[name].mean(axis=1) for name in names}
    corr_flat = {
        f"{a}_vs_{b}": pearson_corrcoef(flat[a], flat[b])
        for a in names
        for b in names
        if a < b
    }
    corr_daily = {
        f"{a}_vs_{b}": pearson_corrcoef(daily_mean[a], daily_mean[b])
        for a in names
        for b in names
        if a < b
    }
    return {
        "interpretation": (
            "Same-day (L, P, p) forecast residuals. Values are Pearson correlations, "
            "not causal effects. Residual dates are strictly those with archived causal "
            "load, PV, and day-ahead price forecasts."
        ),
        "n_days": int(load_r.shape[0]),
        "n_slots": int(load_r.size),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "pearson_flattened_slots": corr_flat,
        "pearson_daily_mean_residual": corr_daily,
        "residual_std": {
            "load_kwh": float(load_r.std()),
            "pv_kwh": float(pv_r.std()),
            "price_yuan_per_kwh": float(price_r.std()),
        },
        "scenario_audit_source": str(Q4_2_SCENARIO_AUDIT_CSV),
    }


def build_residual_correlation_from_bundle(bundle) -> dict:
    from q4.scenarios import residual_stack

    ok = []
    for i in range(bundle.n_days()):
        if not np.isfinite(bundle.price_archive.day_ahead[i]).all():
            continue
        if not np.isfinite(bundle.q2_forecast.load_hat[i]).all():
            continue
        if not np.isfinite(bundle.q2_forecast.pv_hat[i]).all():
            continue
        ok.append(i)
    indices = np.asarray(ok, dtype=int)
    load_r, pv_r, price_r = residual_stack(bundle, indices)
    dates = [bundle.prices.dates[i].strftime("%Y-%m-%d") for i in indices]
    report = residual_correlation_report(load_r, pv_r, price_r, dates)
    if Q4_2_SCENARIO_AUDIT_CSV.exists():
        audit = pd.read_csv(Q4_2_SCENARIO_AUDIT_CSV)
        report["scenario_audit_n_rows"] = int(len(audit))
        report["scenario_audit_n_days"] = int(audit["date"].nunique())
    return report
