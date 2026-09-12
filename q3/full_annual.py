"""Official 365-day continuous-SOC runs for year-end boundaries A and B.

Each boundary is an independent annual campaign: every strategy starts at
6000 kWh on 2025-01-01 and carries its own SOC. Does not write result3.xlsx
or overwrite q3_pilot / q3_sensitivity / q3_terminal_soc_pilot.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from time import perf_counter

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from q3.config import (
    ANNUAL_END,
    ANNUAL_FIG_DIR,
    ANNUAL_OUTPUT_DIR,
    ANNUAL_START,
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    LOAD_INFORMATION_MAIN,
    PV_MAPPING_LINEAR,
    SETTLEMENT_MAIN,
    SIMULTANEOUS_CD_TOL,
    STRATEGIES,
    YEAR_END_BOUNDARIES,
    YEAR_END_BOUNDARY_A,
    YEAR_END_BOUNDARY_B,
    YEAR_END_SOC_A_KWH,
    YEAR_END_SOC_B_KWH,
    YEAR_N_DAYS,
    dispatch_stem,
    make_run_id,
)
from q3.data import Q3Data, write_input_audit
from q3.forecast import causal_load_sources
from q3.pilot import (
    NAVY,
    ORANGE,
    PURPLE,
    TEAL,
    ValueCutCache,
    run_day,
)
from q3.terminal_soc_pilot import DISPATCH_COLS, boundary_delta

plt.rcParams.update(
    {
        "font.sans-serif": ["Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 140,
    }
)

STRATEGY_COLORS = {
    "M0": NAVY,
    "M1_M6": TEAL,
    "M6_only": ORANGE,
    "M12_only": PURPLE,
    "M18_only": "#9c6644",
}

DAILY_CSV = "q3_annual_daily_summary.csv"
UPDATE_CSV = "q3_update_log.csv"
LEDGER_RAW_NAME = "period_ledger.csv"


def parse_boundaries(name: str | None) -> tuple[tuple[str, float], ...]:
    text = (name or "both").strip().lower()
    if text in {"both", "all", "ab", "a,b"}:
        return YEAR_END_BOUNDARIES
    if text in {"a", "a_q2_aligned", "1200"}:
        return ((YEAR_END_BOUNDARY_A, YEAR_END_SOC_A_KWH),)
    if text in {"b", "b_energy_neutral", "6000"}:
        return ((YEAR_END_BOUNDARY_B, YEAR_END_SOC_B_KWH),)
    raise ValueError(f"unknown year-end boundary {name!r}; use A, B, or both")


def annual_dates(data: Q3Data) -> list[str]:
    dates = [ts.strftime("%Y-%m-%d") for ts in data.dates]
    if len(dates) != YEAR_N_DAYS:
        raise ValueError(f"expected {YEAR_N_DAYS} dates, got {len(dates)}")
    if dates[0] != ANNUAL_START or dates[-1] != ANNUAL_END:
        raise ValueError(f"expected {ANNUAL_START}..{ANNUAL_END}, got {dates[0]}..{dates[-1]}")
    return dates


def write_annual_forecast_audit(data: Q3Data, path) -> pd.DataFrame:
    rows = []
    for i, ts in enumerate(data.dates):
        _hat, sources, label = causal_load_sources(data, i, i)
        max_source = int(max(sources)) if sources else -1
        rows.append(
            {
                "date": ts.strftime("%Y-%m-%d"),
                "day_index": i,
                "load_information_case": LOAD_INFORMATION_MAIN,
                "pv_mapping_mode": PV_MAPPING_LINEAR,
                "n_sources": len(sources),
                "source_dates": label,
                "used_attachment1_fallback": label == "attachment1_fallback",
                "history_end_exclusive_index": i,
                "max_source_index": max_source,
                "source_cutoff_ok": bool(max_source < i),
            }
        )
    frame = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def _append_csv(path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists() or path.stat().st_size == 0
    frame.to_csv(path, mode="a", header=header, index=False)


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
                "soc_start_jan01_kwh": float(block["soc_start_kwh"].iloc[0]),
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


def continuity_audit(daily: pd.DataFrame) -> dict:
    items = []
    all_pass = True
    ordered = daily.sort_values(["year_end_boundary", "strategy", "date"])
    for (strategy, boundary), block in ordered.groupby(["strategy", "year_end_boundary"], sort=False):
        starts = block["soc_start_kwh"].to_numpy()
        ends = block["soc_end_kwh"].to_numpy()
        dates = block["date"].to_numpy()
        max_gap = float(np.max(np.abs(starts[1:] - ends[:-1]))) if len(block) > 1 else 0.0
        start_ok = abs(float(starts[0]) - E_INITIAL_KWH) <= 1e-5
        end_target = float(block["year_end_soc_kwh"].iloc[0])
        end_ok = abs(float(ends[-1]) - end_target) <= 1e-5
        n_ok = (
            len(block) == YEAR_N_DAYS
            and str(dates[0]) == ANNUAL_START
            and str(dates[-1]) == ANNUAL_END
        )
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


def plot_annual_figures(daily: pd.DataFrame, totals: pd.DataFrame) -> None:
    fig_dir = ANNUAL_FIG_DIR
    fig_dir.mkdir(parents=True, exist_ok=True)
    present = [name for name, _target in YEAR_END_BOUNDARIES if name in set(totals["year_end_boundary"])]
    colors = {YEAR_END_BOUNDARY_A: NAVY, YEAR_END_BOUNDARY_B: TEAL}
    x = np.arange(len(STRATEGIES))
    width = 0.36 if len(present) > 1 else 0.55
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    bottoms = {name: np.zeros(len(STRATEGIES)) for name in present}
    for component, alpha, hatch in (
        ("settlement_cost_yuan", 1.0, None),
        ("emergency_cost_yuan", 0.55, "//"),
    ):
        for i, boundary in enumerate(present):
            subset = totals[totals["year_end_boundary"] == boundary].set_index("strategy").loc[list(STRATEGIES)]
            offset = (i - 0.5) * width if len(present) > 1 else 0.0
            ax.bar(
                x + offset,
                subset[component],
                width=width,
                bottom=bottoms[boundary],
                color=colors[boundary],
                alpha=alpha,
                hatch=hatch,
                label=f"{boundary} / {component.split('_')[0]}",
            )
            bottoms[boundary] = bottoms[boundary] + subset[component].to_numpy()
    ax.set_xticks(x)
    ax.set_xticklabels(STRATEGIES)
    ax.set_ylabel("annual purchase cost (yuan)")
    ax.set_title("Q3 annual main path: year-end A=1200 vs B=6000 (settlement + emergency)")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig3_annual_strategy_cost_decomposition.png")
    plt.close(fig)

    ordered = daily.sort_values("date")
    dates = list(dict.fromkeys(ordered["date"]))
    x_dates = np.arange(len(dates))
    xtick = list(range(0, len(dates), 20))
    fig, axes = plt.subplots(len(present), 1, figsize=(10.2, 3.6 * len(present)), sharex=True)
    if len(present) == 1:
        axes = [axes]
    for ax, boundary in zip(axes, present):
        for strategy in STRATEGIES:
            block = daily[
                (daily["year_end_boundary"] == boundary) & (daily["strategy"] == strategy)
            ].sort_values("date")
            ax.plot(x_dates, block["soc_end_kwh"], color=STRATEGY_COLORS[strategy], lw=1.15, label=strategy)
        ax.axhline(E_MIN_KWH, color=ORANGE, ls="--", lw=0.8)
        ax.axhline(E_MAX_KWH, color=ORANGE, ls="--", lw=0.8)
        ax.axhline(E_INITIAL_KWH, color="#888888", ls=":", lw=0.8)
        ax.set_ylabel("end-of-day SOC (kWh)")
        ax.set_title(boundary)
        ax.legend(frameon=False, ncol=5, fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xticks(xtick)
        ax.set_xticklabels([dates[i][5:] for i in xtick], rotation=60)
    axes[-1].set_xlabel("date")
    fig.suptitle("Annual continuous SOC paths (main mapping/settlement)", fontsize=12)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig3_annual_soc_paths.png")
    plt.close(fig)

    month = pd.to_datetime(daily["date"]).dt.to_period("M").astype(str)
    work = daily.copy()
    work["month"] = month
    monthly = (
        work.groupby(["month", "strategy", "year_end_boundary"], as_index=False)[
            ["emergency_cost_yuan", "curtailment_kwh"]
        ].sum()
    )
    months = list(dict.fromkeys(monthly["month"]))
    xm = np.arange(len(months))
    fig, axes = plt.subplots(2, 1, figsize=(10.2, 7.0), sharex=True)
    for ax, (column, ylabel) in zip(
        axes,
        (("emergency_cost_yuan", "emergency cost (yuan)"), ("curtailment_kwh", "curtailment (kWh)")),
    ):
        for strategy in STRATEGIES:
            styles = {YEAR_END_BOUNDARY_A: "-", YEAR_END_BOUNDARY_B: "--"}
            for boundary in present:
                block = monthly[
                    (monthly["year_end_boundary"] == boundary) & (monthly["strategy"] == strategy)
                ].set_index("month").reindex(months)
                ax.plot(
                    xm,
                    block[column],
                    color=STRATEGY_COLORS[strategy],
                    ls=styles.get(boundary, "-"),
                    lw=1.2,
                    label=f"{strategy} / {boundary.split('_')[0]}",
                )
        ax.set_ylabel(ylabel)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xticks(xm)
        ax.set_xticklabels(months, rotation=45)
    axes[0].legend(frameon=False, ncol=2, fontsize=7)
    fig.suptitle("Monthly emergency cost and curtailment (main path; dashed = B)", fontsize=12)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig3_annual_monthly_emergency_curtailment.png")
    plt.close(fig)
    monthly.to_csv(ANNUAL_OUTPUT_DIR / "q3_annual_monthly.csv", index=False)


def _physical_from_daily(daily: pd.DataFrame) -> dict:
    recs = []
    all_pass = True
    for _, row in daily.iterrows():
        ok = bool(
            float(row["max_balance_residual_kwh"]) < 1e-5
            and float(row["max_soc_residual_kwh"]) < 1e-5
            and float(row["max_simultaneous_cd_kwh2"]) <= SIMULTANEOUS_CD_TOL
            and int(row["locked_period_violations"]) == 0
        )
        all_pass = all_pass and ok
        if not ok:
            recs.append(
                {
                    "run_id": row["run_id"],
                    "date": row["date"],
                    "strategy": row["strategy"],
                    "year_end_boundary": row["year_end_boundary"],
                    "max_balance_residual_kwh": float(row["max_balance_residual_kwh"]),
                    "max_soc_residual_kwh": float(row["max_soc_residual_kwh"]),
                    "max_simultaneous_cd_kwh2": float(row["max_simultaneous_cd_kwh2"]),
                    "locked_period_violations": int(row["locked_period_violations"]),
                    "pass": False,
                }
            )
    return {"all_pass": all_pass, "n_failed_days": len(recs), "failures": recs}


def run_q3_full_annual(
    data: Q3Data,
    boundaries: Iterable[tuple[str, float]] | None = None,
) -> dict:
    out = ANNUAL_OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    dispatch_dir = out / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    ledger_raw = out / "ledger_raw"
    ledger_raw.mkdir(parents=True, exist_ok=True)
    ANNUAL_FIG_DIR.mkdir(parents=True, exist_ok=True)
    write_input_audit(data, out / "input_audit.json")
    dates = annual_dates(data)
    write_annual_forecast_audit(data, out / "q3_annual_forecast_audit.csv")

    selected = tuple(boundaries) if boundaries is not None else YEAR_END_BOUNDARIES
    daily_path = out / DAILY_CSV
    update_path = out / UPDATE_CSV
    existing = pd.read_csv(daily_path) if daily_path.exists() else pd.DataFrame()
    completed = set(existing["run_id"].astype(str)) if len(existing) else set()
    cache: ValueCutCache = {}
    started = perf_counter()
    n_expected = len(selected) * len(STRATEGIES) * len(dates)
    done = 0

    for boundary, target in selected:
        print(f"===== year-end {boundary} target={target:.0f} kWh =====", flush=True)
        ledger_path = ledger_raw / f"{boundary}_{LEDGER_RAW_NAME}"
        for strategy in STRATEGIES:
            soc = E_INITIAL_KWH
            for date in dates:
                run_id = make_run_id(
                    date,
                    strategy,
                    LOAD_INFORMATION_MAIN,
                    PV_MAPPING_LINEAR,
                    SETTLEMENT_MAIN,
                    True,
                    target,
                )
                done += 1
                if run_id in completed:
                    row = existing[existing["run_id"] == run_id].iloc[-1]
                    soc = float(row["soc_end_kwh"])
                    print(f"[{done}/{n_expected}] skip {run_id}", flush=True)
                    continue
                day_index = data.date_index(date)
                run = run_day(
                    data,
                    day_index,
                    strategy,
                    soc,
                    with_terminal_value=True,
                    load_information_case=LOAD_INFORMATION_MAIN,
                    pv_mapping_mode=PV_MAPPING_LINEAR,
                    settlement_mode=SETTLEMENT_MAIN,
                    value_cut_cache=cache,
                    year_end_soc_kwh=target,
                )
                soc = float(run.summary["soc_end_kwh"])
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
                _append_csv(daily_path, pd.DataFrame([run.summary]))
                _append_csv(update_path, run.update_log)
                period = run.ledger[run.ledger["row_role"] == "period_total"]
                _append_csv(ledger_path, period)
                completed.add(run_id)
                print(
                    f"[{done}/{n_expected}] {run.run_id} "
                    f"cost={run.summary['total_cost_yuan']:.2f} "
                    f"soc_end={soc:.4f}",
                    flush=True,
                )

    daily = pd.read_csv(daily_path)
    daily = daily.drop_duplicates("run_id", keep="last")
    daily = daily.sort_values(["year_end_boundary", "strategy", "date"])
    daily.to_csv(daily_path, index=False)
    totals = strategy_totals(daily)
    totals.to_csv(out / "q3_annual_strategy_comparison.csv", index=False)
    if set(daily["year_end_boundary"]) >= {YEAR_END_BOUNDARY_A, YEAR_END_BOUNDARY_B}:
        delta = boundary_delta(totals)
        delta.to_csv(out / "q3_annual_boundary_delta.csv", index=False)
    else:
        delta = pd.DataFrame()
    value_rows = []
    for key in sorted(cache):
        value_rows.extend(cache[key][1])
    if value_rows:
        pd.DataFrame(value_rows).to_csv(out / "q3_next_day_value_audit.csv", index=False)

    plot_annual_figures(daily, totals)
    phys = _physical_from_daily(daily)
    cont = continuity_audit(daily)
    audit = {
        "all_pass": bool(phys.get("all_pass") and cont.get("all_pass")),
        "physical": phys,
        "continuity": cont,
        "n_day_runs": int(len(daily)),
        "n_paths": int(daily.groupby(["strategy", "year_end_boundary"]).ngroups),
        "start_date": ANNUAL_START,
        "end_date": ANNUAL_END,
        "jan01_soc_kwh": E_INITIAL_KWH,
        "pv_mapping_mode": PV_MAPPING_LINEAR,
        "settlement_mode": SETTLEMENT_MAIN,
        "load_information_case": LOAD_INFORMATION_MAIN,
        "boundaries_run": [name for name, _target in selected],
        "note": (
            "A and B are independent 365-day campaigns. "
            "This archive does not choose a single official year-end boundary "
            "and does not write result3.xlsx. Mapping/settlement annual "
            "sensitivities are not included in this run."
        ),
        "elapsed_seconds_this_process": float(perf_counter() - started),
    }
    (out / "q3_annual_physical_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "n_runs": int(len(daily)),
        "daily": daily,
        "totals": totals,
        "delta": delta,
        "audit": audit,
        "output_dir": str(out),
    }
