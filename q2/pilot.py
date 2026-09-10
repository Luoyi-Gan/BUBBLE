from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from math import sqrt
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from q2.config import (
    EMERGENCY_PRICE_MULTIPLIER,
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    FIG_DIR,
    K_CANDIDATES,
    K_VALIDATION_DAYS,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    NEXT_DAY_VALUE_MAX_SAMPLES,
    NUMERIC_TOL,
    OUTPUT_DIR,
    PILOT_DATES,
    POWER_LIMIT_KWH,
    SIMULTANEOUS_CD_TOL,
    T,
    T_MAX_SECONDS,
)
from q2.data import Q2Data
from q2.forecast import ForecastArchive, forecast_as_of
from q2.optimization import (
    ValueCut,
    dispatch_balance_residual,
    evaluate_value_cuts,
    solve_fixed_plan_dispatch,
    solve_perfect_information_day,
    solve_stochastic_plan,
)
from q2.scenarios import (
    ScenarioSet,
    build_scenarios,
    posterior_weights,
    scenario_trajectories,
    write_scenarios_csv,
)


@dataclass(frozen=True)
class KChoice:
    target_index: int
    selected_k: int
    scenarios: ScenarioSet
    rows: tuple[dict, ...]


@dataclass(frozen=True)
class FreezeCalendar:
    daily_k: np.ndarray
    choices: tuple[KChoice | None, ...]
    rows: tuple[dict, ...]


def planned_q_hash(q: np.ndarray) -> str:
    # Decimal canonicalization survives CSV round-trips while detecting any
    # operationally meaningful mutation of the locked plan.
    canonical = ",".join(f"{float(value):.9f}" for value in np.asarray(q).ravel())
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def scenario_inputs_as_of(
    data: Q2Data,
    archive: ForecastArchive,
    target_index: int,
    history_end_exclusive: int,
    k: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, ScenarioSet | None, dict]:
    load_hat, pv_hat, load_sources, pv_sources = forecast_as_of(
        data, target_index, history_end_exclusive
    )
    if history_end_exclusive == 0:
        loads, pvs = load_hat[None, :], pv_hat[None, :]
        probabilities = np.ones(1)
        scenarios = None
    else:
        scenarios = build_scenarios(
            target_index,
            data,
            archive,
            min(k, history_end_exclusive),
            history_end_exclusive=history_end_exclusive,
        )
        loads, pvs = scenario_trajectories(
            scenarios, archive, base_load=load_hat, base_pv=pv_hat
        )
        probabilities = scenarios.probabilities
    audit = {
        "target_date": data.dates[target_index].strftime("%Y-%m-%d"),
        "history_cutoff_date": (
            data.dates[history_end_exclusive - 1].strftime("%Y-%m-%d")
            if history_end_exclusive
            else "attachment1_fallback"
        ),
        "load_source_dates": ";".join(
            data.dates[j].strftime("%Y-%m-%d") for j in load_sources
        )
        or "attachment1_fallback",
        "pv_source_dates": ";".join(
            data.dates[j].strftime("%Y-%m-%d") for j in pv_sources
        )
        or "attachment1_fallback",
        "residual_pool_end_date": (
            data.dates[scenarios.pool_indices[-1]].strftime("%Y-%m-%d")
            if scenarios is not None
            else "none"
        ),
        "scenario_k": len(probabilities),
    }
    return loads, pvs, probabilities, scenarios, audit


