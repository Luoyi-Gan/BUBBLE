"""Policy-consistent Q2 redesign: baseline forecast LP + K=8 reserve + residual MPC.

This module is independent of the signed-off stochastic day-ahead production path.
K-medoids enter only through the risk reserve R(alpha) and intra-day residual weights.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from math import sqrt
import json
import os
from pathlib import Path
from threading import Lock

import numpy as np
import pandas as pd

from q2.config import (
    EMERGENCY_PRICE_MULTIPLIER,
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    FIXED_SCENARIO_K,
    K_RECALIBRATION_DAYS,
    LOAD_HISTORY_SAME_WEEKDAY,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    NEXT_DAY_VALUE_MAX_SAMPLES,
    NUMERIC_TOL,
    OFFICIAL_OUTPUT_START,
    POWER_LIMIT_KWH,
    PV_HISTORY_DAYS,
    RISK_ALPHA_CANDIDATES,
    RISK_CALIBRATION_DAYS,
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
ValueCutCache = dict[
    tuple[int, str, float | None, int],
    tuple[tuple[ValueCut, ...], list[dict]],
]
PERIOD_JANUARY_WARMUP = "january_warmup"
PERIOD_FEB_DEC_OUTPUT = "feb_dec_output"


@dataclass(frozen=True)
class FrozenDayPolicy:
    date: str
    forecast_mode: ForecastMode
    risk_alpha: float | None
    fallback_reason: str
    calibration_date: str
    effective_start_date: str
    effective_end_date: str

    def effective_k(self, requested_k: int) -> int:
        if self.risk_alpha is None:
            return 1
        return int(requested_k)


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
            "history_cutoff_date": (
                data.dates[current_index - 1].strftime("%Y-%m-%d")
                if current_index
                else "attachment1_fallback"
            ),
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


def value_cut_cache_key(
    day_index: int,
    mode: ForecastMode,
    risk_alpha: float | None,
    k: int,
) -> tuple[int, str, float | None, int]:
    return (int(day_index), mode.value, None if risk_alpha is None else float(risk_alpha), int(k))


def cached_baseline_value_cuts(
    cache: ValueCutCache,
    data: Q2Data,
    archive: ForecastArchive,
    day_index: int,
    mode: ForecastMode,
    k: int,
    risk_alpha: float | None,
    lock: Lock | None = None,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    """Reuse next-day baseline value cuts for the same (day, m, α, K)."""
    key = value_cut_cache_key(day_index, mode, risk_alpha, k)
    if lock is None:
        hit = cache.get(key)
        if hit is not None:
            return hit
        built = build_baseline_value_cuts(
            data, archive, day_index, mode, k=k, risk_alpha=risk_alpha
        )
        cache[key] = built
        return built
    with lock:
        hit = cache.get(key)
        if hit is not None:
            return hit
    built = build_baseline_value_cuts(
        data, archive, day_index, mode, k=k, risk_alpha=risk_alpha
    )
    with lock:
        existing = cache.get(key)
        if existing is not None:
            return existing
        cache[key] = built
        return built


def score_one_candidate(
    data: Q2Data,
    archive: ForecastArchive,
    mode_value: str,
    alpha: float,
    validation_indices: tuple[int, ...],
    window_start_soc: float,
    k: int = FIXED_SCENARIO_K,
    include_value_cuts: bool = True,
    cut_cache: ValueCutCache | None = None,
    cut_cache_lock: Lock | None = None,
) -> dict:
    """Run one (m, alpha) on a finished-day window with that candidate's own SOC path."""
    mode = ForecastMode(mode_value)
    costs: list[float] = []
    unused: list[float] = []
    planned: list[float] = []
    emergency: list[float] = []
    times: list[float] = []
    soc_path = [float(window_start_soc)]
    soc = float(window_start_soc)
    used_full_day_actual_lp = False
    future_actuals_in_optimizer = False
    cache = {} if cut_cache is None else cut_cache
    for i in validation_indices:
        cuts: tuple[ValueCut, ...] | None = None
        if include_value_cuts:
            cuts, _cut_rows = cached_baseline_value_cuts(
                cache,
                data,
                archive,
                int(i),
                mode,
                k,
                float(alpha),
                lock=cut_cache_lock,
            )
        summary, _frame, _plan, _floor, _scenarios = plan_closed_loop_day(
            data,
            archive,
            int(i),
            soc,
            mode=mode,
            risk_alpha=float(alpha),
            k=k,
            terminal_value_cuts=cuts,
        )
        used_full_day_actual_lp = used_full_day_actual_lp or bool(
            summary["used_full_day_actual_lp"]
        )
        future_actuals_in_optimizer = future_actuals_in_optimizer or bool(
            summary["future_actuals_in_optimizer"]
        )
        costs.append(summary["total_cost_yuan"])
        unused.append(summary["unused_plan_kwh"])
        planned.append(summary["planned_cost_yuan"])
        emergency.append(summary["emergency_cost_yuan"])
        times.append(summary["day_ahead_solve_seconds"] + summary["total_mpc_solve_seconds"])
        soc = float(summary["soc_end_kwh"])
        soc_path.append(soc)
    return {
        "forecast_mode": mode.value,
        "risk_alpha": float(alpha),
        "validation_days": int(len(validation_indices)),
        "window_start_soc_kwh": float(window_start_soc),
        "candidate_soc_end_kwh": soc,
        "candidate_soc_path_kwh": ";".join(f"{value:.6f}" for value in soc_path),
        "mean_actual_cost_yuan": float(np.mean(costs)),
        "standard_error_yuan": float(
            np.std(costs, ddof=1) / sqrt(len(costs)) if len(costs) > 1 else 0.0
        ),
        "mean_planned_cost_yuan": float(np.mean(planned)),
        "mean_emergency_cost_yuan": float(np.mean(emergency)),
        "mean_unused_plan_kwh": float(np.mean(unused)),
        "mean_solve_seconds": float(np.mean(times)),
        "used_full_day_actual_lp": used_full_day_actual_lp,
        "future_actuals_in_optimizer": future_actuals_in_optimizer,
        "selection_criterion": "mean_actual_cost_sum_pq_plus_5pe",
        "include_value_cuts": bool(include_value_cuts),
    }


