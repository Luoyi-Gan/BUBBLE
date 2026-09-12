"""Q4-3: fixed M1_M6 with causal price forecasts and delivery-time settlement."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

import numpy as np
import pandas as pd

from q3.config import (
    E_MAX_KWH,
    E_MIN_KWH,
    EMERGENCY_PRICE_MULTIPLIER,
    HOUR_TO_FIRST_MUTABLE,
    LOAD_INFORMATION_MAIN,
    NUMERIC_TOL,
    PV_MAPPING_LINEAR,
    SETTLEMENT_MAIN,
    SIMULTANEOUS_CD_TOL,
    STRATEGY_ALLOWED_UPDATES,
    T,
    VOI_EPS_YUAN,
    next_day_year_end_soc,
    today_year_end_soc,
)
from q3.forecast import (
    execution_load_horizon,
    map_issue_forecast,
    next_day_pv_forecast,
    planning_load_curve,
    causal_load_forecast,
)
from q3.optimization import (
    ValueCut,
    evaluate_value_cuts,
    settlement_cost,
    solve_horizon,
)
from q4.bundle import Q4Bundle
from q4.config import (
    LOAD_INFORMATION_CASE,
    Q4_3_STRATEGY,
    Q4_3_YEAR_END_BOUNDARY,
    Q4_3_YEAR_END_SOC_KWH,
    SETTLEMENT_RULE,
)
from q4.prices import day_ahead_as_of, day_ahead_today, remaining_price_forecast
from q4.q4_2 import planned_q_hash


def _index_to_update_hour(index: int) -> int | None:
    inverse = {first: hour for hour, first in HOUR_TO_FIRST_MUTABLE.items() if hour != 0}
    return inverse.get(index)


def _price_vector(bundle: Q4Bundle, day_index: int, tau: int) -> np.ndarray:
    forecast, _fb = remaining_price_forecast(bundle, day_index, tau)
    return forecast


def build_q4_3_value_cuts(
    bundle: Q4Bundle,
    current_index: int,
    issue_hour: int,
    next_day_terminal_soc: float | None,
    cache: dict | None,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    key = (int(current_index), int(issue_hour), None if next_day_terminal_soc is None else float(next_day_terminal_soc))
    if cache is not None and key in cache:
        return cache[key]
    next_index = current_index + 1
    if next_index >= bundle.n_days():
        cuts, rows = (), []
        if cache is not None:
            cache[key] = (cuts, rows)
        return cuts, rows
    load = causal_load_forecast(bundle.q3, next_index, current_index)
    pv = next_day_pv_forecast(bundle.q3, current_index, issue_hour, PV_MAPPING_LINEAR)
    price, price_src, chosen = day_ahead_as_of(bundle, next_index, current_index)

    # Reuse Q3's supporting-cut sampler by solving with the causal next-day price.
    from q3.config import NEXT_DAY_VALUE_GAP_TOL_YUAN, NEXT_DAY_VALUE_MAX_SAMPLES
    from math import inf

    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = solve_horizon(
            price,
            load,
            pv,
            float(soc),
            bill_as_day_ahead=True,
            throughput_tiebreak=False,
            terminal_soc=next_day_terminal_soc,
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
            raise AssertionError("Q4-3 next-day value subgradients are not monotone")
        gap, refine_soc = certified_max_gap(cuts)
        if gap <= NEXT_DAY_VALUE_GAP_TOL_YUAN:
            break
        if len(cuts) >= NEXT_DAY_VALUE_MAX_SAMPLES:
            raise AssertionError(
                f"Q4-3 next-day value gap {gap:.6f} exceeds tolerance after {len(cuts)} samples"
            )
        if min(abs(refine_soc - soc) for soc in solved) < 1e-7:
            raise AssertionError("Q4-3 next-day value refinement stalled")
        solve_at(refine_soc)
    date = bundle.prices.dates[current_index].strftime("%Y-%m-%d")
    rows = [
        {
            "current_date": date,
            "target_date": bundle.prices.dates[next_index].strftime("%Y-%m-%d"),
            "issue_hour": issue_hour,
            "price_source": price_src,
            "chosen_price_model": chosen,
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
        }
        for reference, value, slope in cuts
    ]
    if cache is not None:
        cache[key] = (cuts, rows)
    return cuts, rows


def plan_g0(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    year_end_soc_kwh: float | None = Q4_3_YEAR_END_SOC_KWH,
    value_cut_cache: dict | None = None,
    with_value_cuts: bool = True,
) -> np.ndarray:
    """Midnight g0 only (no intraday updates). Used by information-set probes."""
    data = bundle.q3
    n_days = len(data.dates)
    today_terminal = today_year_end_soc(day_index, n_days, year_end_soc_kwh)
    next_terminal = next_day_year_end_soc(day_index, n_days, year_end_soc_kwh)
    plan_load = planning_load_curve(data, day_index, LOAD_INFORMATION_MAIN)
    mapped0 = map_issue_forecast(data, day_index, 0, PV_MAPPING_LINEAR)
    price0, _src, _chosen = day_ahead_today(bundle, day_index)
    cuts = ()
    if with_value_cuts:
        cuts, _rows = build_q4_3_value_cuts(
            bundle, day_index, 0, next_terminal, value_cut_cache
        )
    midnight = solve_horizon(
        price0,
        plan_load,
        mapped0.today_kwh.copy(),
        initial_soc,
        bill_as_day_ahead=True,
        terminal_value_cuts=cuts or None,
        terminal_soc=today_terminal,
    )
    return midnight.g.copy()


@dataclass
class Q43DayResult:
    date: str
    day_index: int
    g0: np.ndarray
    g_final: np.ndarray
    dispatch: pd.DataFrame
    update_log: pd.DataFrame
    summary: dict
    value_rows: list[dict] = field(default_factory=list)


def run_q4_3_day(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    year_end_soc_kwh: float | None = Q4_3_YEAR_END_SOC_KWH,
    value_cut_cache: dict | None = None,
) -> Q43DayResult:
    data = bundle.q3
    date = data.dates[day_index].strftime("%Y-%m-%d")
    n_days = len(data.dates)
    today_terminal = today_year_end_soc(day_index, n_days, year_end_soc_kwh)
    next_terminal = next_day_year_end_soc(day_index, n_days, year_end_soc_kwh)
    allowed = STRATEGY_ALLOWED_UPDATES[Q4_3_STRATEGY]
    actual_load = data.load[day_index]
    plan_load = planning_load_curve(data, day_index, LOAD_INFORMATION_MAIN)
    actual_pv = data.pv[day_index]
    actual_p = bundle.prices.price[day_index]
    started = perf_counter()
    mapped0 = map_issue_forecast(data, day_index, 0, PV_MAPPING_LINEAR)
    current_forecast = mapped0.today_kwh.copy()
    price0, price_src, chosen = day_ahead_today(bundle, day_index)
    cuts, value_rows = build_q4_3_value_cuts(
        bundle, day_index, 0, next_terminal, value_cut_cache
    )
    midnight = solve_horizon(
        price0,
        plan_load,
        current_forecast,
        initial_soc,
        bill_as_day_ahead=True,
        terminal_value_cuts=cuts or None,
        terminal_soc=today_terminal,
    )
    g0 = midnight.g.copy()
    g = g0.copy()
    versions = [g0.copy()]
    last_update = "00:00"
    first_intraday = HOUR_TO_FIRST_MUTABLE[6]
    update_rows = [
        {
            "date": date,
            "update_time": "00:00",
            "first_mutable_index": 0,
            "voi_yuan": np.nan,
            "implemented": True,
            "l1_change_kwh": float(np.abs(g0).sum()),
            "price_source": price_src,
            "chosen_price_model": chosen,
            "affected_periods": "0:143",
            "prefix_lock_ok": True,
            "forecast_version": "day_ahead",
            "g_old_sha256": "",
            "g_new_sha256": planned_q_hash(g0),
        }
    ]

    def remaining_kwargs(t: int, price_rem: np.ndarray) -> dict:
        return {
            "settlement_mode": SETTLEMENT_MAIN,
            "terminal_value_cuts": cuts or None,
            "g0": g0[t:],
            "terminal_soc": today_terminal,
        }

    dispatch_rows = []
    soc = float(initial_soc)
    max_cd = 0.0
    max_balance = 0.0
    locked_violations = 0
    g_before_update = g.copy()

    for t in range(T):
        hour = _index_to_update_hour(t)
        if hour is not None and hour in allowed:
            g_before_update = g.copy()
            mapped = map_issue_forecast(data, day_index, hour, PV_MAPPING_LINEAR)
            current_forecast = mapped.today_kwh.copy()
            cuts, rows = build_q4_3_value_cuts(
                bundle, day_index, hour, next_terminal, value_cut_cache
            )
            value_rows.extend(rows)
            price_now, _fb = remaining_price_forecast(bundle, day_index, t)
            pv_plan = current_forecast[t:]
            load_plan = plan_load[t:]
            g_pre = g[t:].copy()
            settle_kw = remaining_kwargs(t, price_now[t:])
            j_fix = solve_horizon(
                price_now[t:],
                load_plan,
                pv_plan,
                soc,
                g_fixed=g_pre,
                **settle_kw,
            )
            j_free = solve_horizon(
                price_now[t:],
                load_plan,
                pv_plan,
                soc,
                **settle_kw,
            )
            voi = float(j_fix.objective - j_free.objective)
            implemented = bool(voi > VOI_EPS_YUAN)
            prefix_ok = bool(np.max(np.abs(g[:t] - g_before_update[:t])) <= NUMERIC_TOL)
            if implemented:
                g[t:] = j_free.g
                versions.append(g.copy())
            if not prefix_ok:
                locked_violations += 1
            delta = g[t:] - g_pre
            update_rows.append(
                {
                    "date": date,
                    "update_time": f"{hour:02d}:00",
                    "first_mutable_index": t,
                    "voi_yuan": voi,
                    "implemented": implemented,
                    "l1_change_kwh": float(np.abs(delta).sum()),
                    "price_source": "intraday_ols",
                    "chosen_price_model": chosen,
                    "affected_periods": f"{t}:{T - 1}",
                    "prefix_lock_ok": prefix_ok,
                    "forecast_version": f"tau_{t}",
                    "g_old_sha256": planned_q_hash(g_before_update),
                    "g_new_sha256": planned_q_hash(g),
                }
            )
            last_update = f"{hour:02d}:00"
            if np.max(np.abs(g[:t] - g_before_update[:t])) > NUMERIC_TOL:
                locked_violations += 1

        price_now, _fb = remaining_price_forecast(bundle, day_index, t)
        pv_horizon = current_forecast[t:].copy()
        pv_horizon[0] = actual_pv[t]
        load_horizon = execution_load_horizon(plan_load, actual_load, t)
        step = solve_horizon(
            price_now[t:],
            load_horizon,
            pv_horizon,
            soc,
            g_fixed=g[t:],
            **remaining_kwargs(t, price_now[t:]),
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
        max_cd = max(max_cd, float(step.charge[0] * step.discharge[0]))
        max_balance = max(max_balance, abs(float(residual)))
        dispatch_rows.append(
            {
                "date": date,
                "period_index": t,
                "time_label": data.time_labels[t],
                "q_or_g0_kwh": float(g0[t]),
                "g_final_kwh": float(g[t]),
                "x_kwh": float(step.x[0]),
                "emergency_kwh": float(step.emergency[0]),
                "charge_kwh": float(step.charge[0]),
                "discharge_kwh": float(step.discharge[0]),
                "curtailment_kwh": float(step.curtailment[0]),
                "soc_start_kwh": soc,
                "soc_end_kwh": soc_next,
                "actual_load_kwh": float(actual_load[t]),
                "actual_pv_kwh": float(actual_pv[t]),
                "actual_price": float(actual_p[t]),
                "price_forecast_used": float(price_now[t]),
                "last_update_time": last_update,
                "balance_residual_kwh": float(residual),
            }
        )
        if abs(g[t] - step.g[0]) > 1e-6:
            locked_violations += 1
        soc = soc_next

    dispatch = pd.DataFrame(dispatch_rows)
    g_final = g.copy()
    if np.max(np.abs(g_final[:first_intraday] - g0[:first_intraday])) > NUMERIC_TOL:
        locked_violations += 1
        raise AssertionError("Q4-3 6:00 prefix lock violated: gF[:36] differs from g0")
    phi = settlement_cost(actual_p, g0, g_final)
    emergency_cost = EMERGENCY_PRICE_MULTIPLIER * actual_p * dispatch["emergency_kwh"].to_numpy()
    dispatch["normal_cost_yuan"] = actual_p * g_final
    dispatch["adjustment_cost_yuan"] = phi - actual_p * g_final
    dispatch["emergency_cost_yuan"] = emergency_cost
    n_adjust = int(
        sum(1 for row in update_rows if row["update_time"] != "00:00" and row["implemented"])
    )
    summary = {
        "date": date,
        "day_index": day_index,
        "strategy": Q4_3_STRATEGY,
        "load_information_case": LOAD_INFORMATION_CASE,
        "year_end_boundary": Q4_3_YEAR_END_BOUNDARY,
        "year_end_soc_kwh": year_end_soc_kwh,
        "settlement_rule": SETTLEMENT_RULE,
        "normal_cost_yuan": float(np.sum(actual_p * g_final)),
        "adjustment_cost_yuan": float(np.sum(phi - actual_p * g_final)),
        "emergency_cost_yuan": float(np.sum(emergency_cost)),
        "total_cost_yuan": float(np.sum(phi) + np.sum(emergency_cost)),
        "g0_kwh": float(g0.sum()),
        "g_final_kwh": float(g_final.sum()),
        "emergency_kwh": float(dispatch["emergency_kwh"].sum()),
        "curtailment_kwh": float(dispatch["curtailment_kwh"].sum()),
        "soc_start_kwh": float(initial_soc),
        "soc_end_kwh": float(soc),
        "adjustment_count": n_adjust,
        "locked_period_violations": int(locked_violations),
        "max_balance_residual_kwh": float(max_balance),
        "max_simultaneous_cd_kwh2": float(max_cd),
        "runtime_seconds": float(perf_counter() - started),
        "max_x_minus_g_kwh": float(np.max(dispatch["x_kwh"].to_numpy() - g_final)),
        "pass": bool(
            max_balance < NUMERIC_TOL
            and locked_violations == 0
            and max_cd <= SIMULTANEOUS_CD_TOL
            and np.max(dispatch["x_kwh"].to_numpy() - g_final) < NUMERIC_TOL
            and dispatch["soc_end_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL
            and dispatch["soc_end_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL
        ),
    }
    return Q43DayResult(
        date=date,
        day_index=day_index,
        g0=g0,
        g_final=g_final,
        dispatch=dispatch,
        update_log=pd.DataFrame(update_rows),
        summary=summary,
        value_rows=value_rows,
    )
