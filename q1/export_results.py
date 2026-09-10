from __future__ import annotations

from pathlib import Path
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import load_workbook

from q1.config import (
    C_MAX,
    D_MAX,
    DELTA_H,
    E0_KWH,
    EPS_C,
    ETA_C,
    ETA_D,
    ETA_RT,
    FIG_DIR,
    FOUR_HOUR_BLOCKS,
    OUTPUT_DIR,
    SIMUL_CD_TOL,
    T,
)
from q1.optimize import SolveResult


def _cjk_rc() -> None:
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Heiti SC", "Songti SC", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def write_plan_csv(path: Path, labels: list[str], data: pd.DataFrame, res: SolveResult) -> None:
    balance = res.g + data["pv_kwh"].to_numpy() + res.d - data["load_kwh"].to_numpy() - res.c - res.s
    plan = pd.DataFrame(
        {
            "time": labels,
            "price": data["price"],
            "load_kwh": data["load_kwh"],
            "pv_kwh": data["pv_kwh"],
            "grid_purchase_kwh": res.g,
            "charge_kwh": res.c,
            "discharge_kwh": res.d,
            "soc_kwh": res.E[1:],
            "curtailment_kwh": res.s,
            "balance_residual_kwh": balance,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    plan.to_csv(path, index=False)


def write_summary_csv(path: Path, res: SolveResult) -> None:
    rows = [
        ("grid_purchase_kwh", res.grid_purchase, "kWh", "全天计划购电量合计"),
        ("purchase_cost_yuan", res.purchase_cost, "yuan", "全天购电费"),
        ("curtailment_kwh", res.curtailment, "kWh", "全天弃光量"),
        ("throughput_kwh", res.throughput, "kWh", "充放电吞吐量 Q=sum(c+d)"),
        ("soc_min_kwh", res.soc_min, "kWh", "SOC 最小值含 E0"),
        ("soc_max_kwh", res.soc_max, "kWh", "SOC 最大值含 E0"),
        ("E0_kwh", res.E[0], "kWh", "0:00 储电量"),
        ("E144_kwh", res.E[-1], "kWh", "24:00 储电量"),
        ("max_balance_residual_kwh", res.max_balance_residual, "kWh", "能量平衡残差绝对值最大"),
        ("max_simultaneous_charge_discharge", res.max_cd, "kWh^2", "max(c_t * d_t)"),
        ("eta_rt", ETA_RT, "1", "主方案往返效率"),
        ("eta_c", ETA_C, "1", "sqrt(0.9)"),
        ("eta_d", ETA_D, "1", "sqrt(0.9)"),
        ("c_max_kwh", C_MAX, "kWh", "每时段充电上限 5000*Delta"),
        ("d_max_kwh", D_MAX, "kWh", "每时段放电上限"),
        ("eps_C", EPS_C, "yuan", "词典序成本容差"),
    ]
    pd.DataFrame(rows, columns=["metric", "value", "unit", "meaning"]).to_csv(path, index=False)


def write_comparison_csv(path: Path, results: list[SolveResult]) -> None:
    rows = []
    for r in results:
        rows.append(
            {
                "case": r.name,
                "solver": "HIGHS",
                "purchase_cost_yuan": r.purchase_cost,
                "grid_purchase_kwh": r.grid_purchase,
                "curtailment_kwh": r.curtailment,
                "throughput_kwh": r.throughput,
                "max_simultaneous_charge_discharge": r.max_cd,
                "soc_min_kwh": r.soc_min,
                "soc_max_kwh": r.soc_max,
                "max_balance_residual_kwh": r.max_balance_residual,
                "solve_seconds": r.solve_seconds,
                "pass": r.passed,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def write_model_selection_md(path: Path, results: dict[str, SolveResult], official: str) -> None:
    m1, m2, m3, m4 = results["M1"], results["M2"], results["M3"], results["M4"]
    lines = [
        "# Q1 模型形式对照与选择",
        "",
        f"- 词典序成本容差 `eps_C` = {EPS_C} 元（求解器数值容差量级）。",
        f"- 效率口径：η_rt = {ETA_RT}，η_c = η_d = sqrt(0.9) ≈ {ETA_C:.12f}。",
        f"- 正式导出使用 **{official}**（交接单：暂按 M2，待 Codex 验收后定稿）。",
        "",
        "## 结果摘要",
        "",
        "| case | cost | G | S | Q | max c*d | SOC min/max | residual | seconds | pass |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for key in ("M1", "M2", "M3", "M4"):
        r = results[key]
        lines.append(
            f"| {key} | {r.purchase_cost:.6f} | {r.grid_purchase:.6f} | {r.curtailment:.6f} | "
            f"{r.throughput:.6f} | {r.max_cd:.3e} | {r.soc_min:.4f}/{r.soc_max:.4f} | "
            f"{r.max_balance_residual:.3e} | {r.solve_seconds:.3f} | {r.passed} |"
        )
    lines += [
        "",
        "## 约束检查",
        "",
        f"- M1 同时充放电 max(c d) = {m1.max_cd:.6e}；阈值 {SIMUL_CD_TOL}。",
        f"- M1 与 M3 成本差 = {abs(m1.purchase_cost - m3.purchase_cost):.6e}。",
        f"- M2 相对 M1 成本增量 = {m2.purchase_cost - m1.purchase_cost:.6e}（应 ≤ eps_C）。",
        f"- M2 相对 M1 吞吐量变化 ΔQ = {m2.throughput - m1.throughput:.6f}。",
        f"- M2 与 M4 成本差 = {abs(m2.purchase_cost - m4.purchase_cost):.6e}，ΔQ = {m2.throughput - m4.throughput:.6f}。",
        "",
        "## 推荐",
        "",
    ]
    if m1.passed and m3.passed and abs(m1.purchase_cost - m3.purchase_cost) <= EPS_C and m1.max_cd <= SIMUL_CD_TOL:
        lines.append("- M1 与 M3 成本相同且 M1 同时充放电仅为数值残差，不需要为正式模型保留二元互斥变量。")
    else:
        lines.append("- 互斥二元变量是否必要：见上表 max(c d) 与成本差；未满足“可省略 MILP”的默认规则时保留对照说明。")
    if m2.passed and m2.purchase_cost <= m1.purchase_cost + EPS_C + 1e-9:
        lines.append("- M2 在成本最优容差内最小化吞吐量，作为正式 `result1.xlsx` 候选。")
    if m2.passed and m4.passed and abs(m2.purchase_cost - m4.purchase_cost) <= EPS_C and abs(m2.throughput - m4.throughput) <= 1e-4:
        lines.append("- M2 与 M4 无实质差异，论文可不展示 MILP，仅说明已完成稳健性核验。")
    lines += ["", "## 求解状态", ""]
    for key, r in results.items():
        lines.append(f"- {key}: status={r.status}; notes={r.notes or 'ok'}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_validation_md(
    path: Path,
    data: pd.DataFrame,
    labels: list[str],
    official: SolveResult,
    attach_path: Path,
    template_path: Path,
) -> None:
    mapping_rows = []
    for i in [0, 1, 2, T // 2 - 1, T - 3, T - 2, T - 1]:
        mapping_rows.append(
            f"| {i + 1} | {data['attach_time'].iloc[i]} | {labels[i]} |"
        )
    lines = [
        "# Q1 验收",
        "",
        f"- 附件1：`{attach_path}`",
        f"- 模板：`{template_path}`",
        f"- 正式方案：{official.name}，solver=HIGHS，status={official.status}",
        "",
        "## 时间标签映射",
        "",
        "内部模型用整数索引 t=1..144。SOC 独立使用 E_0,...,E_144，其中 E_0=E_144=6000 kWh 对应 0:00 与 24:00。",
        "导出时按官方模板**既有行序**填写第 t 个购电结果，不新增 `0:00-0:10`，不改标签。",
        "",
        "规则：内部索引 t → 附件1第 t 条数据 → 模板第 t 条时间标签。",
        "",
        "| t | 附件1时间 | 模板时间段 |",
        "|---:|---|---|",
        *mapping_rows,
        "",
        "附件1首条为 `00:10:00`，模板首条为 `0:10-0:20`，相差约 10 分钟表述；本题按行序一一对应，不伪造额外区间。",
        "四小时充放电汇总按内部索引每 24 个时段分块：t=1..24, 25..48, …, 121..144。",
        "",
        "## 数值验收",
        "",
        f"- 时段数：{T}",
        f"- 功率已乘 Δ={DELTA_H} h 转为 kWh",
        f"- max |能量平衡残差| = {official.max_balance_residual:.6e} kWh（阈值 1e-6）",
        f"- max c,d = {official.c.max():.6f}, {official.d.max():.6f} kWh（上限 {C_MAX:.9f}）",
        f"- SOC min/max = {official.soc_min:.6f} / {official.soc_max:.6f} kWh（[1200, 10800]）",
        f"- E0 = {official.E[0]:.12f}，E144 = {official.E[-1]:.12f}，|E144-6000|={abs(official.E[-1]-E0_KWH):.6e}",
        f"- max(c_t d_t) = {official.max_cd:.6e}（阈值 1e-4）",
        f"- 验收通过：{official.passed}",
        "",
    ]
    if not official.passed:
        lines.append(f"**未通过：** {official.notes}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_result1_xlsx(template: Path, dest: Path, res: SolveResult) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, dest)
    wb = load_workbook(dest)
    ws_g = wb["计划购电量"]
    for i in range(T):
        header = ws_g.cell(row=i + 2, column=1).value
        if header is None:
            raise RuntimeError(f"template row {i+2} missing time label")
        ws_g.cell(row=i + 2, column=2).value = float(res.g[i])
    ws_cd = wb["充放电量"]
    for row, (_name, a, b) in enumerate(FOUR_HOUR_BLOCKS, start=2):
        ws_cd.cell(row=row, column=2).value = float(np.sum(res.c[a:b]))
        ws_cd.cell(row=row, column=3).value = float(np.sum(res.d[a:b]))
    # 0:00 / 24:00 SOC sit on rows 2–3, columns D–E as in the official template
    ws_cd.cell(row=2, column=5).value = float(res.E[0])
    ws_cd.cell(row=3, column=5).value = float(res.E[-1])
    wb.save(dest)


def write_figures(data: pd.DataFrame, res: SolveResult) -> None:
    _cjk_rc()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    hours = (np.arange(T) + 1) * DELTA_H

    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(hours, data["load_kwh"], label="负荷 (kWh/10min)", lw=1.2)
    ax.plot(hours, data["pv_kwh"], label="光伏 (kWh/10min)", lw=1.2)
    ax.plot(hours, res.g, label="购电 (kWh)", lw=1.2)
    ax.plot(hours, res.c, label="充电 (kWh)", lw=1.0)
    ax.plot(hours, res.d, label="放电 (kWh)", lw=1.0)
    ax.set_xlabel("时刻 (h)")
    ax.set_ylabel("能量 (kWh / 时段)")
    ax.set_xlim(0, 24)
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig1_dispatch.png", dpi=200)
    plt.close(fig)

    fig, ax1 = plt.subplots(figsize=(10, 4.2))
    ax1.plot(np.concatenate([[0.0], hours]), res.E, color="#1D4ED8", label="SOC (kWh)")
    ax1.set_xlabel("时刻 (h)")
    ax1.set_ylabel("SOC (kWh)")
    ax1.set_xlim(0, 24)
    ax1.set_ylim(1000, 11000)
    ax2 = ax1.twinx()
    ax2.step(hours, data["price"], where="pre", color="#B45309", label="电价 (元/kWh)", alpha=0.85)
    ax2.set_ylabel("电价 (元/kWh)")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8)
    ax1.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig1_soc_price.png", dpi=200)
    plt.close(fig)