def _score_candidate_job(payload: dict) -> dict:
    return score_one_candidate(
        payload["data"],
        payload["archive"],
        payload["mode_value"],
        payload["alpha"],
        payload["validation_indices"],
        payload["window_start_soc"],
        payload["k"],
        include_value_cuts=payload.get("include_value_cuts", True),
        cut_cache=payload.get("cut_cache"),
        cut_cache_lock=payload.get("cut_cache_lock"),
    )


def closed_loop_candidate_window(
    data: Q2Data,
    archives: dict[ForecastMode, ForecastArchive],
    validation_indices: np.ndarray,
    window_start_soc: float,
    k: int = FIXED_SCENARIO_K,
    workers: int | None = None,
    include_value_cuts: bool = True,
    cut_cache: ValueCutCache | None = None,
    cut_cache_lock: Lock | None = None,
) -> list[dict]:
    """Score all 12 (m, alpha) pairs by the same residual-MPC policy."""
    indices = tuple(int(i) for i in np.asarray(validation_indices).ravel())
    cache = {} if cut_cache is None else cut_cache
    jobs = [
        {
            "data": data,
            "archive": archives[mode],
            "mode_value": mode.value,
            "alpha": float(alpha),
            "validation_indices": indices,
            "window_start_soc": float(window_start_soc),
            "k": k,
            "include_value_cuts": include_value_cuts,
            "cut_cache": cache,
            "cut_cache_lock": cut_cache_lock,
        }
        for mode in FORECAST_MODES
        for alpha in RISK_ALPHA_CANDIDATES
    ]
    n_workers = int(os.environ.get("Q2_R2_WORKERS", workers if workers is not None else 8))
    n_workers = max(1, min(n_workers, len(jobs)))
    if n_workers == 1:
        records = [_score_candidate_job(job) for job in jobs]
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            records = list(pool.map(_score_candidate_job, jobs))
    if len(records) != len(FORECAST_MODES) * len(RISK_ALPHA_CANDIDATES):
        raise AssertionError("closed-loop calibration must evaluate 12 (m, alpha) pairs")
    selected = one_se_tiebreak(records)
    threshold = selected["mean_actual_cost_yuan"] + selected["standard_error_yuan"]
    for row in records:
        row["selected"] = (
            row["forecast_mode"] == selected["forecast_mode"]
            and row["risk_alpha"] == selected["risk_alpha"]
        )
        row["one_se_threshold_yuan"] = threshold
    return records


