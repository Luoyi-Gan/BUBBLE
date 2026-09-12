#!/usr/bin/env python3
"""Export Q4-3 paper tables and figures from signed-off outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.export_paper_q2_q3 import (  # noqa: E402
    SAMPLE_DATE,
    SAMPLE_SLOTS,
    configure_style,
    fmt_num,
    load_adjust_row,
    load_charge_blocks,
    load_emergency_segments,
    load_purchase_row,
    save_figure,
    write_text,
)

RESULT43 = ROOT / "output" / "result4-3.xlsx"
WARMUP = ROOT / "output" / "q4" / "q4_3_warmup_daily.csv"
META = ROOT / "output" / "q4" / "q4_3_run_metadata.json"
Q3_STRATEGY = ROOT / "output" / "q3_full_annual" / "q3_annual_strategy_comparison.csv"
TABLES = ROOT / "paper" / "manuscript" / "tables" / "q4"
FIGURES = ROOT / "paper" / "overleaf" / "figures" / "q4"

Q3_ANNUAL_FIXED = 16_373_508.75
Q3_EXPORT_FIXED = 14_512_748.53


def load_cost_slices() -> tuple[pd.Series, pd.Series, pd.Series, float]:
    daily = pd.read_csv(WARMUP, parse_dates=["date"])
    jan = daily[daily["date"].dt.month == 1].sum(numeric_only=True)
    feb_frame = daily[(daily["date"] >= "2025-02-01") & (daily["date"] <= "2025-12-31")]
    feb = feb_frame.sum(numeric_only=True)
    full = daily.sum(numeric_only=True)
    feb1_soc = float(feb_frame.iloc[0]["soc_start_kwh"])
    return jan, feb, full, feb1_soc


def build_value_table(caption: str, label: str, col_title: str, mapping: dict[str, float]) -> str:
    rows = [(slot, fmt_num(mapping[slot])) for slot in SAMPLE_SLOTS]
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{{caption}}}\\label{{{label}}}",
        "\\normalsize\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}cccccc@{}}",
        "\\toprule",
        f"时间段 & {col_title} & 时间段 & {col_title} & 时间段 & {col_title} \\\\",
        "\\midrule",
    ]
    for i in range(0, 6, 3):
        chunk = rows[i : i + 3]
        lines.append(
            f"{chunk[0][0]} & {chunk[0][1]} & {chunk[1][0]} & {chunk[1][1]} & "
            f"{chunk[2][0]} & {chunk[2][1]} \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    return "\n".join(lines)


def export_tables() -> dict:
    TABLES.mkdir(parents=True, exist_ok=True)
    jan, feb, full, feb1_soc = load_cost_slices()
    meta = json.loads(META.read_text(encoding="utf-8"))
    m16 = pd.read_csv(Q3_STRATEGY)
    m16 = m16[(m16["strategy"] == "M1_M6") & (m16["year_end_boundary"] == "A_q2_aligned")].iloc[0]

    _, g0_vals, _, _ = load_purchase_row(RESULT43, "计划购电量", SAMPLE_DATE)
    gf_vals = load_adjust_row(RESULT43, SAMPLE_DATE)
    blocks, soc_start, soc_end = load_charge_blocks(RESULT43, SAMPLE_DATE)
    emergency = load_emergency_segments(RESULT43, SAMPLE_DATE)

    purchase_tex = build_value_table(
        f"问题四多时点调整策略（Q4-3）{SAMPLE_DATE} 计划购电量 $g^0$（交付时段实际价）",
        "tab:q4-3-purchase",
        "计划购电量",
        g0_vals,
    )
    adjust_tex = build_value_table(
        f"问题四多时点调整策略（Q4-3）{SAMPLE_DATE} 调整购电量 $g^F$（交付时段实际价）",
        "tab:q4-3-adjust",
        "调整购电量",
        gf_vals,
    )

    storage_lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{问题四多时点调整策略（Q4-3）{SAMPLE_DATE} 充放电量及日初/日末储电量}}\\label{{tab:q4-3-storage}}",
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

    emergency_lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{问题四多时点调整策略（Q4-3）{SAMPLE_DATE} 紧急购电记录}}\\label{{tab:q4-3-emergency}}",
        "\\normalsize\\setlength{\\tabcolsep}{6pt}",
        "\\begin{tabular}{@{}ccc@{}}",
        "\\toprule",
        "购电时间段 & 购电量 & 备注 \\\\",
        "\\midrule",
    ]
    for interval, amount in emergency[:6]:
        emergency_lines.append(f"{interval} & {fmt_num(amount)} & 紧急购电 \\\\")
    if len(emergency) > 6:
        emergency_lines.append(
            f"\\multicolumn{{3}}{{c}}{{其余 {len(emergency) - 6} 条记录见随附正式工作簿}} \\\\"
        )
    emergency_lines.extend(
        [
            "\\midrule",
            f"当日合计 & {fmt_num(sum(x for _, x in emergency))} & kWh \\\\",
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "",
        ]
    )

    cost_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{问题四多时点调整策略（Q4-3）成本分解（交付时段实际价；2--12 月为题设输出区间）}}\\label{{tab:q4-3-cost-summary}}
\\small\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{tabular}}{{@{{}}lrrrrr@{{}}}}
\\toprule
统计口径 & 天数 & 普通购电/元 & 调整费/元 & 紧急购电/元 & 总成本/元 \\\\
\\midrule
1 月预热（不计入题设输出） & 31 & {fmt_num(jan.normal_cost_yuan, 2)} & {fmt_num(jan.adjustment_cost_yuan, 2)} & {fmt_num(jan.emergency_cost_yuan, 2)} & {fmt_num(jan.total_cost_yuan, 2)} \\\\
2--12 月正式输出 & 334 & {fmt_num(feb.normal_cost_yuan, 2)} & {fmt_num(feb.adjustment_cost_yuan, 2)} & {fmt_num(feb.emergency_cost_yuan, 2)} & {fmt_num(feb.total_cost_yuan, 2)} \\\\
\\midrule
2--12 月紧急购电量/kWh & \\multicolumn{{5}}{{c}}{{{fmt_num(feb.emergency_kwh, 2)}}} \\\\
2--12 月调整次数 & \\multicolumn{{5}}{{c}}{{{int(feb.adjustment_count)}}} \\\\
2 月 1 日继承 SOC/kWh & \\multicolumn{{5}}{{c}}{{{fmt_num(feb1_soc, 4)}}} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    full_delta = float(full.total_cost_yuan) - Q3_ANNUAL_FIXED
    full_pct = 100.0 * full_delta / Q3_ANNUAL_FIXED
    export_delta = float(feb.total_cost_yuan) - Q3_EXPORT_FIXED
    export_pct = 100.0 * export_delta / Q3_EXPORT_FIXED
    adj_share = 100.0 * float(full.adjustment_cost_yuan) / float(full.total_cost_yuan)

    compare_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{多时点调整策略在固定价与交付价机制下的成本对照}}\\label{{tab:q4-3-mechanism-compare}}
\\footnotesize\\setlength{{\\tabcolsep}}{{2.5pt}}
\\begin{{tabular}}{{@{{}}lrrrrr@{{}}}}
\\toprule
方案 & 价格机制 & 1--12 月/元 & 2--12 月输出/元 & 紧急购电/元 & 调整次数 \\\\
\\midrule
问题三 & 固定价附件 1 & {fmt_num(Q3_ANNUAL_FIXED, 2)} & {fmt_num(Q3_EXPORT_FIXED, 2)} & {fmt_num(m16.emergency_cost_yuan, 2)} & {int(m16.adjustment_count)} \\\\
问题四调整策略 & 交付时段实际价 & {fmt_num(full.total_cost_yuan, 2)} & {fmt_num(feb.total_cost_yuan, 2)} & {fmt_num(full.emergency_cost_yuan, 2)} & {int(full.adjustment_count)} \\\\
\\midrule
1--12 月机制差 & \\multicolumn{{5}}{{c}}{{{fmt_num(full_delta, 2)} 元（{fmt_num(full_pct, 2)}\\%）；反映价格波动权重，非策略重选收益}} \\\\
2--12 月输出区间差 & \\multicolumn{{5}}{{c}}{{{fmt_num(export_delta, 2)} 元（{fmt_num(export_pct, 2)}\\%）}} \\\\
问题四调整费占全年 & \\multicolumn{{5}}{{c}}{{{fmt_num(full.adjustment_cost_yuan, 2)} 元（{fmt_num(adj_share, 2)}\\%）}} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    write_text(TABLES / "purchase_q43.tex", purchase_tex)
    write_text(TABLES / "adjust_q43.tex", adjust_tex)
    write_text(TABLES / "storage_q43.tex", "\n".join(storage_lines))
    write_text(TABLES / "emergency_q43.tex", "\n".join(emergency_lines))
    write_text(TABLES / "cost_summary_q43.tex", cost_tex)
    write_text(TABLES / "mechanism_compare_q43.tex", compare_tex)

    return {
        "annual_cost_yuan": float(meta["annual_cost_yuan"]),
        "export_window_yuan": float(feb.total_cost_yuan),
        "adjustment_count": int(full.adjustment_count),
        "adjustment_share_pct": adj_share,
    }


def export_figures() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    configure_style()
    daily = pd.read_csv(WARMUP, parse_dates=["date"])
    feb = daily[daily["date"] >= "2025-02-01"].copy()
    feb["month"] = feb["date"].dt.to_period("M").astype(str)
    monthly = feb.groupby("month", sort=True)[
        ["normal_cost_yuan", "adjustment_cost_yuan", "emergency_cost_yuan"]
    ].sum()

    fig, ax = plt.subplots(figsize=(8.8, 4.2))
    x = range(len(monthly))
    bottom = monthly["normal_cost_yuan"] / 1e6
    ax.bar(x, bottom, label="普通购电费")
    ax.bar(
        x,
        monthly["adjustment_cost_yuan"] / 1e6,
        bottom=bottom,
        label="调整费",
    )
    ax.bar(
        x,
        monthly["emergency_cost_yuan"] / 1e6,
        bottom=bottom + monthly["adjustment_cost_yuan"] / 1e6,
        label="紧急购电费",
    )
    ax.set_xticks(list(x), [m.replace("2025-", "") + "月" for m in monthly.index])
    ax.set_ylabel("成本 / 百万元")
    ax.set_title("多时点调整策略月度购电成本构成（2025 年 2--12 月）")
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, "fig_q4_3_monthly_cost", FIGURES)

    _jan, feb_sum, full, _feb1_soc = load_cost_slices()
    labels = ["1--12 月", "2--12 月输出"]
    q3_vals = [Q3_ANNUAL_FIXED, Q3_EXPORT_FIXED]
    q43_vals = [float(full.total_cost_yuan), float(feb_sum.total_cost_yuan)]
    width = 0.35
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.bar([i - width / 2 for i in range(2)], np.asarray(q3_vals) / 1e6, width, label="问题三固定价")
    ax.bar([i + width / 2 for i in range(2)], np.asarray(q43_vals) / 1e6, width, label="问题四交付价")
    ax.set_xticks([0, 1], labels)
    ax.set_ylabel("总成本 / 百万元")
    ax.set_title("多时点调整策略：同一策略、不同价格机制")
    ax.legend()
    fig.tight_layout()
    save_figure(fig, "fig_q4_3_mechanism_compare", FIGURES)


def main() -> None:
    summary = export_tables()
    export_figures()
    audit_path = ROOT / "paper" / "overleaf" / "paper_assets_audit.json"
    payload = {}
    if audit_path.exists():
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
    payload["q4_3"] = summary
    audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
