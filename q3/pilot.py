from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import inf
from pathlib import Path
from time import perf_counter

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from q3.config import (
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    EMERGENCY_PRICE_MULTIPLIER,
    ETA_C,
    ETA_D,
    FIG_DIR,
    HOUR_TO_FIRST_MUTABLE,
    LOAD_INFORMATION_CASES,
    LOAD_INFORMATION_MAIN,
    LOAD_INFORMATION_PROXY,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    NEXT_DAY_VALUE_MAX_SAMPLES,
    NUMERIC_TOL,
    OUTPUT_DIR,
    PILOT_DATES,
    PV_MAPPING_LINEAR,
    SETTLEMENT_ALT,
    SETTLEMENT_MAIN,
    SIMULTANEOUS_CD_TOL,
    STRATEGY_ALLOWED_UPDATES,
    STRATEGIES,
    T,
    VOI_EPS_YUAN,
    WARMUP_CSV_MAIN,
    make_run_id,
)
from q3.data import Q3Data
from q3.forecast import (
    causal_load_forecast,
    causal_load_sources,
    execution_load_horizon,
    load_forecast_audit_rows,
    map_issue_forecast,
    next_day_pv_forecast,
    planning_load_curve,
    write_forecast_mapping,
)
from q3.optimization import (
    ValueCut,
    assert_physical,
    decompose_settlement,
    evaluate_value_cuts,
    realized_settlement,
    settlement_cost,
    solve_horizon,
)