def _validation_diagnostics(
    data: Q2Data,
    archives: dict[ForecastMode, ForecastArchive],
    validation_indices: np.ndarray,
    k: int,
) -> dict[str, dict[str, float]]:
    by_mode: dict[str, dict[str, float]] = {}
    for mode, archive in archives.items():
        load_mae = []
        pv_mae = []
        net_mae = []
        coverage = []
        for i in validation_indices:
            rows = mode_diagnostics(data, int(i), {mode: archive}, RISK_ALPHA_CANDIDATES[0], k=k)
            load_mae.append(rows[0]["load_mae_kwh"])
            pv_mae.append(rows[0]["pv_mae_kwh"])
            net_mae.append(rows[0]["net_load_mae_kwh"])
            coverage.append(rows[0]["quantile_coverage"])
        coverage_arr = np.asarray(coverage, dtype=float)
        finite = coverage_arr[np.isfinite(coverage_arr)]
        by_mode[mode.value] = {
            "load_mae_kwh": float(np.mean(load_mae)),
            "pv_mae_kwh": float(np.mean(pv_mae)),
            "net_load_mae_kwh": float(np.mean(net_mae)),
            "quantile_coverage": float(np.mean(finite)) if finite.size else float("nan"),
        }
    return by_mode


def run_rolling_closed_loop_calibration(
    data: Q2Data,
    archives: dict[ForecastMode, ForecastArchive],
    k: int = FIXED_SCENARIO_K,
    workers: int | None = None,
    include_value_cuts: bool = True,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Walk 14-day blocks, score 12 candidates, then deploy the winner to carry SOC."""
    n = len(data.dates)
    policy_start_soc = np.full(n, np.nan)
    soc = float(E_INITIAL_KWH)
    calibration_rows: list[dict] = []
    diagnostic_rows: list[dict] = []
    deployed_rows: list[dict] = []
    block = K_RECALIBRATION_DAYS
    window = RISK_CALIBRATION_DAYS
    cut_cache: ValueCutCache = {}
    cut_lock = Lock()

    for calibration in range(0, n, block):
        effective_end = min(calibration + block - 1, n - 1)
        validation = np.arange(max(0, calibration - window), calibration)
        history_cutoff = (
            data.dates[calibration - 1].strftime("%Y-%m-%d")
            if calibration
            else "attachment1_fallback"
        )
        block_meta = {
            "calibration_date": data.dates[calibration].strftime("%Y-%m-%d"),
            "history_cutoff_date": history_cutoff,
            "effective_start_date": data.dates[calibration].strftime("%Y-%m-%d"),
            "effective_end_date": data.dates[effective_end].strftime("%Y-%m-%d"),
        }
        if len(validation) < window:
            selected_mode = ForecastMode.M1
            selected_alpha: float | None = None
            fallback = "insufficient_prior_14_day_window"
            calibration_rows.append(
                {
                    **block_meta,
                    "forecast_mode": selected_mode.value,
                    "risk_alpha": selected_alpha,
                    "validation_days": int(len(validation)),
                    "validation_start_date": "none",
                    "validation_end_date": "none",
                    "window_start_soc_kwh": float(soc),
                    "candidate_soc_end_kwh": float("nan"),
                    "candidate_soc_path_kwh": "",
                    "mean_actual_cost_yuan": float("nan"),
                    "standard_error_yuan": float("nan"),
                    "mean_planned_cost_yuan": float("nan"),
                    "mean_emergency_cost_yuan": float("nan"),
                    "mean_unused_plan_kwh": float("nan"),
                    "mean_solve_seconds": float("nan"),
                    "used_full_day_actual_lp": False,
                    "future_actuals_in_optimizer": False,
                    "selection_criterion": "mean_actual_cost_sum_pq_plus_5pe",
                    "one_se_threshold_yuan": float("nan"),
                    "selected": True,
                    "fallback_reason": fallback,
                    "include_value_cuts": bool(include_value_cuts),
                }
            )
            active_k = 1
        else:
            window_start_soc = float(policy_start_soc[int(validation[0])])
            if not np.isfinite(window_start_soc):
                raise AssertionError("deployed policy SOC missing at validation window start")
            records = closed_loop_candidate_window(
                data,
                archives,
                validation,
                window_start_soc,
                k=k,
                workers=workers,
                include_value_cuts=include_value_cuts,
                cut_cache=cut_cache,
                cut_cache_lock=cut_lock,
            )
            mae_by_mode = _validation_diagnostics(data, archives, validation, k=k)
            selected_row = next(row for row in records if row["selected"])
            selected_mode = ForecastMode(selected_row["forecast_mode"])
            selected_alpha = float(selected_row["risk_alpha"])
            fallback = ""
            active_k = k
            for row in records:
                calibration_rows.append(
                    {
                        **block_meta,
                        **row,
                        "validation_start_date": data.dates[int(validation[0])].strftime(
                            "%Y-%m-%d"
                        ),
                        "validation_end_date": data.dates[int(validation[-1])].strftime(
                            "%Y-%m-%d"
                        ),
                        "fallback_reason": fallback,
                    }
                )
                diagnostic = mae_by_mode[row["forecast_mode"]]
                diagnostic_rows.append(
                    {
                        **block_meta,
                        "forecast_mode": row["forecast_mode"],
                        "risk_alpha": row["risk_alpha"],
                        "load_mae_kwh": diagnostic["load_mae_kwh"],
                        "pv_mae_kwh": diagnostic["pv_mae_kwh"],
                        "net_load_mae_kwh": diagnostic["net_load_mae_kwh"],
                        "quantile_coverage": diagnostic["quantile_coverage"],
                        "mean_planned_cost_yuan": row["mean_planned_cost_yuan"],
                        "mean_emergency_cost_yuan": row["mean_emergency_cost_yuan"],
                        "mean_unused_plan_kwh": row["mean_unused_plan_kwh"],
                        "mean_actual_cost_yuan": row["mean_actual_cost_yuan"],
                        "selected": row["selected"],
                        "selection_role": "diagnostic_only",
                    }
                )
            print(
                f"C2-R2 {block_meta['calibration_date']}: "
                f"selected {selected_mode.value} α={selected_alpha:.2f} "
                f"cost={selected_row['mean_actual_cost_yuan']:.2f}",
                flush=True,
            )

        for i in range(calibration, effective_end + 1):
            policy_start_soc[i] = soc
            cuts: tuple[ValueCut, ...] | None = None
            if include_value_cuts:
                cuts, _cut_rows = cached_baseline_value_cuts(
                    cut_cache,
                    data,
                    archives[selected_mode],
                    i,
                    selected_mode,
                    active_k,
                    selected_alpha,
                    lock=cut_lock,
                )
            summary, _frame, _plan, _floor, _scenarios = plan_closed_loop_day(
                data,
                archives[selected_mode],
                i,
                soc,
                mode=selected_mode,
                risk_alpha=selected_alpha,
                k=active_k,
                terminal_value_cuts=cuts,
            )
            if not summary["pass"]:
                raise AssertionError(f"deployed policy failed on {summary['date']}")
            deployed_rows.append(
                {
                    "date": summary["date"],
                    "forecast_mode": selected_mode.value,
                    "risk_alpha": selected_alpha,
                    "scenario_k": active_k if selected_alpha is not None else 1,
                    "soc_start_kwh": summary["soc_start_kwh"],
                    "soc_end_kwh": summary["soc_end_kwh"],
                    "planned_cost_yuan": summary["planned_cost_yuan"],
                    "emergency_cost_yuan": summary["emergency_cost_yuan"],
                    "total_cost_yuan": summary["total_cost_yuan"],
                    "unused_plan_kwh": summary["unused_plan_kwh"],
                    "emergency_kwh": summary["emergency_kwh"],
                    "used_full_day_actual_lp": summary["used_full_day_actual_lp"],
                    "future_actuals_in_optimizer": summary["future_actuals_in_optimizer"],
                    "pass": summary["pass"],
                    "fallback_reason": fallback,
                    "include_value_cuts": bool(include_value_cuts),
                }
            )
            soc = float(summary["soc_end_kwh"])
    return (
        calibration_rows,
        diagnostic_rows,
        deployed_rows,
        {
            "include_value_cuts": bool(include_value_cuts),
            "calibration_include_value_cuts": bool(include_value_cuts),
            "deployment_include_value_cuts": bool(include_value_cuts),
            "value_cut_cache_entries": int(len(cut_cache)),
        },
    )


def output_period(date: pd.Timestamp | str) -> str:
    stamp = pd.Timestamp(date).normalize()
    if stamp < pd.Timestamp(OFFICIAL_OUTPUT_START):
        return PERIOD_JANUARY_WARMUP
    return PERIOD_FEB_DEC_OUTPUT


def selected_calendar_for_dates(
    calibration: pd.DataFrame,
    dates: pd.DatetimeIndex,
) -> list[FrozenDayPolicy]:
    """Map each calendar day to the unique R2-selected (m, α) block."""
    selected = calibration.loc[calibration["selected"].astype(bool)].copy()
    if selected.empty:
        raise AssertionError("closed-loop calibration has no selected rows")
    selected["effective_start_date"] = pd.to_datetime(selected["effective_start_date"])
    selected["effective_end_date"] = pd.to_datetime(selected["effective_end_date"])
    policies: list[FrozenDayPolicy] = []
    for date in pd.DatetimeIndex(dates):
        match = selected.loc[
            (selected["effective_start_date"] <= date)
            & (selected["effective_end_date"] >= date)
        ]
        if len(match) != 1:
            raise AssertionError(f"expected one selected block for {date.date()}, got {len(match)}")
        row = match.iloc[0]
        alpha_raw = row["risk_alpha"]
        alpha = None if pd.isna(alpha_raw) else float(alpha_raw)
        policies.append(
            FrozenDayPolicy(
                date=date.strftime("%Y-%m-%d"),
                forecast_mode=ForecastMode(str(row["forecast_mode"])),
                risk_alpha=alpha,
                fallback_reason=str(row["fallback_reason"] or ""),
                calibration_date=pd.Timestamp(row["calibration_date"]).strftime("%Y-%m-%d"),
                effective_start_date=pd.Timestamp(row["effective_start_date"]).strftime(
                    "%Y-%m-%d"
                ),
                effective_end_date=pd.Timestamp(row["effective_end_date"]).strftime("%Y-%m-%d"),
            )
        )
    return policies


def _forecast_audit_row(summary: dict) -> dict:
    return {
        "date": summary["date"],
        "forecast_mode": summary["forecast_mode"],
        "risk_alpha": summary["risk_alpha"],
        "scenario_k": summary["scenario_k"],
        "load_source_dates": summary["load_source_dates"],
        "pv_source_dates": summary["pv_source_dates"],
        "residual_pool_end_date": summary["residual_pool_end_date"],
        "medoid_dates": summary["medoid_dates"],
        "load_fallback": summary["load_fallback"],
        "pv_fallback": summary["pv_fallback"],
        "risk_q_floor_kwh": summary["risk_q_floor_kwh"],
        "has_scenario_specific_battery": summary["has_scenario_specific_battery"],
        "day_ahead_variable_shapes": json.dumps(
            summary["day_ahead_variable_shapes"], ensure_ascii=False
        )
        if not isinstance(summary["day_ahead_variable_shapes"], str)
        else summary["day_ahead_variable_shapes"],
    }


def _physical_audit_row(summary: dict) -> dict:
    return {
        "date": summary["date"],
        "period": summary["period"],
        "pass": summary["pass"],
        "planned_q_sha256": summary["planned_q_sha256"],
        "max_balance_residual_kwh": summary["max_balance_residual_kwh"],
        "max_x_minus_q_kwh": summary["max_x_minus_q_kwh"],
        "max_simultaneous_cd_kwh2": summary["max_simultaneous_cd_kwh2"],
        "soc_start_kwh": summary["soc_start_kwh"],
        "soc_end_kwh": summary["soc_end_kwh"],
        "unused_plan_kwh": summary["unused_plan_kwh"],
        "emergency_kwh": summary["emergency_kwh"],
        "curtailment_kwh": summary["curtailment_kwh"],
        "used_full_day_actual_lp": summary["used_full_day_actual_lp"],
        "future_actuals_in_optimizer": summary["future_actuals_in_optimizer"],
    }


def _daily_summary_row(summary: dict) -> dict:
    shapes = summary["day_ahead_variable_shapes"]
    if isinstance(shapes, dict):
        shapes = json.dumps(shapes, ensure_ascii=False)
    row = {key: value for key, value in summary.items() if key != "day_ahead_variable_shapes"}
    row["day_ahead_variable_shapes"] = shapes
    return row


def aggregate_cost_row(
    frame: pd.DataFrame,
    *,
    label: str,
    extra: dict | None = None,
) -> dict:
    if frame.empty:
        raise AssertionError(f"cannot aggregate empty ledger for {label}")
    row = {
        "label": label,
        "n_days": int(len(frame)),
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "planned_cost_yuan": float(frame["planned_cost_yuan"].sum()),
        "emergency_cost_yuan": float(frame["emergency_cost_yuan"].sum()),
        "total_cost_yuan": float(frame["total_cost_yuan"].sum()),
        "planned_q_kwh": float(frame["planned_q_kwh"].sum()),
        "actual_x_kwh": float(frame["actual_x_kwh"].sum()),
        "unused_plan_kwh": float(frame["unused_plan_kwh"].sum()),
        "emergency_kwh": float(frame["emergency_kwh"].sum()),
        "curtailment_kwh": float(frame["curtailment_kwh"].sum()),
        "soc_start_kwh": float(frame["soc_start_kwh"].iloc[0]),
        "soc_end_kwh": float(frame["soc_end_kwh"].iloc[-1]),
        "max_balance_residual_kwh": float(frame["max_balance_residual_kwh"].max()),
        "all_days_pass": bool(frame["pass"].all()),
        "used_full_day_actual_lp": bool(frame["used_full_day_actual_lp"].any()),
        "future_actuals_in_optimizer": bool(frame["future_actuals_in_optimizer"].any()),
    }
    if extra:
        row.update(extra)
    return row


def k_sensitivity_conclusion(rows: list[dict]) -> str:
    """Keep K=8 when cost and emergency remain stable versus K=4 and K=12."""
    by_k = {int(row["scenario_k"]): row for row in rows if int(row["scenario_k"]) in {4, 8, 12}}
    if set(by_k) != {4, 8, 12}:
        raise AssertionError("K sensitivity must report K=4, 8 and 12")
    costs = np.array([by_k[k]["total_cost_yuan"] for k in (4, 8, 12)], dtype=float)
    emergencies = np.array([by_k[k]["emergency_kwh"] for k in (4, 8, 12)], dtype=float)
    cost_span = float(np.max(np.abs(costs - costs[1])) / max(abs(costs[1]), 1.0))
    emergency_span = float(
        np.max(np.abs(emergencies - emergencies[1])) / max(abs(emergencies[1]), 1.0)
    )
    if cost_span <= 0.05 and emergency_span <= 0.10:
        return "retain_k8_stable"
    return "review_k_reselection"


def run_frozen_policy_path(
    data: Q2Data,
    archives: dict[ForecastMode, ForecastArchive],
    calendar: list[FrozenDayPolicy],
    *,
    start_index: int,
    end_index: int,
    initial_soc: float,
    requested_k: int,
    soc_source: str,
    include_value_cuts: bool = True,
    dispatch_dir: Path | None = None,
    cut_cache: ValueCutCache | None = None,
    progress_label: str = "",
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Execute a frozen (m, α) calendar with residual MPC; never uses full-day actual LP."""
    if not 0 <= start_index <= end_index < len(data.dates):
        raise ValueError("frozen path indices out of range")
    if len(calendar) != len(data.dates):
        raise AssertionError("frozen calendar must cover every 2025 day")
    cache: ValueCutCache = {} if cut_cache is None else cut_cache
    daily_rows: list[dict] = []
    forecast_rows: list[dict] = []
    physical_rows: list[dict] = []
    value_rows: list[dict] = []
    soc = float(initial_soc)
    for i in range(start_index, end_index + 1):
        policy = calendar[i]
        if policy.date != data.dates[i].strftime("%Y-%m-%d"):
            raise AssertionError(f"calendar date mismatch at {i}: {policy.date}")
        archive = archives[policy.forecast_mode]
        active_k = policy.effective_k(requested_k)
        cuts: tuple[ValueCut, ...] | None = None
        if include_value_cuts:
            cuts, cut_rows = cached_baseline_value_cuts(
                cache,
                data,
                archive,
                i,
                policy.forecast_mode,
                active_k,
                policy.risk_alpha,
            )
            value_rows.extend({"decision_date": policy.date, **row} for row in cut_rows)
        dispatch_path = (
            dispatch_dir / f"dispatch_{policy.date}.csv" if dispatch_dir is not None else None
        )
        summary, _frame, _plan, _floor, _scenarios = plan_closed_loop_day(
            data,
            archive,
            i,
            soc,
            mode=policy.forecast_mode,
            risk_alpha=policy.risk_alpha,
            k=active_k,
            terminal_value_cuts=cuts,
            dispatch_path=dispatch_path,
        )
        if not summary["pass"]:
            raise AssertionError(f"physical validation failed on {summary['date']}")
        summary.update(
            {
                "period": output_period(policy.date),
                "soc_source": soc_source,
                "requested_k": int(requested_k),
                "calibration_date": policy.calibration_date,
                "fallback_reason": policy.fallback_reason,
                "include_value_cuts": bool(include_value_cuts),
            }
        )
        daily_rows.append(_daily_summary_row(summary))
        forecast_rows.append(_forecast_audit_row(summary))
        physical_rows.append(_physical_audit_row(summary))
        soc = float(summary["soc_end_kwh"])
        if progress_label and (i == start_index or (i + 1) % 14 == 0 or i == end_index):
            print(
                f"{progress_label} {policy.date}: "
                f"{policy.forecast_mode.value} α={policy.risk_alpha} K={active_k} "
                f"cost={summary['total_cost_yuan']:.2f}",
                flush=True,
            )
    return daily_rows, forecast_rows, physical_rows, value_rows
