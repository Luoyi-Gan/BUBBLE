"""December A/B year-end SOC pilot. Does not write q3_pilot/ or q3_sensitivity/."""

from __future__ import annotations

import json
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from q3.config import (
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    LOAD_INFORMATION_MAIN,
    PV_MAPPING_LINEAR,
    SETTLEMENT_MAIN,
    SIMULTANEOUS_CD_TOL,
    STRATEGIES,
    T,
    TERMINAL_SOC_FIG_DIR,
    TERMINAL_SOC_OUTPUT_DIR,
    TERMINAL_SOC_PILOT_END,
    TERMINAL_SOC_PILOT_START,
    YEAR_END_BOUNDARIES,
    YEAR_END_BOUNDARY_A,
    YEAR_END_BOUNDARY_B,
    dispatch_stem,
)
from q3.data import Q3Data, write_input_audit
from q3.forecast import load_forecast_audit_rows, mapping_rows_for_day
from q3.pilot import (
    NAVY,
    ORANGE,
    PURPLE,
    TEAL,
    DayRun,
    ValueCutCache,
    physical_audit,
    run_day,
)

plt.rcParams.update(
    {
        "font.sans-serif": ["Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 140,
    }
)

HIGHLIGHT_DATES = ("2025-12-29", "2025-12-30", "2025-12-31")
DISPATCH_COLS = [
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
    "price",
    "phi_yuan",
    "emergency_cost_yuan",
    "run_id",
    "pv_mapping_mode",
    "settlement_mode",
    "year_end_soc_kwh",
    "year_end_boundary",
]


def terminal_soc_pilot_dates(data: Q3Data) -> list[str]:
    start = pd.Timestamp(TERMINAL_SOC_PILOT_START)
    end = pd.Timestamp(TERMINAL_SOC_PILOT_END)
    dates = [ts.strftime("%Y-%m-%d") for ts in data.dates if start <= ts <= end]
    if not dates:
        raise ValueError("no December dates in Attachment 2")
    if dates[0] != TERMINAL_SOC_PILOT_START or dates[-1] != TERMINAL_SOC_PILOT_END:
        raise ValueError(f"expected {TERMINAL_SOC_PILOT_START}..{TERMINAL_SOC_PILOT_END}, got {dates[0]}..{dates[-1]}")
    return dates


def write_december_forecast_mapping(data: Q3Data, dates: list[str], path) -> pd.DataFrame:
    rows: list[dict] = []
    for date in dates:
        rows.extend(mapping_rows_for_day(data, data.date_index(date), PV_MAPPING_LINEAR))
    frame = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def write_december_load_forecast_audit(data: Q3Data, dates: list[str], path) -> pd.DataFrame:
    rows: list[dict] = []
    for date in dates:
        rows.extend(load_forecast_audit_rows(data, data.date_index(date)))
    frame = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def _path_key(strategy: str, boundary: str) -> tuple[str, str]:
    return (strategy, boundary)


def strategy_totals(daily: pd.DataFrame) -> pd.DataFrame:
    ordered = daily.sort_values(["year_end_boundary", "strategy", "date"])
    rows = []
    for (strategy, boundary), block in ordered.groupby(["strategy", "year_end_boundary"], sort=False):
        rows.append(
            {
                "strategy": strategy,
                "year_end_boundary": boundary,
                "year_end_soc_kwh": float(block["year_end_soc_kwh"].iloc[0]),
                "load_information_case": LOAD_INFORMATION_MAIN,
                "pv_mapping_mode": PV_MAPPING_LINEAR,
                "settlement_mode": SETTLEMENT_MAIN,
                "with_terminal_value": True,
                "n_days": int(block["date"].nunique()),
                "total_cost_yuan": float(block["total_cost_yuan"].sum()),
                "settlement_cost_yuan": float(block["settlement_cost_yuan"].sum()),
                "emergency_cost_yuan": float(block["emergency_cost_yuan"].sum()),
                "emergency_kwh": float(block["emergency_kwh"].sum()),
                "curtailment_kwh": float(block["curtailment_kwh"].sum()),
                "charge_kwh": float(block["charge_kwh"].sum()),
                "discharge_kwh": float(block["discharge_kwh"].sum()),
                "adjustment_count": int(block["adjustment_count"].sum()),
                "up_adjust_kwh": float(block["up_adjust_kwh"].sum()),
                "down_adjust_kwh": float(block["down_adjust_kwh"].sum()),
                "soc_start_dec01_kwh": float(block["soc_start_kwh"].iloc[0]),
                "soc_end_dec31_kwh": float(block["soc_end_kwh"].iloc[-1]),
                "max_balance_residual_kwh": float(block["max_balance_residual_kwh"].max()),
                "max_soc_residual_kwh": float(block["max_soc_residual_kwh"].max()),
                "max_simultaneous_cd_kwh2": float(block["max_simultaneous_cd_kwh2"].max()),
                "locked_period_violations": int(block["locked_period_violations"].sum()),
                "runtime_seconds": float(block["runtime_seconds"].sum()),
            }
        )
    totals = pd.DataFrame(rows)
    totals["cost_rank_within_boundary"] = totals.groupby("year_end_boundary")["total_cost_yuan"].rank(
        method="min"
    )
    return totals


def boundary_delta(totals: pd.DataFrame) -> pd.DataFrame:
    a = totals[totals["year_end_boundary"] == YEAR_END_BOUNDARY_A].set_index("strategy")
    b = totals[totals["year_end_boundary"] == YEAR_END_BOUNDARY_B].set_index("strategy")
    rows = []
    for strategy in STRATEGIES:
        rows.append(
            {
                "strategy": strategy,
                "delta_cost_B_minus_A_yuan": float(b.loc[strategy, "total_cost_yuan"] - a.loc[strategy, "total_cost_yuan"]),
                "delta_emergency_cost_B_minus_A_yuan": float(
                    b.loc[strategy, "emergency_cost_yuan"] - a.loc[strategy, "emergency_cost_yuan"]
                ),
                "delta_emergency_kwh_B_minus_A": float(
                    b.loc[strategy, "emergency_kwh"] - a.loc[strategy, "emergency_kwh"]
                ),
                "delta_curtailment_kwh_B_minus_A": float(
                    b.loc[strategy, "curtailment_kwh"] - a.loc[strategy, "curtailment_kwh"]
                ),
                "delta_charge_kwh_B_minus_A": float(b.loc[strategy, "charge_kwh"] - a.loc[strategy, "charge_kwh"]),
                "delta_discharge_kwh_B_minus_A": float(
                    b.loc[strategy, "discharge_kwh"] - a.loc[strategy, "discharge_kwh"]
                ),
                "rank_A": int(a.loc[strategy, "cost_rank_within_boundary"]),
                "rank_B": int(b.loc[strategy, "cost_rank_within_boundary"]),
                "rank_changed": bool(
                    int(a.loc[strategy, "cost_rank_within_boundary"])
                    != int(b.loc[strategy, "cost_rank_within_boundary"])
                ),
                "soc_end_A_kwh": float(a.loc[strategy, "soc_end_dec31_kwh"]),
                "soc_end_B_kwh": float(b.loc[strategy, "soc_end_dec31_kwh"]),
            }
        )
    return pd.DataFrame(rows)


def plot_terminal_soc_figures(daily: pd.DataFrame, totals: pd.DataFrame, runs: list[DayRun]) -> None:
    fig_dir = TERMINAL_SOC_FIG_DIR
    fig_dir.mkdir(parents=True, exist_ok=True)
    x = np.arange(len(STRATEGIES))
    width = 0.36
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    for i, (boundary, color) in enumerate(((YEAR_END_BOUNDARY_A, NAVY), (YEAR_END_BOUNDARY_B, TEAL))):
        subset = totals[totals["year_end_boundary"] == boundary].set_index("strategy").loc[list(STRATEGIES)]
        ax.bar(
            x + (i - 0.5) * width,
            subset["total_cost_yuan"],
            width=width,
            color=color,
            label=boundary,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(STRATEGIES)
    ax.set_ylabel("December total purchase cost (yuan)")
    ax.set_title("Year-end SOC pilot: A=1200 vs B=6000 (isolated Dec 1 start=6000)")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig3_terminal_soc_strategy_cost.png")
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(9.2, 7.0), sharex=True)
    colors = {
        "M0": NAVY,
        "M1_M6": TEAL,
        "M6_only": ORANGE,
        "M12_only": PURPLE,
        "M18_only": "#9c6644",
    }
    dates = list(dict.fromkeys(daily["date"]))
    x_dates = np.arange(len(dates))
    highlight = [i for i, date in enumerate(dates) if date in HIGHLIGHT_DATES]
    xtick = list(range(0, len(dates), 2))
    for ax, boundary in zip(axes, (YEAR_END_BOUNDARY_A, YEAR_END_BOUNDARY_B)):
        for strategy in STRATEGIES:
            block = daily[
                (daily["year_end_boundary"] == boundary) & (daily["strategy"] == strategy)
            ].sort_values("date")
            ax.plot(
                x_dates,
                block["soc_end_kwh"],
                color=colors[strategy],
                lw=1.3,
                marker="o",
                ms=3.0,
                label=strategy,
            )
        if highlight:
            ax.axvspan(highlight[0] - 0.4, highlight[-1] + 0.4, color="#f4e1c1", alpha=0.55, zorder=0)
        ax.axhline(E_MIN_KWH, color=ORANGE, ls="--", lw=0.8)
        ax.axhline(E_INITIAL_KWH, color="#888888", ls=":", lw=0.8)
        ax.set_ylabel("end-of-day SOC (kWh)")
        ax.set_title(boundary)
        ax.legend(frameon=False, ncol=5, fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xticks(xtick)
        ax.set_xticklabels([dates[i][5:] for i in xtick], rotation=60)
    axes[1].set_xlabel("date")
    fig.suptitle("Daily end SOC; shaded = Dec 29–31 (year-end constraint active)", fontsize=12)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig3_terminal_soc_daily_soc.png")
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(9.2, 7.0), sharex=True)
    for ax, (column, ylabel) in zip(
        axes,
        (("total_cost_yuan", "daily cost (yuan)"), ("emergency_kwh", "emergency energy (kWh)")),
    ):
        for strategy in STRATEGIES:
            for boundary, ls in ((YEAR_END_BOUNDARY_A, "-"), (YEAR_END_BOUNDARY_B, "--")):
                block = daily[
                    (daily["year_end_boundary"] == boundary) & (daily["strategy"] == strategy)
                ].sort_values("date")
                ax.plot(
                    x_dates,
                    block[column],
                    color=colors[strategy],
                    ls=ls,
                    lw=1.15,
                    label=f"{strategy} / {boundary.split('_')[0]}",
                )
        if highlight:
            ax.axvspan(highlight[0] - 0.4, highlight[-1] + 0.4, color="#f4e1c1", alpha=0.55, zorder=0)
        ax.set_ylabel(ylabel)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xticks(xtick)
        ax.set_xticklabels([dates[i][5:] for i in xtick], rotation=60)
    axes[0].legend(frameon=False, ncol=2, fontsize=7)
    axes[1].set_xlabel("date")
    fig.suptitle("Daily cost and emergency energy; shaded = Dec 29–31", fontsize=12)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig3_terminal_soc_daily_cost_emergency.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    t = np.arange(T)
    for run in runs:
        if run.date != "2025-12-31" or run.strategy != "M1_M6":
            continue
        color = NAVY if run.summary["year_end_boundary"] == YEAR_END_BOUNDARY_A else TEAL
        ax.plot(
            t,
            run.dispatch["soc_kwh"],
            color=color,
            lw=1.4,
            label=f"{run.summary['year_end_boundary']} target={run.year_end_soc_kwh:.0f}",
        )
    ax.axhline(E_MIN_KWH, color=ORANGE, ls="--", lw=0.8)
    ax.axhline(E_MAX_KWH, color=ORANGE, ls="--", lw=0.8)
    ax.set_xlabel("10-minute index")
    ax.set_ylabel("SOC (kWh)")
    ax.set_title("Dec 31 M1/M6 SOC path under A vs B terminal targets")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig3_terminal_soc_dec31_M1_M6.png")
    plt.close(fig)


def continuity_audit(daily: pd.DataFrame) -> dict:
    items = []
    all_pass = True
    ordered = daily.sort_values(["year_end_boundary", "strategy", "date"])
    for (strategy, boundary), block in ordered.groupby(["strategy", "year_end_boundary"], sort=False):
        starts = block["soc_start_kwh"].to_numpy()
        ends = block["soc_end_kwh"].to_numpy()
        dates = block["date"].to_numpy()
        max_gap = 0.0
        if len(block) > 1:
            max_gap = float(np.max(np.abs(starts[1:] - ends[:-1])))
        start_ok = abs(float(starts[0]) - E_INITIAL_KWH) <= 1e-5
        end_target = float(block["year_end_soc_kwh"].iloc[0])
        end_ok = abs(float(ends[-1]) - end_target) <= 1e-5
        n_ok = len(block) == 31 and dates[0] == TERMINAL_SOC_PILOT_START and dates[-1] == TERMINAL_SOC_PILOT_END
        rec = {
            "strategy": strategy,
            "year_end_boundary": boundary,
            "n_days": int(len(block)),
            "start_soc_kwh": float(starts[0]),
            "end_soc_kwh": float(ends[-1]),
            "year_end_target_kwh": end_target,
            "max_cross_day_soc_gap_kwh": max_gap,
            "pass": bool(start_ok and end_ok and n_ok and max_gap <= 1e-5),
        }
        all_pass = all_pass and rec["pass"]
        items.append(rec)
    return {"all_pass": all_pass, "paths": items}


def run_q3_terminal_soc_pilot(data: Q3Data) -> dict:
    out = TERMINAL_SOC_OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    dispatch_dir = out / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    TERMINAL_SOC_FIG_DIR.mkdir(parents=True, exist_ok=True)
    write_input_audit(data, out / "input_audit.json")

    dates = terminal_soc_pilot_dates(data)
    write_december_forecast_mapping(data, dates, out / "q3_forecast_mapping.csv")
    write_december_load_forecast_audit(data, dates, out / "q3_load_forecast_audit.csv")

    cache: ValueCutCache = {}
    runs: list[DayRun] = []
    last_end: dict[tuple[str, str], float] = defaultdict(lambda: E_INITIAL_KWH)
    n_expected = len(YEAR_END_BOUNDARIES) * len(STRATEGIES) * len(dates)
    done = 0
    for date in dates:
        day_index = data.date_index(date)
        for strategy in STRATEGIES:
            for boundary, target in YEAR_END_BOUNDARIES:
                key = _path_key(strategy, boundary)
                soc0 = E_INITIAL_KWH if date == TERMINAL_SOC_PILOT_START else last_end[key]
                run = run_day(
                    data,
                    day_index,
                    strategy,
                    soc0,
                    with_terminal_value=True,
                    load_information_case=LOAD_INFORMATION_MAIN,
                    pv_mapping_mode=PV_MAPPING_LINEAR,
                    settlement_mode=SETTLEMENT_MAIN,
                    value_cut_cache=cache,
                    year_end_soc_kwh=target,
                )
                last_end[key] = float(run.summary["soc_end_kwh"])
                runs.append(run)
                stem = dispatch_stem(
                    run.date,
                    run.strategy,
                    run.load_information_case,
                    run.pv_mapping_mode,
                    run.settlement_mode,
                    run.with_terminal_value,
                    run.year_end_soc_kwh,
                )
                run.dispatch[DISPATCH_COLS].to_csv(dispatch_dir / f"{stem}.csv", index=False)
                done += 1
                print(f"[{done}/{n_expected}] {run.run_id} cost={run.summary['total_cost_yuan']:.2f}", flush=True)

    daily = pd.DataFrame([run.summary for run in runs])
    daily.to_csv(out / "q3_terminal_soc_daily.csv", index=False)
    totals = strategy_totals(daily)
    totals.to_csv(out / "q3_terminal_soc_strategy_totals.csv", index=False)
    delta = boundary_delta(totals)
    delta.to_csv(out / "q3_terminal_soc_boundary_delta.csv", index=False)
    pd.concat([run.update_log for run in runs], ignore_index=True).to_csv(
        out / "q3_update_log.csv", index=False
    )
    pd.concat([run.ledger for run in runs], ignore_index=True).to_csv(
        out / "q3_settlement_ledger.csv", index=False
    )
    value_rows = []
    for key in sorted(cache):
        value_rows.extend(cache[key][1])
    if value_rows:
        pd.DataFrame(value_rows).to_csv(out / "q3_next_day_value_audit.csv", index=False)

    plot_terminal_soc_figures(daily, totals, runs)
    phys = physical_audit(runs, None)
    cont = continuity_audit(daily)
    audit = {
        "all_pass": bool(phys.get("all_pass") and cont.get("all_pass")),
        "physical": phys,
        "continuity": cont,
        "n_day_runs": len(runs),
        "n_paths": len(YEAR_END_BOUNDARIES) * len(STRATEGIES),
        "start_date": TERMINAL_SOC_PILOT_START,
        "end_date": TERMINAL_SOC_PILOT_END,
        "isolated_dec01_soc_kwh": E_INITIAL_KWH,
        "note": (
            "Dec 1 start SOC is an isolated 6000 kWh boundary, not the true annual Dec 1 SOC. "
            "This pilot does not choose A vs B."
        ),
    }
    (out / "q3_physical_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "n_runs": len(runs),
        "daily": daily,
        "totals": totals,
        "delta": delta,
        "audit": audit,
        "output_dir": str(out),
    }
