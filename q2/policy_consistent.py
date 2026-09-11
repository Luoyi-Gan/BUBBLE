"""Policy-consistent Q2 redesign: baseline forecast LP + K=8 reserve + residual MPC.

This module is independent of the signed-off stochastic day-ahead production path.
K-medoids enter only through the risk reserve R(alpha) and intra-day residual weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import (
    EMERGENCY_PRICE_MULTIPLIER,
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    FIXED_SCENARIO_K,
    LOAD_HISTORY_SAME_WEEKDAY,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    NEXT_DAY_VALUE_MAX_SAMPLES,
    NUMERIC_TOL,
    POWER_LIMIT_KWH,
    PV_HISTORY_DAYS,
    RISK_ALPHA_CANDIDATES,
    SIMULTANEOUS_CD_TOL,
    T,
)
from q2.data import Q2Data
from q2.forecast import ForecastArchive
from q2.optimization import (
    BaselinePlanResult,
    ValueCut,
    evaluate_value_cuts,
    solve_baseline_plan,
    solve_fixed_plan_dispatch,
)
from q2.pilot import planned_q_hash, risk_quantile_floor
from q2.scenarios import (
    ScenarioSet,
    build_scenarios,
    posterior_weights,
)


class ForecastMode(str, Enum):
    M1 = "m1"
    M2 = "m2"
    M3 = "m3"


FORECAST_MODES: tuple[ForecastMode, ...] = (
    ForecastMode.M1,
    ForecastMode.M2,
    ForecastMode.M3,
)
R1_DEFAULT_MODE = ForecastMode.M1
R1_DEFAULT_ALPHA = 0.60


@dataclass(frozen=True)
class DayForecast:
    mode: ForecastMode
    load_hat: np.ndarray
    pv_hat: np.ndarray
    load_sources: tuple[int, ...]
    pv_sources: tuple[int, ...]
    load_fallback: bool
    pv_fallback: bool


def _aggregate_rows(rows: np.ndarray, mode: ForecastMode) -> np.ndarray:
    if rows.ndim != 2 or rows.shape[0] == 0:
        raise ValueError("forecast aggregation requires at least one history row")
    if mode is ForecastMode.M1:
        return rows.mean(axis=0)
    if mode is ForecastMode.M2:
        return np.median(rows, axis=0)
    if mode is ForecastMode.M3:
        weights = np.arange(1, rows.shape[0] + 1, dtype=float)
        weights /= weights.sum()
        return weights @ rows
    raise ValueError(f"unknown forecast mode: {mode}")


def forecast_as_of_mode(
    data: Q2Data,
    target_index: int,
    history_end_exclusive: int,
    mode: ForecastMode,
) -> DayForecast:
    if not 0 <= history_end_exclusive <= target_index:
        raise ValueError("forecast cutoff must not exceed target date")
    target = data.dates[target_index]
    same_weekday = [
        j
        for j in range(history_end_exclusive)
        if data.dates[j].weekday() == target.weekday()
    ]
    load_sources = tuple(same_weekday[-LOAD_HISTORY_SAME_WEEKDAY:])
    pv_sources = tuple(
        range(max(0, history_end_exclusive - PV_HISTORY_DAYS), history_end_exclusive)
    )
    if load_sources:
        load_hat = _aggregate_rows(data.load[list(load_sources)], mode)
        load_fallback = False
    else:
        load_hat = data.fallback_load.copy()
        load_fallback = True
    if pv_sources:
        pv_hat = _aggregate_rows(data.pv[list(pv_sources)], mode)
        pv_fallback = False
    else:
        pv_hat = data.fallback_pv.copy()
        pv_fallback = True
    return DayForecast(
        mode=mode,
        load_hat=np.maximum(0.0, load_hat),
        pv_hat=np.maximum(0.0, pv_hat),
        load_sources=load_sources,
        pv_sources=pv_sources,
        load_fallback=load_fallback,
        pv_fallback=pv_fallback,
    )


def build_forecast_archive_mode(data: Q2Data, mode: ForecastMode) -> ForecastArchive:
    n = len(data.dates)
    load_hat = np.empty_like(data.load)
    pv_hat = np.empty_like(data.pv)
    load_sources: list[tuple[int, ...]] = []
    pv_sources: list[tuple[int, ...]] = []
    for i in range(n):
        forecast = forecast_as_of_mode(data, i, i, mode)
        load_hat[i] = forecast.load_hat
        pv_hat[i] = forecast.pv_hat
        load_sources.append(forecast.load_sources)
        pv_sources.append(forecast.pv_sources)
    return ForecastArchive(
        load_hat=load_hat,
        pv_hat=pv_hat,
        load_residual=data.load - load_hat,
        pv_residual=data.pv - pv_hat,
        load_sources=tuple(load_sources),
        pv_sources=tuple(pv_sources),
    )


def assert_history_strictly_prior(
    indices: tuple[int, ...] | np.ndarray, decision_index: int, label: str
) -> None:
    values = np.asarray(indices, dtype=int).ravel()
    if values.size and np.any(values >= decision_index):
        raise AssertionError(f"{label} leaks into decision index {decision_index}")


def k8_scenarios(
    target_index: int,
    data: Q2Data,
    archive: ForecastArchive,
    history_end_exclusive: int | None = None,
    k: int = FIXED_SCENARIO_K,
) -> ScenarioSet | None:
    history_end = target_index if history_end_exclusive is None else history_end_exclusive
    if history_end <= 0:
        return None
    scenarios = build_scenarios(
        target_index,
        data,
        archive,
        min(k, history_end),
        history_end_exclusive=history_end,
    )
    assert_history_strictly_prior(
        scenarios.pool_indices, target_index, "residual pool"
    )
    assert_history_strictly_prior(
        scenarios.medoid_indices, target_index, "medoid dates"
    )
    return scenarios


def risk_reserve_from_scenarios(
    scenarios: ScenarioSet | None,
    archive: ForecastArchive,
    load_hat: np.ndarray,
    pv_hat: np.ndarray,
    alpha: float | None,
) -> np.ndarray:
    if scenarios is None or alpha is None:
        return np.zeros(T)
    loads = np.maximum(
        0.0, load_hat[None, :] + archive.load_residual[scenarios.medoid_indices]
    )
    pvs = np.maximum(
        0.0, pv_hat[None, :] + archive.pv_residual[scenarios.medoid_indices]
    )
    return risk_quantile_floor(
        loads, pvs, scenarios.probabilities, load_hat, pv_hat, alpha
    )


def build_baseline_value_cuts(
    data: Q2Data,
    archive: ForecastArchive,
    current_index: int,
    mode: ForecastMode,
    k: int = FIXED_SCENARIO_K,
    risk_alpha: float | None = R1_DEFAULT_ALPHA,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    if current_index + 1 >= len(data.dates):
        return (), []
    nxt = current_index + 1
    forecast = forecast_as_of_mode(data, nxt, current_index, mode)
    assert_history_strictly_prior(forecast.load_sources, nxt, "next-day load forecast")
    assert_history_strictly_prior(forecast.pv_sources, nxt, "next-day PV forecast")
    scenarios = k8_scenarios(nxt, data, archive, current_index, k=k)
    q_floor = risk_reserve_from_scenarios(
        scenarios, archive, forecast.load_hat, forecast.pv_hat, risk_alpha
    )
    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = solve_baseline_plan(
            data.price, forecast.load_hat, forecast.pv_hat, float(soc), q_floor=q_floor
        )
        if result.has_scenario_specific_battery:
            raise AssertionError("next-day baseline LP created scenario battery variables")
        value = result.planned_cost + result.expected_emergency_cost
        solved[float(soc)] = (
            float(soc),
            float(value),
            float(result.initial_soc_marginal),
        )

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
            for a in range(len(lower_lines)):
                for b in range(a + 1, len(lower_lines)):
                    slope_a, intercept_a = lower_lines[a]
                    slope_b, intercept_b = lower_lines[b]
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
    gap = 0.0
    while True:
        cuts = tuple(solved[soc] for soc in sorted(solved))
        slopes = np.array([cut[2] for cut in cuts])
        if np.any(np.diff(slopes) < -1e-6):
            raise AssertionError("baseline next-day value subgradients are not monotone")
        gap, refine_soc = certified_max_gap(cuts)
        if gap <= NEXT_DAY_VALUE_GAP_TOL_YUAN:
            break
        if len(cuts) >= NEXT_DAY_VALUE_MAX_SAMPLES:
            raise AssertionError(
                f"baseline next-day value gap {gap:.6f} exceeds tolerance after {len(cuts)} samples"
            )
        if min(abs(refine_soc - soc) for soc in solved) < 1e-7:
            raise AssertionError("baseline next-day value refinement stalled")
        solve_at(refine_soc)

    rows = [
        {
            "target_date": data.dates[nxt].strftime("%Y-%m-%d"),
            "history_cutoff_date": data.dates[current_index].strftime("%Y-%m-%d"),
            "forecast_mode": mode.value,
            "risk_alpha": risk_alpha,
            "risk_q_floor_kwh": float(q_floor.sum()),
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
            "gap_tolerance_yuan": NEXT_DAY_VALUE_GAP_TOL_YUAN,
            "bundle_sample_count": len(cuts),
        }
        for reference, value, slope in cuts
    ]
    return cuts, rows


def _horizon_forecasts(
    data: Q2Data,
    archive: ForecastArchive,
    scenarios: ScenarioSet | None,
    load_hat: np.ndarray,
    pv_hat: np.ndarray,
    day_index: int,
    period: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    remaining = slice(period, T)
    if scenarios is None:
        weights = np.ones(1)
        bandwidth = float("nan")
        load_horizon = load_hat[remaining].copy()
        pv_horizon = pv_hat[remaining].copy()
    else:
        observed_lr = data.load[day_index, : period + 1] - load_hat[: period + 1]
        observed_pr = data.pv[day_index, : period + 1] - pv_hat[: period + 1]
        weights, bandwidth = posterior_weights(
            scenarios, archive, observed_lr, observed_pr
        )
        load_horizon = np.maximum(
            0.0,
            load_hat[remaining]
            + weights @ archive.load_residual[scenarios.medoid_indices, remaining],
        )
        pv_horizon = np.maximum(
            0.0,
            pv_hat[remaining]
            + weights @ archive.pv_residual[scenarios.medoid_indices, remaining],
        )
    load_horizon[0] = data.load[day_index, period]
    pv_horizon[0] = data.pv[day_index, period]
    return load_horizon, pv_horizon, weights, bandwidth


def run_residual_mpc(
    data: Q2Data,
    archive: ForecastArchive,
    scenarios: ScenarioSet | None,
    load_hat: np.ndarray,
    pv_hat: np.ndarray,
    locked_q: np.ndarray,
    initial_soc: float,
    day_index: int,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    path: Path | None = None,
    mpc_periods: int | None = None,
) -> tuple[dict, pd.DataFrame]:
    locked_q = np.asarray(locked_q, dtype=float).ravel()
    locked_hash = planned_q_hash(locked_q)
    rows = []
    soc = float(initial_soc)
    max_cd = 0.0
    n_steps = T if mpc_periods is None else int(mpc_periods)
    if not 1 <= n_steps <= T:
        raise ValueError("mpc_periods must lie in 1..T")
    for t in range(n_steps):
        load_horizon, pv_horizon, weights, bandwidth = _horizon_forecasts(
            data, archive, scenarios, load_hat, pv_hat, day_index, t
        )
        result = solve_fixed_plan_dispatch(
            data.price[t:],
            locked_q[t:],
            load_horizon,
            pv_horizon,
            soc,
            terminal_value_cuts=terminal_value_cuts,
        )
        residual = (
            result.x[0]
            + result.emergency[0]
            + data.pv[day_index, t]
            - result.curtailment[0]
            + result.discharge[0]
            - data.load[day_index, t]
            - result.charge[0]
        )
        entropy = float(-np.sum(weights * np.log(np.maximum(weights, 1e-300))))
        rows.append(
            {
                "date": data.dates[day_index].strftime("%Y-%m-%d"),
                "period": t,
                "time": data.time_labels[t],
                "planned_q_kwh": locked_q[t],
                "actual_x_kwh": result.x[0],
                "load_kwh": data.load[day_index, t],
                "pv_kwh": data.pv[day_index, t],
                "charge_kwh": result.charge[0],
                "discharge_kwh": result.discharge[0],
                "curtailment_kwh": result.curtailment[0],
                "emergency_kwh": result.emergency[0],
                "soc_kwh": result.soc[1],
                "posterior_entropy": entropy,
                "posterior_bandwidth": bandwidth,
                "solve_seconds": result.solve_seconds,
                "virtual_next_day_value_yuan": result.terminal_value,
                "balance_residual_kwh": residual,
            }
        )
        max_cd = max(max_cd, float(result.charge[0] * result.discharge[0]))
        soc = float(result.soc[1])
        if planned_q_hash(locked_q) != locked_hash:
            raise AssertionError("locked day-ahead q changed during MPC")
    frame = pd.DataFrame(rows)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
    x = frame["actual_x_kwh"].to_numpy()
    emergency = frame["emergency_kwh"].to_numpy()
    executed_q = locked_q[:n_steps]
    executed_price = data.price[:n_steps]
    planned_cost = float(executed_price @ executed_q)
    emergency_cost = float(EMERGENCY_PRICE_MULTIPLIER * executed_price @ emergency)
    physical_ok = bool(
        frame["balance_residual_kwh"].abs().max() < NUMERIC_TOL
        and np.max(x - executed_q) < NUMERIC_TOL
        and frame["soc_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL
        and frame["soc_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL
        and max_cd <= SIMULTANEOUS_CD_TOL
        and np.max(frame["charge_kwh"].to_numpy()) <= POWER_LIMIT_KWH + NUMERIC_TOL
        and np.max(frame["discharge_kwh"].to_numpy()) <= POWER_LIMIT_KWH + NUMERIC_TOL
    )
    summary = {
        "date": data.dates[day_index].strftime("%Y-%m-%d"),
        "planned_cost_yuan": planned_cost,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": planned_cost + emergency_cost,
        "planned_q_kwh": float(executed_q.sum()),
        "planned_q_sha256": locked_hash,
        "actual_x_kwh": float(x.sum()),
        "unused_plan_kwh": float((executed_q - x).sum()),
        "emergency_kwh": float(emergency.sum()),
        "curtailment_kwh": float(frame["curtailment_kwh"].sum()),
        "soc_start_kwh": float(initial_soc),
        "soc_end_kwh": soc,
        "max_balance_residual_kwh": float(frame["balance_residual_kwh"].abs().max()),
        "max_simultaneous_cd_kwh2": max_cd,
        "max_x_minus_q_kwh": float(np.max(x - executed_q)),
        "mean_mpc_solve_seconds": float(frame["solve_seconds"].mean()),
        "total_mpc_solve_seconds": float(frame["solve_seconds"].sum()),
        "pass": physical_ok,
        "used_full_day_actual_lp": False,
        "future_actuals_in_optimizer": False,
    }
    return summary, frame


def plan_closed_loop_day(
    data: Q2Data,
    archive: ForecastArchive,
    day_index: int,
    initial_soc: float,
    mode: ForecastMode = R1_DEFAULT_MODE,
    risk_alpha: float | None = R1_DEFAULT_ALPHA,
    k: int = FIXED_SCENARIO_K,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    dispatch_path: Path | None = None,
    mpc_periods: int | None = None,
) -> tuple[dict, pd.DataFrame, BaselinePlanResult, np.ndarray, ScenarioSet | None]:
    forecast = forecast_as_of_mode(data, day_index, day_index, mode)
    assert_history_strictly_prior(forecast.load_sources, day_index, "load forecast")
    assert_history_strictly_prior(forecast.pv_sources, day_index, "PV forecast")
    scenarios = k8_scenarios(day_index, data, archive, day_index, k=k)
    q_floor = risk_reserve_from_scenarios(
        scenarios, archive, forecast.load_hat, forecast.pv_hat, risk_alpha
    )
    plan = solve_baseline_plan(
        data.price,
        forecast.load_hat,
        forecast.pv_hat,
        initial_soc,
        q_floor=q_floor,
        terminal_value_cuts=terminal_value_cuts,
    )
    if plan.has_scenario_specific_battery:
        raise AssertionError("day-ahead baseline LP created scenario battery variables")
    for name, shape in plan.variable_shapes.items():
        if name in {"charge", "discharge", "soc"} and shape not in {(T,), (T + 1,)}:
            raise AssertionError(f"unexpected {name} shape {shape}")
    summary, frame = run_residual_mpc(
        data,
        archive,
        scenarios,
        forecast.load_hat,
        forecast.pv_hat,
        plan.q,
        initial_soc,
        day_index,
        terminal_value_cuts=terminal_value_cuts,
        path=dispatch_path,
        mpc_periods=mpc_periods,
    )
    summary.update(
        {
            "forecast_mode": mode.value,
            "risk_alpha": risk_alpha,
            "scenario_k": 0 if scenarios is None else int(len(scenarios.probabilities)),
            "risk_q_floor_kwh": float(q_floor.sum()),
            "load_fallback": forecast.load_fallback,
            "pv_fallback": forecast.pv_fallback,
            "load_source_dates": ";".join(
                data.dates[j].strftime("%Y-%m-%d") for j in forecast.load_sources
            )
            or "attachment1_fallback",
            "pv_source_dates": ";".join(
                data.dates[j].strftime("%Y-%m-%d") for j in forecast.pv_sources
            )
            or "attachment1_fallback",
            "residual_pool_end_date": (
                data.dates[scenarios.pool_indices[-1]].strftime("%Y-%m-%d")
                if scenarios is not None
                else "none"
            ),
            "medoid_dates": (
                ";".join(
                    data.dates[j].strftime("%Y-%m-%d") for j in scenarios.medoid_indices
                )
                if scenarios is not None
                else "none"
            ),
            "day_ahead_variable_shapes": {
                name: list(shape) for name, shape in plan.variable_shapes.items()
            },
            "has_scenario_specific_battery": plan.has_scenario_specific_battery,
            "day_ahead_solve_seconds": plan.solve_seconds,
            "day_ahead_expected_emergency_cost_yuan": plan.expected_emergency_cost,
            "day_ahead_virtual_next_day_value_yuan": plan.expected_terminal_value,
        }
    )
    return summary, frame, plan, q_floor, scenarios


def forecast_mae(actual: np.ndarray, hat: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - hat)))


def target_quantile_coverage(
    realised_net: np.ndarray,
    scenario_net: np.ndarray,
    probabilities: np.ndarray,
    alpha: float,
) -> float:
    hits = []
    for t in range(len(realised_net)):
        order = np.argsort(scenario_net[:, t])
        cumulative = np.cumsum(probabilities[order])
        threshold = scenario_net[order][np.searchsorted(cumulative, alpha, side="left")]
        hits.append(realised_net[t] <= threshold + 1e-12)
    return float(np.mean(hits))


def mode_diagnostics(
    data: Q2Data,
    day_index: int,
    archives: dict[ForecastMode, ForecastArchive],
    alpha: float,
    k: int = FIXED_SCENARIO_K,
) -> list[dict]:
    rows = []
    for mode, archive in archives.items():
        forecast = forecast_as_of_mode(data, day_index, day_index, mode)
        scenarios = k8_scenarios(day_index, data, archive, day_index, k=k)
        load_mae = forecast_mae(data.load[day_index], forecast.load_hat)
        pv_mae = forecast_mae(data.pv[day_index], forecast.pv_hat)
        net_mae = forecast_mae(
            data.load[day_index] - data.pv[day_index],
            forecast.load_hat - forecast.pv_hat,
        )
        coverage = float("nan")
        if scenarios is not None:
            scenario_net = (
                archive.load_residual[scenarios.medoid_indices]
                - archive.pv_residual[scenarios.medoid_indices]
            )
            realised_net = (
                data.load[day_index]
                - data.pv[day_index]
                - (forecast.load_hat - forecast.pv_hat)
            )
            coverage = target_quantile_coverage(
                realised_net, scenario_net, scenarios.probabilities, alpha
            )
        rows.append(
            {
                "date": data.dates[day_index].strftime("%Y-%m-%d"),
                "forecast_mode": mode.value,
                "load_mae_kwh": load_mae,
                "pv_mae_kwh": pv_mae,
                "net_load_mae_kwh": net_mae,
                "risk_alpha": alpha,
                "quantile_coverage": coverage,
                "selection_role": "diagnostic_only",
            }
        )
    return rows


def one_se_tiebreak(
    rows: list[dict],
) -> dict:
    """Select by mean actual cost, then unused plan, then m1, then smaller alpha."""
    best = min(rows, key=lambda row: row["mean_actual_cost_yuan"])
    threshold = best["mean_actual_cost_yuan"] + best["standard_error_yuan"]
    eligible = [row for row in rows if row["mean_actual_cost_yuan"] <= threshold]
    mode_rank = {ForecastMode.M1.value: 0, ForecastMode.M2.value: 1, ForecastMode.M3.value: 2}
    return min(
        eligible,
        key=lambda row: (
            row["mean_unused_plan_kwh"],
            mode_rank[row["forecast_mode"]],
            row["risk_alpha"],
        ),
    )


def closed_loop_candidate_window(
    data: Q2Data,
    archives: dict[ForecastMode, ForecastArchive],
    validation_indices: np.ndarray,
    window_start_soc: float,
    k: int = FIXED_SCENARIO_K,
) -> list[dict]:
    """Score each (m, alpha) by the same residual-MPC policy. No full-day actual LP."""
    records: list[dict] = []
    for mode in FORECAST_MODES:
        archive = archives[mode]
        for alpha in RISK_ALPHA_CANDIDATES:
            costs = []
            unused = []
            planned = []
            emergency = []
            times = []
            soc = float(window_start_soc)
            for i in validation_indices:
                summary, _frame, _plan, _floor, _scenarios = plan_closed_loop_day(
                    data,
                    archive,
                    int(i),
                    soc,
                    mode=mode,
                    risk_alpha=float(alpha),
                    k=k,
                    terminal_value_cuts=None,
                )
                costs.append(summary["total_cost_yuan"])
                unused.append(summary["unused_plan_kwh"])
                planned.append(summary["planned_cost_yuan"])
                emergency.append(summary["emergency_cost_yuan"])
                times.append(
                    summary["day_ahead_solve_seconds"] + summary["total_mpc_solve_seconds"]
                )
                soc = float(summary["soc_end_kwh"])
            records.append(
                {
                    "forecast_mode": mode.value,
                    "risk_alpha": float(alpha),
                    "validation_days": int(len(validation_indices)),
                    "mean_actual_cost_yuan": float(np.mean(costs)),
                    "standard_error_yuan": float(
                        np.std(costs, ddof=1) / sqrt(len(costs)) if len(costs) > 1 else 0.0
                    ),
                    "mean_planned_cost_yuan": float(np.mean(planned)),
                    "mean_emergency_cost_yuan": float(np.mean(emergency)),
                    "mean_unused_plan_kwh": float(np.mean(unused)),
                    "mean_solve_seconds": float(np.mean(times)),
                    "used_full_day_actual_lp": False,
                }
            )
    selected = one_se_tiebreak(records)
    for row in records:
        row["selected"] = row is selected
    return records