def build_next_day_value_cuts(
    data: Q2Data,
    archive: ForecastArchive,
    current_index: int,
    k: int,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    if current_index + 1 >= len(data.dates):
        return (), []
    # At day d 0:00, only indices < d are available. Day d actual data is excluded.
    loads, pvs, probabilities, _scenarios, source_audit = scenario_inputs_as_of(
        data,
        archive,
        target_index=current_index + 1,
        history_end_exclusive=current_index,
        k=k,
    )
    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = solve_stochastic_plan(data.price, loads, pvs, probabilities, float(soc))
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
            (slope, value - slope * reference)
            for reference, value, slope in cuts
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
    while True:
        cuts = tuple(solved[soc] for soc in sorted(solved))
        slopes = np.array([cut[2] for cut in cuts])
        if np.any(np.diff(slopes) < -1e-6):
            raise AssertionError("next-day LP value subgradients are not monotone")
        gap, refine_soc = certified_max_gap(cuts)
        if gap <= NEXT_DAY_VALUE_GAP_TOL_YUAN:
            break
        if len(cuts) >= NEXT_DAY_VALUE_MAX_SAMPLES:
            raise AssertionError(
                f"next-day value gap {gap:.6f} exceeds tolerance after {len(cuts)} samples"
            )
        if min(abs(refine_soc - soc) for soc in solved) < 1e-7:
            raise AssertionError("next-day value refinement stalled")
        solve_at(refine_soc)

    rows = [
        {
            **source_audit,
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
            "gap_tolerance_yuan": NEXT_DAY_VALUE_GAP_TOL_YUAN,
            "bundle_sample_count": len(cuts),
        }
        for reference, value, slope in cuts
    ]
    for reference_soc, reference_value, _slope in cuts:
        if evaluate_value_cuts(reference_soc, cuts) > reference_value + 1e-4:
            raise AssertionError("next-day value supporting cuts violate sampled LP values")
    return tuple(cuts), rows


def run_perfect_information(data: Q2Data, path: Path) -> np.ndarray:
    rows = []
    day_start_soc = np.empty(len(data.dates))
    soc = E_INITIAL_KWH
    for i, date in enumerate(data.dates):
        day_start_soc[i] = soc
        result = solve_perfect_information_day(data.price, data.load[i], data.pv[i], soc)
        residual = dispatch_balance_residual(data.load[i], data.pv[i], result)
        normal_cost = float(data.price @ result.x)
        rows.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "normal_purchase_cost_yuan": normal_cost,
                "emergency_cost_yuan": result.emergency_cost,
                "total_cost_yuan": normal_cost + result.emergency_cost,
                "normal_purchase_kwh": float(result.x.sum()),
                "emergency_kwh": float(result.emergency.sum()),
                "curtailment_kwh": float(result.curtailment.sum()),
                "soc_start_kwh": float(result.soc[0]),
                "soc_end_kwh": float(result.soc[-1]),
                "soc_min_kwh": float(result.soc.min()),
                "soc_max_kwh": float(result.soc.max()),
                "max_balance_residual_kwh": float(np.max(np.abs(residual))),
                "max_simultaneous_cd_kwh2": result.max_cd,
                "solve_seconds": result.solve_seconds,
                "pass": bool(
                    np.max(np.abs(residual)) < NUMERIC_TOL
                    and result.emergency.sum() < NUMERIC_TOL
                    and result.soc.min() >= E_MIN_KWH - NUMERIC_TOL
                    and result.soc.max() <= E_MAX_KWH + NUMERIC_TOL
                ),
            }
        )
        soc = float(result.soc[-1])
    frame = pd.DataFrame(rows)
    if not np.allclose(
        frame["soc_start_kwh"].to_numpy()[1:],
        frame["soc_end_kwh"].to_numpy()[:-1],
        atol=NUMERIC_TOL,
    ):
        raise AssertionError("perfect-information SOC is not continuous across days")
    frame.to_csv(path, index=False)
    return day_start_soc


def _validation_score(
    data: Q2Data,
    archive: ForecastArchive,
    day_start_soc: np.ndarray,
    validation_index: int,
    k: int,
) -> tuple[float, float, float]:
    scenarios = build_scenarios(validation_index, data, archive, k)
    loads, pvs = scenario_trajectories(scenarios, archive)
    plan = solve_stochastic_plan(
        data.price, loads, pvs, scenarios.probabilities, day_start_soc[validation_index]
    )
    execution = solve_fixed_plan_dispatch(
        data.price,
        plan.q,
        data.load[validation_index],
        data.pv[validation_index],
        day_start_soc[validation_index],
    )
    actual_cost = plan.planned_cost + execution.emergency_cost
    return actual_cost, float(execution.emergency.sum()), plan.solve_seconds + execution.solve_seconds