plt.rcParams.update(
    {
        "font.sans-serif": ["Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 140,
    }
)

NAVY = "#1f4e79"
TEAL = "#2a9d8f"
ORANGE = "#e09f3e"
PURPLE = "#6d597a"


ValueCutCache = dict[tuple[int, int, str], tuple[tuple[ValueCut, ...], list[dict]]]


@dataclass
class DayRun:
    date: str
    strategy: str
    load_information_case: str
    pv_mapping_mode: str
    settlement_mode: str
    with_terminal_value: bool
    run_id: str
    dispatch: pd.DataFrame
    update_log: pd.DataFrame
    ledger: pd.DataFrame
    summary: dict
    next_day_value_rows: list[dict] = field(default_factory=list)


def dispatch_output_stem(date: str, strategy: str, load_information_case: str, with_terminal_value: bool) -> str:
    suffix = strategy + "_" + load_information_case
    if not with_terminal_value:
        suffix += "_no48h"
    return f"q3_dispatch_{date}_{suffix}"


def build_next_day_value_cuts(
    data: Q3Data,
    current_index: int,
    issue_hour: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    if current_index + 1 >= len(data.dates):
        return (), []
    load = causal_load_forecast(
        data, target_index=current_index + 1, history_end_exclusive=current_index
    )
    pv = next_day_pv_forecast(data, current_index, issue_hour, pv_mapping_mode)
    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = solve_horizon(
            data.price,
            load,
            pv,
            float(soc),
            bill_as_day_ahead=True,
            throughput_tiebreak=False,
        )
        value = result.settlement_cost + result.emergency_cost
        solved[float(soc)] = (float(soc), float(value), float(result.initial_soc_marginal))

    def certified_max_gap(cuts: tuple[ValueCut, ...]) -> tuple[float, float]:
        points = sorted(solved)
        best_gap, best_soc = -np.inf, points[0]
        lower_lines = [(0.0, 0.0)] + [
            (slope, value - slope * reference) for reference, value, slope in cuts
        ]
        for left, right in zip(points[:-1], points[1:]):
            left_value, right_value = solved[left][1], solved[right][1]
            upper_slope = (right_value - left_value) / (right - left)
            upper_intercept = left_value - upper_slope * left
            candidates = [left, right]
            for a, (slope_a, intercept_a) in enumerate(lower_lines):
                for slope_b, intercept_b in lower_lines[a + 1 :]:
                    if abs(slope_a - slope_b) <= 1e-14:
                        continue
                    cross = (intercept_b - intercept_a) / (slope_a - slope_b)
                    if left < cross < right:
                        candidates.append(float(cross))
            for soc in candidates:
                upper = upper_slope * soc + upper_intercept
                gap = upper - evaluate_value_cuts(soc, cuts)
                if gap > best_gap:
                    best_gap, best_soc = float(gap), float(soc)
        return max(best_gap, 0.0), best_soc

    solve_at(E_MIN_KWH)
    solve_at(E_MAX_KWH)
    gap = inf
    while True:
        cuts = tuple(solved[soc] for soc in sorted(solved))
        slopes = np.array([cut[2] for cut in cuts])
        if np.any(np.diff(slopes) < -1e-6):
            raise AssertionError("Q3 next-day value subgradients are not monotone")
        gap, refine_soc = certified_max_gap(cuts)
        if gap <= NEXT_DAY_VALUE_GAP_TOL_YUAN:
            break
        if len(cuts) >= NEXT_DAY_VALUE_MAX_SAMPLES:
            raise AssertionError(
                f"Q3 next-day value gap {gap:.6f} exceeds tolerance after {len(cuts)} samples"
            )
        if min(abs(refine_soc - soc) for soc in solved) < 1e-7:
            raise AssertionError("Q3 next-day value refinement stalled")
        solve_at(refine_soc)

    target = data.dates[current_index + 1].strftime("%Y-%m-%d")
    rows = [
        {
            "current_date": data.dates[current_index].strftime("%Y-%m-%d"),
            "target_date": target,
            "issue_hour": issue_hour,
            "pv_mapping_mode": pv_mapping_mode,
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
            "bundle_sample_count": len(cuts),
            "information": (
                f"Q3 {pv_mapping_mode} overlay + causal prior-day load/PV; no future actual PV"
            ),
        }
        for reference, value, slope in cuts
    ]
    return cuts, rows


def _index_to_update_hour(index: int) -> int | None:
    inverse = {first: hour for hour, first in HOUR_TO_FIRST_MUTABLE.items() if hour != 0}
    return inverse.get(index)


def _run_key_fields(
    date: str,
    strategy: str,
    load_information_case: str,
    pv_mapping_mode: str,
    settlement_mode: str,
    with_terminal_value: bool,
    run_id: str,
) -> dict:
    return {
        "date": date,
        "strategy": strategy,
        "load_information_case": load_information_case,
        "pv_mapping_mode": pv_mapping_mode,
        "settlement_mode": settlement_mode,
        "with_terminal_value": with_terminal_value,
        "run_id": run_id,
    }


def _settlement_ledger_rows(
    date: str,
    strategy: str,
    load_information_case: str,
    pv_mapping_mode: str,
    settlement_mode: str,
    with_terminal_value: bool,
    run_id: str,
    time_labels: tuple[str, ...],
    price: np.ndarray,
    versions: list[np.ndarray],
    version_times: list[str],
    dispatch: pd.DataFrame,
) -> list[dict]:
    keys = _run_key_fields(
        date,
        strategy,
        load_information_case,
        pv_mapping_mode,
        settlement_mode,
        with_terminal_value,
        run_id,
    )
    ordinary, up_fee, down_fee = decompose_settlement(price, versions, settlement_mode)
    emergency = dispatch["emergency_cost_yuan"].to_numpy()
    emergency_kwh = dispatch["emergency_kwh"].to_numpy()
    g0 = versions[0]
    gf = versions[-1]
    rows: list[dict] = []
    for t in range(T):
        p = float(price[t])
        rows.append(
            {
                **keys,
                "row_role": "period_total",
                "period": t,
                "time": time_labels[t],
                "plan_version_time": str(dispatch["last_update_time"].iloc[t]),
                "g_before_kwh": float(g0[t]),
                "g_after_kwh": float(gf[t]),
                "up_adjust_kwh": float(max(gf[t] - g0[t], 0.0)),
                "down_adjust_kwh": float(max(g0[t] - gf[t], 0.0)),
                "ordinary_yuan": float(ordinary[t]),
                "up_fee_yuan": float(up_fee[t]),
                "down_fee_yuan": float(down_fee[t]),
                "emergency_kwh": float(emergency_kwh[t]),
                "emergency_yuan": float(emergency[t]),
                "total_yuan": float(ordinary[t] + up_fee[t] + down_fee[t] + emergency[t]),
            }
        )
        if settlement_mode == SETTLEMENT_ALT:
            rows.append(
                {
                    **keys,
                    "row_role": "event",
                    "period": t,
                    "time": time_labels[t],
                    "plan_version_time": "00:00",
                    "g_before_kwh": 0.0,
                    "g_after_kwh": float(g0[t]),
                    "up_adjust_kwh": float(g0[t]),
                    "down_adjust_kwh": 0.0,
                    "ordinary_yuan": p * float(g0[t]),
                    "up_fee_yuan": 0.0,
                    "down_fee_yuan": 0.0,
                    "emergency_kwh": 0.0,
                    "emergency_yuan": 0.0,
                    "total_yuan": p * float(g0[t]),
                }
            )
            for prev, cur, ts in zip(versions[:-1], versions[1:], version_times[1:]):
                up = float(max(cur[t] - prev[t], 0.0))
                down = float(max(prev[t] - cur[t], 0.0))
                rows.append(
                    {
                        **keys,
                        "row_role": "event",
                        "period": t,
                        "time": time_labels[t],
                        "plan_version_time": ts,
                        "g_before_kwh": float(prev[t]),
                        "g_after_kwh": float(cur[t]),
                        "up_adjust_kwh": up,
                        "down_adjust_kwh": down,
                        "ordinary_yuan": 0.0,
                        "up_fee_yuan": 1.5 * p * up,
                        "down_fee_yuan": 0.5 * p * down,
                        "emergency_kwh": 0.0,
                        "emergency_yuan": 0.0,
                        "total_yuan": 1.5 * p * up + 0.5 * p * down,
                    }
                )
        else:
            up = float(max(gf[t] - g0[t], 0.0))
            down = float(max(g0[t] - gf[t], 0.0))
            rows.append(
                {
                    **keys,
                    "row_role": "event",
                    "period": t,
                    "time": time_labels[t],
                    "plan_version_time": str(dispatch["last_update_time"].iloc[t]),
                    "g_before_kwh": float(g0[t]),
                    "g_after_kwh": float(gf[t]),
                    "up_adjust_kwh": up,
                    "down_adjust_kwh": down,
                    "ordinary_yuan": p * float(gf[t]),
                    "up_fee_yuan": 0.5 * p * up,
                    "down_fee_yuan": 0.5 * p * down,
                    "emergency_kwh": 0.0,
                    "emergency_yuan": 0.0,
                    "total_yuan": p * float(gf[t]) + 0.5 * p * (up + down),
                }
            )
        rows.append(
            {
                **keys,
                "row_role": "event",
                "period": t,
                "time": time_labels[t],
                "plan_version_time": "execution",
                "g_before_kwh": float(gf[t]),
                "g_after_kwh": float(gf[t]),
                "up_adjust_kwh": 0.0,
                "down_adjust_kwh": 0.0,
                "ordinary_yuan": 0.0,
                "up_fee_yuan": 0.0,
                "down_fee_yuan": 0.0,
                "emergency_kwh": float(emergency_kwh[t]),
                "emergency_yuan": float(emergency[t]),
                "total_yuan": float(emergency[t]),
            }
        )
    return rows


def _next_day_value_cuts(
    data: Q3Data,
    day_index: int,
    issue_hour: int,
    cache: ValueCutCache | None,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    key = (day_index, issue_hour, pv_mapping_mode)
    if cache is not None and key in cache:
        return cache[key]
    cuts, rows = build_next_day_value_cuts(data, day_index, issue_hour, pv_mapping_mode)
    if cache is not None:
        cache[key] = (cuts, rows)
    return cuts, rows


def run_day(
    data: Q3Data,
    day_index: int,
    strategy: str,
    initial_soc: float,
    with_terminal_value: bool = True,
    load_information_case: str = LOAD_INFORMATION_MAIN,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
    settlement_mode: str = SETTLEMENT_MAIN,
    value_cut_cache: ValueCutCache | None = None,
) -> DayRun:
    date = data.dates[day_index].strftime("%Y-%m-%d")
    run_id = make_run_id(
        date,
        strategy,
        load_information_case,
        pv_mapping_mode,
        settlement_mode,
        with_terminal_value,
    )
    allowed = STRATEGY_ALLOWED_UPDATES[strategy]
    price = data.price
    actual_load = data.load[day_index]
    plan_load = planning_load_curve(data, day_index, load_information_case)
    actual_pv = data.pv[day_index]
    started = perf_counter()

    mapped0 = map_issue_forecast(data, day_index, 0, pv_mapping_mode)
    current_forecast = mapped0.today_kwh.copy()
    cuts: tuple[ValueCut, ...] = ()
    value_rows: list[dict] = []
    if with_terminal_value:
        cuts, rows = _next_day_value_cuts(
            data, day_index, 0, value_cut_cache, pv_mapping_mode
        )
        value_rows.extend(rows)

    midnight = solve_horizon(
        price,
        plan_load,
        current_forecast,
        initial_soc,
        bill_as_day_ahead=True,
        terminal_value_cuts=cuts or None,
    )
    assert_physical(midnight, plan_load, current_forecast, prefix=f"{date} 0:00 plan ")
    g0 = midnight.g.copy()
    g = g0.copy()
    versions = [g0.copy()]
    version_times = ["00:00"]
    last_update = "00:00"

    def remaining_kwargs(t: int, g_pre_rem: np.ndarray) -> dict:
        kwargs: dict = {
            "settlement_mode": settlement_mode,
            "terminal_value_cuts": cuts or None,
            "g0": g0[t:],
        }
        if settlement_mode == SETTLEMENT_ALT:
            kwargs["g_pre"] = g_pre_rem
            kwargs["sunk_settlement"] = float(
                np.sum(
                    realized_settlement(
                        price[t:], [v[t:] for v in versions], SETTLEMENT_ALT
                    )
                )
            )
        return kwargs

    update_rows = [
        {
            "date": date,
            "update_time": "00:00",
            "first_mutable_index": 0,
            "voi_yuan": np.nan,
            "implemented": True,
            "l1_change_kwh": float(np.abs(g0).sum()),
            "up_adjust_kwh": float(g0.sum()),
            "down_adjust_kwh": 0.0,
            "j_fix_yuan": np.nan,
            "j_free_yuan": float(midnight.objective),
            "soc_before_kwh": float(initial_soc),
            "soc_after_plan_kwh": float(midnight.soc[-1]),
            "solver_status": midnight.status,
            "solve_seconds": midnight.solve_seconds,
        }
    ]

    dispatch_rows = []
    soc = float(initial_soc)
    max_cd = 0.0
    max_balance = 0.0
    max_soc_residual = 0.0
    locked_violations = 0
    g_before_update = g.copy()

    for t in range(T):
        hour = _index_to_update_hour(t)
        if hour is not None and hour in allowed:
            g_before_update = g.copy()
            mapped = map_issue_forecast(data, day_index, hour, pv_mapping_mode)
            current_forecast = mapped.today_kwh.copy()
            if with_terminal_value:
                cuts, rows = _next_day_value_cuts(
                    data, day_index, hour, value_cut_cache, pv_mapping_mode
                )
                value_rows.extend(rows)
            pv_plan = current_forecast[t:]
            load_plan = plan_load[t:]
            g_pre = g[t:].copy()
            settle_kw = remaining_kwargs(t, g_pre)
            j_fix = solve_horizon(
                price[t:],
                load_plan,
                pv_plan,
                soc,
                g_fixed=g_pre,
                **settle_kw,
            )
            j_free = solve_horizon(
                price[t:],
                load_plan,
                pv_plan,
                soc,
                **settle_kw,
            )
            voi = float(j_fix.objective - j_free.objective)
            implemented = bool(voi > VOI_EPS_YUAN)
            if implemented:
                g[t:] = j_free.g
                versions.append(g.copy())
                version_times.append(f"{hour:02d}:00")
            delta = g[t:] - g_pre
            update_rows.append(
                {
                    "date": date,
                    "update_time": f"{hour:02d}:00",
                    "first_mutable_index": t,
                    "voi_yuan": voi,
                    "implemented": implemented,
                    "l1_change_kwh": float(np.abs(delta).sum()),
                    "up_adjust_kwh": float(np.maximum(delta, 0.0).sum()),
                    "down_adjust_kwh": float(np.maximum(-delta, 0.0).sum()),
                    "j_fix_yuan": float(j_fix.objective),
                    "j_free_yuan": float(j_free.objective),
                    "soc_before_kwh": float(soc),
                    "soc_after_plan_kwh": float((j_free if implemented else j_fix).soc[-1]),
                    "solver_status": j_free.status,
                    "solve_seconds": j_fix.solve_seconds + j_free.solve_seconds,
                }
            )
            last_update = f"{hour:02d}:00"
            if np.max(np.abs(g[:t] - g_before_update[:t])) > NUMERIC_TOL:
                locked_violations += 1

        pv_horizon = current_forecast[t:].copy()
        pv_horizon[0] = actual_pv[t]
        load_horizon = execution_load_horizon(plan_load, actual_load, t)
        step = solve_horizon(
            price[t:],
            load_horizon,
            pv_horizon,
            soc,
            g_fixed=g[t:],
            **remaining_kwargs(t, g[t:]),
        )
        residual = (
            step.x[0]
            + step.emergency[0]
            + actual_pv[t]
            - step.curtailment[0]
            + step.discharge[0]
            - actual_load[t]
            - step.charge[0]
        )
        soc_next = float(step.soc[1])
        soc_residual = soc_next - (
            soc + ETA_C * step.charge[0] - step.discharge[0] / ETA_D
        )
        max_cd = max(max_cd, float(step.charge[0] * step.discharge[0]))
        max_balance = max(max_balance, abs(float(residual)))
        max_soc_residual = max(max_soc_residual, abs(float(soc_residual)))
        dispatch_rows.append(
            {
                "time": data.time_labels[t],
                "period": t,
                "planned_g0_kwh": float(g0[t]),
                "final_g_kwh": float(g[t]),
                "normal_x_kwh": float(step.x[0]),
                "load_kwh": float(actual_load[t]),
                "forecast_load_kwh": float(plan_load[t]),
                "actual_pv_kwh": float(actual_pv[t]),
                "forecast_pv_kwh": float(current_forecast[t]),
                "charge_kwh": float(step.charge[0]),
                "discharge_kwh": float(step.discharge[0]),
                "curtailment_kwh": float(step.curtailment[0]),
                "emergency_kwh": float(step.emergency[0]),
                "soc_kwh": soc_next,
                "balance_residual_kwh": float(residual),
                "last_update_time": last_update,
                "price": float(price[t]),
            }
        )
        if abs(g[t] - step.g[0]) > 1e-6:
            locked_violations += 1
        soc = soc_next
        if max_cd > SIMULTANEOUS_CD_TOL:
            raise AssertionError(
                f"{date} {strategy} t={t}: simultaneous charge/discharge {max_cd:.3e}"
            )

    dispatch = pd.DataFrame(dispatch_rows)
    phi = realized_settlement(price, versions, settlement_mode)
    dispatch["phi_yuan"] = phi
    dispatch["emergency_cost_yuan"] = (
        EMERGENCY_PRICE_MULTIPLIER * dispatch["price"] * dispatch["emergency_kwh"]
    )
    dispatch["run_id"] = run_id
    dispatch["pv_mapping_mode"] = pv_mapping_mode
    dispatch["settlement_mode"] = settlement_mode
    ledger = pd.DataFrame(
        _settlement_ledger_rows(
            date=date,
            strategy=strategy,
            load_information_case=load_information_case,
            pv_mapping_mode=pv_mapping_mode,
            settlement_mode=settlement_mode,
            with_terminal_value=with_terminal_value,
            run_id=run_id,
            time_labels=data.time_labels,
            price=price,
            versions=versions,
            version_times=version_times,
            dispatch=dispatch,
        )
    )
    update_log = pd.DataFrame(update_rows)
    update_log.insert(1, "strategy", strategy)
    update_log.insert(2, "load_information_case", load_information_case)
    update_log.insert(3, "pv_mapping_mode", pv_mapping_mode)
    update_log.insert(4, "settlement_mode", settlement_mode)
    update_log.insert(5, "with_terminal_value", with_terminal_value)
    update_log.insert(6, "run_id", run_id)
    n_adjust = int(((update_log["update_time"] != "00:00") & update_log["implemented"]).sum())
    summary = {
        "date": date,
        "strategy": strategy,
        "load_information_case": load_information_case,
        "pv_mapping_mode": pv_mapping_mode,
        "settlement_mode": settlement_mode,
        "with_terminal_value": with_terminal_value,
        "run_id": run_id,
        "total_cost_yuan": float(dispatch["phi_yuan"].sum() + dispatch["emergency_cost_yuan"].sum()),
        "settlement_cost_yuan": float(dispatch["phi_yuan"].sum()),
        "emergency_cost_yuan": float(dispatch["emergency_cost_yuan"].sum()),
        "curtailment_kwh": float(dispatch["curtailment_kwh"].sum()),
        "emergency_kwh": float(dispatch["emergency_kwh"].sum()),
        "soc_start_kwh": float(initial_soc),
        "soc_end_kwh": float(dispatch["soc_kwh"].iloc[-1]),
        "adjustment_count": n_adjust,
        "up_adjust_kwh": float(
            np.maximum(
                dispatch["final_g_kwh"].to_numpy() - dispatch["planned_g0_kwh"].to_numpy(),
                0.0,
            ).sum()
        ),
        "down_adjust_kwh": float(
            np.maximum(
                dispatch["planned_g0_kwh"].to_numpy() - dispatch["final_g_kwh"].to_numpy(),
                0.0,
            ).sum()
        ),
        "max_balance_residual_kwh": float(max_balance),
        "max_soc_residual_kwh": float(max_soc_residual),
        "max_simultaneous_cd_kwh2": float(max_cd),
        "locked_period_violations": int(locked_violations),
        "runtime_seconds": float(perf_counter() - started),
    }
    return DayRun(
        date,
        strategy,
        load_information_case,
        pv_mapping_mode,
        settlement_mode,
        with_terminal_value,
        run_id,
        dispatch,
        update_log,
        ledger,
        summary,
        value_rows,
    )


def warmup_soc_to(
    data: Q3Data, target_index: int, path: Path
) -> tuple[np.ndarray, pd.DataFrame]:
    """Propagate M0 from 2025-01-01 so the first pilot day has a causal SOC."""
    starts = np.full(target_index + 1, E_INITIAL_KWH)
    rows = []
    soc = E_INITIAL_KWH
    for i in range(target_index):
        starts[i] = soc
        result = run_day(
            data,
            i,
            "M0",
            soc,
            with_terminal_value=True,
            load_information_case=LOAD_INFORMATION_MAIN,
        )
        soc = float(result.summary["soc_end_kwh"])
        rows.append(
            {
                "date": result.date,
                "soc_start_kwh": result.summary["soc_start_kwh"],
                "soc_end_kwh": result.summary["soc_end_kwh"],
                "total_cost_yuan": result.summary["total_cost_yuan"],
                "strategy": "M0_warmup",
                "load_information_case": LOAD_INFORMATION_MAIN,
            }
        )
    starts[target_index] = soc
    frame = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return starts, frame


def _spotcheck_settlement(dispatch: pd.DataFrame) -> list[dict]:
    phi = dispatch["phi_yuan"].to_numpy()
    g0 = dispatch["planned_g0_kwh"].to_numpy()
    gf = dispatch["final_g_kwh"].to_numpy()
    price = dispatch["price"].to_numpy()
    rows = []
    cases = {
        "no_adjust": np.where(np.abs(gf - g0) <= 1e-8)[0],
        "down": np.where(gf + 1e-8 < g0)[0],
        "up": np.where(gf > g0 + 1e-8)[0],
    }
    for name, indices in cases.items():
        if len(indices) == 0:
            rows.append({"case": name, "found": False})
            continue
        t = int(indices[len(indices) // 2])
        expected = settlement_cost(price[t : t + 1], g0[t : t + 1], gf[t : t + 1])[0]
        rows.append(
            {
                "case": name,
                "found": True,
                "period": t,
                "time": str(dispatch["time"].iloc[t]),
                "g0_kwh": float(g0[t]),
                "gF_kwh": float(gf[t]),
                "price": float(price[t]),
                "phi_yuan": float(phi[t]),
                "expected_phi_yuan": float(expected),
                "abs_error": float(abs(phi[t] - expected)),
            }
        )
    return rows


def write_cost_audit(runs: list[DayRun], path: Path) -> pd.DataFrame:
    frames = []
    spot = []
    for run in runs:
        block = run.dispatch.copy()
        block["date"] = run.date
        block["strategy"] = run.strategy
        block["load_information_case"] = run.load_information_case
        block["pv_mapping_mode"] = run.pv_mapping_mode
        block["settlement_mode"] = run.settlement_mode
        block["with_terminal_value"] = run.with_terminal_value
        block["run_id"] = run.run_id
        frames.append(
            block[
                [
                    "date",
                    "strategy",
                    "load_information_case",
                    "pv_mapping_mode",
                    "settlement_mode",
                    "with_terminal_value",
                    "run_id",
                    "time",
                    "planned_g0_kwh",
                    "final_g_kwh",
                    "price",
                    "phi_yuan",
                    "emergency_kwh",
                    "emergency_cost_yuan",
                ]
            ]
        )
        for item in _spotcheck_settlement(run.dispatch):
            spot.append(
                {
                    "date": run.date,
                    "strategy": run.strategy,
                    "load_information_case": run.load_information_case,
                    "pv_mapping_mode": run.pv_mapping_mode,
                    "settlement_mode": run.settlement_mode,
                    "with_terminal_value": run.with_terminal_value,
                    "run_id": run.run_id,
                    **item,
                }
            )
    frame = pd.concat(frames, ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    path.with_name("q3_cost_spotcheck.csv").write_text(
        pd.DataFrame(spot).to_csv(index=False), encoding="utf-8"
    )
    return frame


def plot_pilot_figures(runs: list[DayRun], comparison: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    main = comparison[
        comparison["strategy"].isin(STRATEGIES)
        & comparison["with_terminal_value"]
        & comparison["load_information_case"].eq(LOAD_INFORMATION_MAIN)
    ].copy()
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    dates = list(dict.fromkeys(main["date"]))
    x = np.arange(len(STRATEGIES))
    width = 0.35
    for i, date in enumerate(dates):
        subset = main[main["date"] == date].set_index("strategy").loc[list(STRATEGIES)]
        ax.bar(
            x + (i - 0.5) * width,
            subset["total_cost_yuan"],
            width=width,
            color=(NAVY if i == 0 else TEAL),
            label=date,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(STRATEGIES)
    ax.set_ylabel("total purchase cost (yuan)")
    ax.set_title("Q3 pilot: update-policy cost (causal_load_main)")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_strategy_cost.png")
    fig.savefig(FIG_DIR / "fig3_strategy_cost_causal_load_main.png")
    plt.close(fig)

    for run in runs:
        if (
            run.strategy != "M1_M6"
            or not run.with_terminal_value
            or run.load_information_case != LOAD_INFORMATION_MAIN
        ):
            continue
        d = run.dispatch
        fig, axes = plt.subplots(3, 1, figsize=(8.6, 7.2), sharex=True)
        t = np.arange(len(d))
        axes[0].plot(t, d["load_kwh"], color=NAVY, lw=1.2, label="actual load")
        axes[0].plot(t, d["forecast_load_kwh"], color=PURPLE, lw=1.0, ls="--", label="causal load hat")
        axes[0].plot(t, d["actual_pv_kwh"], color=TEAL, lw=1.2, label="actual PV")
        axes[0].plot(t, d["forecast_pv_kwh"], color=ORANGE, lw=1.0, ls="--", label="active PV forecast")
        axes[0].legend(frameon=False, ncol=2)
        axes[0].set_ylabel("kWh / 10 min")
        axes[1].plot(t, d["planned_g0_kwh"], color=PURPLE, lw=1.1, label="g0")
        axes[1].plot(t, d["final_g_kwh"], color=ORANGE, lw=1.2, label="gF")
        axes[1].plot(t, d["normal_x_kwh"], color=NAVY, lw=1.0, ls=":", label="x")
        axes[1].legend(frameon=False, ncol=3)
        axes[1].set_ylabel("purchase kWh")
        axes[2].plot(t, d["soc_kwh"], color=TEAL, lw=1.3)
        axes[2].axhline(E_MIN_KWH, color=ORANGE, ls="--", lw=0.8)
        axes[2].axhline(E_MAX_KWH, color=ORANGE, ls="--", lw=0.8)
        axes[2].set_ylabel("SOC kWh")
        axes[2].set_xlabel("10-minute index")
        fig.suptitle(f"{run.date} M1/M6 dispatch ({LOAD_INFORMATION_MAIN})", fontsize=12)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"fig3_dispatch_{run.date}_M1_M6.png")
        fig.savefig(FIG_DIR / f"fig3_dispatch_{run.date}_M1_M6_{LOAD_INFORMATION_MAIN}.png")
        plt.close(fig)

        log = run.update_log[run.update_log["update_time"] != "00:00"]
        fig, ax = plt.subplots(figsize=(6.4, 3.8))
        ax.bar(log["update_time"], log["voi_yuan"], color=TEAL)
        ax.axhline(VOI_EPS_YUAN, color=ORANGE, ls="--", lw=0.9, label="VoI threshold")
        ax.set_ylabel("VoI (yuan)")
        ax.set_title(f"{run.date} information value by update ({LOAD_INFORMATION_MAIN})")
        ax.legend(frameon=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"fig3_voi_{run.date}.png")
        fig.savefig(FIG_DIR / f"fig3_voi_{run.date}_{LOAD_INFORMATION_MAIN}.png")
        plt.close(fig)

    info = comparison[
        comparison["strategy"].isin(STRATEGIES) & comparison["with_terminal_value"]
    ].copy()
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.2), sharey=True)
    x = np.arange(len(STRATEGIES))
    width = 0.35
    for ax, date in zip(axes, list(dict.fromkeys(info["date"]))):
        for i, case in enumerate(LOAD_INFORMATION_CASES):
            subset = (
                info[(info["date"] == date) & (info["load_information_case"] == case)]
                .set_index("strategy")
                .loc[list(STRATEGIES)]
            )
            ax.bar(
                x + (i - 0.5) * width,
                subset["total_cost_yuan"],
                width=width,
                color=(NAVY if i == 0 else ORANGE),
                label=case,
            )
        ax.set_xticks(x)
        ax.set_xticklabels(STRATEGIES, rotation=20, ha="right")
        ax.set_title(date)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("total purchase cost (yuan)")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Load-information comparison (same SOC, prices, PV, settlement)", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_load_information_comparison.png")
    plt.close(fig)


def physical_audit(runs: list[DayRun], warmup_end_soc: float | None) -> dict:
    items = []
    all_pass = True
    for run in runs:
        d = run.dispatch
        soc = np.concatenate([[run.summary["soc_start_kwh"]], d["soc_kwh"].to_numpy()])
        rec = {
            "date": run.date,
            "strategy": run.strategy,
            "load_information_case": run.load_information_case,
            "pv_mapping_mode": run.pv_mapping_mode,
            "settlement_mode": run.settlement_mode,
            "with_terminal_value": run.with_terminal_value,
            "run_id": run.run_id,
            "max_balance_residual_kwh": run.summary["max_balance_residual_kwh"],
            "max_soc_residual_kwh": run.summary["max_soc_residual_kwh"],
            "max_simultaneous_cd_kwh2": run.summary["max_simultaneous_cd_kwh2"],
            "soc_min_kwh": float(np.min(soc)),
            "soc_max_kwh": float(np.max(soc)),
            "locked_period_violations": run.summary["locked_period_violations"],
            "pass": bool(
                run.summary["max_balance_residual_kwh"] < 1e-5
                and run.summary["max_soc_residual_kwh"] < 1e-5
                and run.summary["max_simultaneous_cd_kwh2"] <= SIMULTANEOUS_CD_TOL
                and run.summary["locked_period_violations"] == 0
                and np.min(soc) >= E_MIN_KWH - 1e-6
                and np.max(soc) <= E_MAX_KWH + 1e-6
            ),
        }
        all_pass = all_pass and rec["pass"]
        items.append(rec)
    return {
        "all_pass": all_pass,
        "warmup_end_soc_for_2025-02-01": warmup_end_soc,
        "warmup_load_information_case": LOAD_INFORMATION_MAIN,
        "runs": items,
    }


def write_load_forecast_audit(data: Q3Data, path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    for date in PILOT_DATES:
        rows.extend(load_forecast_audit_rows(data, data.date_index(date)))
    frame = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def write_load_information_comparison(comparison: pd.DataFrame, path: Path) -> pd.DataFrame:
    cols = [
        "date",
        "strategy",
        "load_information_case",
        "with_terminal_value",
        "total_cost_yuan",
        "settlement_cost_yuan",
        "emergency_cost_yuan",
        "emergency_kwh",
        "curtailment_kwh",
        "soc_start_kwh",
        "soc_end_kwh",
        "runtime_seconds",
    ]
    frame = comparison[cols].copy()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def run_causality_audit(data: Q3Data, day_index: int, initial_soc: float) -> dict:
    """Perturb unrealized same-day actual load: main forecasts stay put, proxy may move."""
    date = data.dates[day_index].strftime("%Y-%m-%d")
    price = data.price
    pv0 = map_issue_forecast(data, day_index, 0).today_kwh
    hat_before, sources_before, label_before = causal_load_sources(data, day_index, day_index)
    proxy_before = planning_load_curve(data, day_index, LOAD_INFORMATION_PROXY)
    next_before = (
        causal_load_forecast(data, day_index + 1, day_index)
        if day_index + 1 < len(data.dates)
        else None
    )
    g0_main_before = solve_horizon(
        price, hat_before, pv0, initial_soc, bill_as_day_ahead=True, throughput_tiebreak=False
    ).g
    g0_proxy_before = solve_horizon(
        price, proxy_before, pv0, initial_soc, bill_as_day_ahead=True, throughput_tiebreak=False
    ).g

    original = data.load[day_index].copy()
    perturbation_kwh = 500.0
    try:
        data.load[day_index, 36:] += perturbation_kwh
        hat_after, sources_after, label_after = causal_load_sources(data, day_index, day_index)
        proxy_after = planning_load_curve(data, day_index, LOAD_INFORMATION_PROXY)
        next_after = (
            causal_load_forecast(data, day_index + 1, day_index)
            if day_index + 1 < len(data.dates)
            else None
        )
        g0_main_after = solve_horizon(
            price, hat_after, pv0, initial_soc, bill_as_day_ahead=True, throughput_tiebreak=False
        ).g
        g0_proxy_after = solve_horizon(
            price, proxy_after, pv0, initial_soc, bill_as_day_ahead=True, throughput_tiebreak=False
        ).g
        mapped6_before = map_issue_forecast(data, day_index, 6)
        plan_main_update_before = hat_before[36:]
        plan_main_update_after = hat_after[36:]
    finally:
        data.load[day_index] = original

    main_forecast_delta = float(np.max(np.abs(hat_after - hat_before)))
    main_update_delta = float(np.max(np.abs(plan_main_update_after - plan_main_update_before)))
    main_g0_delta = float(np.max(np.abs(g0_main_after - g0_main_before)))
    proxy_plan_delta = float(np.max(np.abs(proxy_after - proxy_before)))
    proxy_g0_delta = float(np.max(np.abs(g0_proxy_after - g0_proxy_before)))
    next_delta = (
        float(np.max(np.abs(next_after - next_before))) if next_before is not None else 0.0
    )
    payload = {
        "date": date,
        "perturbed_slice": "periods[36:] (unrealized same-day actual load after 06:00)",
        "perturbation_kwh": perturbation_kwh,
        "source_dates": label_before,
        "source_dates_after_perturbation": label_after,
        "main_day_ahead_forecast_unchanged": bool(main_forecast_delta < 1e-12),
        "main_update_forecast_unchanged": bool(main_update_delta < 1e-12),
        "main_next_day_forecast_unchanged": bool(next_delta < 1e-12),
        "main_g0_unchanged": bool(main_g0_delta < 1e-6),
        "proxy_planning_load_changed": bool(proxy_plan_delta > 1.0),
        "proxy_g0_changed": bool(proxy_g0_delta > 1e-6),
        "max_abs_main_forecast_delta_kwh": main_forecast_delta,
        "max_abs_main_update_forecast_delta_kwh": main_update_delta,
        "max_abs_main_g0_delta_kwh": main_g0_delta,
        "max_abs_proxy_planning_delta_kwh": proxy_plan_delta,
        "max_abs_proxy_g0_delta_kwh": proxy_g0_delta,
        "max_abs_next_day_forecast_delta_kwh": next_delta,
        "source_indices_unchanged": sources_before == sources_after,
        "six_am_first_mutable_index": int(mapped6_before.first_mutable_index),
        "note": (
            "causal_load_main day-ahead and 6/12/18 future load stay at the 0:00 hat. "
            "actual_load_proxy is allowed to change because it reads the full same-day Attachment 2 path."
        ),
    }
    payload["all_pass"] = bool(
        payload["main_day_ahead_forecast_unchanged"]
        and payload["main_update_forecast_unchanged"]
        and payload["main_next_day_forecast_unchanged"]
        and payload["main_g0_unchanged"]
        and payload["proxy_planning_load_changed"]
        and payload["proxy_g0_changed"]
        and payload["source_indices_unchanged"]
    )
    return payload


def run_q3_pilot(data: Q3Data) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    from q3.data import write_input_audit

    write_input_audit(data, OUTPUT_DIR / "input_audit.json")
    write_forecast_mapping(data, OUTPUT_DIR / "q3_forecast_mapping.csv")
    write_load_forecast_audit(data, OUTPUT_DIR / "q3_load_forecast_audit.csv")

    feb_index = data.date_index("2025-02-01")
    warmup_path = OUTPUT_DIR / WARMUP_CSV_MAIN
    if warmup_path.exists() and len(pd.read_csv(warmup_path)) >= feb_index:
        warmup_frame = pd.read_csv(warmup_path)
        warmup_starts = np.full(feb_index + 1, E_INITIAL_KWH)
        warmup_starts[1:] = warmup_frame["soc_end_kwh"].to_numpy()[:feb_index]
        print(f"reusing causal_load_main warmup SOC from {warmup_path}")
    else:
        warmup_starts, _warmup = warmup_soc_to(data, feb_index, warmup_path)
    initial = {
        "2025-02-01": float(warmup_starts[feb_index]),
        "2025-06-21": E_INITIAL_KWH,
    }

    value_cut_cache: ValueCutCache = {}
    runs: list[DayRun] = []
    for date in PILOT_DATES:
        i = data.date_index(date)
        soc0 = initial[date]
        for case in LOAD_INFORMATION_CASES:
            for strategy in STRATEGIES:
                runs.append(
                    run_day(
                        data,
                        i,
                        strategy,
                        soc0,
                        with_terminal_value=True,
                        load_information_case=case,
                        value_cut_cache=value_cut_cache,
                    )
                )
            runs.append(
                run_day(
                    data,
                    i,
                    "M1_M6",
                    soc0,
                    with_terminal_value=False,
                    load_information_case=case,
                    value_cut_cache=value_cut_cache,
                )
            )

    comparison = pd.DataFrame([run.summary for run in runs])
    comparison.to_csv(OUTPUT_DIR / "q3_strategy_comparison.csv", index=False)
    write_load_information_comparison(
        comparison, OUTPUT_DIR / "q3_load_information_comparison.csv"
    )
    update_log = pd.concat([run.update_log for run in runs], ignore_index=True)
    update_log.to_csv(OUTPUT_DIR / "q3_update_log.csv", index=False)
    value_rows = []
    for _key in sorted(value_cut_cache):
        value_rows.extend(value_cut_cache[_key][1])
    if value_rows:
        pd.DataFrame(value_rows).to_csv(OUTPUT_DIR / "q3_next_day_value_audit.csv", index=False)
    write_cost_audit(runs, OUTPUT_DIR / "q3_cost_audit.csv")

    dispatch_cols = [
        "time",
        "planned_g0_kwh",
        "final_g_kwh",
        "normal_x_kwh",
        "load_kwh",
        "forecast_load_kwh",
        "actual_pv_kwh",
        "forecast_pv_kwh",
        "charge_kwh",
        "discharge_kwh",
        "curtailment_kwh",
        "emergency_kwh",
        "soc_kwh",
        "balance_residual_kwh",
        "last_update_time",
    ]
    for run in runs:
        stem = dispatch_output_stem(
            run.date, run.strategy, run.load_information_case, run.with_terminal_value
        )
        run.dispatch[dispatch_cols].to_csv(OUTPUT_DIR / f"{stem}.csv", index=False)

    plot_pilot_figures(runs, comparison)
    audit = physical_audit(runs, initial["2025-02-01"])
    (OUTPUT_DIR / "q3_physical_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    causality = run_causality_audit(
        data, data.date_index("2025-02-01"), initial["2025-02-01"]
    )
    (OUTPUT_DIR / "q3_causality_audit.json").write_text(
        json.dumps(causality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not causality["all_pass"]:
        raise AssertionError(f"Q3 load causality audit failed: {causality}")
    return {
        "initial_soc": initial,
        "comparison": comparison,
        "audit": audit,
        "causality": causality,
        "n_runs": len(runs),
        "load_treatment": LOAD_INFORMATION_MAIN,
    }
