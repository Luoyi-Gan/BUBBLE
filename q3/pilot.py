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
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    NEXT_DAY_VALUE_MAX_SAMPLES,
    NUMERIC_TOL,
    OUTPUT_DIR,
    PILOT_DATES,
    SIMULTANEOUS_CD_TOL,
    STRATEGY_ALLOWED_UPDATES,
    STRATEGIES,
    T,
    VOI_EPS_YUAN,
)
from q3.data import Q3Data
from q3.forecast import (
    causal_load_forecast,
    map_issue_forecast,
    next_day_pv_forecast,
    write_forecast_mapping,
)
from q3.optimization import (
    ValueCut,
    assert_physical,
    evaluate_value_cuts,
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


@dataclass
class DayRun:
    date: str
    strategy: str
    with_terminal_value: bool
    dispatch: pd.DataFrame
    update_log: pd.DataFrame
    summary: dict
    next_day_value_rows: list[dict] = field(default_factory=list)


def build_next_day_value_cuts(
    data: Q3Data,
    current_index: int,
    issue_hour: int,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    if current_index + 1 >= len(data.dates):
        return (), []
    load = causal_load_forecast(
        data, target_index=current_index + 1, history_end_exclusive=current_index
    )
    pv = next_day_pv_forecast(data, current_index, issue_hour)
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
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
            "bundle_sample_count": len(cuts),
            "information": "Q3 attach3 overlay + causal prior-day load/PV; no future actual PV",
        }
        for reference, value, slope in cuts
    ]
    return cuts, rows


def _index_to_update_hour(index: int) -> int | None:
    inverse = {first: hour for hour, first in HOUR_TO_FIRST_MUTABLE.items() if hour != 0}
    return inverse.get(index)