def select_dynamic_k(
    data: Q2Data,
    archive: ForecastArchive,
    day_start_soc: np.ndarray,
    target_index: int,
) -> KChoice:
    validation = np.arange(max(1, target_index - K_VALIDATION_DAYS), target_index)
    min_pool = min(min(28, i) for i in validation)
    candidates = [k for k in K_CANDIDATES if k <= min_pool]
    if not candidates:
        candidates = [1]
    records: list[dict] = []
    for k in candidates:
        costs, emergency, times = [], [], []
        for i in validation:
            cost, e, seconds = _validation_score(data, archive, day_start_soc, int(i), k)
            costs.append(cost)
            emergency.append(e)
            times.append(seconds)
        records.append(
            {
                "calibration_date": data.dates[target_index].strftime("%Y-%m-%d"),
                "candidate_k": k,
                "validation_days": len(validation),
                "mean_validation_cost_yuan": float(np.mean(costs)),
                "standard_error_yuan": float(
                    np.std(costs, ddof=1) / sqrt(len(costs)) if len(costs) > 1 else 0.0
                ),
                "emergency_purchase_kwh": float(np.sum(emergency)),
                "mean_solve_seconds": float(np.mean(times)),
                "within_time_limit": bool(
                    T_MAX_SECONDS is None or np.mean(times) <= T_MAX_SECONDS
                ),
                "selected": False,
            }
        )
    best = min(records, key=lambda x: x["mean_validation_cost_yuan"])
    threshold = best["mean_validation_cost_yuan"] + best["standard_error_yuan"]
    eligible = [
        row
        for row in records
        if row["mean_validation_cost_yuan"] <= threshold and row["within_time_limit"]
    ]
    selected = min(eligible, key=lambda x: x["candidate_k"]) if eligible else best
    selected["selected"] = True
    scenarios = build_scenarios(target_index, data, archive, int(selected["candidate_k"]))
    return KChoice(target_index, int(selected["candidate_k"]), scenarios, tuple(records))


def build_k_freeze_calendar(
    data: Q2Data,
    archive: ForecastArchive,
    day_start_soc: np.ndarray,
) -> FreezeCalendar:
    daily_k = np.ones(len(data.dates), dtype=int)
    choices: list[KChoice | None] = []
    calendar_rows: list[dict] = []
    for calibration in range(0, len(data.dates), 14):
        effective_end = min(calibration + 13, len(data.dates) - 1)
        if calibration < 2:
            selected_k = 1
            choice = None
            candidate_rows = [
                {
                    "candidate_k": 1,
                    "validation_days": 0,
                    "mean_validation_cost_yuan": np.nan,
                    "standard_error_yuan": np.nan,
                    "emergency_purchase_kwh": np.nan,
                    "mean_solve_seconds": np.nan,
                    "within_time_limit": True,
                    "selected": True,
                }
            ]
            fallback = "no_complete_prior_residual_pool"
        else:
            choice = select_dynamic_k(
                data, archive, day_start_soc, calibration
            )
            selected_k = choice.selected_k
            candidate_rows = list(choice.rows)
            fallback = "K=1_early_pool_fallback" if selected_k == 1 else ""
        daily_k[calibration : effective_end + 1] = selected_k
        choices.append(choice)
        for candidate in candidate_rows:
            calendar_rows.append(
                {
                    "calibration_date": data.dates[calibration].strftime("%Y-%m-%d"),
                    "history_cutoff_date": (
                        data.dates[calibration - 1].strftime("%Y-%m-%d")
                        if calibration
                        else "none"
                    ),
                    "candidate_k": int(candidate["candidate_k"]),
                    "selected_k": selected_k,
                    "effective_start_date": data.dates[calibration].strftime("%Y-%m-%d"),
                    "effective_end_date": data.dates[effective_end].strftime("%Y-%m-%d"),
                    "mean_validation_cost_yuan": candidate["mean_validation_cost_yuan"],
                    "standard_error_yuan": candidate["standard_error_yuan"],
                    "validation_days": candidate["validation_days"],
                    "emergency_purchase_kwh": candidate[
                        "emergency_purchase_kwh"
                    ],
                    "mean_solve_seconds": candidate["mean_solve_seconds"],
                    "within_time_limit": candidate["within_time_limit"],
                    "candidate_selected": bool(candidate["selected"]),
                    "selected": bool(candidate["selected"]),
                    "fallback_reason": fallback,
                }
            )
    return FreezeCalendar(daily_k, tuple(choices), tuple(calendar_rows))


def write_k_freeze_calendar(path: Path, calendar: FreezeCalendar) -> None:
    pd.DataFrame(calendar.rows).to_csv(path, index=False)


