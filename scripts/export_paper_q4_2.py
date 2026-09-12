#!/usr/bin/env python3
"""Export Q4-2 paper tables and figures from signed-off outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.export_paper_q2_q3 import (  # noqa: E402
    SAMPLE_DATE,
    SAMPLE_SLOTS,
    configure_style,
    fmt_num,
    latex_code,
    load_charge_blocks,
    load_purchase_row,
    render_triplet_table,
    save_figure,
    write_text,
)

RESULT42 = ROOT / "output" / "result4-2.xlsx"
WARMUP = ROOT / "output" / "q4" / "q4_2_warmup_daily.csv"
K_REVIEW = ROOT / "output" / "q4" / "q4_2_k_review.json"
PRICE_MONTHLY = ROOT / "output" / "q4" / "q4_price_forecast_monthly.csv"
META = ROOT / "output" / "q4" / "q4_2_run_metadata.json"
TABLES = ROOT / "paper" / "manuscript" / "tables" / "q4"
FIGURES = ROOT / "paper" / "overleaf" / "figures" / "q4"


def load_cost_slices() -> tuple[pd.Series, pd.Series]:
    daily = pd.read_csv(WARMUP)
    daily["date"] = pd.to_datetime(daily["date"])
    jan = daily[daily["date"].dt.month == 1]
    feb_dec = daily[(daily["date"] >= "2025-02-01") & (daily["date"] <= "2025-12-31")]
    return jan.sum(numeric_only=True), feb_dec.sum(numeric_only=True)


def export_tables() -> dict:
    TABLES.mkdir(parents=True, exist_ok=True)
    jan, feb = load_cost_slices()
    meta = json.loads(META.read_text(encoding="utf-8"))
    k_meta = json.loads(K_REVIEW.read_text(encoding="utf-8"))
    k_rows = []
    for k in k_meta["k_candidates"]:
        row = k_meta["by_k"][str(k)]
        conclusion = latex_code("retain_k8_stable" if k == k_meta["decision"]["keep_k"] else "review_only")
        k_rows.append(
            f"$K={k}$ & {int(row['n_windows'])} & "
            f"{fmt_num(row['total_cost_yuan'], 2)} & "
            f"{fmt_num(row['total_emergency_fee_yuan'], 2)} & "
            f"{fmt_num(row['mean_elapsed_seconds'], 1)} & {conclusion} \\\\"
        )
    _, purchase_vals, day_q, day_fee = load_purchase_row(RESULT42, "计划购电量", SAMPLE_DATE)
    blocks, soc_start, soc_end = load_charge_blocks(RESULT42, SAMPLE_DATE)

    purchase_rows = [(slot, fmt_num(purchase_vals[slot])) for slot in SAMPLE_SLOTS]
    purchase_tex = render_triplet_table(
        f"问题四（Q4-2）{SAMPLE_DATE} 计划购电量及全天汇总（波动电价；$K=8$）",
        "tab:q4-purchase",
        "购电量",
        purchase_rows,
        footer=("全天购电量", fmt_num(day_q), "全天购电费", fmt_num(day_fee)),
    )

    storage_lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{问题四（Q4-2）{SAMPLE_DATE} 充放电量及日初/日末储电量}}\\label{{tab:q4-storage}}",
        "\\normalsize\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}cccccc@{}}",
        "\\toprule",
        "时间段 & 充电量 & 放电量 & 时间段 & 充电量 & 放电量 \\\\",
        "\\midrule",
    ]
    for i in range(0, 6, 2):
        b0, b1 = blocks[i], blocks[i + 1]
        storage_lines.append(
            f"{b0[0]} & {fmt_num(b0[1])} & {fmt_num(b0[2])} & "
            f"{b1[0]} & {fmt_num(b1[1])} & {fmt_num(b1[2])} \\\\"
        )
    storage_lines.extend(
        [
            f"0:00 储电量 & \\multicolumn{{2}}{{c}}{{{fmt_num(soc_start)}}} & "
            f"24:00 储电量 & \\multicolumn{{2}}{{c}}{{{fmt_num(soc_end)}}} \\\\",
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "",
        ]
    )

    cost_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{问题四（Q4-2）年度成本分解（交付时段实际价结算；2--12 月为题设输出区间）}}\\label{{tab:q4-cost-summary}}
\\normalsize\\setlength{{\\tabcolsep}}{{6pt}}
\\begin{{tabular}}{{@{{}}lrrrr@{{}}}}
\\toprule
统计口径 & 天数 & 计划购电费/元 & 紧急购电费/元 & 总成本/元 \\\\
\\midrule
1 月预热（不计入题设输出） & 31 & {fmt_num(jan.normal_cost_yuan, 2)} & {fmt_num(jan.emergency_cost_yuan, 2)} & {fmt_num(jan.total_cost_yuan, 2)} \\\\
2--12 月正式输出 & 334 & {fmt_num(feb.normal_cost_yuan, 2)} & {fmt_num(feb.emergency_cost_yuan, 2)} & {fmt_num(feb.total_cost_yuan, 2)} \\\\
\\midrule
2--12 月紧急购电量/kWh & \\multicolumn{{4}}{{c}}{{{fmt_num(feb.emergency_kwh, 2)}}} \\\\
2 月 1 日继承 SOC/kWh & \\multicolumn{{4}}{{c}}{{{fmt_num(feb.soc_start_kwh, 4)}}} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    param_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{问题四（Q4-2）情景数 $K$ 的闭环复核（与正式部署同一 $\\alpha$ 校准协议）}}\\label{{tab:q4-parameter}}
\\normalsize\\setlength{{\\tabcolsep}}{{5pt}}
\\begin{{tabular}}{{@{{}}crrrrl@{{}}}}
\\toprule
$K$ & 窗口数 & 验证总成本/元 & 验证紧急费/元 & 平均耗时/s & 结论 \\\\
\\midrule
{chr(10).join(k_rows)}\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    annual = pd.read_csv(PRICE_MONTHLY)
    annual = annual[annual["year_month"] != "2025-annual"]
    price_rows = []
    for _, row in annual.iterrows():
        price_rows.append(
            f"{row.year_month} & {fmt_num(row.day_ahead_mae, 4)} & "
            f"{fmt_num(row.day_ahead_rmse, 4)} & {fmt_num(row.mpc_remaining_mae_mean, 4)} \\\\"
        )
    price_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{Q4-2 价格预测误差（逐月；单位：元/kWh）}}\\label{{tab:q4-price-error}}
\\normalsize\\setlength{{\\tabcolsep}}{{6pt}}
\\begin{{tabular}}{{@{{}}lrrr@{{}}}}
\\toprule
月份 & 日初 MAE & 日初 RMSE & 日内剩余 MAE均值 \\\\
\\midrule
{chr(10).join(price_rows)}\\midrule
全年 & {fmt_num(annual['day_ahead_mae'].mean(), 4)} & {fmt_num(annual['day_ahead_rmse'].mean(), 4)} & {fmt_num(annual['mpc_remaining_mae_mean'].mean(), 4)} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    write_text(TABLES / "purchase.tex", purchase_tex)
    write_text(TABLES / "storage.tex", "\n".join(storage_lines))
    write_text(TABLES / "cost_summary.tex", cost_tex)
    write_text(TABLES / "parameter_selection.tex", param_tex)
    write_text(TABLES / "price_forecast_error.tex", price_tex)

    return {
        "annual_cost_yuan": float(meta["annual_cost_yuan"]),
        "export_window_yuan": float(meta["export_window_cost_yuan"]),
        "feb_dec_emergency_kwh": float(feb.emergency_kwh),
    }


def export_figures() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    configure_style()
    daily = pd.read_csv(WARMUP)
    daily["date"] = pd.to_datetime(daily["date"])
    feb = daily[daily["date"] >= "2025-02-01"].copy()
    feb["month"] = feb["date"].dt.to_period("M").astype(str)
    monthly = feb.groupby("month", sort=True)[["normal_cost_yuan", "emergency_cost_yuan"]].sum()

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    x = range(len(monthly))
    ax.bar(x, monthly["normal_cost_yuan"], label="计划购电（按 $pq$）")
    ax.bar(x, monthly["emergency_cost_yuan"], bottom=monthly["normal_cost_yuan"], label="紧急购电（按 $5pe$）")
    ax.set_xticks(list(x), monthly.index, rotation=45, ha="right")
    ax.set_ylabel("成本 / 元")
    ax.set_title("Q4-2：2025 年 2--12 月月度购电成本构成")
    ax.legend()
    fig.tight_layout()
    save_figure(fig, "fig_q4_monthly_cost", FIGURES)

    price = pd.read_csv(PRICE_MONTHLY)
    price = price[price["year_month"] != "2025-annual"]
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    ax.plot(price["year_month"], price["day_ahead_mae"], marker="o", label="日初 MAE")
    ax.plot(price["year_month"], price["mpc_remaining_mae_mean"], marker="s", label="日内剩余 MAE均值")
    ax.set_ylabel("误差 / 元·kWh$^{-1}$")
    ax.set_title("Q4-2：价格预测误差（逐月）")
    ax.tick_params(axis="x", rotation=45)
    ax.legend()
    fig.tight_layout()
    save_figure(fig, "fig_q4_price_error", FIGURES)


def main() -> None:
    summary = export_tables()
    export_figures()
    audit_path = ROOT / "paper" / "overleaf" / "paper_assets_audit.json"
    payload = {}
    if audit_path.exists():
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
    payload["q4_2"] = summary
    audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