def run_day(
    data: Q3Data,
    day_index: int,
    strategy: str,
    initial_soc: float,
    with_terminal_value: bool = True,
) -> DayRun:
    date = data.dates[day_index].strftime("%Y-%m-%d")
    allowed = STRATEGY_ALLOWED_UPDATES[strategy]
    price = data.price
    load = data.load[day_index]
    actual_pv = data.pv[day_index]
    started = perf_counter()

    mapped0 = map_issue_forecast(data, day_index, 0)
    current_forecast = mapped0.today_kwh.copy()
    cuts: tuple[ValueCut, ...] = ()
    value_rows: list[dict] = []
    if with_terminal_value:
        cuts, rows = build_next_day_value_cuts(data, day_index, 0)
        value_rows.extend(rows)

    midnight = solve_horizon(
        price,
        load,
        current_forecast,
        initial_soc,
        bill_as_day_ahead=True,
        terminal_value_cuts=cuts or None,
    )
    assert_physical(midnight, load, current_forecast, prefix=f"{date} 0:00 plan ")
    g0 = midnight.g.copy()
    g = g0.copy()
    last_update = "00:00"
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
            mapped = map_issue_forecast(data, day_index, hour)
            current_forecast = mapped.today_kwh.copy()
            if with_terminal_value:
                cuts, rows = build_next_day_value_cuts(data, day_index, hour)
                value_rows.extend(rows)
            pv_plan = current_forecast[t:]
            load_plan = load[t:]
            g0_rem = g0[t:]
            g_pre = g[t:].copy()
            j_fix = solve_horizon(
                price[t:],
                load_plan,
                pv_plan,
                soc,
                g0=g0_rem,
                g_fixed=g_pre,
                terminal_value_cuts=cuts or None,
            )
            j_free = solve_horizon(
                price[t:],
                load_plan,
                pv_plan,
                soc,
                g0=g0_rem,
                terminal_value_cuts=cuts or None,
            )
            voi = float(j_fix.objective - j_free.objective)
            implemented = bool(voi > VOI_EPS_YUAN)
            if implemented:
                g[t:] = j_free.g
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
        step = solve_horizon(
            price[t:],
            load[t:],
            pv_horizon,
            soc,
            g0=g0[t:],
            g_fixed=g[t:],
            terminal_value_cuts=cuts or None,
        )
        residual = (
            step.x[0]
            + step.emergency[0]
            + actual_pv[t]
            - step.curtailment[0]
            + step.discharge[0]
            - load[t]
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
                "load_kwh": float(load[t]),
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
    phi = settlement_cost(
        dispatch["price"].to_numpy(),
        dispatch["planned_g0_kwh"].to_numpy(),
        dispatch["final_g_kwh"].to_numpy(),
    )
    dispatch["phi_yuan"] = phi
    dispatch["emergency_cost_yuan"] = (
        EMERGENCY_PRICE_MULTIPLIER * dispatch["price"] * dispatch["emergency_kwh"]
    )
    update_log = pd.DataFrame(update_rows)
    update_log.insert(1, "strategy", strategy)
    update_log.insert(2, "with_terminal_value", with_terminal_value)
    n_adjust = int(((update_log["update_time"] != "00:00") & update_log["implemented"]).sum())
    summary = {
        "date": date,
        "strategy": strategy,
        "with_terminal_value": with_terminal_value,
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
    return DayRun(date, strategy, with_terminal_value, dispatch, update_log, summary, value_rows)


def warmup_soc_to(
    data: Q3Data, target_index: int, path: Path
) -> tuple[np.ndarray, pd.DataFrame]:
    """Propagate M0 from 2025-01-01 so the first pilot day has a causal SOC."""
    starts = np.full(target_index + 1, E_INITIAL_KWH)
    rows = []
    soc = E_INITIAL_KWH
    for i in range(target_index):
        starts[i] = soc
        result = run_day(data, i, "M0", soc, with_terminal_value=True)
        soc = float(result.summary["soc_end_kwh"])
        rows.append(
            {
                "date": result.date,
                "soc_start_kwh": result.summary["soc_start_kwh"],
                "soc_end_kwh": result.summary["soc_end_kwh"],
                "total_cost_yuan": result.summary["total_cost_yuan"],
                "strategy": "M0_warmup",
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
        frames.append(
            block[
                [
                    "date",
                    "strategy",
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
            spot.append({"date": run.date, "strategy": run.strategy, **item})
    frame = pd.concat(frames, ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    path.with_name("q3_cost_spotcheck.csv").write_text(
        pd.DataFrame(spot).to_csv(index=False), encoding="utf-8"
    )
    return frame


def plot_pilot_figures(runs: list[DayRun], comparison: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    main = comparison[comparison["strategy"].isin(STRATEGIES)].copy()
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
    ax.set_title("Q3 pilot: update-policy cost")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_strategy_cost.png")
    plt.close(fig)

    for run in runs:
        if run.strategy != "M1_M6" or not run.with_terminal_value:
            continue
        d = run.dispatch
        fig, axes = plt.subplots(3, 1, figsize=(8.6, 7.2), sharex=True)
        t = np.arange(len(d))
        axes[0].plot(t, d["load_kwh"], color=NAVY, lw=1.2, label="load")
        axes[0].plot(t, d["actual_pv_kwh"], color=TEAL, lw=1.2, label="actual PV")
        axes[0].plot(t, d["forecast_pv_kwh"], color=ORANGE, lw=1.0, ls="--", label="active PV forecast")
        axes[0].legend(frameon=False, ncol=3)
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
        fig.suptitle(f"{run.date} M1/M6 dispatch", fontsize=12)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"fig3_dispatch_{run.date}_M1_M6.png")
        plt.close(fig)

        log = run.update_log[run.update_log["update_time"] != "00:00"]
        fig, ax = plt.subplots(figsize=(6.4, 3.8))
        ax.bar(log["update_time"], log["voi_yuan"], color=TEAL)
        ax.axhline(VOI_EPS_YUAN, color=ORANGE, ls="--", lw=0.9, label="VoI threshold")
        ax.set_ylabel("VoI (yuan)")
        ax.set_title(f"{run.date} information value by update")
        ax.legend(frameon=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"fig3_voi_{run.date}.png")
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
            "with_terminal_value": run.with_terminal_value,
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
        "runs": items,
    }


def run_q3_pilot(data: Q3Data) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    from q3.data import write_input_audit

    write_input_audit(data, OUTPUT_DIR / "input_audit.json")
    write_forecast_mapping(data, OUTPUT_DIR / "q3_forecast_mapping.csv")

    feb_index = data.date_index("2025-02-01")
    warmup_starts, _warmup = warmup_soc_to(
        data, feb_index, OUTPUT_DIR / "q3_warmup_daily.csv"
    )
    initial = {
        "2025-02-01": float(warmup_starts[feb_index]),
        "2025-06-21": E_INITIAL_KWH,
    }

    runs: list[DayRun] = []
    for date in PILOT_DATES:
        i = data.date_index(date)
        soc0 = initial[date]
        for strategy in STRATEGIES:
            runs.append(run_day(data, i, strategy, soc0, with_terminal_value=True))
        runs.append(
            run_day(data, i, "M1_M6", soc0, with_terminal_value=False)
        )

    comparison = pd.DataFrame([run.summary for run in runs])
    comparison.to_csv(OUTPUT_DIR / "q3_strategy_comparison.csv", index=False)
    update_log = pd.concat([run.update_log for run in runs], ignore_index=True)
    update_log.to_csv(OUTPUT_DIR / "q3_update_log.csv", index=False)
    value_rows = [row for run in runs for row in run.next_day_value_rows]
    if value_rows:
        pd.DataFrame(value_rows).to_csv(OUTPUT_DIR / "q3_next_day_value_audit.csv", index=False)
    write_cost_audit(runs, OUTPUT_DIR / "q3_cost_audit.csv")

    for run in runs:
        suffix = run.strategy + ("" if run.with_terminal_value else "_no48h")
        cols = [
            "time",
            "planned_g0_kwh",
            "final_g_kwh",
            "normal_x_kwh",
            "load_kwh",
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
        run.dispatch[cols].to_csv(
            OUTPUT_DIR / f"q3_dispatch_{run.date}_{suffix}.csv", index=False
        )

    plot_pilot_figures(runs, comparison)
    audit = physical_audit(runs, initial["2025-02-01"])
    (OUTPUT_DIR / "q3_physical_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "initial_soc": initial,
        "comparison": comparison,
        "audit": audit,
        "n_runs": len(runs),
    }
