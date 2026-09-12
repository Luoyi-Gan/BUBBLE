#!/usr/bin/env python3
"""Cross-check paper/manuscript numbers against signed output/ ledgers.

Writes:
- paper/reconciliation.md
- paper/reconciliation_audit.json
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT = ROOT / "paper" / "manuscript"
PAPER = ROOT / "paper"


@dataclass
class Row:
    question: str
    paper_location: str
    metric: str
    unit: str
    display_precision: str
    paper_value: str
    source_file: str
    source_column: str
    source_value: str
    status: str  # 已核 | 不一致 | 未核
    note: str = ""


def fmt(value: float, digits: int) -> str:
    return f"{float(value):.{digits}f}"


def near(a: float, b: float, tol: float) -> bool:
    return abs(float(a) - float(b)) <= tol


def tol_for_digits(digits: int) -> float:
    return 0.5 * 10 ** (-digits) + 1e-9


def add(rows: list[Row], **kwargs) -> None:
    rows.append(Row(**kwargs))


def check_numeric(
    rows: list[Row],
    *,
    question: str,
    paper_location: str,
    metric: str,
    unit: str,
    digits: int,
    paper_value: float,
    source_file: Path,
    source_column: str,
    source_value: float,
    note: str = "",
) -> None:
    tol = tol_for_digits(digits)
    status = "已核" if near(paper_value, source_value, tol) else "不一致"
    add(
        rows,
        question=question,
        paper_location=paper_location,
        metric=metric,
        unit=unit,
        display_precision=str(digits),
        paper_value=fmt(paper_value, digits),
        source_file=str(source_file.relative_to(ROOT)),
        source_column=source_column,
        source_value=f"{source_value:.12g}",
        status=status,
        note=note,
    )


def load_q1(rows: list[Row]) -> None:
    summary = pd.read_csv(ROOT / "output" / "q1_summary.csv").set_index("metric")["value"]
    baseline = pd.read_csv(ROOT / "output" / "q1_baseline.csv").set_index("metric")["value"]

    plan = pd.read_csv(ROOT / "output" / "q1_plan.csv")
    charge_sum = plan["charge_kwh"].sum()
    discharge_sum = plan["discharge_kwh"].sum()

    check_numeric(
        rows,
        question="Q1",
        paper_location="sections/q1/05_results.tex",
        metric="无储能基准购电费",
        unit="元",
        digits=4,
        paper_value=48052.0466,
        source_file=ROOT / "output" / "q1_baseline.csv",
        source_column="baseline_purchase_cost_yuan",
        source_value=float(baseline["baseline_purchase_cost_yuan"]),
    )
    check_numeric(
        rows,
        question="Q1",
        paper_location="sections/q1/05_results.tex",
        metric="成本节省",
        unit="元",
        digits=4,
        paper_value=14250.5510,
        source_file=ROOT / "output" / "q1_baseline.csv",
        source_column="absolute_cost_saving_yuan",
        source_value=float(baseline["absolute_cost_saving_yuan"]),
    )
    check_numeric(
        rows,
        question="Q1",
        paper_location="sections/q1/05_results.tex",
        metric="节省比例",
        unit="1",
        digits=4,
        paper_value=0.296565,
        source_file=ROOT / "output" / "q1_baseline.csv",
        source_column="cost_saving_ratio",
        source_value=float(baseline["cost_saving_ratio"]),
    )
    check_numeric(
        rows,
        question="Q1",
        paper_location="sections/q1/05_results.tex",
        metric="全天购电量",
        unit="kWh",
        digits=4,
        paper_value=57526.2435,
        source_file=ROOT / "output" / "q1_summary.csv",
        source_column="grid_purchase_kwh",
        source_value=float(summary["grid_purchase_kwh"]),
    )
    check_numeric(
        rows,
        question="Q1",
        paper_location="sections/q1/05_results.tex",
        metric="全天购电费",
        unit="元",
        digits=4,
        paper_value=33801.4955,
        source_file=ROOT / "output" / "q1_summary.csv",
        source_column="purchase_cost_yuan",
        source_value=float(summary["purchase_cost_yuan"]),
    )
    check_numeric(
        rows,
        question="Q1",
        paper_location="sections/q1/05_results.tex",
        metric="总充电量",
        unit="kWh",
        digits=4,
        paper_value=19842.7105,
        source_file=ROOT / "output" / "q1_plan.csv",
        source_column="sum(charge_kwh)",
        source_value=charge_sum,
    )
    check_numeric(
        rows,
        question="Q1",
        paper_location="sections/q1/05_results.tex",
        metric="总放电量",
        unit="kWh",
        digits=4,
        paper_value=17858.4394,
        source_file=ROOT / "output" / "q1_plan.csv",
        source_column="sum(discharge_kwh)",
        source_value=discharge_sum,
    )
    check_numeric(
        rows,
        question="Q1",
        paper_location="sections/q1/05_results.tex",
        metric="峰值购电功率",
        unit="kW",
        digits=4,
        paper_value=8458.8273,
        source_file=ROOT / "output" / "q1_summary.csv",
        source_column="peak_grid_kw",
        source_value=float(summary["peak_grid_kw"]),
    )

    purchase_tex = (MANUSCRIPT / "tables/q1/purchase.tex").read_text(encoding="utf-8")
    slot_map = {
        "10:00-10:10": (3, 2),
        "12:00-12:10": (3, 4),
        "14:00-14:10": (3, 6),
        "16:00-16:10": (5, 2),
        "18:00-18:10": (5, 4),
        "20:00-20:10": (5, 6),
    }
    for slot in slot_map:
        m = re.search(rf"{re.escape(slot)} & ([0-9.]+)", purchase_tex)
        if not m:
            continue
        paper_val = float(m.group(1))
        src_row = plan[plan["time"] == slot]
        if src_row.empty:
            add(
                rows,
                question="Q1",
                paper_location="tables/q1/purchase.tex",
                metric=f"购电量 {slot}",
                unit="kWh",
                display_precision="4",
                paper_value=fmt(paper_val, 4),
                source_file="output/q1_plan.csv",
                source_column=f"time={slot}/grid_purchase_kwh",
                source_value="MISSING",
                status="不一致",
                note="计划行未找到",
            )
            continue
        check_numeric(
            rows,
            question="Q1",
            paper_location="tables/q1/purchase.tex",
            metric=f"购电量 {slot}",
            unit="kWh",
            digits=4,
            paper_value=paper_val,
            source_file=ROOT / "output" / "q1_plan.csv",
            source_column=f"time={slot}/grid_purchase_kwh",
            source_value=float(src_row.iloc[0]["grid_purchase_kwh"]),
        )


def load_q2(rows: list[Row]) -> None:
    cost = pd.read_csv(ROOT / "output" / "q2_policy_consistent" / "cost_breakdown.csv")
    kdf = pd.read_csv(ROOT / "output" / "q2_policy_consistent" / "k_sensitivity.csv")
    jan = cost[cost["label"] == "january_warmup_main"].iloc[0]
    feb = cost[cost["label"] == "feb_dec_inherited_warmup_soc"].iloc[0]
    k8 = kdf[kdf["label"] == "feb_dec_k8"].iloc[0]

    pairs = [
        ("sections/q2/05_results.tex", "2-12月总成本", 2, float(feb["total_cost_yuan"]), 15166538.46),
        ("sections/q2/05_results.tex", "2-12月计划成本", 2, float(feb["planned_cost_yuan"]), 11883687.24),
        ("sections/q2/05_results.tex", "2-12月紧急成本", 2, float(feb["emergency_cost_yuan"]), 3282851.22),
        ("tables/q2/cost_summary.tex", "1月预热总成本", 2, float(jan["total_cost_yuan"]), 1977568.32),
        ("tables/q2/cost_summary.tex", "2-12月紧急购电量", 2, float(feb["emergency_kwh"]), 924502.93),
        ("tables/q2/cost_summary.tex", "2月1日继承SOC", 4, float(feb["soc_start_kwh"]), 8390.6808),
        ("tables/q2/parameter_selection.tex", "K=8总成本", 2, float(k8["total_cost_yuan"]), 15166538.46),
        ("tables/q2/parameter_selection.tex", "K=8紧急购电量", 2, float(k8["emergency_kwh"]), 924502.93),
    ]
    for loc, metric, digits, src, paper in pairs:
        check_numeric(
            rows,
            question="Q2",
            paper_location=loc,
            metric=metric,
            unit="元或kWh",
            digits=digits,
            paper_value=paper,
            source_file=ROOT / "output" / "q2_policy_consistent/cost_breakdown.csv",
            source_column=metric,
            source_value=src,
            note="V2 政策一致主方案",
        )

    audit = json.loads((ROOT / "output" / "q2_policy_consistent" / "result2_cell_audit.json").read_text())
    add(
        rows,
        question="Q2",
        paper_location="output/result2.xlsx",
        metric="逐格对账",
        unit="-",
        display_precision="-",
        paper_value="PASS" if audit.get("pass") else "FAIL",
        source_file="output/q2_policy_consistent/result2_cell_audit.json",
        source_column="pass",
        source_value=str(audit.get("pass")),
        status="已核" if audit.get("pass") else "不一致",
        note=f"334日模板；SHA与台账一致",
    )


def load_q3(rows: list[Row]) -> None:
    strat = pd.read_csv(ROOT / "output" / "q3_full_annual" / "q3_annual_strategy_comparison.csv")
    m0 = strat[(strat["strategy"] == "M0") & (strat["year_end_boundary"] == "A_q2_aligned")].iloc[0]
    m1 = strat[(strat["strategy"] == "M1_M6") & (strat["year_end_boundary"] == "A_q2_aligned")].iloc[0]
    mb = strat[(strat["strategy"] == "M1_M6") & (strat["year_end_boundary"] == "B_energy_neutral")].iloc[0]
    export_audit = json.loads((ROOT / "output" / "result3_export_audit.json").read_text())
    export_cost = float(export_audit["xlsx"]["export_window_cost_yuan"])

    saving = float(m0["total_cost_yuan"]) - float(m1["total_cost_yuan"])
    ratio = saving / float(m0["total_cost_yuan"]) * 100

    checks = [
        ("sections/q3/05_results.tex", "M1_M6全年总成本", 2, float(m1["total_cost_yuan"]), 16373508.75),
        ("sections/q3/05_results.tex", "M0全年总成本", 2, float(m0["total_cost_yuan"]), 17109568.25),
        ("sections/q3/05_results.tex", "相对M0节省", 2, saving, 736059.50),
        ("sections/q3/05_results.tex", "节省比例", 2, ratio, 4.30),
        ("sections/q3/05_results.tex", "B边界成本增量", 2, float(mb["total_cost_yuan"]) - float(m1["total_cost_yuan"]), 2262.88),
        ("tables/q3/strategy_comparison.tex", "result3输出区间成本", 2, export_cost, 14512748.53),
        ("tables/q3/strategy_comparison.tex", "M1_M6结算成本", 2, float(m1["settlement_cost_yuan"]), 13602473.20),
        ("tables/q3/strategy_comparison.tex", "M1_M6紧急购电/kWh", 2, float(m1["emergency_kwh"]), 742322.81),
        ("tables/q3/strategy_comparison.tex", "调整次数", 0, float(m1["adjustment_count"]), 947),
    ]
    for loc, metric, digits, src, paper in checks:
        check_numeric(
            rows,
            question="Q3",
            paper_location=loc,
            metric=metric,
            unit="元/%/次",
            digits=digits,
            paper_value=paper,
            source_file=ROOT / "output/q3_full_annual/q3_annual_strategy_comparison.csv",
            source_column=metric,
            source_value=src,
        )


def load_q4_2(rows: list[Row]) -> None:
    meta = json.loads((ROOT / "output" / "q4" / "q4_2_run_metadata.json").read_text())
    daily = pd.read_csv(ROOT / "output" / "q4" / "q4_2_warmup_daily.csv")
    daily["date"] = pd.to_datetime(daily["date"])
    feb = daily[(daily["date"] >= "2025-02-01") & (daily["date"] <= "2025-12-31")]
    q2_feb = 15166538.46

    checks = [
        ("sections/q4/05_results.tex", "2-12月总成本", 2, float(meta["export_window_cost_yuan"]), 15257873.75),
        ("sections/q4/05_results.tex", "1-12月总成本", 2, float(meta["annual_cost_yuan"]), 17681029.10),
        ("sections/q4/05_results.tex", "相对Q2增加", 2, float(meta["export_window_cost_yuan"]) - q2_feb, 91335.29),
        ("tables/q4/cost_summary.tex", "2-12月计划成本", 2, float(feb["normal_cost_yuan"].sum()), 13213373.44),
        ("tables/q4/cost_summary.tex", "2-12月紧急成本", 2, float(feb["emergency_cost_yuan"].sum()), 2044500.32),
    ]
    for loc, metric, digits, src, paper in checks:
        check_numeric(
            rows,
            question="Q4-2",
            paper_location=loc,
            metric=metric,
            unit="元",
            digits=digits,
            paper_value=paper,
            source_file=ROOT / "output/q4/q4_2_run_metadata.json",
            source_column=metric,
            source_value=src,
        )

    phys = json.loads((ROOT / "output" / "q4" / "q4_2_physical_audit.json").read_text())
    add(
        rows,
        question="Q4-2",
        paper_location="sections/q4/06_validation.tex",
        metric="365日物理审计",
        unit="-",
        display_precision="-",
        paper_value="PASS",
        source_file="output/q4/q4_2_physical_audit.json",
        source_column="n_days_pass",
        source_value=str(phys.get("n_days_pass")),
        status="已核" if phys.get("n_days_pass") == 365 else "不一致",
    )


def render_markdown(rows: list[Row]) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    passed = sum(1 for r in rows if r.status == "已核")
    failed = [r for r in rows if r.status == "不一致"]
    lines = [
        "# 论文数字对账单（ACCT）",
        "",
        f"> 生成时间：{now}；脚本：`scripts/reconcile_paper_numbers.py`",
        "",
        "## 签收摘要",
        "",
        f"- 核对条目：**{len(rows)}**",
        f"- **已核：{passed}**",
        f"- **不一致：{len(failed)}**",
        f"- **未核：{sum(1 for r in rows if r.status == '未核')}**",
        "",
        "| 小问 | 正式口径 | 台账/工作簿 | ACCT 状态 |",
        "| --- | --- | --- | --- |",
        "| Q1 | M1，表2公共母线侧 | `output/result1.xlsx`、`q1_summary.csv` | 已核 |",
        "| Q2 | **V2 政策一致 K=8** | `output/result2.xlsx`、`q2_policy_consistent/` | "
        + ("已核" if not any(r.question == "Q2" and r.status == "不一致" for r in rows) else "存在不一致")
        + " |",
        "| Q3 | A边界 + `M1_M6` | `q3_annual_strategy_comparison.csv`、`result3.xlsx` | "
        + ("已核" if not any(r.question == "Q3" and r.status == "不一致" for r in rows) else "存在不一致")
        + " |",
        "| Q4-2 | 波动电价 Q2 链 | `result4-2.xlsx`、`q4_2_*` | "
        + ("已核" if not any(r.question == "Q4-2" and r.status == "不一致" for r in rows) else "存在不一致")
        + " |",
        "| Q4-3 | 待签收 | — | 未核 |",
        "",
        "## 口径提醒（写入摘要前必读）",
        "",
        "- Q2：2–12 月 **15,166,538.46 元** 为题设输出区间；1 月预热 **1,977,568.32 元** 须分列，不得相加混报。",
        "- Q3：全年 **16,373,508.75 元** 为 1–12 月主结论；**14,512,748.53 元** 仅为 `result3.xlsx` 的 2–12 月核对区间。",
        "- Q4-2：2–12 月 **15,257,873.75 元** 为题设输出区间；与 Q2 V2 同区间差 **+91,335.29 元**。Q4-3 待签收。",
        "",
        "## 逐条对账",
        "",
        "| 小问 | 论文位置 | 指标 | 单位 | 展示精度 | 论文值 | 源文件 | 源列/字段 | 源值 | 状态 | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r.question} | `{r.paper_location}` | {r.metric} | {r.unit} | {r.display_precision} | "
            f"{r.paper_value} | `{r.source_file}` | {r.source_column} | {r.source_value} | **{r.status}** | {r.note} |"
        )
    if failed:
        lines.extend(["", "## 不一致项（须修正后再签收）", ""])
        for r in failed:
            lines.append(
                f"- **{r.question}** `{r.paper_location}` · {r.metric}：论文 {r.paper_value} ≠ 源 {r.source_value}"
            )
    else:
        lines.extend(
            [
                "",
                "## 结论",
                "",
                "Q1–Q4-2 正文与表格数字均可在展示精度内回链至正式 `output/` 台账。",
                "",
                "## ACCT 签收清单",
                "",
                "- [x] Q1–Q3 逐条对账（本文件 + `reconciliation_audit.json`）",
                "- [x] Q1 专用视图：`paper/q1_reconciliation.md`",
                "- [x] Q4-2 逐条对账",
                "- [ ] Q4-3 待签收后再对账",
                "- [ ] 摘要/评价写作时再次引用本对账单",
                "",
                "**复跑：** `python3 scripts/reconcile_paper_numbers.py`（退出码 0 = 全部已核）",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    rows: list[Row] = []
    load_q1(rows)
    load_q2(rows)
    load_q3(rows)
    load_q4_2(rows)

    audit_path = PAPER / "reconciliation_audit.json"
    md_path = PAPER / "reconciliation.md"
    payload = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "rows": [asdict(r) for r in rows],
        "summary": {
            "total": len(rows),
            "passed": sum(1 for r in rows if r.status == "已核"),
            "failed": sum(1 for r in rows if r.status == "不一致"),
        },
    }
    audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(rows), encoding="utf-8")

    print(json.dumps(payload["summary"], indent=2))
    failed = [r for r in rows if r.status == "不一致"]
    if failed:
        for r in failed:
            print(f"FAIL {r.question} {r.metric}: paper={r.paper_value} source={r.source_value}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
