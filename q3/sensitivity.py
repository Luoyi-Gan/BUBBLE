"""Two-day RQ3-2 / RQ3-4 / RQ3-5 sensitivity trial. Does not write q3_pilot/."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from q3.config import (
    E_INITIAL_KWH,
    LOAD_INFORMATION_MAIN,
    OUTPUT_DIR,
    PILOT_DATES,
    PV_MAPPING_LINEAR,
    PV_MAPPING_MODES,
    PV_MAPPING_STEP,
    SENSITIVITY_FIG_DIR,
    SENSITIVITY_OUTPUT_DIR,
    SETTLEMENT_MAIN,
    SETTLEMENT_MODES,
    STRATEGIES,
    WARMUP_CSV_MAIN,
    dispatch_stem,
)
from q3.data import Q3Data, write_input_audit
from q3.forecast import write_forecast_mapping_modes
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

COMBOS = tuple((pv, settle) for pv in PV_MAPPING_MODES for settle in SETTLEMENT_MODES)
BASELINE = (PV_MAPPING_LINEAR, SETTLEMENT_MAIN)


def load_causal_warmup_soc(data: Q3Data) -> dict[str, float]:
    feb_index = data.date_index("2025-02-01")
    warmup_path = OUTPUT_DIR / WARMUP_CSV_MAIN
    if not warmup_path.exists():
        raise FileNotFoundError(
            f"Need accepted causal warmup at {warmup_path} so sensitivity SOC matches the signed-off main case"
        )
    warmup = pd.read_csv(warmup_path)
    if len(warmup) < feb_index:
        raise ValueError("causal warmup file is shorter than January")
    return {
        "2025-02-01": float(warmup["soc_end_kwh"].iloc[feb_index - 1]),
        "2025-06-21": E_INITIAL_KWH,
    }


def plot_sensitivity_figures(comparison: pd.DataFrame, mapping: pd.DataFrame) -> None:
    SENSITIVITY_FIG_DIR.mkdir(parents=True, exist_ok=True)
    labels = [f"{pv.split('_')[0]}\n+ {settle.split('_')[0]}" for pv, settle in COMBOS]
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.4), sharey=False)
    x = np.arange(len(STRATEGIES))
    width = 0.18
    colors = (NAVY, TEAL, ORANGE, PURPLE)
    for ax, date in zip(axes, PILOT_DATES):
        for i, (pv, settle) in enumerate(COMBOS):
            subset = comparison[
                (comparison["date"] == date)
                & (comparison["pv_mapping_mode"] == pv)
                & (comparison["settlement_mode"] == settle)
            ].set_index("strategy").loc[list(STRATEGIES)]
            ax.bar(
                x + (i - 1.5) * width,
                subset["total_cost_yuan"],
                width=width,
                color=colors[i],
                label=f"{pv} / {settle}" if date == PILOT_DATES[0] else None,
            )
        ax.set_xticks(x)
        ax.set_xticklabels(STRATEGIES, rotation=20, ha="right")
        ax.set_title(date)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("total purchase cost (yuan)")
    fig.legend(frameon=False, loc="upper center", ncol=2, fontsize=8, bbox_to_anchor=(0.5, 1.12))
    fig.suptitle("Q3 sensitivity: PV mapping × settlement (causal_load_main)", y=1.18, fontsize=12)
    fig.tight_layout()
    fig.savefig(SENSITIVITY_FIG_DIR / "fig3_sensitivity_four_combo_cost.png", bbox_inches="tight")
    plt.close(fig)

    # 6:00-7:00 zoom for both mapping modes on both dates (issue 6:00, periods 36-41).
    fig, axes = plt.subplots(2, 1, figsize=(8.4, 6.2), sharex=True)
    clocks = ["06:10", "06:20", "06:30", "06:40", "06:50", "07:00"]
    for ax, date in zip(axes, PILOT_DATES):
        for mode, color, ls in (
            (PV_MAPPING_LINEAR, NAVY, "-"),
            (PV_MAPPING_STEP, ORANGE, "--"),
        ):
            block = mapping[
                (mapping["date"] == date)
                & (mapping["update_time"] == "06:00")
                & (mapping["pv_mapping_mode"] == mode)
                & (mapping["period"].between(36, 41))
            ].sort_values("period")
            ax.plot(
                clocks,
                block["forecast_kwh"],
                color=color,
                ls=ls,
                marker="o",
                lw=1.4,
                label=mode,
            )
        actual = mapping[
            (mapping["date"] == date)
            & (mapping["update_time"] == "06:00")
            & (mapping["pv_mapping_mode"] == PV_MAPPING_LINEAR)
            & (mapping["period"].between(36, 41))
        ].sort_values("period")
        ax.plot(clocks, actual["actual_pv_kwh"], color=TEAL, ls=":", marker="x", lw=1.1, label="actual PV (not a forecast)")
        ax.set_ylabel("kWh / 10 min")
        ax.set_title(f"{date} 6:00 issue, first forecast hour")
        ax.legend(frameon=False, fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[1].set_xlabel("period end")
    fig.suptitle("PV mapping zoom: linear_anchor_main vs step_hourly_sensitivity", fontsize=12)
    fig.tight_layout()
    fig.savefig(SENSITIVITY_FIG_DIR / "fig3_sensitivity_mapping_6h_zoom.png")
    plt.close(fig)


def run_q3_sensitivity(data: Q3Data) -> dict:
    out = SENSITIVITY_OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    SENSITIVITY_FIG_DIR.mkdir(parents=True, exist_ok=True)
    write_input_audit(data, out / "input_audit.json")
    mapping = write_forecast_mapping_modes(data, out / "q3_forecast_mapping.csv")

    initial = load_causal_warmup_soc(data)
    cache: ValueCutCache = {}
    runs: list[DayRun] = []
    for date in PILOT_DATES:
        i = data.date_index(date)
        soc0 = initial[date]
        for pv_mode, settle_mode in COMBOS:
            for strategy in STRATEGIES:
                runs.append(
                    run_day(
                        data,
                        i,
                        strategy,
                        soc0,
                        with_terminal_value=True,
                        load_information_case=LOAD_INFORMATION_MAIN,
                        pv_mapping_mode=pv_mode,
                        settlement_mode=settle_mode,
                        value_cut_cache=cache,
                    )
                )

    comparison = pd.DataFrame([run.summary for run in runs])
    baseline = comparison[
        (comparison["pv_mapping_mode"] == BASELINE[0])
        & (comparison["settlement_mode"] == BASELINE[1])
    ][["date", "strategy", "total_cost_yuan", "settlement_cost_yuan", "emergency_cost_yuan"]].rename(
        columns={
            "total_cost_yuan": "baseline_total_yuan",
            "settlement_cost_yuan": "baseline_settlement_yuan",
            "emergency_cost_yuan": "baseline_emergency_yuan",
        }
    )
    comparison = comparison.merge(baseline, on=["date", "strategy"], how="left")
    comparison["delta_total_vs_baseline_yuan"] = (
        comparison["total_cost_yuan"] - comparison["baseline_total_yuan"]
    )
    comparison["delta_settlement_vs_baseline_yuan"] = (
        comparison["settlement_cost_yuan"] - comparison["baseline_settlement_yuan"]
    )
    comparison["delta_emergency_vs_baseline_yuan"] = (
        comparison["emergency_cost_yuan"] - comparison["baseline_emergency_yuan"]
    )
    comparison.to_csv(out / "q3_sensitivity_comparison.csv", index=False)
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
        "price",
        "phi_yuan",
        "emergency_cost_yuan",
        "run_id",
        "pv_mapping_mode",
        "settlement_mode",
    ]
    for run in runs:
        stem = dispatch_stem(
            run.date,
            run.strategy,
            run.load_information_case,
            run.pv_mapping_mode,
            run.settlement_mode,
            run.with_terminal_value,
        )
        run.dispatch[dispatch_cols].to_csv(out / f"{stem}.csv", index=False)

    plot_sensitivity_figures(comparison, mapping)
    audit = physical_audit(runs, initial["2025-02-01"])
    (out / "q3_physical_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "initial_soc": initial,
        "comparison": comparison,
        "audit": audit,
        "n_runs": len(runs),
        "output_dir": str(out),
    }
