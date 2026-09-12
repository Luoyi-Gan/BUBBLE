"""Q4-2: triple-scenario day-ahead q, locked all day, causal MPC execution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from math import inf, sqrt
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from q2.config import (
    E_MAX_KWH,
    E_MIN_KWH,
    EMERGENCY_PRICE_MULTIPLIER,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    NEXT_DAY_VALUE_MAX_SAMPLES,
    NUMERIC_TOL,
    SIMULTANEOUS_CD_TOL,
    T,
)
from q2.forecast import forecast_as_of
from q2.optimization import ValueCut, evaluate_value_cuts
from q2.pilot import risk_quantile_floor
from q4.bundle import Q4Bundle
from q4.config import (
    ALPHA_POLICY_LOOP,
    FIXED_SCENARIO_K,
    LOAD_INFORMATION_CASE,
    Q4_2_YEAR_END_RULE,
    RISK_ALPHA_CANDIDATES,
    RISK_CALIBRATION_DAYS,
    RISK_WARMUP_DAYS,
    SETTLEMENT_RULE,
)
from q4.optimization import solve_fixed_q_dispatch, solve_stochastic_plan_varying_price
from q4.prices import day_ahead_as_of, day_ahead_today, remaining_price_forecast
from q4.scenarios import (
    TripleScenarioSet,
    build_triple_scenarios,
    posterior_weights,
    residual_stack,
    scenario_paths,
)


def plan_locked_q(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    risk_alpha: float | None,
    k_target: int = FIXED_SCENARIO_K,
    with_value_cuts: bool = True,
) -> np.ndarray:
    """Day-ahead q only (no MPC). Used by information-set probes."""
    loads, pvs, prices, probs, _sc, base_load, base_pv, _src, _ch = q4_2_day_inputs(
        bundle, day_index, day_index, k_target
    )
    q_floor = risk_quantile_floor(loads, pvs, probs, base_load, base_pv, risk_alpha)
    cuts = ()
    if with_value_cuts:
        cuts, _ = build_q4_2_value_cuts(bundle, day_index, k_target, risk_alpha)
    plan = solve_stochastic_plan_varying_price(
        prices,
        loads,
        pvs,
        probs,
        initial_soc,
        terminal_value_cuts=cuts or None,
        q_floor=q_floor,
    )
    return plan.q.copy()


def planned_q_hash(q: np.ndarray) -> str:
    canonical = ",".join(f"{float(value):.9f}" for value in np.asarray(q).ravel())
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


@dataclass
class Q42DayResult:
    date: str
    day_index: int
    q: np.ndarray
    dispatch: pd.DataFrame
    summary: dict
    day_ahead_audit: dict
    scenario_rows: list[dict] = field(default_factory=list)
    value_rows: list[dict] = field(default_factory=list)


def _point_paths(load_hat: np.ndarray, pv_hat: np.ndarray, price_hat: np.ndarray):
    return load_hat[None, :], pv_hat[None, :], price_hat[None, :], np.ones(1)


def q4_2_day_inputs(
    bundle: Q4Bundle,
    day_index: int,
    history_end_exclusive: int,
    k_target: int = FIXED_SCENARIO_K,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, TripleScenarioSet | None, np.ndarray, np.ndarray, str, int]:
    load_hat, pv_hat, _ls, _ps = forecast_as_of(
        bundle.q2, day_index, history_end_exclusive
    )
    if history_end_exclusive == day_index:
        price_hat, price_src, chosen = day_ahead_today(bundle, day_index)
    else:
        price_hat, price_src, chosen = day_ahead_as_of(
            bundle, day_index, history_end_exclusive
        )
    scenarios = build_triple_scenarios(
        bundle, day_index, history_end_exclusive, k_target=k_target
    )
    if scenarios is None:
        loads, pvs, prices, probs = _point_paths(load_hat, pv_hat, price_hat)
    else:
        loads, pvs, prices = scenario_paths(
            bundle, scenarios, load_hat, pv_hat, price_hat
        )
        probs = scenarios.probabilities
    return loads, pvs, prices, probs, scenarios, load_hat, pv_hat, price_src, chosen


def build_q4_2_value_cuts(
    bundle: Q4Bundle,
    current_index: int,
    k_target: int,
    risk_alpha: float | None,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    next_index = current_index + 1
    if next_index >= bundle.n_days():
        return (), []
    loads, pvs, prices, probs, scenarios, base_load, base_pv, price_src, chosen = q4_2_day_inputs(
        bundle, next_index, current_index, k_target
    )
    q_floor = risk_quantile_floor(loads, pvs, probs, base_load, base_pv, risk_alpha)
    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = solve_stochastic_plan_varying_price(
            prices, loads, pvs, probs, float(soc), q_floor=q_floor
        )
        value = result.expected_normal_cost + result.expected_emergency_cost
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
            raise AssertionError("Q4-2 next-day value subgradients are not monotone")
        gap, refine_soc = certified_max_gap(cuts)
        if gap <= NEXT_DAY_VALUE_GAP_TOL_YUAN:
            break
        if len(cuts) >= NEXT_DAY_VALUE_MAX_SAMPLES:
            raise AssertionError(
                f"Q4-2 next-day value gap {gap:.6f} exceeds tolerance after {len(cuts)} samples"
            )
        if min(abs(refine_soc - soc) for soc in solved) < 1e-7:
            raise AssertionError("Q4-2 next-day value refinement stalled")
        solve_at(refine_soc)
    k_eff = 1 if scenarios is None else scenarios.k_effective
    rows = [
        {
            "current_date": bundle.prices.dates[current_index].strftime("%Y-%m-%d"),
            "target_date": bundle.prices.dates[next_index].strftime("%Y-%m-%d"),
            "k_effective": k_eff,
            "risk_alpha": risk_alpha,
            "price_source": price_src,
            "chosen_price_model": chosen,
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
        }
        for reference, value, slope in cuts
    ]
    return cuts, rows


@dataclass
class AlphaSelection:
    selected_alpha: float
    window_records: list[dict]
    daily_records: list[dict]


def calibration_window(target_index: int, n_validation: int | None = None) -> np.ndarray:
    n = RISK_CALIBRATION_DAYS if n_validation is None else int(n_validation)
    if n <= 0 or target_index <= 0:
        return np.zeros(0, dtype=int)
    return np.arange(max(0, target_index - n), target_index, dtype=int)


def q2_aligned_calibration_indices(n_days: int) -> list[int]:
    """Q2 14-day blocks after the 28-day warmup: 28, 42, ..., up to the last complete index."""
    return [
        i
        for i in range(RISK_WARMUP_DAYS, n_days)
        if i % RISK_CALIBRATION_DAYS == 0
    ]


def _metrics_from_day(result: Q42DayResult, elapsed_seconds: float) -> dict:
    q = np.asarray(result.q, dtype=float)
    x = result.dispatch["x_kwh"].to_numpy(float)
    soc_end = result.dispatch["soc_end_kwh"].to_numpy(float)
    gap = (
        float(result.value_rows[0]["certified_max_gap_yuan"])
        if result.value_rows
        else float("nan")
    )
    return {
        "date": result.date,
        "day_index": int(result.day_index),
        "planned_fee_yuan": float(result.summary["normal_cost_yuan"]),
        "emergency_fee_yuan": float(result.summary["emergency_cost_yuan"]),
        "total_cost_yuan": float(result.summary["total_cost_yuan"]),
        "unused_quota_kwh": float(np.sum(q - x)),
        "emergency_kwh": float(result.summary["emergency_kwh"]),
        "soc_start_kwh": float(result.summary["soc_start_kwh"]),
        "soc_end_kwh": float(result.summary["soc_end_kwh"]),
        "soc_min_kwh": float(soc_end.min()),
        "soc_max_kwh": float(soc_end.max()),
        "soc_end_path_kwh": ";".join(f"{value:.6f}" for value in soc_end),
        "has_value_cuts": bool(result.value_rows),
        "n_value_cuts": int(len(result.value_rows)),
        "value_cut_gap_yuan": gap,
        "value_cuts_used": bool(result.value_rows),
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "k_effective": int(result.summary["k_effective"]),
        "elapsed_seconds": float(elapsed_seconds),
        "policy_loop": ALPHA_POLICY_LOOP,
    }


def run_candidate_window(
    bundle: Q4Bundle,
    policy_start_soc: np.ndarray,
    target_index: int,
    *,
    risk_alpha: float | None,
    k_target: int = FIXED_SCENARIO_K,
    n_validation: int | None = None,
    log_prefix: str | None = None,
) -> tuple[list[dict], dict]:
    """Replay prior completed days with the official Q4-2 closed loop.

    Each candidate carries its own SOC. The window opens at the deployed
    policy's recorded start SOC on the first validation day. Full-day actual
    path dispatch is not used.
    """
    validation = calibration_window(target_index, n_validation)
    empty = {
        "risk_alpha": None if risk_alpha is None else float(risk_alpha),
        "k_target": int(k_target),
        "validation_days": 0,
        "mean_validation_cost_yuan": np.nan,
        "standard_error_yuan": np.nan,
        "total_planned_fee_yuan": np.nan,
        "total_emergency_fee_yuan": np.nan,
        "total_cost_yuan": np.nan,
        "total_unused_quota_kwh": np.nan,
        "emergency_purchase_kwh": np.nan,
        "soc_window_start_kwh": np.nan,
        "soc_window_end_kwh": np.nan,
        "daily_soc_end_path_kwh": "",
        "all_value_cuts_present": False,
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "mean_elapsed_seconds": np.nan,
        "mean_solve_seconds": np.nan,
        "policy_loop": ALPHA_POLICY_LOOP,
        "fallback_reason": "empty_validation_window",
    }
    if len(validation) == 0:
        return [], empty
    soc = float(policy_start_soc[int(validation[0])])
    if not np.isfinite(soc):
        empty["fallback_reason"] = "no_validation_soc"
        return [], empty
    daily: list[dict] = []
    for offset, day_index in enumerate(validation):
        started = perf_counter()
        result = run_q4_2_day(
            bundle, int(day_index), soc, risk_alpha, k_target=k_target
        )
        elapsed = perf_counter() - started
        row = _metrics_from_day(result, elapsed)
        row["risk_alpha"] = None if risk_alpha is None else float(risk_alpha)
        row["k_target"] = int(k_target)
        row["calibration_day_index"] = int(target_index)
        daily.append(row)
        soc = float(result.summary["soc_end_kwh"])
        if log_prefix:
            print(
                f"{log_prefix} [{offset + 1}/{len(validation)}] {result.date} "
                f"cost={row['total_cost_yuan']:.2f} soc={soc:.2f}",
                flush=True,
            )
        del result
    costs = np.asarray([row["total_cost_yuan"] for row in daily], dtype=float)
    summary = {
        "risk_alpha": None if risk_alpha is None else float(risk_alpha),
        "k_target": int(k_target),
        "validation_days": int(len(daily)),
        "mean_validation_cost_yuan": float(np.mean(costs)),
        "standard_error_yuan": float(
            np.std(costs, ddof=1) / sqrt(len(costs)) if len(costs) > 1 else 0.0
        ),
        "total_planned_fee_yuan": float(sum(row["planned_fee_yuan"] for row in daily)),
        "total_emergency_fee_yuan": float(
            sum(row["emergency_fee_yuan"] for row in daily)
        ),
        "total_cost_yuan": float(np.sum(costs)),
        "total_unused_quota_kwh": float(
            sum(row["unused_quota_kwh"] for row in daily)
        ),
        "emergency_purchase_kwh": float(sum(row["emergency_kwh"] for row in daily)),
        "soc_window_start_kwh": float(daily[0]["soc_start_kwh"]),
        "soc_window_end_kwh": float(daily[-1]["soc_end_kwh"]),
        "daily_soc_end_path_kwh": ";".join(
            f"{row['soc_end_kwh']:.6f}" for row in daily
        ),
        "all_value_cuts_present": bool(all(row["has_value_cuts"] for row in daily)),
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "mean_elapsed_seconds": float(np.mean([row["elapsed_seconds"] for row in daily])),
        "mean_solve_seconds": float(np.mean([row["elapsed_seconds"] for row in daily])),
        "policy_loop": ALPHA_POLICY_LOOP,
        "fallback_reason": "",
    }
    return daily, summary


def select_risk_alpha(
    bundle: Q4Bundle,
    policy_start_soc: np.ndarray,
    target_index: int,
    k_target: int,
    n_validation: int | None = None,
    alphas: tuple[float, ...] | None = None,
    log: bool = False,
) -> AlphaSelection:
    """Score each α on the prior completed days with the official Q4-2 loop."""
    candidates = RISK_ALPHA_CANDIDATES if alphas is None else tuple(alphas)
    records: list[dict] = []
    daily_records: list[dict] = []
    for alpha in candidates:
        prefix = (
            f"Q4-2 alpha-cal d={target_index} α={float(alpha):.2f}" if log else None
        )
        daily, summary = run_candidate_window(
            bundle,
            policy_start_soc,
            target_index,
            risk_alpha=float(alpha),
            k_target=k_target,
            n_validation=n_validation,
            log_prefix=prefix,
        )
        summary["selected"] = False
        records.append(summary)
        daily_records.extend(daily)
    eligible = [row for row in records if np.isfinite(row["mean_validation_cost_yuan"])]
    selected = min(
        eligible or records,
        key=lambda row: (
            row["mean_validation_cost_yuan"]
            if np.isfinite(row["mean_validation_cost_yuan"])
            else inf,
            row["risk_alpha"] if row["risk_alpha"] is not None else inf,
        ),
    )
    selected["selected"] = True
    chosen = float(selected["risk_alpha"])
    for row in daily_records:
        row["selected"] = bool(
            row["risk_alpha"] is not None and abs(float(row["risk_alpha"]) - chosen) < 1e-12
        )
    return AlphaSelection(chosen, records, daily_records)


def run_q4_2_day(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    risk_alpha: float | None,
    k_target: int = FIXED_SCENARIO_K,
    write_dispatch: Path | None = None,
) -> Q42DayResult:
    started = perf_counter()
    date = bundle.prices.dates[day_index].strftime("%Y-%m-%d")
    loads, pvs, prices, probs, scenarios, base_load, base_pv, price_src, chosen = q4_2_day_inputs(
        bundle, day_index, day_index, k_target
    )
    q_floor = risk_quantile_floor(loads, pvs, probs, base_load, base_pv, risk_alpha)
    cuts, value_rows = build_q4_2_value_cuts(bundle, day_index, k_target, risk_alpha)
    plan = solve_stochastic_plan_varying_price(
        prices,
        loads,
        pvs,
        probs,
        initial_soc,
        terminal_value_cuts=cuts or None,
        q_floor=q_floor,
    )
    locked_q = plan.q.copy()
    q_hash = planned_q_hash(locked_q)
    actual_p = bundle.prices.price[day_index]
    actual_load = bundle.q2.load[day_index]
    actual_pv = bundle.q2.pv[day_index]
    day_ahead, _, _ = day_ahead_today(bundle, day_index)
    rows = []
    soc = float(initial_soc)
    max_cd = 0.0
    k_eff = 1 if scenarios is None else scenarios.k_effective
    for t in range(T):
        price_hat_tau, ols_fb = remaining_price_forecast(bundle, day_index, t)
        if scenarios is None:
            weights = np.ones(1)
            bandwidth = np.nan
            load_horizon = base_load[t:].copy()
            pv_horizon = base_pv[t:].copy()
            price_horizon = price_hat_tau[t:].copy()
        else:
            if t == 0:
                obs_l = np.zeros(0)
                obs_p = np.zeros(0)
                obs_r = np.zeros(0)
            else:
                # Ended prefix only; do not form a full-day residual against today's future actuals.
                obs_l = actual_load[:t] - base_load[:t]
                obs_p = actual_pv[:t] - base_pv[:t]
                obs_r = actual_p[:t] - day_ahead[:t]
            weights, bandwidth = posterior_weights(
                bundle, scenarios, obs_l, obs_p, obs_r
            )
            med_l, med_p, med_r = residual_stack(bundle, scenarios.medoid_indices)
            load_horizon = np.maximum(0.0, base_load[t:] + weights @ med_l[:, t:])
            pv_horizon = np.maximum(0.0, base_pv[t:] + weights @ med_p[:, t:])
            price_horizon = np.maximum(0.0, price_hat_tau[t:] + weights @ med_r[:, t:])
        load_horizon[0] = actual_load[t]
        pv_horizon[0] = actual_pv[t]
        step = solve_fixed_q_dispatch(
            price_horizon,
            locked_q[t:],
            load_horizon,
            pv_horizon,
            soc,
            terminal_value_cuts=cuts or None,
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
        rows.append(
            {
                "date": date,
                "period_index": t,
                "time_label": bundle.q3.time_labels[t],
                "q_or_g0_kwh": float(locked_q[t]),
                "g_final_kwh": np.nan,
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
                "price_forecast_used": float(price_horizon[0]),
                "last_update_time": "00:00",
                "balance_residual_kwh": float(residual),
                "ols_fallback": bool(ols_fb),
            }
        )
        max_cd = max(max_cd, float(step.charge[0] * step.discharge[0]))
        if np.max(np.abs(locked_q - plan.q)) > 0:
            raise AssertionError("Q4-2 q changed during the day")
        soc = soc_next
    if planned_q_hash(locked_q) != q_hash:
        raise AssertionError("Q4-2 q hash changed")
    dispatch = pd.DataFrame(rows)
    if write_dispatch is not None:
        write_dispatch.parent.mkdir(parents=True, exist_ok=True)
        dispatch.to_csv(write_dispatch, index=False)
    normal_cost = float(actual_p @ locked_q)
    emergency_cost = float(
        EMERGENCY_PRICE_MULTIPLIER * actual_p @ dispatch["emergency_kwh"].to_numpy()
    )
    scenario_rows = []
    if scenarios is not None:
        for cluster, medoid in enumerate(scenarios.medoid_indices):
            scenario_rows.append(
                {
                    "date": date,
                    "cluster": int(cluster),
                    "medoid_date": bundle.prices.dates[medoid].strftime("%Y-%m-%d"),
                    "medoid_index": int(medoid),
                    "probability": float(scenarios.probabilities[cluster]),
                    "cluster_size": int(np.sum(scenarios.cluster_labels == cluster)),
                    "pool_start": bundle.prices.dates[scenarios.pool_indices[0]].strftime("%Y-%m-%d"),
                    "pool_end": bundle.prices.dates[scenarios.pool_indices[-1]].strftime("%Y-%m-%d"),
                    "k_effective": int(scenarios.k_effective),
                    "scale_load": float(scenarios.scale_load),
                    "scale_pv": float(scenarios.scale_pv),
                    "scale_price": float(scenarios.scale_price),
                }
            )
    day_ahead_audit = {
        "date": date,
        "day_index": day_index,
        "history_cutoff_date": (
            bundle.prices.dates[day_index - 1].strftime("%Y-%m-%d") if day_index else ""
        ),
        "k_target": k_target,
        "k_effective": k_eff,
        "risk_alpha": risk_alpha,
        "risk_q_floor_kwh": float(np.sum(q_floor)),
        "price_source": price_src,
        "chosen_price_model": chosen,
        "planned_q_kwh": float(locked_q.sum()),
        "planned_q_sha256": q_hash,
        "n_scenarios": int(len(probs)),
        "load_information_case": LOAD_INFORMATION_CASE,
        "year_end_rule": Q4_2_YEAR_END_RULE,
        "settlement_rule": SETTLEMENT_RULE,
    }
    summary = {
        "date": date,
        "day_index": day_index,
        "load_information_case": LOAD_INFORMATION_CASE,
        "year_end_rule": Q4_2_YEAR_END_RULE,
        "settlement_rule": SETTLEMENT_RULE,
        "k_effective": k_eff,
        "risk_alpha": risk_alpha,
        "normal_cost_yuan": normal_cost,
        "adjustment_cost_yuan": 0.0,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": normal_cost + emergency_cost,
        "planned_q_kwh": float(locked_q.sum()),
        "actual_x_kwh": float(dispatch["x_kwh"].sum()),
        "emergency_kwh": float(dispatch["emergency_kwh"].sum()),
        "curtailment_kwh": float(dispatch["curtailment_kwh"].sum()),
        "soc_start_kwh": float(initial_soc),
        "soc_end_kwh": float(soc),
        "unused_quota_kwh": float(np.sum(locked_q - dispatch["x_kwh"].to_numpy(float))),
        "has_value_cuts": bool(value_rows),
        "n_value_cuts": int(len(value_rows)),
        "value_cut_gap_yuan": (
            float(value_rows[0]["certified_max_gap_yuan"]) if value_rows else float("nan")
        ),
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "elapsed_seconds": float(perf_counter() - started),
        "max_balance_residual_kwh": float(dispatch["balance_residual_kwh"].abs().max()),
        "max_simultaneous_cd_kwh2": max_cd,
        "max_x_minus_q_kwh": float(np.max(dispatch["x_kwh"].to_numpy() - locked_q)),
        "q_unchanged": True,
        "pass": bool(
            dispatch["balance_residual_kwh"].abs().max() < NUMERIC_TOL
            and np.max(dispatch["x_kwh"].to_numpy() - locked_q) < NUMERIC_TOL
            and dispatch["soc_end_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL
            and dispatch["soc_end_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL
            and max_cd <= SIMULTANEOUS_CD_TOL
        ),
    }
    return Q42DayResult(
        date=date,
        day_index=day_index,
        q=locked_q,
        dispatch=dispatch,
        summary=summary,
        day_ahead_audit=day_ahead_audit,
        scenario_rows=scenario_rows,
        value_rows=value_rows,
    )


def alpha_for_day(day_index: int, calibrated: dict[int, float | None]) -> float | None:
    if day_index < RISK_WARMUP_DAYS:
        return None
    start = (day_index // RISK_CALIBRATION_DAYS) * RISK_CALIBRATION_DAYS
    return calibrated.get(start, None)