def write_k_audit(path: Path, choices: list[KChoice], data: Q2Data) -> None:
    lines = [
        "# Q2 动态 K 试算审计",
        "",
        "- 每个试算日前只使用此前 14 个验证日；每个验证日的情景池只含更早日期。",
        "- 验证成本以锁定计划 q 在验证日实际轨迹上的固定计划再调度计算；实际轨迹只用于已结束验证日评分。",
        "- 采用一标准误规则选取满足阈值的最小 K。",
        "- `T_MAX_SECONDS` 尚未由队长给定，本试算只记录耗时，不据此剔除 K。",
        "- 初期池不足时，自动删除大于可用完整残差日数量的候选 K；若不足 2 日则回退 K=1。",
        "- 完整冻结日历见 `k_freeze_calendar.csv`；两个目标日使用其所在周期已冻结的 K。",
        "",
    ]
    for choice in choices:
        pool = choice.scenarios.pool_indices
        lines += [
            f"## {data.dates[choice.target_index].strftime('%Y-%m-%d')}",
            "",
            f"- 选中 K：{choice.selected_k}",
            f"- 情景候选池：{data.dates[pool[0]].strftime('%Y-%m-%d')} 至 "
            f"{data.dates[pool[-1]].strftime('%Y-%m-%d')}，共 {len(pool)} 日。",
            f"- 压力测试日：{data.dates[choice.scenarios.stress_index].strftime('%Y-%m-%d')}（不额外加入期望模型）。",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_posterior_mpc(
    data: Q2Data,
    archive: ForecastArchive,
    choice: KChoice | None,
    initial_soc: float,
    path: Path | None,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    variant: str = "with_48h_value",
) -> dict:
    if choice is None:
        i = 0
        scenarios = None
        scenario_load = archive.load_hat[i][None, :]
        scenario_pv = archive.pv_hat[i][None, :]
        probabilities = np.ones(1)
        selected_k = 1
    else:
        i = choice.target_index
        scenarios = choice.scenarios
        scenario_load, scenario_pv = scenario_trajectories(scenarios, archive)
        probabilities = scenarios.probabilities
        selected_k = choice.selected_k
    plan = solve_stochastic_plan(
        data.price,
        scenario_load,
        scenario_pv,
        probabilities,
        initial_soc,
        terminal_value_cuts=terminal_value_cuts,
    )
    locked_q = plan.q.copy()
    locked_q_sha256 = planned_q_hash(locked_q)
    rows = []
    soc = initial_soc
    max_cd = 0.0
    for t in range(T):
        if scenarios is None:
            weights = np.ones(1)
            bandwidth = np.nan
            load_horizon = archive.load_hat[i, t:].copy()
            pv_horizon = archive.pv_hat[i, t:].copy()
        else:
            observed_lr = archive.load_residual[i, : t + 1]
            observed_pr = archive.pv_residual[i, : t + 1]
            weights, bandwidth = posterior_weights(
                scenarios, archive, observed_lr, observed_pr
            )
            load_horizon = np.maximum(
                0.0,
                archive.load_hat[i, t:]
                + weights @ archive.load_residual[scenarios.medoid_indices, t:],
            )
            pv_horizon = np.maximum(
                0.0,
                archive.pv_hat[i, t:]
                + weights @ archive.pv_residual[scenarios.medoid_indices, t:],
            )
        load_horizon[0] = data.load[i, t]
        pv_horizon[0] = data.pv[i, t]
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
            + data.pv[i, t]
            - result.curtailment[0]
            + result.discharge[0]
            - data.load[i, t]
            - result.charge[0]
        )
        entropy = float(-np.sum(weights * np.log(np.maximum(weights, 1e-300))))
        rows.append(
            {
                "date": data.dates[i].strftime("%Y-%m-%d"),
                "period": t,
                "time": data.time_labels[t],
                "planned_q_kwh": locked_q[t],
                "actual_x_kwh": result.x[0],
                "load_kwh": data.load[i, t],
                "pv_kwh": data.pv[i, t],
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
    if not np.array_equal(plan.q, locked_q):
        raise AssertionError("locked day-ahead q changed during MPC")
    if planned_q_hash(locked_q) != locked_q_sha256:
        raise AssertionError("locked day-ahead q hash changed during MPC")
    frame = pd.DataFrame(rows)
    if path is not None:
        frame.to_csv(path, index=False)
    return {
        "date": data.dates[i].strftime("%Y-%m-%d"),
        "variant": variant,
        "selected_k": selected_k,
        "planned_cost_yuan": plan.planned_cost,
        "emergency_cost_yuan": float(
            np.sum(
                EMERGENCY_PRICE_MULTIPLIER
                * data.price
                * frame["emergency_kwh"].to_numpy()
            )
        ),
        "total_cost_yuan": float(
            plan.planned_cost
            + np.sum(
                EMERGENCY_PRICE_MULTIPLIER
                * data.price
                * frame["emergency_kwh"].to_numpy()
            )
        ),
        "planned_q_kwh": float(locked_q.sum()),
        "planned_q_sha256": locked_q_sha256,
        "day_ahead_virtual_next_day_value_yuan": plan.expected_terminal_value,
        "actual_x_kwh": float(frame["actual_x_kwh"].sum()),
        "unused_plan_kwh": float((locked_q - frame["actual_x_kwh"].to_numpy()).sum()),
        "emergency_kwh": float(frame["emergency_kwh"].sum()),
        "curtailment_kwh": float(frame["curtailment_kwh"].sum()),
        "soc_start_kwh": initial_soc,
        "soc_end_kwh": soc,
        "max_balance_residual_kwh": float(frame["balance_residual_kwh"].abs().max()),
        "max_simultaneous_cd_kwh2": max_cd,
        "max_x_minus_q_kwh": float(
            np.max(frame["actual_x_kwh"].to_numpy() - locked_q)
        ),
        "mean_mpc_solve_seconds": float(frame["solve_seconds"].mean()),
        "total_mpc_solve_seconds": float(frame["solve_seconds"].sum()),
        "terminal_virtual_next_day_value_yuan": float(
            frame["virtual_next_day_value_yuan"].iloc[-1]
        ),
        "estimated_334_day_runtime_hours": float(
            frame["solve_seconds"].mean() * T * 334 / 3600.0
        ),
        "pass": bool(
            frame["balance_residual_kwh"].abs().max() < NUMERIC_TOL
            and np.max(frame["actual_x_kwh"].to_numpy() - locked_q) < NUMERIC_TOL
            and frame["soc_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL
            and frame["soc_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL
            and max_cd <= SIMULTANEOUS_CD_TOL
        ),
    }


def run_linked_warmup(
    data: Q2Data,
    archive: ForecastArchive,
    calendar: FreezeCalendar,
    path: Path,
) -> tuple[pd.DataFrame, list[dict]]:
    rows = []
    soc = E_INITIAL_KWH
    value_audits: list[dict] = []
    for i in range(31):
        k = int(calendar.daily_k[i])
        if i == 0:
            choice = None
        else:
            scenarios = build_scenarios(i, data, archive, k)
            choice = KChoice(i, k, scenarios, ())
        cuts, cut_rows = build_next_day_value_cuts(data, archive, i, k)
        value_audits.extend({"decision_date": data.dates[i].strftime("%Y-%m-%d"), **row} for row in cut_rows)
        start_soc = soc
        result = run_posterior_mpc(
            data,
            archive,
            choice,
            start_soc,
            path=None,
            terminal_value_cuts=cuts,
            variant="linked_warmup_48h",
        )
        soc = float(result["soc_end_kwh"])
        forecast_fallback = (
            len(archive.load_sources[i]) == 0 or len(archive.pv_sources[i]) == 0
        )
        rows.append(
            {
                "date": data.dates[i].strftime("%Y-%m-%d"),
                "soc_start_kwh": start_soc,
                "soc_end_kwh": soc,
                "planned_cost_yuan": result["planned_cost_yuan"],
                "emergency_cost_yuan": result["emergency_cost_yuan"],
                "total_cost_yuan": result["total_cost_yuan"],
                "selected_k": k,
                "forecast_fallback": forecast_fallback,
                "k_fallback": k == 1,
                "max_balance_residual_kwh": result["max_balance_residual_kwh"],
                "max_simultaneous_cd_kwh2": result[
                    "max_simultaneous_cd_kwh2"
                ],
                "pass": result["pass"],
            }
        )
    frame = pd.DataFrame(rows)
    continuity = np.abs(
        frame["soc_start_kwh"].to_numpy()[1:]
        - frame["soc_end_kwh"].to_numpy()[:-1]
    )
    if np.max(continuity) >= NUMERIC_TOL or not frame["pass"].all():
        raise AssertionError("linked January warmup validation failed")
    frame.to_csv(path, index=False)
    return frame, value_audits


def write_pilot_figures(data: Q2Data, summaries: list[dict]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["axes.unicode_minus"] = False
    for summary in summaries:
        date = summary["date"]
        frame = pd.read_csv(OUTPUT_DIR / f"q2_pilot_dispatch_{date}.csv")
        hours = (np.arange(T) + 1) / 6.0
        fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
        axes[0].plot(hours, frame["load_kwh"], label="Load")
        axes[0].plot(hours, frame["pv_kwh"], label="PV")
        axes[0].plot(hours, frame["planned_q_kwh"], label="Planned q")
        axes[0].plot(hours, frame["emergency_kwh"], label="Emergency")
        axes[0].legend(ncol=4, fontsize=8)
        axes[0].set_ylabel("kWh / period")
        axes[0].grid(alpha=0.25)
        axes[1].plot(hours, frame["soc_kwh"], label="SOC", color="#1d4ed8")
        axes[1].set_ylabel("kWh")
        axes[1].set_xlabel("Hour")
        axes[1].grid(alpha=0.25)
        fig.suptitle(f"Q2 pilot MPC: {date}")
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"q2_pilot_{date}.png", dpi=180)
        plt.close(fig)


def write_validation_report(
    path_json: Path,
    path_md: Path,
    perfect_path: Path,
    summaries: list[dict],
) -> None:
    perfect = pd.read_csv(perfect_path)
    warmup = pd.read_csv(OUTPUT_DIR / "linked_warmup_daily.csv")
    calendar = pd.read_csv(OUTPUT_DIR / "k_freeze_calendar.csv")
    value_comparison = pd.read_csv(OUTPUT_DIR / "next_day_value_comparison.csv")
    warmup_gap = float(
        np.max(
            np.abs(
                warmup["soc_start_kwh"].to_numpy()[1:]
                - warmup["soc_end_kwh"].to_numpy()[:-1]
            )
        )
    )
    calendar_periods = calendar[
        ["effective_start_date", "effective_end_date", "selected_k"]
    ].drop_duplicates()
    report = {
        "status": (
            "pass"
            if (
                perfect["pass"].all()
                and all(x["pass"] for x in summaries)
                and warmup["pass"].all()
                and warmup_gap < NUMERIC_TOL
                and len(calendar_periods) == int(np.ceil(365 / 14))
                and not value_comparison["virtual_next_day_value_billed_today"].any()
            )
            else "fail"
        ),
        "perfect_information": {
            "days": len(perfect),
            "all_days_pass": bool(perfect["pass"].all()),
            "max_balance_residual_kwh": float(perfect["max_balance_residual_kwh"].max()),
            "emergency_purchase_kwh": float(perfect["emergency_kwh"].sum()),
            "max_cross_day_soc_gap_kwh": float(
                np.max(
                    np.abs(
                        perfect["soc_start_kwh"].to_numpy()[1:]
                        - perfect["soc_end_kwh"].to_numpy()[:-1]
                    )
                )
            ),
            "max_simultaneous_cd_kwh2": float(
                perfect["max_simultaneous_cd_kwh2"].max()
            ),
        },
        "pilot_days": summaries,
        "linked_january_warmup": {
            "days": len(warmup),
            "soc_continuity_max_gap_kwh": warmup_gap,
            "february_1_initial_soc_kwh": float(warmup["soc_end_kwh"].iloc[-1]),
            "all_days_pass": bool(warmup["pass"].all()),
        },
        "next_day_value_comparison": value_comparison.to_dict(orient="records"),
        "k_freeze_calendar": {
            "calibration_periods": len(calendar_periods),
            "first_effective_date": calendar_periods["effective_start_date"].iloc[0],
            "last_effective_date": calendar_periods["effective_end_date"].iloc[-1],
            "all_periods_at_most_14_days": bool(
                all(
                    (
                        pd.Timestamp(row.effective_end_date)
                        - pd.Timestamp(row.effective_start_date)
                    ).days
                    <= 13
                    for row in calendar_periods.itertuples()
                )
            ),
        },
        "contract_audit": {
            "normal_cost_uses": "sum(price_t * planned_q_t)",
            "emergency_cost_uses": "sum(5 * price_t * emergency_t)",
            "actual_normal_purchase_constraint": "0 <= x_t <= q_t",
            "q_locked_during_day": True,
        },
        "output_guard": "No result2.xlsx is created or modified by the pilot.",
        "open_items": [
            "x<=q contract semantics await captain sign-off",
            (
                "P1 is a sequential daily perfect-information comparator, not a proven "
                "global lower bound against a controller with a different horizon"
            ),
            "T_max is not yet specified; timings are reported without K filtering",
            "June 21 remains an isolated pilot initialized from the comparator path",
            "the next-day value is an adaptively certified LP cut approximation pending sign-off",
        ],
    }
    path_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Q2 分阶段试算验证",
        "",
        f"- 总体状态：**{report['status']}**",
        f"- 逐日完美信息比较器 365 日全部通过：{report['perfect_information']['all_days_pass']}",
        f"- 完美信息紧急购电：{report['perfect_information']['emergency_purchase_kwh']:.6e} kWh",
        f"- 完美信息最大能量平衡残差：{report['perfect_information']['max_balance_residual_kwh']:.6e} kWh",
        f"- 完美信息跨日 SOC 最大断点：{report['perfect_information']['max_cross_day_soc_gap_kwh']:.6e} kWh",
        f"- 联动 1 月预热全部通过：{report['linked_january_warmup']['all_days_pass']}；"
        f"跨日 SOC 最大断点 {warmup_gap:.3e} kWh；2 月 1 日初值 "
        f"{report['linked_january_warmup']['february_1_initial_soc_kwh']:.6f} kWh。",
        f"- K 冻结日历覆盖 {report['k_freeze_calendar']['first_effective_date']} 至 "
        f"{report['k_freeze_calendar']['last_effective_date']}，共 "
        f"{report['k_freeze_calendar']['calibration_periods']} 个周期。",
        "",
        "## 两个 MPC 试算日",
        "",
    ]
    for item in summaries:
        lines += [
            f"### {item['date']}",
            "",
            f"- K={item['selected_k']}，计划成本 {item['planned_cost_yuan']:.6f} 元，"
            f"紧急成本 {item['emergency_cost_yuan']:.6f} 元，总成本 {item['total_cost_yuan']:.6f} 元。",
            f"- 次日虚拟价值仅进入决策目标，不计入上述当天实际成本；日初使用 "
            f"{item['soc_start_kwh']:.6f} kWh。",
            f"- 紧急购电 {item['emergency_kwh']:.6f} kWh，弃光 {item['curtailment_kwh']:.6f} kWh。",
            f"- SOC {item['soc_start_kwh']:.6f} → {item['soc_end_kwh']:.6f} kWh。",
            f"- 最大平衡残差 {item['max_balance_residual_kwh']:.3e} kWh；"
            f"max(c*d)={item['max_simultaneous_cd_kwh2']:.3e} kWh²；通过={item['pass']}。",
            f"- 每步平均 {item['mean_mpc_solve_seconds']:.4f} s；外推 334 日约 "
            f"{item['estimated_334_day_runtime_hours']:.2f} h。",
            "",
        ]
    lines += ["## 48 小时价值对比", ""]
    for item in value_comparison.to_dict(orient="records"):
        lines += [
            f"- {item['date']}：当天有/无价值成本差 {item['cost_difference_yuan']:.6f} 元；"
            f"两日实现成本差 {item['realized_two_day_cost_difference_yuan']:.6f} 元；"
            f"日末 SOC 差 {item['soc_end_difference_kwh']:.6f} kWh；"
            f"紧急购电差 {item['emergency_difference_kwh']:.6f} kWh。",
        ]
    lines += [""]
    lines += [
        "## 未决口径",
        "",
        "- `x<=q` 暂定合同语义待队长签收。",
        "- P1 与主方案视域不同，因此当前只能称“逐日完美信息比较器”，不能据此强制认定全局下界。",
        "- `T_max` 未给定，因此动态 K 只按一标准误规则选取并报告耗时。",
        f"- 次日价值采用自适应 LP 对偶支撑切面，弦线—切面最大认证误差不超过 "
        f"{NEXT_DAY_VALUE_GAP_TOL_YUAN:.2f} 元，待 Codex/队长签收。",
        "- 6 月 21 日仍为孤立试算，其日初 SOC 暂取逐日比较器路径；2 月 1 日已改用联动 1 月预热末值。",
        "- 未生成或修改 `result2.xlsx`。",
    ]
    path_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

