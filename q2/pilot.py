from __future__ import annotations

import json
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
    NUMERIC_TOL,
    OUTPUT_DIR,
    PILOT_DATES,
    POWER_LIMIT_KWH,
    SIMULTANEOUS_CD_TOL,
    T,
    T_MAX_SECONDS,
)
from q2.data import Q2Data
from q2.forecast import ForecastArchive
from q2.optimization import (
    dispatch_balance_residual,
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


def write_k_audit(path: Path, choices: list[KChoice], data: Q2Data) -> None:
    lines = [
        "# Q2 动态 K 试算审计",
        "",
        "- 每个试算日前只使用此前 14 个验证日；每个验证日的情景池只含更早日期。",
        "- 验证成本以锁定计划 q 在验证日实际轨迹上的固定计划再调度计算；实际轨迹只用于已结束验证日评分。",
        "- 采用一标准误规则选取满足阈值的最小 K。",
        "- `T_MAX_SECONDS` 尚未由队长给定，本试算只记录耗时，不据此剔除 K。",
        "- 初期池不足时，自动删除大于可用完整残差日数量的候选 K；若不足 2 日则回退 K=1。",
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
    choice: KChoice,
    initial_soc: float,
    path: Path,
) -> dict:
    i = choice.target_index
    scenarios = choice.scenarios
    scenario_load, scenario_pv = scenario_trajectories(scenarios, archive)
    plan = solve_stochastic_plan(
        data.price, scenario_load, scenario_pv, scenarios.probabilities, initial_soc
    )
    locked_q = plan.q.copy()
    rows = []
    soc = initial_soc
    max_cd = 0.0
    for t in range(T):
        observed_lr = archive.load_residual[i, : t + 1]
        observed_pr = archive.pv_residual[i, : t + 1]
        weights, bandwidth = posterior_weights(scenarios, archive, observed_lr, observed_pr)
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
            data.price[t:], locked_q[t:], load_horizon, pv_horizon, soc
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
                "balance_residual_kwh": residual,
            }
        )
        max_cd = max(max_cd, float(result.charge[0] * result.discharge[0]))
        soc = float(result.soc[1])
    if not np.array_equal(plan.q, locked_q):
        raise AssertionError("locked day-ahead q changed during MPC")
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    return {
        "date": data.dates[i].strftime("%Y-%m-%d"),
        "selected_k": choice.selected_k,
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
    report = {
        "status": "pass" if perfect["pass"].all() and all(x["pass"] for x in summaries) else "fail",
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
        "contract_audit": {
            "normal_cost_uses": "sum(price_t * planned_q_t)",
            "emergency_cost_uses": "sum(5 * price_t * emergency_t)",
            "actual_normal_purchase_constraint": "0 <= x_t <= q_t",
            "q_locked_during_day": True,
        },
        "output_guard": "No result2.xlsx is created or modified by the pilot.",
        "open_items": [
            "x<=q contract semantics await captain sign-off",
            "48-hour terminal value is not included in this two-day pilot",
            "T_max is not yet specified; timings are reported without K filtering",
            "pilot day initial SOC comes from the perfect-information continuous path",
        ],
    }
    path_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Q2 分阶段试算验证",
        "",
        f"- 总体状态：**{report['status']}**",
        f"- 完美信息 365 日全部通过：{report['perfect_information']['all_days_pass']}",
        f"- 完美信息紧急购电：{report['perfect_information']['emergency_purchase_kwh']:.6e} kWh",
        f"- 完美信息最大能量平衡残差：{report['perfect_information']['max_balance_residual_kwh']:.6e} kWh",
        f"- 完美信息跨日 SOC 最大断点：{report['perfect_information']['max_cross_day_soc_gap_kwh']:.6e} kWh",
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
            f"- 紧急购电 {item['emergency_kwh']:.6f} kWh，弃光 {item['curtailment_kwh']:.6f} kWh。",
            f"- SOC {item['soc_start_kwh']:.6f} → {item['soc_end_kwh']:.6f} kWh。",
            f"- 最大平衡残差 {item['max_balance_residual_kwh']:.3e} kWh；"
            f"max(c*d)={item['max_simultaneous_cd_kwh2']:.3e} kWh²；通过={item['pass']}。",
            f"- 每步平均 {item['mean_mpc_solve_seconds']:.4f} s；外推 334 日约 "
            f"{item['estimated_334_day_runtime_hours']:.2f} h。",
            "",
        ]
    lines += [
        "## 未决口径",
        "",
        "- `x<=q` 暂定合同语义待队长签收。",
        "- 本两日试算未实现 48 小时终端价值；日初 SOC 来自完美信息连续轨迹。",
        "- `T_max` 未给定，因此动态 K 只按一标准误规则选取并报告耗时。",
        "- 未生成或修改 `result2.xlsx`。",
    ]
    path_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

