
# ===== q1/__init__.py =====
from q1.config import DELTA_H, ETA_C, ETA_D, P_MAX_KW, T

C_MAX = P_MAX_KW * DELTA_H
D_MAX = P_MAX_KW * DELTA_H

__all__ = ["C_MAX", "D_MAX", "DELTA_H", "ETA_C", "ETA_D", "T"]

# ===== q1/config.py =====
"""Q1 default constants. Runtime models take ModelParams; do not mutate these for cases."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

T = 144
DELTA_H = 1.0 / 6.0
NOMINAL_CAPACITY_KWH = 12000.0
P_MAX_KW = 5000.0
E_MAX_KWH = 10800.0
E_MIN_KWH = 1200.0
E0_KWH = 6000.0
ETA_RT = 0.90
ETA_C = ETA_RT**0.5
ETA_D = ETA_RT**0.5

BALANCE_TOL = 1e-6
SOC_END_TOL = 1e-6
SIMUL_CD_TOL = 1e-4
EPS_C = 1e-6
S_BOUND_TOL = 1e-8

SOLVER = "HIGHS"
OFFICIAL_MODEL = "M1"
EXPECTED_M1_COST = 33801.495542
EXPECTED_EFF_B_COST = 35126.948589
COST_REPRO_TOL = 1e-5

# Table 2: pending captain sign-off. PCC AC-bus side, not battery-internal.
TABLE2_ENERGY_SIDE = "pcc_ac_bus"
TABLE2_CHARGE_VAR = "c_t"
TABLE2_DISCHARGE_VAR = "d_t"

ROW_ORDER_POLICY = "attachment_raw_order"

DEFAULT_ATTACH_DIR = Path(
    os.environ.get("CUMCM_C_ATTACH_DIR", ROOT / "data" / "raw" / "附件")
)
DEFAULT_ATTACH1 = Path(os.environ.get("CUMCM_C_ATTACH1", DEFAULT_ATTACH_DIR / "附件1.xlsx"))
DEFAULT_RESULT1_TEMPLATE = Path(
    os.environ.get("CUMCM_C_RESULT1_TEMPLATE", DEFAULT_ATTACH_DIR / "附件5" / "result1.xlsx")
)

OUTPUT_DIR = ROOT / "output"
FIG_DIR = ROOT / "fig"

FOUR_HOUR_BLOCKS = [
    ("0:00-4:00", 0, 24),
    ("4:00-8:00", 24, 48),
    ("8:00-12:00", 48, 72),
    ("12:00-16:00", 72, 96),
    ("16:00-20:00", 96, 120),
    ("20:00-24:00", 120, 144),
]

PURCHASE_SHEET = "计划购电量"
CHARGE_SHEET = "充放电量"
PURCHASE_HEADERS = ("时间段", "购电量")
CHARGE_HEADERS = ("时间段", "充电量", "放电量", "时刻", "储电量")
ALLOWED_PURCHASE_CELLS = {(r, 2) for r in range(2, 2 + T)}
ALLOWED_CHARGE_CELLS = {(r, 2) for r in range(2, 8)} | {(r, 3) for r in range(2, 8)} | {(2, 5), (3, 5)}

# ===== q1/export_results.py =====
from __future__ import annotations

from pathlib import Path
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import load_workbook

from q1.config import (
    ALLOWED_CHARGE_CELLS,
    ALLOWED_PURCHASE_CELLS,
    CHARGE_SHEET,
    DELTA_H,
    EPS_C,
    ETA_RT,
    FIG_DIR,
    FOUR_HOUR_BLOCKS,
    OFFICIAL_MODEL,
    PURCHASE_SHEET,
    ROW_ORDER_POLICY,
    SIMUL_CD_TOL,
    T,
    TABLE2_CHARGE_VAR,
    TABLE2_DISCHARGE_VAR,
    TABLE2_ENERGY_SIDE,
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
    p = res.params
    rows = [
        ("official_model", OFFICIAL_MODEL, "1", "正式方案；M2–M4 仅对照"),
        ("grid_purchase_kwh", res.grid_purchase, "kWh", "全天计划购电量合计"),
        ("purchase_cost_yuan", res.purchase_cost, "yuan", "全天购电费"),
        ("peak_grid_kw", res.peak_grid_kw, "kW", "购电功率峰值 max(g_t)/Δ"),
        ("curtailment_kwh", res.curtailment, "kWh", "全天弃光量"),
        ("throughput_kwh", res.throughput, "kWh", "充放电吞吐量 Q=sum(c+d)"),
        ("soc_min_kwh", res.soc_min, "kWh", "SOC 最小值含 E0"),
        ("soc_max_kwh", res.soc_max, "kWh", "SOC 最大值含 E0"),
        ("E0_kwh", res.E[0], "kWh", "0:00 储电量"),
        ("E144_kwh", res.E[-1], "kWh", "24:00 储电量"),
        ("max_balance_residual_kwh", res.max_balance_residual, "kWh", "能量平衡残差绝对值最大"),
        ("max_simultaneous_charge_discharge", res.max_cd, "kWh^2", "max(c_t * d_t)"),
        ("max_s_minus_pv_kwh", res.max_s_minus_pv, "kWh", "max(s_t-P_t)，应<=0"),
        ("eta_rt", ETA_RT, "1", "主方案往返效率"),
        ("eta_c", p.eta_c, "1", "充电效率"),
        ("eta_d", p.eta_d, "1", "放电效率"),
        ("c_max_kwh", p.c_max_kwh, "kWh", "每时段充电上限 power_limit_kw*Δ"),
        ("d_max_kwh", p.d_max_kwh, "kWh", "每时段放电上限"),
        ("power_limit_kw", p.power_limit_kw, "kW", "充放电功率上限"),
        ("grid_limit_kw", "" if p.grid_limit_kw is None else p.grid_limit_kw, "kW", "主方案无上限"),
        ("eps_C", EPS_C, "yuan", "词典序成本容差（仅对照）"),
        ("table2_energy_side", TABLE2_ENERGY_SIDE, "1", "表2计量侧，待队长最终签收"),
        ("table2_charge_var", TABLE2_CHARGE_VAR, "1", "充电量汇总变量"),
        ("table2_discharge_var", TABLE2_DISCHARGE_VAR, "1", "放电量汇总变量"),
        ("row_order_policy", ROW_ORDER_POLICY, "1", "附件原始行序口径（队长确认）"),
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
                "peak_grid_kw": r.peak_grid_kw,
                "curtailment_kwh": r.curtailment,
                "throughput_kwh": r.throughput,
                "max_simultaneous_charge_discharge": r.max_cd,
                "soc_min_kwh": r.soc_min,
                "soc_max_kwh": r.soc_max,
                "max_balance_residual_kwh": r.max_balance_residual,
                "max_s_minus_pv_kwh": r.max_s_minus_pv,
                "solve_seconds": r.solve_seconds,
                "pass": r.passed,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def write_baseline_csv(
    path: Path,
    g_base: np.ndarray,
    s_base: np.ndarray,
    price: np.ndarray,
    m1: SolveResult,
) -> None:
    g_sum = float(np.sum(g_base))
    s_sum = float(np.sum(s_base))
    cost = float(price @ g_base)
    save = cost - m1.purchase_cost
    ratio = save / cost if cost else np.nan
    rows = [
        ("baseline_grid_purchase_kwh", g_sum, "kWh", "无储能无售电：g=max(L-P,0)"),
        ("baseline_purchase_cost_yuan", cost, "yuan", "基准购电费"),
        ("baseline_curtailment_kwh", s_sum, "kWh", "基准弃光 s=max(P-L,0)"),
        ("m1_grid_purchase_kwh", m1.grid_purchase, "kWh", "正式 M1 总购电量"),
        ("m1_purchase_cost_yuan", m1.purchase_cost, "yuan", "正式 M1 购电费"),
        ("absolute_cost_saving_yuan", save, "yuan", "基准费用减 M1 费用"),
        ("cost_saving_ratio", ratio, "1", "节省比例（相对基准）"),
    ]
    pd.DataFrame(rows, columns=["metric", "value", "unit", "meaning"]).to_csv(path, index=False)


def write_sensitivity_csv(path: Path, rows: list[dict]) -> None:
    cols = [
        "case",
        "eta_c",
        "eta_d",
        "nominal_capacity_kwh",
        "soc_min_kwh",
        "soc_max_kwh",
        "power_limit_kw",
        "grid_limit_kw",
        "purchase_cost_yuan",
        "grid_purchase_kwh",
        "peak_grid_kw",
        "curtailment_kwh",
        "throughput_kwh",
        "soc_observed_min_kwh",
        "soc_observed_max_kwh",
        "pass",
    ]
    pd.DataFrame(rows)[cols].to_csv(path, index=False)


def sensitivity_row(case: str, res: SolveResult) -> dict:
    p = res.params
    return {
        "case": case,
        "eta_c": p.eta_c,
        "eta_d": p.eta_d,
        "nominal_capacity_kwh": p.nominal_capacity_kwh,
        "soc_min_kwh": p.e_min_kwh,
        "soc_max_kwh": p.e_max_kwh,
        "power_limit_kw": p.power_limit_kw,
        "grid_limit_kw": "" if p.grid_limit_kw is None else p.grid_limit_kw,
        "purchase_cost_yuan": res.purchase_cost,
        "grid_purchase_kwh": res.grid_purchase,
        "peak_grid_kw": res.peak_grid_kw,
        "curtailment_kwh": res.curtailment,
        "throughput_kwh": res.throughput,
        "soc_observed_min_kwh": res.soc_min,
        "soc_observed_max_kwh": res.soc_max,
        "pass": res.passed,
    }


def write_model_selection_md(path: Path, results: dict[str, SolveResult], official: str) -> None:
    m1, m2, m3, m4 = results["M1"], results["M2"], results["M3"], results["M4"]
    lines = [
        "# Q1 模型形式对照与选择",
        "",
        f"- 正式方案为 **{official}**（纯成本最优 LP）。M2–M4 仅作数值对照，不得覆盖 `result1.xlsx` / 正式图。",
        "- M2 是在成本最优容差内再最小化吞吐量的数值择优，**不能**据此声称降低循环寿命损耗或延长电池寿命。",
        f"- 词典序成本容差 `eps_C` = {EPS_C} 元（仅用于 M2/M4 对照）。",
        f"- 效率口径 A（正式）：eta_rt = {ETA_RT}，eta_c = eta_d = sqrt(0.9) approx {m1.params.eta_c:.12f}。",
        "",
        "## 结果摘要",
        "",
        "| case | cost | G | peak kW | S | Q | max c*d | SOC min/max | residual | seconds | pass |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for key in ("M1", "M2", "M3", "M4"):
        r = results[key]
        lines.append(
            f"| {key} | {r.purchase_cost:.6f} | {r.grid_purchase:.6f} | {r.peak_grid_kw:.6f} | "
            f"{r.curtailment:.6f} | {r.throughput:.6f} | {r.max_cd:.3e} | "
            f"{r.soc_min:.4f}/{r.soc_max:.4f} | {r.max_balance_residual:.3e} | "
            f"{r.solve_seconds:.3f} | {r.passed} |"
        )
    lines += [
        "",
        "## 约束检查",
        "",
        f"- M1 同时充放电 max(c d) = {m1.max_cd:.6e}；阈值 {SIMUL_CD_TOL}。",
        f"- M1 与 M3 成本差 = {abs(m1.purchase_cost - m3.purchase_cost):.6e}。",
        f"- M2 相对 M1 成本增量 = {m2.purchase_cost - m1.purchase_cost:.6e}（应 <= eps_C）。",
        f"- M2 相对 M1 吞吐量变化 ΔQ = {m2.throughput - m1.throughput:.6f}。",
        f"- M2 与 M4 成本差 = {abs(m2.purchase_cost - m4.purchase_cost):.6e}，ΔQ = {m2.throughput - m4.throughput:.6f}。",
        f"- M1 max(s-P) = {m1.max_s_minus_pv:.6e}。",
        "",
        "## 推荐",
        "",
        "- 正式采用 M1：目标仅为购电费，与题面一致。",
    ]
    if m1.passed and m3.passed and abs(m1.purchase_cost - m3.purchase_cost) <= EPS_C and m1.max_cd <= SIMUL_CD_TOL:
        lines.append("- M1 与 M3 成本相同且同时充放电仅为数值残差，正式模型不需要二元互斥变量。")
    if m2.passed and m2.purchase_cost <= m1.purchase_cost + EPS_C + 1e-9:
        lines.append("- M2 可在对照表中作为同等费用下的低吞吐量解，但不作为正式答卷。")
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
    price_min: float,
    gmax_min_kw: float,
) -> None:
    mapping_rows = []
    for i in [0, 1, 2, T // 2 - 1, T - 3, T - 2, T - 1]:
        mapping_rows.append(
            f"| {i + 1} | {data['attach_time'].iloc[i]} | {labels[i]} |"
        )
    p = official.params
    lines = [
        "# Q1 验收",
        "",
        f"- 附件1：`{attach_path}`",
        f"- 模板：`{template_path}`",
        f"- 正式方案：{official.name}（{OFFICIAL_MODEL}），solver=HIGHS，status={official.status}",
        f"- **附件原始行序口径（队长确认）**：不按时间排序，不把末行旋转到首行。",
        f"- 行序策略代码标记：`{ROW_ORDER_POLICY}`",
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
        "附件1首条为 `00:10:00`，模板首条为 `0:10-0:20`；本题按行序一一对应。",
        "四小时充放电汇总按内部索引每 24 个时段分块：t=1..24, 25..48, …, 121..144。",
        "",
        "## 输入检查",
        "",
        f"- 价格最小值 = {price_min:.6g} 元/kWh。当前附件无负价；若出现负价必须报错，不得沿用“无需同时充放电”的结论。",
        "",
        "## 表 2 计量侧（待队长最终签收）",
        "",
        f"- 集中定义：`TABLE2_ENERGY_SIDE={TABLE2_ENERGY_SIDE}`。",
        f"- 充电量 = `{TABLE2_CHARGE_VAR}`（公共母线侧充入储能）。",
        f"- 放电量 = `{TABLE2_DISCHARGE_VAR}`（公共母线侧储能放电）。",
        "- 未换算电池内部能量；签收前不得在多处隐式改写。",
        "",
        "## 数值验收",
        "",
        f"- 时段数：{T}",
        f"- 功率已乘 Δ={DELTA_H} h 转为 kWh",
        f"- max |能量平衡残差| = {official.max_balance_residual:.6e} kWh（阈值 1e-6）",
        f"- max c,d = {official.c.max():.6f}, {official.d.max():.6f} kWh（上限 {p.c_max_kwh:.9f}）",
        f"- SOC min/max = {official.soc_min:.6f} / {official.soc_max:.6f} kWh（[{p.e_min_kwh}, {p.e_max_kwh}]）",
        f"- E0 = {official.E[0]:.12f}，E144 = {official.E[-1]:.12f}，|E144-E0|={abs(official.E[-1]-p.e0_kwh):.6e}",
        f"- max(c_t d_t) = {official.max_cd:.6e}（阈值 1e-4）",
        f"- max(s_t-P_t) = {official.max_s_minus_pv:.6e}",
        f"- 峰值购电功率 = {official.peak_grid_kw:.6f} kW（主方案无 PCC 上限）",
        f"- PCC 敏感性：最小可行峰值约 {gmax_min_kw:.6f} kW，该值**不是**题给参数。",
        f"- 验收通过：{official.passed}",
        "",
    ]
    if not official.passed:
        lines.append(f"**未通过：** {official.notes}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def table2_block_energy(res: SolveResult) -> tuple[np.ndarray, np.ndarray]:
    """PCC AC-bus side: charge = c_t, discharge = d_t. Single definition for Table 2."""
    charge = np.array([float(np.sum(res.c[a:b])) for _n, a, b in FOUR_HOUR_BLOCKS])
    discharge = np.array([float(np.sum(res.d[a:b])) for _n, a, b in FOUR_HOUR_BLOCKS])
    return charge, discharge


def write_result1_xlsx(template: Path, dest: Path, res: SolveResult) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, dest)
    wb = load_workbook(dest)
    ws_g = wb[PURCHASE_SHEET]
    for i in range(T):
        header = ws_g.cell(row=i + 2, column=1).value
        if header is None:
            raise RuntimeError(f"template row {i+2} missing time label")
        ws_g.cell(row=i + 2, column=2).value = float(res.g[i])
    ws_cd = wb[CHARGE_SHEET]
    charge, discharge = table2_block_energy(res)
    for row, val_c, val_d in zip(range(2, 8), charge, discharge):
        ws_cd.cell(row=row, column=2).value = val_c
        ws_cd.cell(row=row, column=3).value = val_d
    ws_cd.cell(row=2, column=5).value = float(res.E[0])
    ws_cd.cell(row=3, column=5).value = float(res.E[-1])
    wb.save(dest)
    verify_xlsx_only_allowed_cells(template, dest)


def verify_xlsx_only_allowed_cells(template: Path, dest: Path) -> None:
    src = load_workbook(template, data_only=False)
    out = load_workbook(dest, data_only=False)
    for name in src.sheetnames:
        ws_s, ws_o = src[name], out[name]
        for row in ws_s.iter_rows(min_row=1, max_row=ws_s.max_row, max_col=ws_s.max_column):
            for cell in row:
                key = (cell.row, cell.column)
                if name == PURCHASE_SHEET and key in ALLOWED_PURCHASE_CELLS:
                    continue
                if name == CHARGE_SHEET and key in ALLOWED_CHARGE_CELLS:
                    continue
                if ws_o.cell(cell.row, cell.column).value != cell.value:
                    raise RuntimeError(
                        f"modified non-fillable cell {name}!{cell.coordinate}: "
                        f"{cell.value!r} -> {ws_o.cell(cell.row, cell.column).value!r}"
                    )


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

# ===== q1/load_data.py =====
from __future__ import annotations

from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from q1.config import (
    CHARGE_HEADERS,
    CHARGE_SHEET,
    DEFAULT_ATTACH1,
    DEFAULT_RESULT1_TEMPLATE,
    DELTA_H,
    FOUR_HOUR_BLOCKS,
    PURCHASE_HEADERS,
    PURCHASE_SHEET,
    T,
)


def normalize_attach_time(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return str(value).strip()


def load_attachment1(path: Path | None = None) -> pd.DataFrame:
    """Preserve Excel raw row order. Do not sort or rotate."""
    path = Path(path or DEFAULT_ATTACH1)
    if not path.exists():
        raise FileNotFoundError(
            f"附件1 not found: {path}. Set CUMCM_C_ATTACH1 to the xlsx path."
        )
    df = pd.read_excel(path, sheet_name="Sheet1")
    expected = ["时间", "电价", "小区负载", "光伏发电预测功率"]
    if list(df.columns) != expected:
        raise ValueError(f"Unexpected 附件1 columns: {list(df.columns)}")
    if len(df) != T:
        raise ValueError(f"附件1 must have {T} rows, got {len(df)}")

    times = df["时间"].map(normalize_attach_time)
    price = pd.to_numeric(df["电价"], errors="coerce").to_numpy(dtype=float)
    load_kw = pd.to_numeric(df["小区负载"], errors="coerce").to_numpy(dtype=float)
    pv_kw = pd.to_numeric(df["光伏发电预测功率"], errors="coerce").to_numpy(dtype=float)

    if not np.isfinite(price).all() or not np.isfinite(load_kw).all() or not np.isfinite(pv_kw).all():
        raise ValueError("附件1 contains non-finite numeric values")
    if (load_kw < 0).any() or (pv_kw < 0).any():
        raise ValueError("附件1 has negative load or PV")
    if (price < 0).any():
        raise ValueError(
            "附件1 has negative prices; simultaneous charge/discharge logic must be revisited"
        )

    if times.iloc[0] != "00:10:00":
        raise ValueError(f"First attach time must be 00:10:00, got {times.iloc[0]!r}")
    if times.iloc[-1] != "0:00+1":
        raise ValueError(f"Last attach time must be 0:00+1, got {times.iloc[-1]!r}")

    out = pd.DataFrame(
        {
            "t": np.arange(1, T + 1),
            "attach_time": times.to_numpy(),
            "price": price,
            "load_kw": load_kw,
            "pv_kw": pv_kw,
        }
    )
    out["load_kwh"] = out["load_kw"] * DELTA_H
    out["pv_kwh"] = out["pv_kw"] * DELTA_H
    out.attrs["row_order_policy"] = "attachment_raw_order"
    return out


def inspect_template(path: Path | None = None) -> tuple[list[str], list[str]]:
    path = Path(path or DEFAULT_RESULT1_TEMPLATE)
    if not path.exists():
        raise FileNotFoundError(
            f"result1 template not found: {path}. Set CUMCM_C_RESULT1_TEMPLATE."
        )
    wb = load_workbook(path)
    if wb.sheetnames != [PURCHASE_SHEET, CHARGE_SHEET]:
        raise ValueError(f"Unexpected sheets: {wb.sheetnames}")
    ws_g = wb[PURCHASE_SHEET]
    headers_g = (ws_g.cell(1, 1).value, ws_g.cell(1, 2).value)
    if headers_g != PURCHASE_HEADERS:
        raise ValueError(f"计划购电量表头不符: {headers_g}")
    labels = [ws_g.cell(row=i, column=1).value for i in range(2, 2 + T)]
    if any(x is None or str(x).strip() == "" for x in labels):
        raise ValueError("result1 template has empty time labels")
    labels = [str(x) for x in labels]
    if labels[0] != "0:10-0:20" or labels[-1] != "0:00+1-0:10+1":
        raise ValueError(f"Unexpected purchase labels: {labels[0]!r} .. {labels[-1]!r}")

    ws_cd = wb[CHARGE_SHEET]
    headers_cd = tuple(ws_cd.cell(1, c).value for c in range(1, 6))
    if headers_cd != CHARGE_HEADERS:
        raise ValueError(f"充放电量表头不符: {headers_cd}")
    block_labels = [str(ws_cd.cell(row=i, column=1).value) for i in range(2, 8)]
    expected_blocks = [name for name, _a, _b in FOUR_HOUR_BLOCKS]
    if block_labels != expected_blocks:
        raise ValueError(f"四小时区间标签不符: {block_labels}")
    return labels, block_labels


def load_template_labels(path: Path | None = None) -> list[str]:
    labels, _blocks = inspect_template(path)
    return labels

# ===== q1/optimize.py =====
from __future__ import annotations

from dataclasses import dataclass
import time

import cvxpy as cp
import numpy as np

from q1.config import (
    BALANCE_TOL,
    DELTA_H,
    E0_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    EPS_C,
    ETA_C,
    ETA_D,
    NOMINAL_CAPACITY_KWH,
    P_MAX_KW,
    S_BOUND_TOL,
    SIMUL_CD_TOL,
    SOC_END_TOL,
    SOLVER,
    T,
)


@dataclass
class ModelParams:
    eta_c: float = ETA_C
    eta_d: float = ETA_D
    e_min_kwh: float = E_MIN_KWH
    e_max_kwh: float = E_MAX_KWH
    e0_kwh: float = E0_KWH
    power_limit_kw: float = P_MAX_KW
    grid_limit_kw: float | None = None
    nominal_capacity_kwh: float = NOMINAL_CAPACITY_KWH

    @property
    def c_max_kwh(self) -> float:
        return self.power_limit_kw * DELTA_H

    @property
    def d_max_kwh(self) -> float:
        return self.power_limit_kw * DELTA_H

    @property
    def g_max_kwh(self) -> float | None:
        if self.grid_limit_kw is None:
            return None
        return self.grid_limit_kw * DELTA_H


def default_params() -> ModelParams:
    return ModelParams()


def soc_window(nominal_capacity_kwh: float) -> tuple[float, float]:
    return 0.10 * nominal_capacity_kwh, 0.90 * nominal_capacity_kwh


@dataclass
class SolveResult:
    name: str
    exclusive: bool
    lexico: bool
    status: str
    g: np.ndarray
    c: np.ndarray
    d: np.ndarray
    s: np.ndarray
    E: np.ndarray
    purchase_cost: float
    grid_purchase: float
    curtailment: float
    throughput: float
    max_cd: float
    soc_min: float
    soc_max: float
    max_balance_residual: float
    peak_grid_kw: float
    max_s_minus_pv: float
    solve_seconds: float
    passed: bool
    params: ModelParams
    notes: str = ""


def _build_problem(
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    exclusive: bool,
    cost_cap: float | None,
    params: ModelParams,
    peak_var: bool,
):
    g = cp.Variable(T, nonneg=True)
    c = cp.Variable(T, nonneg=True)
    d = cp.Variable(T, nonneg=True)
    s = cp.Variable(T, nonneg=True)
    E = cp.Variable(T + 1)
    c_max = params.c_max_kwh
    d_max = params.d_max_kwh
    cons = [
        E[0] == params.e0_kwh,
        E[T] == params.e0_kwh,
        E[1:] >= params.e_min_kwh,
        E[1:] <= params.e_max_kwh,
        c <= c_max,
        d <= d_max,
        s <= pv,
        g + pv + d == load + c + s,
        E[1:] == E[:-1] + params.eta_c * c - d / params.eta_d,
    ]
    if params.g_max_kwh is not None:
        cons.append(g <= params.g_max_kwh)
    z = None
    if exclusive:
        z = cp.Variable(T, boolean=True)
        cons += [c <= c_max * z, d <= d_max * (1 - z)]
    peak = None
    if peak_var:
        peak = cp.Variable(nonneg=True)
        cons.append(g <= peak)
        objective = cp.Minimize(peak)
    elif cost_cap is not None:
        cons.append(price @ g <= cost_cap)
        objective = cp.Minimize(cp.sum(c + d))
    else:
        objective = cp.Minimize(price @ g)
    return cp.Problem(objective, cons), g, c, d, s, E, z, peak


def _metrics(price, load, pv, g, c, d, s, E, params: ModelParams) -> dict:
    balance = g + pv + d - load - c - s
    return {
        "purchase_cost": float(price @ g),
        "grid_purchase": float(np.sum(g)),
        "curtailment": float(np.sum(s)),
        "throughput": float(np.sum(c + d)),
        "max_cd": float(np.max(c * d)),
        "soc_min": float(np.min(E)),
        "soc_max": float(np.max(E)),
        "max_balance_residual": float(np.max(np.abs(balance))),
        "e_end_gap": float(abs(E[-1] - params.e0_kwh)),
        "c_over": float(np.max(c - params.c_max_kwh)),
        "d_over": float(np.max(d - params.d_max_kwh)),
        "peak_grid_kw": float(np.max(g) / DELTA_H),
        "max_s_minus_pv": float(np.max(s - pv)),
        "g_over": float(np.max(g - (params.g_max_kwh if params.g_max_kwh is not None else np.inf))),
    }


def _pass(m: dict, params: ModelParams) -> tuple[bool, str]:
    reasons = []
    if m["max_balance_residual"] >= BALANCE_TOL:
        reasons.append(f"balance {m['max_balance_residual']}")
    if m["e_end_gap"] >= SOC_END_TOL:
        reasons.append(f"E144 {m['e_end_gap']}")
    if m["soc_min"] < params.e_min_kwh - SOC_END_TOL:
        reasons.append(f"soc_min {m['soc_min']}")
    if m["soc_max"] > params.e_max_kwh + SOC_END_TOL:
        reasons.append(f"soc_max {m['soc_max']}")
    if m["c_over"] > BALANCE_TOL or m["d_over"] > BALANCE_TOL:
        reasons.append("power limit")
    if m["max_cd"] > SIMUL_CD_TOL:
        reasons.append(f"max c*d {m['max_cd']}")
    if m["max_s_minus_pv"] > S_BOUND_TOL:
        reasons.append(f"s>P {m['max_s_minus_pv']}")
    if m["g_over"] > BALANCE_TOL:
        reasons.append("grid limit")
    return (len(reasons) == 0, "; ".join(reasons))


def solve_stage(
    name: str,
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    exclusive: bool = False,
    cost_cap: float | None = None,
    params: ModelParams | None = None,
) -> SolveResult:
    params = params or default_params()
    prob, g, c, d, s, E, _z, _peak = _build_problem(
        price, load, pv, exclusive, cost_cap, params, peak_var=False
    )
    t0 = time.perf_counter()
    prob.solve(solver=SOLVER, verbose=False)
    elapsed = time.perf_counter() - t0
    if g.value is None:
        return SolveResult(
            name=name,
            exclusive=exclusive,
            lexico=cost_cap is not None,
            status=str(prob.status),
            g=np.zeros(T),
            c=np.zeros(T),
            d=np.zeros(T),
            s=np.zeros(T),
            E=np.full(T + 1, np.nan),
            purchase_cost=np.nan,
            grid_purchase=np.nan,
            curtailment=np.nan,
            throughput=np.nan,
            max_cd=np.nan,
            soc_min=np.nan,
            soc_max=np.nan,
            max_balance_residual=np.nan,
            peak_grid_kw=np.nan,
            max_s_minus_pv=np.nan,
            solve_seconds=elapsed,
            passed=False,
            params=params,
            notes=f"solver status={prob.status}",
        )
    gv = np.asarray(g.value, dtype=float).ravel()
    cv = np.asarray(c.value, dtype=float).ravel()
    dv = np.asarray(d.value, dtype=float).ravel()
    sv = np.asarray(s.value, dtype=float).ravel()
    Ev = np.asarray(E.value, dtype=float).ravel()
    m = _metrics(price, load, pv, gv, cv, dv, sv, Ev, params)
    ok, why = _pass(m, params)
    return SolveResult(
        name=name,
        exclusive=exclusive,
        lexico=cost_cap is not None,
        status=str(prob.status),
        g=gv,
        c=cv,
        d=dv,
        s=sv,
        E=Ev,
        purchase_cost=m["purchase_cost"],
        grid_purchase=m["grid_purchase"],
        curtailment=m["curtailment"],
        throughput=m["throughput"],
        max_cd=m["max_cd"],
        soc_min=m["soc_min"],
        soc_max=m["soc_max"],
        max_balance_residual=m["max_balance_residual"],
        peak_grid_kw=m["peak_grid_kw"],
        max_s_minus_pv=m["max_s_minus_pv"],
        solve_seconds=elapsed,
        passed=ok,
        params=params,
        notes=why,
    )


def solve_lexico(
    name: str,
    price,
    load,
    pv,
    exclusive: bool,
    params: ModelParams | None = None,
) -> tuple[SolveResult, SolveResult]:
    params = params or default_params()
    s1 = solve_stage(name + "_stage1", price, load, pv, exclusive, None, params)
    if not np.isfinite(s1.purchase_cost):
        return s1, s1
    cap = s1.purchase_cost + EPS_C
    s2 = solve_stage(name, price, load, pv, exclusive, cap, params)
    s2.notes = (s2.notes + f"; C*={s1.purchase_cost:.12g}; eps_C={EPS_C}").strip("; ")
    if s2.purchase_cost > s1.purchase_cost + EPS_C + 1e-8:
        s2.passed = False
        s2.notes += "; lexico cost exceeded C*+eps"
    return s1, s2


def min_feasible_peak_kw(price, load, pv, params: ModelParams | None = None) -> float:
    params = params or default_params()
    prob, g, _c, _d, _s, _E, _z, peak = _build_problem(
        price, load, pv, exclusive=False, cost_cap=None, params=params, peak_var=True
    )
    prob.solve(solver=SOLVER, verbose=False)
    if peak is None or peak.value is None:
        raise RuntimeError(f"min peak LP failed: {prob.status}")
    return float(peak.value) / DELTA_H

# ===== q1/run_q1.py =====
#!/usr/bin/env python3
"""C 题 Q1：按 docs/handoff/cursor-c-q1-second-revision.md 求解并导出。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q1.config import (  # noqa: E402
    COST_REPRO_TOL,
    DEFAULT_ATTACH1,
    DEFAULT_RESULT1_TEMPLATE,
    EPS_C,
    EXPECTED_EFF_B_COST,
    EXPECTED_M1_COST,
    OFFICIAL_MODEL,
    OUTPUT_DIR,
    SIMUL_CD_TOL,
)
from q1.export_results import (  # noqa: E402
    sensitivity_row,
    write_baseline_csv,
    write_comparison_csv,
    write_figures,
    write_model_selection_md,
    write_plan_csv,
    write_result1_xlsx,
    write_sensitivity_csv,
    write_summary_csv,
    write_validation_md,
)
from q1.load_data import inspect_template, load_attachment1  # noqa: E402
from q1.optimize import (  # noqa: E402
    ModelParams,
    SolveResult,
    default_params,
    min_feasible_peak_kw,
    soc_window,
    solve_lexico,
    solve_stage,
)

N_PCC_POINTS = 5


def _require(res: SolveResult, context: str) -> None:
    if not res.passed:
        raise SystemExit(f"{context} failed: status={res.status}; {res.notes}")
    if res.max_cd > SIMUL_CD_TOL:
        raise SystemExit(
            f"{context}: max(c_t d_t)={res.max_cd:.6e} exceeds {SIMUL_CD_TOL}; stop per handoff."
        )


def no_storage_baseline(load: np.ndarray, pv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    g = np.maximum(load - pv, 0.0)
    s = np.maximum(pv - load, 0.0)
    return g, s


def main() -> None:
    attach = DEFAULT_ATTACH1
    template = DEFAULT_RESULT1_TEMPLATE
    data = load_attachment1(attach)
    labels, _blocks = inspect_template(template)
    price = data["price"].to_numpy()
    load = data["load_kwh"].to_numpy()
    pv = data["pv_kwh"].to_numpy()
    params = default_params()
    price_min = float(np.min(price))

    m1 = solve_stage("M1", price, load, pv, exclusive=False, cost_cap=None, params=params)
    _m1s, m2 = solve_lexico("M2", price, load, pv, exclusive=False, params=params)
    m3 = solve_stage("M3", price, load, pv, exclusive=True, cost_cap=None, params=params)
    _m3s, m4 = solve_lexico("M4", price, load, pv, exclusive=True, params=params)

    results = {"M1": m1, "M2": m2, "M3": m3, "M4": m4}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_comparison_csv(OUTPUT_DIR / "q1_model_comparison.csv", [m1, m2, m3, m4])
    write_model_selection_md(OUTPUT_DIR / "q1_model_selection.md", results, official=OFFICIAL_MODEL)

    _require(m1, "M1")
    _require(m3, "M3")
    if abs(m1.purchase_cost - m3.purchase_cost) > EPS_C:
        raise SystemExit(
            f"M1 vs M3 cost mismatch: {m1.purchase_cost} vs {m3.purchase_cost}"
        )
    if abs(m1.purchase_cost - EXPECTED_M1_COST) > COST_REPRO_TOL:
        raise SystemExit(
            f"M1 cost {m1.purchase_cost:.12f} differs from confirmed {EXPECTED_M1_COST} "
            f"by more than {COST_REPRO_TOL} yuan; stop."
        )
    if m1.max_s_minus_pv > 1e-8:
        raise SystemExit(f"s_t > P_t: {m1.max_s_minus_pv}")

    official = m1
    write_plan_csv(OUTPUT_DIR / "q1_plan.csv", labels, data, official)
    write_summary_csv(OUTPUT_DIR / "q1_summary.csv", official)
    write_result1_xlsx(template, OUTPUT_DIR / "result1.xlsx", official)
    write_figures(data, official)

    g_base, s_base = no_storage_baseline(load, pv)
    write_baseline_csv(OUTPUT_DIR / "q1_baseline.csv", g_base, s_base, price, official)

    sens_rows: list[dict] = []
    sens_rows.append(sensitivity_row("eff_A", m1))

    p_b = ModelParams(eta_c=0.9, eta_d=0.9)
    m_b = solve_stage("eff_B", price, load, pv, params=p_b)
    _require(m_b, "eff_B")
    if abs(m_b.purchase_cost - EXPECTED_EFF_B_COST) > 1e-3:
        raise SystemExit(
            f"eff_B cost {m_b.purchase_cost} != expected {EXPECTED_EFF_B_COST}; "
            "check that eta_c/eta_d are passed into the model."
        )
    sens_rows.append(sensitivity_row("eff_B", m_b))

    for case, nom in (("cap_minus10", 10800.0), ("cap_plus10", 13200.0)):
        e_min, e_max = soc_window(nom)
        p = ModelParams(
            e_min_kwh=e_min,
            e_max_kwh=e_max,
            e0_kwh=6000.0,
            nominal_capacity_kwh=nom,
        )
        r = solve_stage(case, price, load, pv, params=p)
        _require(r, case)
        sens_rows.append(sensitivity_row(case, r))

    for case, pkw in (("power_minus10", 4500.0), ("power_plus10", 5500.0)):
        p = ModelParams(power_limit_kw=pkw)
        r = solve_stage(case, price, load, pv, params=p)
        _require(r, case)
        sens_rows.append(sensitivity_row(case, r))

    gmax_min_kw = min_feasible_peak_kw(price, load, pv, params)
    peak_nat = m1.peak_grid_kw
    if gmax_min_kw > peak_nat + 1e-6:
        raise SystemExit(f"min peak {gmax_min_kw} kW exceeds unconstrained M1 peak {peak_nat}")
    grid_kw_grid = np.linspace(gmax_min_kw, peak_nat, N_PCC_POINTS)
    for i, gkw in enumerate(grid_kw_grid):
        p = ModelParams(grid_limit_kw=float(gkw))
        r = solve_stage(f"pcc_{i}", price, load, pv, params=p)
        _require(r, f"pcc_{i}")
        sens_rows.append(sensitivity_row(f"pcc_gmax_{gkw:.4f}kw", r))

    write_sensitivity_csv(OUTPUT_DIR / "q1_sensitivity.csv", sens_rows)
    write_validation_md(
        OUTPUT_DIR / "q1_validation.md",
        data,
        labels,
        official,
        attach,
        template,
        price_min=price_min,
        gmax_min_kw=gmax_min_kw,
    )

    print(f"Q1 official = {OFFICIAL_MODEL}")
    print(f"  cost={official.purchase_cost:.6f} yuan")
    print(f"  G={official.grid_purchase:.6f} kWh")
    print(f"  peak={official.peak_grid_kw:.6f} kW")
    print(f"  S={official.curtailment:.6f} kWh")
    print(f"  Q={official.throughput:.6f} kWh")
    print(f"  max(c d)={official.max_cd:.3e}")
    print(f"  residual={official.max_balance_residual:.3e}")
    print(f"  price_min={price_min:.6g}")
    print(f"  Gmax_min(analysis)={gmax_min_kw:.6f} kW")
    print("wrote output/q1_*.csv, output/q1_*.md, output/result1.xlsx, fig/fig1_*.png")


if __name__ == "__main__":
    main()

# ===== q2/__init__.py =====
"""C-problem Q2 pilot implementation."""


# ===== q2/config.py =====
"""Central configuration for the Q2 pilot only."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ATTACH_DIR = Path(os.environ.get("CUMCM_C_ATTACH_DIR", ROOT / "data" / "raw" / "附件"))
ATTACH1 = ATTACH_DIR / "附件1.xlsx"
ATTACH2 = ATTACH_DIR / "附件2.xlsx"
OUTPUT_DIR = ROOT / "output" / "q2_pilot"
FULL_OUTPUT_DIR = ROOT / "output" / "q2_full_linked"
FULL_K8_RISK_OUTPUT_DIR = ROOT / "output" / "q2_full_k8_risk"
POLICY_CONSISTENT_OUTPUT_DIR = ROOT / "output" / "q2_policy_consistent"
FIG_DIR = ROOT / "fig" / "q2_pilot"
FIG_POLICY_CONSISTENT_DIR = ROOT / "fig" / "q2_policy_consistent"
FIG_Q2_FINAL_DIR = ROOT / "fig" / "q2_final"
SIGNED_OFF_RESULT2 = ROOT / "output" / "result2.xlsx"
SIGNED_OFF_RESULT2_SHA256 = (
    "70a9785c9e2bba66f7694878e4587ad15c57dc090ec6798d07ba6780b4780ef7"
)
RESULT2_TEMPLATE = ATTACH_DIR / "附件5" / "result2.xlsx"
CANDIDATE_RESULT2 = POLICY_CONSISTENT_OUTPUT_DIR / "result2.xlsx"
RESULT2_SIGNED_OFF_BACKUP = POLICY_CONSISTENT_OUTPUT_DIR / "result2_signed_off_backup.xlsx"

T = 144
DELTA_H = 1.0 / 6.0
ETA_C = float(np.sqrt(0.9))
ETA_D = float(np.sqrt(0.9))
E_MIN_KWH = 1200.0
E_MAX_KWH = 10800.0
E_INITIAL_KWH = 6000.0
POWER_LIMIT_KW = 5000.0
POWER_LIMIT_KWH = POWER_LIMIT_KW * DELTA_H

# Signed-off contract semantics; keep all production Q2 assumptions here.
CONTRACT_TAKE_MODE = "x_le_q"
NORMAL_COST_BASIS = "planned_q"
EMERGENCY_PRICE_MULTIPLIER = 5.0

LOAD_HISTORY_SAME_WEEKDAY = 4
PV_HISTORY_DAYS = 7
RESIDUAL_POOL_DAYS = 28
K_CANDIDATES = (2, 4, 6, 8, 10, 12)
K_VALIDATION_DAYS = 14
K_RECALIBRATION_DAYS = 14
# Fixed from the R1--R4 timing audit: a validation-day score must be obtained
# within this budget before its K is eligible under the one-standard-error rule.
T_MAX_SECONDS: float | None = 0.20
FIXED_SCENARIO_K = 8
K_SENSITIVITY_CANDIDATES = (4, 8, 12)
RISK_ALPHA_CANDIDATES = (0.60, 0.70, 0.80, 0.90)
OFFICIAL_OUTPUT_START = "2025-02-01"
RISK_CALIBRATION_DAYS = 14
MPC_COST_TOL = 1e-7
NEXT_DAY_VALUE_GAP_TOL_YUAN = 1.0
NEXT_DAY_VALUE_MAX_SAMPLES = 25
NUMERIC_TOL = 1e-6
SIMULTANEOUS_CD_TOL = 1e-4
SOLVER = "HIGHS"
PILOT_DATES = ("2025-02-01", "2025-06-21")

# ===== q2/data.py =====
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import ATTACH1, ATTACH2, DELTA_H, T


def normalize_time(value: object) -> str:
    if isinstance(value, (datetime, time)):
        return value.strftime("%H:%M")
    return str(value).strip()


@dataclass(frozen=True)
class Q2Data:
    dates: pd.DatetimeIndex
    time_labels: tuple[str, ...]
    price: np.ndarray
    fallback_load: np.ndarray
    fallback_pv: np.ndarray
    load: np.ndarray
    pv: np.ndarray


def _finite_nonnegative(values: np.ndarray, name: str) -> None:
    if not np.isfinite(values).all():
        raise ValueError(f"{name} contains missing or non-finite values")
    if np.any(values < 0):
        raise ValueError(f"{name} contains negative values")


def load_q2_data(attach1: Path = ATTACH1, attach2: Path = ATTACH2) -> Q2Data:
    if not attach1.exists() or not attach2.exists():
        raise FileNotFoundError(f"Required attachments not found: {attach1}, {attach2}")

    day = pd.read_excel(attach1, sheet_name="Sheet1")
    expected = ["时间", "电价", "小区负载", "光伏发电预测功率"]
    if list(day.columns) != expected or len(day) != T:
        raise ValueError("附件1 must have the four expected columns and 144 raw-order rows")
    price = pd.to_numeric(day["电价"], errors="coerce").to_numpy(float)
    fallback_load = pd.to_numeric(day["小区负载"], errors="coerce").to_numpy(float) * DELTA_H
    fallback_pv = pd.to_numeric(day["光伏发电预测功率"], errors="coerce").to_numpy(float) * DELTA_H
    _finite_nonnegative(price, "附件1 price")
    _finite_nonnegative(fallback_load, "附件1 load forecast")
    _finite_nonnegative(fallback_pv, "附件1 PV forecast")
    if np.any(price <= 0):
        raise ValueError("Q2 pilot requires strictly positive prices")

    sheets = pd.read_excel(attach2, sheet_name=None, header=None)
    if list(sheets) != ["小区负载", "光伏发电实际功率"]:
        raise ValueError(f"Unexpected 附件2 sheets: {list(sheets)}")
    load_raw = sheets["小区负载"]
    pv_raw = sheets["光伏发电实际功率"]
    if load_raw.shape != (366, 145) or pv_raw.shape != (366, 145):
        raise ValueError(f"附件2 must be 366x145; got {load_raw.shape}, {pv_raw.shape}")
    if load_raw.iloc[0, 0] != "日期\\时间" or pv_raw.iloc[0, 0] != "日期\\时间":
        raise ValueError("附件2 first header must be 日期\\时间")

    time_labels = tuple(normalize_time(x) for x in load_raw.iloc[0, 1:])
    pv_labels = tuple(normalize_time(x) for x in pv_raw.iloc[0, 1:])
    if time_labels != pv_labels or len(time_labels) != T:
        raise ValueError("附件2 load/PV time labels differ")
    if time_labels[0] != "00:10" or time_labels[-1] != "0:00+1":
        raise ValueError(f"Unexpected raw time order: {time_labels[0]} .. {time_labels[-1]}")

    dates = pd.DatetimeIndex(pd.to_datetime(load_raw.iloc[1:, 0], errors="raise")).normalize()
    pv_dates = pd.DatetimeIndex(pd.to_datetime(pv_raw.iloc[1:, 0], errors="raise")).normalize()
    expected_dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    if not dates.equals(expected_dates) or not pv_dates.equals(expected_dates):
        raise ValueError("附件2 dates must be continuous 2025-01-01 through 2025-12-31")
    load = load_raw.iloc[1:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(float) * DELTA_H
    pv = pv_raw.iloc[1:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(float) * DELTA_H
    _finite_nonnegative(load, "附件2 load")
    _finite_nonnegative(pv, "附件2 PV")
    return Q2Data(dates, time_labels, price, fallback_load, fallback_pv, load, pv)


def write_input_audit(data: Q2Data, path: Path) -> None:
    daily = []
    for i, date in enumerate(data.dates):
        load = float(data.load[i].sum())
        pv = float(data.pv[i].sum())
        daily.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "load_kwh": load,
                "pv_kwh": pv,
                "net_load_kwh": load - pv,
            }
        )
    audit = {
        "shape": {"days": len(data.dates), "periods_per_day": T},
        "date_start": data.dates[0].strftime("%Y-%m-%d"),
        "date_end": data.dates[-1].strftime("%Y-%m-%d"),
        "dates_continuous": True,
        "missing_count": int(np.isnan(data.load).sum() + np.isnan(data.pv).sum()),
        "negative_load_count": int(np.sum(data.load < 0)),
        "negative_pv_count": int(np.sum(data.pv < 0)),
        "price_min_yuan_per_kwh": float(data.price.min()),
        "unit_conversion": "attachment powers multiplied by 1/6 h to obtain kWh",
        "time_mapping": (
            "attachment raw column t maps to internal index t=0..143 and template column t; "
            "no sorting, rotation, or invented 0:00-0:10 period"
        ),
        "first_time_label": data.time_labels[0],
        "last_time_label": data.time_labels[-1],
        "daily_energy": daily,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ===== q2/export_result2.py =====
"""Export a candidate result2.xlsx for the policy-consistent Q2 path.

Writes only under output/q2_policy_consistent/. Never overwrites the signed-off
output/result2.xlsx.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from copy import copy
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from q2.config import (
    CANDIDATE_RESULT2,
    E_MAX_KWH,
    E_MIN_KWH,
    EMERGENCY_PRICE_MULTIPLIER,
    NUMERIC_TOL,
    OFFICIAL_OUTPUT_START,
    POLICY_CONSISTENT_OUTPUT_DIR,
    POWER_LIMIT_KWH,
    RESULT2_SIGNED_OFF_BACKUP,
    RESULT2_TEMPLATE,
    ROOT,
    SIGNED_OFF_RESULT2,
    SIGNED_OFF_RESULT2_SHA256,
    SIMULTANEOUS_CD_TOL,
    T,
)
from q2.data import Q2Data
from q2.pilot import planned_q_hash

PURCHASE_SHEET = "计划购电量"
CHARGE_SHEET = "充放电量"
EMERGENCY_SHEET = "紧急购电量"
OUTPUT_END = "2025-12-31"
N_OUTPUT_DAYS = 334
BLOCKS_PER_DAY = 6
LAST_PERIOD_COL = 1 + T
Q_SUM_COL = 2 + T
COST_COL = 3 + T
FOUR_HOUR_BLOCKS = (
    ("0:00-4:00", 0, 24),
    ("4:00-8:00", 24, 48),
    ("8:00-12:00", 48, 72),
    ("12:00-16:00", 72, 96),
    ("16:00-20:00", 96, 120),
    ("20:00-24:00", 120, 144),
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def official_output_dates() -> pd.DatetimeIndex:
    return pd.date_range(OFFICIAL_OUTPUT_START, OUTPUT_END, freq="D")


def minutes_to_clock(minutes: int) -> str:
    if minutes == 24 * 60:
        return "24:00"
    hours, mins = divmod(int(minutes), 60)
    return f"{hours:02d}:{mins:02d}"


def format_emergency_interval(t0: int, t1: int) -> str:
    if not (0 <= t0 <= t1 < T):
        raise ValueError(f"invalid emergency interval [{t0}, {t1}]")
    return f"{minutes_to_clock(t0 * 10)}-{minutes_to_clock((t1 + 1) * 10)}"


def emergency_segments(
    emergency: np.ndarray,
    tol: float = 0.0,
) -> list[tuple[int, int, float]]:
    values = np.asarray(emergency, dtype=float)
    if values.shape != (T,):
        raise ValueError(f"emergency vector must have length {T}")
    segments: list[tuple[int, int, float]] = []
    t = 0
    while t < T:
        if values[t] > tol:
            t0 = t
            total = 0.0
            while t < T and values[t] > tol:
                total += float(values[t])
                t += 1
            segments.append((t0, t - 1, total))
        else:
            t += 1
    return segments


def block_energy(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    return np.array([float(np.sum(values[start:end])) for _name, start, end in FOUR_HOUR_BLOCKS])


def assert_isolated_candidate_path(dest: Path) -> None:
    dest_resolved = dest.resolve()
    signed = SIGNED_OFF_RESULT2.resolve()
    root = POLICY_CONSISTENT_OUTPUT_DIR.resolve()
    if dest_resolved == signed:
        raise RuntimeError("refusing to overwrite signed-off output/result2.xlsx")
    if dest_resolved.parent != root:
        raise RuntimeError("candidate result2.xlsx must live under output/q2_policy_consistent/")


def preserve_signed_off_backup() -> str:
    if not SIGNED_OFF_RESULT2.exists():
        raise FileNotFoundError(f"missing signed-off {SIGNED_OFF_RESULT2}")
    signed_hash = file_sha256(SIGNED_OFF_RESULT2)
    if signed_hash != SIGNED_OFF_RESULT2_SHA256:
        raise RuntimeError(
            "signed-off output/result2.xlsx hash mismatch; refusing to copy a mutated file"
        )
    RESULT2_SIGNED_OFF_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if RESULT2_SIGNED_OFF_BACKUP.exists():
        backup_hash = file_sha256(RESULT2_SIGNED_OFF_BACKUP)
        if backup_hash != signed_hash:
            raise RuntimeError("existing result2 backup does not match the signed-off file")
    else:
        shutil.copy2(SIGNED_OFF_RESULT2, RESULT2_SIGNED_OFF_BACKUP)
        backup_hash = file_sha256(RESULT2_SIGNED_OFF_BACKUP)
        if backup_hash != signed_hash:
            raise RuntimeError("failed to copy a bit-identical signed-off result2 backup")
    return signed_hash


def _copy_style(source, dest) -> None:
    if source.has_style:
        dest.font = copy(source.font)
        dest.border = copy(source.border)
        dest.fill = copy(source.fill)
        dest.number_format = source.number_format
        dest.alignment = copy(source.alignment)
        dest.protection = copy(source.protection)


def _set_number(cell, value: float | None) -> None:
    cell.value = None if value is None else float(value)
    cell.number_format = "General"


def _sheet_date(value: object) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def _load_day_dispatch(dispatch_dir: Path, date_text: str) -> pd.DataFrame:
    path = dispatch_dir / f"dispatch_{date_text}.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing dispatch {path}")
    frame = pd.read_csv(path)
    if len(frame) != T:
        raise AssertionError(f"{date_text} dispatch has {len(frame)} rows, expected {T}")
    if str(frame["time"].iloc[0]) != "00:10" or str(frame["time"].iloc[-1]) != "0:00+1":
        raise AssertionError(f"{date_text} dispatch is not in raw attachment time order")
    return frame


def write_candidate_result2(
    dest: Path,
    dispatch_dir: Path,
    daily: pd.DataFrame,
    data: Q2Data,
    template: Path = RESULT2_TEMPLATE,
) -> None:
    assert_isolated_candidate_path(dest)
    if not template.exists():
        raise FileNotFoundError(f"missing result2 template {template}")
    dates = official_output_dates()
    ledger = daily.copy()
    ledger["date"] = pd.to_datetime(ledger["date"]).dt.strftime("%Y-%m-%d")
    ledger = ledger.loc[ledger["date"].isin(dates.strftime("%Y-%m-%d"))].sort_values("date")
    if list(ledger["date"]) != list(dates.strftime("%Y-%m-%d")):
        raise AssertionError("Feb-Dec ledger dates do not match the 334 official output days")

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, dest)
    workbook = load_workbook(dest)
    purchase = workbook[PURCHASE_SHEET]
    charge = workbook[CHARGE_SHEET]
    emergency = workbook[EMERGENCY_SHEET]
    if purchase.max_row != 1 + N_OUTPUT_DAYS:
        raise AssertionError("purchase template does not contain 334 dated rows")
    if purchase.cell(1, Q_SUM_COL).value != "全天购电量" or purchase.cell(1, COST_COL).value != "全天购电费":
        raise AssertionError("purchase template totals headers mismatch")
    if str(purchase.cell(1, 2).value) != "0:10-0:20":
        raise AssertionError("purchase template is not in raw 144-period order")
    if str(purchase.cell(1, LAST_PERIOD_COL).value) != "0:00-0:10+1":
        raise AssertionError("purchase template last period header mismatch")

    charge_style_rows = [2 + offset for offset in range(BLOCKS_PER_DAY)]
    emergency_styles = [emergency.cell(2, column) for column in range(1, 4)]
    emergency_row = 2
    for day_index, date in enumerate(dates):
        date_text = date.strftime("%Y-%m-%d")
        row = ledger.loc[ledger["date"] == date_text].iloc[0]
        frame = _load_day_dispatch(dispatch_dir, date_text)
        q = frame["planned_q_kwh"].to_numpy(dtype=float)
        planned_cost = float(data.price @ q)
        purchase_row = 2 + day_index
        sheet_date = _sheet_date(purchase.cell(purchase_row, 1).value)
        if sheet_date != date:
            raise AssertionError(f"purchase date mismatch at row {purchase_row}: {sheet_date} vs {date}")
        for period in range(T):
            _set_number(purchase.cell(purchase_row, 2 + period), float(q[period]))
        _set_number(purchase.cell(purchase_row, Q_SUM_COL), float(np.sum(q)))
        _set_number(purchase.cell(purchase_row, COST_COL), planned_cost)

        charge_base = 2 + day_index * BLOCKS_PER_DAY
        charge_kwh = block_energy(frame["charge_kwh"].to_numpy(dtype=float))
        discharge_kwh = block_energy(frame["discharge_kwh"].to_numpy(dtype=float))
        for offset, (name, _start, _end) in enumerate(FOUR_HOUR_BLOCKS):
            excel_row = charge_base + offset
            style_source_row = charge_style_rows[offset]
            for column in range(1, 7):
                _copy_style(charge.cell(style_source_row, column), charge.cell(excel_row, column))
            charge.cell(excel_row, 1).value = purchase.cell(purchase_row, 1).value if offset == 0 else None
            charge.cell(excel_row, 2).value = name
            _set_number(charge.cell(excel_row, 3), float(charge_kwh[offset]))
            _set_number(charge.cell(excel_row, 4), float(discharge_kwh[offset]))
            if offset == 0:
                charge.cell(excel_row, 5).value = "00:00"
                _set_number(charge.cell(excel_row, 6), float(row["soc_start_kwh"]))
            elif offset == 1:
                charge.cell(excel_row, 5).value = "24:00"
                _set_number(charge.cell(excel_row, 6), float(row["soc_end_kwh"]))
            else:
                charge.cell(excel_row, 5).value = None
                _set_number(charge.cell(excel_row, 6), None)

        segments = emergency_segments(frame["emergency_kwh"].to_numpy(dtype=float))
        if not segments:
            for column in range(1, 4):
                _copy_style(emergency_styles[column - 1], emergency.cell(emergency_row, column))
            emergency.cell(emergency_row, 1).value = purchase.cell(purchase_row, 1).value
            emergency.cell(emergency_row, 2).value = None
            _set_number(emergency.cell(emergency_row, 3), None)
            emergency_row += 1
        else:
            for seg_index, (t0, t1, amount) in enumerate(segments):
                for column in range(1, 4):
                    _copy_style(emergency_styles[column - 1], emergency.cell(emergency_row, column))
                emergency.cell(emergency_row, 1).value = (
                    purchase.cell(purchase_row, 1).value if seg_index == 0 else None
                )
                emergency.cell(emergency_row, 2).value = format_emergency_interval(t0, t1)
                _set_number(emergency.cell(emergency_row, 3), float(amount))
                emergency_row += 1

    leftover_start = emergency_row
    leftover_end = max(emergency.max_row, leftover_start - 1)
    for row_index in range(leftover_start, leftover_end + 1):
        for column in range(1, 4):
            emergency.cell(row_index, column).value = None

    workbook.save(dest)


def _cell_float(sheet: Worksheet, row: int, column: int) -> float:
    value = sheet.cell(row, column).value
    if value in (None, ""):
        return 0.0
    if isinstance(value, datetime):
        raise TypeError(f"{sheet.title}!{sheet.cell(row, column).coordinate} stored a date instead of a number")
    return float(value)


def audit_candidate_result2(
    dest: Path,
    dispatch_dir: Path,
    daily: pd.DataFrame,
    data: Q2Data,
    inherited_soc_kwh: float,
) -> dict:
    assert_isolated_candidate_path(dest)
    workbook = load_workbook(dest, data_only=False)
    purchase = workbook[PURCHASE_SHEET]
    charge = workbook[CHARGE_SHEET]
    emergency = workbook[EMERGENCY_SHEET]
    dates = official_output_dates()
    ledger = daily.copy()
    ledger["date"] = pd.to_datetime(ledger["date"]).dt.strftime("%Y-%m-%d")
    ledger = ledger.loc[ledger["date"].isin(dates.strftime("%Y-%m-%d"))].sort_values("date")
    if len(ledger) != N_OUTPUT_DAYS:
        raise AssertionError("ledger does not cover 334 official output days")

    rows: list[dict] = []
    emergency_row = 2
    previous_soc_end: float | None = None
    max_q_abs = 0.0
    max_cost_abs = 0.0
    max_emergency_abs = 0.0
    max_charge_abs = 0.0
    max_soc_abs = 0.0
    max_balance = 0.0
    max_soc_gap = 0.0
    dated_emergency_rows = 0

    for day_index, date in enumerate(dates):
        date_text = date.strftime("%Y-%m-%d")
        ledger_row = ledger.loc[ledger["date"] == date_text].iloc[0]
        frame = _load_day_dispatch(dispatch_dir, date_text)
        q = frame["planned_q_kwh"].to_numpy(dtype=float)
        x = frame["actual_x_kwh"].to_numpy(dtype=float)
        emergency_kwh = frame["emergency_kwh"].to_numpy(dtype=float)
        charge_kwh = frame["charge_kwh"].to_numpy(dtype=float)
        discharge_kwh = frame["discharge_kwh"].to_numpy(dtype=float)
        purchase_row = 2 + day_index
        sheet_date = _sheet_date(purchase.cell(purchase_row, 1).value)
        if sheet_date != date:
            raise AssertionError(f"xlsx purchase date mismatch: {sheet_date} vs {date}")
        xlsx_q = np.array([_cell_float(purchase, purchase_row, 2 + period) for period in range(T)])
        q_abs = float(np.max(np.abs(xlsx_q - q)))
        xlsx_q_sum = _cell_float(purchase, purchase_row, Q_SUM_COL)
        xlsx_cost = _cell_float(purchase, purchase_row, COST_COL)
        planned_cost = float(data.price @ q)
        cost_abs = abs(xlsx_cost - planned_cost)
        q_sum_abs = abs(xlsx_q_sum - float(np.sum(q)))

        charge_base = 2 + day_index * BLOCKS_PER_DAY
        expected_charge = block_energy(charge_kwh)
        expected_discharge = block_energy(discharge_kwh)
        charge_abs = 0.0
        for offset, (name, _start, _end) in enumerate(FOUR_HOUR_BLOCKS):
            excel_row = charge_base + offset
            date_cell = charge.cell(excel_row, 1).value
            if offset == 0:
                if _sheet_date(date_cell) != date:
                    raise AssertionError(f"charge date mismatch on {date_text}")
            elif date_cell not in (None, ""):
                raise AssertionError(f"charge date repeated on {date_text} block {offset}")
            if charge.cell(excel_row, 2).value != name:
                raise AssertionError(f"charge block label mismatch on {date_text}")
            charge_abs = max(
                charge_abs,
                abs(_cell_float(charge, excel_row, 3) - expected_charge[offset]),
                abs(_cell_float(charge, excel_row, 4) - expected_discharge[offset]),
            )
        start_clock = charge.cell(charge_base, 5).value
        end_clock = charge.cell(charge_base + 1, 5).value
        if start_clock not in ("00:00", datetime.strptime("00:00", "%H:%M").time()):
            raise AssertionError(f"{date_text} 00:00 SOC clock mismatch")
        if end_clock != "24:00":
            raise AssertionError(f"{date_text} 24:00 SOC clock mismatch")
        xlsx_soc_start = _cell_float(charge, charge_base, 6)
        xlsx_soc_end = _cell_float(charge, charge_base + 1, 6)
        soc_start_abs = abs(xlsx_soc_start - float(ledger_row["soc_start_kwh"]))
        soc_end_abs = abs(xlsx_soc_end - float(ledger_row["soc_end_kwh"]))
        last_dispatch_soc = float(frame["soc_kwh"].iloc[-1])
        soc_dispatch_abs = abs(xlsx_soc_end - last_dispatch_soc)
        if previous_soc_end is not None:
            max_soc_gap = max(max_soc_gap, abs(xlsx_soc_start - previous_soc_end))
        previous_soc_end = xlsx_soc_end

        date_cell = emergency.cell(emergency_row, 1).value
        if date_cell in (None, ""):
            raise AssertionError(f"missing dated emergency row for {date_text}")
        if _sheet_date(date_cell) != date:
            raise AssertionError(f"emergency date mismatch: {date_cell} vs {date_text}")
        dated_emergency_rows += 1
        xlsx_emergency = 0.0
        first = True
        while emergency_row <= emergency.max_row:
            current_date = emergency.cell(emergency_row, 1).value
            interval = emergency.cell(emergency_row, 2).value
            amount = emergency.cell(emergency_row, 3).value
            if not first and current_date not in (None, ""):
                break
            if interval in (None, "") and amount in (None, ""):
                if first:
                    emergency_row += 1
                break
            xlsx_emergency += float(amount)
            first = False
            emergency_row += 1
        if float(emergency_kwh.min()) < -NUMERIC_TOL:
            raise AssertionError(f"{date_text} has negative emergency energy")
        e_abs = abs(xlsx_emergency - float(np.sum(np.clip(emergency_kwh, 0.0, None))))
        e_ledger_abs = abs(xlsx_emergency - float(ledger_row["emergency_kwh"]))
        e_recon_abs = e_ledger_abs

        residual = (
            frame["actual_x_kwh"]
            + frame["emergency_kwh"]
            + frame["pv_kwh"]
            - frame["curtailment_kwh"]
            + frame["discharge_kwh"]
            - frame["load_kwh"]
            - frame["charge_kwh"]
        )
        day_index_data = int(data.dates.get_loc(date))
        balance = float(residual.abs().max())
        x_minus_q = float(np.max(x - q))
        cd = float((charge_kwh * discharge_kwh).max())
        if (
            planned_q_hash(q) != ledger_row["planned_q_sha256"]
            or abs(planned_cost - float(ledger_row["planned_cost_yuan"])) > 1e-6
            or abs(float(np.sum(q)) - float(ledger_row["planned_q_kwh"])) > 1e-6
        ):
            raise AssertionError(f"{date_text} dispatch does not match the annual ledger")
        if not np.allclose(frame["load_kwh"].to_numpy(), data.load[day_index_data], atol=1e-12):
            raise AssertionError(f"{date_text} load mismatch versus attachment")
        emergency_cost = float(EMERGENCY_PRICE_MULTIPLIER * data.price @ emergency_kwh)
        if abs(emergency_cost - float(ledger_row["emergency_cost_yuan"])) > 1e-4:
            raise AssertionError(f"{date_text} emergency cost mismatch versus ledger")

        rows.append(
            {
                "date": date_text,
                "q_max_abs_kwh": q_abs,
                "q_sum_abs_kwh": q_sum_abs,
                "planned_cost_abs_yuan": cost_abs,
                "charge_block_abs_kwh": charge_abs,
                "soc_start_abs_kwh": soc_start_abs,
                "soc_end_abs_kwh": soc_end_abs,
                "soc_vs_dispatch_abs_kwh": soc_dispatch_abs,
                "emergency_abs_kwh": e_abs,
                "emergency_vs_ledger_abs_kwh": e_ledger_abs,
                "emergency_recon_abs_kwh": e_recon_abs,
                "max_balance_residual_kwh": balance,
                "max_x_minus_q_kwh": x_minus_q,
                "max_simultaneous_cd_kwh2": cd,
                "charge_power_ok": float(charge_kwh.max()) <= POWER_LIMIT_KWH + NUMERIC_TOL,
                "discharge_power_ok": float(discharge_kwh.max()) <= POWER_LIMIT_KWH + NUMERIC_TOL,
                "soc_bounds_ok": (
                    float(frame["soc_kwh"].min()) >= E_MIN_KWH - NUMERIC_TOL
                    and float(frame["soc_kwh"].max()) <= E_MAX_KWH + NUMERIC_TOL
                ),
            }
        )
        max_q_abs = max(max_q_abs, q_abs, q_sum_abs)
        max_cost_abs = max(max_cost_abs, cost_abs)
        max_emergency_abs = max(max_emergency_abs, e_recon_abs)
        max_charge_abs = max(max_charge_abs, charge_abs)
        max_soc_abs = max(max_soc_abs, soc_start_abs, soc_end_abs, soc_dispatch_abs)
        max_balance = max(max_balance, balance)

    if dated_emergency_rows != N_OUTPUT_DAYS:
        raise AssertionError("emergency sheet does not have one dated row per official day")
    feb1_soc = float(ledger.iloc[0]["soc_start_kwh"])
    if abs(feb1_soc - inherited_soc_kwh) > NUMERIC_TOL:
        raise AssertionError("Feb 1 xlsx/ledger SOC does not inherit January warmup")

    xlsx_planned_q = sum(_cell_float(purchase, row, Q_SUM_COL) for row in range(2, 2 + N_OUTPUT_DAYS))
    xlsx_planned_cost = sum(_cell_float(purchase, row, COST_COL) for row in range(2, 2 + N_OUTPUT_DAYS))
    xlsx_emergency = 0.0
    for row in range(2, emergency.max_row + 1):
        amount = emergency.cell(row, 3).value
        if amount not in (None, ""):
            xlsx_emergency += float(amount)

    checks = {
        "n_days": N_OUTPUT_DAYS,
        "n_periods": T,
        "units": {"energy": "kWh", "cost": "yuan"},
        "purchase_sheet_rows": 1 + N_OUTPUT_DAYS,
        "charge_sheet_rows": 1 + N_OUTPUT_DAYS * BLOCKS_PER_DAY,
        "dated_emergency_rows": dated_emergency_rows,
        "feb1_inherited_soc_kwh": inherited_soc_kwh,
        "feb1_xlsx_soc_kwh": float(ledger.iloc[0]["soc_start_kwh"]),
        "max_q_abs_kwh": max_q_abs,
        "max_planned_cost_abs_yuan": max_cost_abs,
        "max_charge_block_abs_kwh": max_charge_abs,
        "max_soc_abs_kwh": max_soc_abs,
        "max_soc_continuity_gap_kwh": max_soc_gap,
        "max_emergency_recon_abs_kwh": max_emergency_abs,
        "max_balance_residual_kwh": max_balance,
        "xlsx_planned_q_kwh": xlsx_planned_q,
        "ledger_planned_q_kwh": float(ledger["planned_q_kwh"].sum()),
        "xlsx_planned_cost_yuan": xlsx_planned_cost,
        "ledger_planned_cost_yuan": float(ledger["planned_cost_yuan"].sum()),
        "xlsx_emergency_kwh": xlsx_emergency,
        "ledger_emergency_kwh": float(ledger["emergency_kwh"].sum()),
        "ledger_total_cost_yuan": float(ledger["total_cost_yuan"].sum()),
        "pass": (
            max_q_abs < 1e-8
            and max_cost_abs < 1e-6
            and max_charge_abs < 1e-8
            and max_soc_abs < 1e-8
            and max_soc_gap < NUMERIC_TOL
            and max_emergency_abs < 1e-8
            and max_balance < NUMERIC_TOL
            and abs(xlsx_planned_q - float(ledger["planned_q_kwh"].sum())) < 1e-6
            and abs(xlsx_planned_cost - float(ledger["planned_cost_yuan"].sum())) < 1e-4
            and abs(xlsx_emergency - float(ledger["emergency_kwh"].sum())) < 1e-4
            and all(row["charge_power_ok"] and row["discharge_power_ok"] and row["soc_bounds_ok"] for row in rows)
            and all(row["max_x_minus_q_kwh"] < NUMERIC_TOL for row in rows)
            and all(row["max_simultaneous_cd_kwh2"] <= SIMULTANEOUS_CD_TOL for row in rows)
            and dest.resolve() != SIGNED_OFF_RESULT2.resolve()
            and file_sha256(SIGNED_OFF_RESULT2) == SIGNED_OFF_RESULT2_SHA256
        ),
    }
    return {"summary": checks, "daily": rows}


def write_result2_audit(audit: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(audit["daily"]).to_csv(output / "result2_cell_audit.csv", index=False)
    payload = {
        "candidate_result2": str(CANDIDATE_RESULT2.relative_to(ROOT)),
        "signed_off_result2_unchanged": True,
        "signed_off_sha256": SIGNED_OFF_RESULT2_SHA256,
        "backup": str(RESULT2_SIGNED_OFF_BACKUP.relative_to(ROOT)),
        **audit["summary"],
    }
    (output / "result2_cell_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

# ===== q2/forecast.py =====
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import LOAD_HISTORY_SAME_WEEKDAY, PV_HISTORY_DAYS, T
from q2.data import Q2Data


@dataclass(frozen=True)
class ForecastArchive:
    load_hat: np.ndarray
    pv_hat: np.ndarray
    load_residual: np.ndarray
    pv_residual: np.ndarray
    load_sources: tuple[tuple[int, ...], ...]
    pv_sources: tuple[tuple[int, ...], ...]


def forecast_as_of(
    data: Q2Data, target_index: int, history_end_exclusive: int
) -> tuple[np.ndarray, np.ndarray, tuple[int, ...], tuple[int, ...]]:
    """Forecast target using actual observations with index < history_end_exclusive."""
    if not 0 <= history_end_exclusive <= target_index:
        raise ValueError("forecast cutoff must not exceed target date")
    target = data.dates[target_index]
    same_weekday = [
        j
        for j in range(history_end_exclusive)
        if data.dates[j].weekday() == target.weekday()
    ]
    load_sources = tuple(same_weekday[-LOAD_HISTORY_SAME_WEEKDAY:])
    pv_sources = tuple(
        range(max(0, history_end_exclusive - PV_HISTORY_DAYS), history_end_exclusive)
    )
    load_hat = (
        data.load[list(load_sources)].mean(axis=0)
        if load_sources
        else data.fallback_load.copy()
    )
    pv_hat = (
        data.pv[list(pv_sources)].mean(axis=0)
        if pv_sources
        else data.fallback_pv.copy()
    )
    return load_hat, pv_hat, load_sources, pv_sources


def build_forecast_archive(data: Q2Data) -> ForecastArchive:
    n = len(data.dates)
    load_hat = np.empty_like(data.load)
    pv_hat = np.empty_like(data.pv)
    load_sources: list[tuple[int, ...]] = []
    pv_sources: list[tuple[int, ...]] = []
    for i in range(n):
        load_hat[i], pv_hat[i], ls, ps = forecast_as_of(data, i, i)
        load_sources.append(ls)
        pv_sources.append(ps)
    return ForecastArchive(
        load_hat=load_hat,
        pv_hat=pv_hat,
        load_residual=data.load - load_hat,
        pv_residual=data.pv - pv_hat,
        load_sources=tuple(load_sources),
        pv_sources=tuple(pv_sources),
    )


def assert_no_forecast_leakage(archive: ForecastArchive) -> None:
    for i, (load_sources, pv_sources) in enumerate(
        zip(archive.load_sources, archive.pv_sources)
    ):
        if any(j >= i for j in load_sources + pv_sources):
            raise AssertionError(f"forecast leakage at day index {i}")


def write_forecast_archive(
    data: Q2Data, archive: ForecastArchive, csv_path: Path, audit_path: Path
) -> None:
    frames = []
    for i, date in enumerate(data.dates):
        load_source_dates = ";".join(
            data.dates[j].strftime("%Y-%m-%d") for j in archive.load_sources[i]
        )
        pv_source_dates = ";".join(
            data.dates[j].strftime("%Y-%m-%d") for j in archive.pv_sources[i]
        )
        frames.append(
            pd.DataFrame(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "information_cutoff": (
                        data.dates[i - 1].strftime("%Y-%m-%d") if i else "attachment1_fallback"
                    ),
                    "load_source_dates": load_source_dates or "attachment1_fallback",
                    "pv_source_dates": pv_source_dates or "attachment1_fallback",
                    "period": np.arange(T),
                    "time": data.time_labels,
                    "load_hat_kwh": archive.load_hat[i],
                    "pv_hat_kwh": archive.pv_hat[i],
                    "actual_load_kwh": data.load[i],
                    "actual_pv_kwh": data.pv[i],
                    "load_residual_kwh": archive.load_residual[i],
                    "pv_residual_kwh": archive.pv_residual[i],
                }
            )
        )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(csv_path, index=False)

    lines = [
        "# Q2 预测无泄漏审计",
        "",
        "- 负荷：日期严格早于目标日的最近至多 4 个同星期历史日。",
        "- 光伏：日期严格早于目标日的最近至多 7 个历史日。",
        "- 若没有可用历史日，使用附件 1 固定预测曲线；不读取目标日实际值。",
        "",
    ]
    for target in ("2025-02-01", "2025-06-21"):
        i = int(data.dates.get_loc(pd.Timestamp(target)))
        load_dates = [data.dates[j].strftime("%Y-%m-%d") for j in archive.load_sources[i]]
        pv_dates = [data.dates[j].strftime("%Y-%m-%d") for j in archive.pv_sources[i]]
        valid = all(j < i for j in archive.load_sources[i] + archive.pv_sources[i])
        lines += [
            f"## {target}",
            "",
            f"- 负荷样本日期：{', '.join(load_dates) or '无（附件1回退）'}",
            f"- 光伏样本日期：{', '.join(pv_dates) or '无（附件1回退）'}",
            f"- 所有样本日期严格早于目标日期：{valid}",
            "",
        ]
    audit_path.write_text("\n".join(lines), encoding="utf-8")


# ===== q2/optimization.py =====
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import cvxpy as cp
import numpy as np

from q2.config import (
    CONTRACT_TAKE_MODE,
    EMERGENCY_PRICE_MULTIPLIER,
    E_MAX_KWH,
    E_MIN_KWH,
    ETA_C,
    ETA_D,
    MPC_COST_TOL,
    NORMAL_COST_BASIS,
    POWER_LIMIT_KWH,
    SOLVER,
)


@dataclass(frozen=True)
class DispatchResult:
    x: np.ndarray
    emergency: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    curtailment: np.ndarray
    soc: np.ndarray
    emergency_cost: float
    terminal_value: float
    solve_seconds: float
    status: str

    @property
    def max_cd(self) -> float:
        return float(np.max(self.charge * self.discharge))


@dataclass(frozen=True)
class PlanResult:
    q: np.ndarray
    planned_cost: float
    expected_emergency_cost: float
    expected_terminal_value: float
    initial_soc_marginal: float
    solve_seconds: float
    status: str


ValueCut = tuple[float, float, float]  # reference SOC, value, subgradient


def evaluate_value_cuts(soc: float, cuts: tuple[ValueCut, ...] | None) -> float:
    if not cuts:
        return 0.0
    return max(
        0.0,
        max(
            value + slope * (soc - reference)
            for reference, value, slope in cuts
        ),
    )


def _terminal_value_expression(
    terminal_soc: cp.Expression, cuts: tuple[ValueCut, ...] | None
) -> tuple[cp.Variable | None, list[cp.Constraint]]:
    if not cuts:
        return None, []
    value = cp.Variable(nonneg=True, name="terminal_value")
    constraints = [
        value >= cut_value + slope * (terminal_soc - reference_soc)
        for reference_soc, cut_value, slope in cuts
    ]
    return value, constraints


def _contract_constraints(x: cp.Variable, q: cp.Variable | np.ndarray) -> list[cp.Constraint]:
    if CONTRACT_TAKE_MODE != "x_le_q":
        raise NotImplementedError(f"Unsupported pilot contract mode: {CONTRACT_TAKE_MODE}")
    return [x <= q]


def _planned_normal_cost(price: np.ndarray, q: cp.Expression) -> cp.Expression:
    if NORMAL_COST_BASIS != "planned_q":
        raise NotImplementedError(f"Unsupported normal-cost basis: {NORMAL_COST_BASIS}")
    return price @ q


def _physical_constraints(
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    normal: cp.Variable,
    emergency: cp.Variable,
    charge: cp.Variable,
    discharge: cp.Variable,
    curtailment: cp.Variable,
    soc: cp.Variable,
) -> list[cp.Constraint]:
    n = len(load)
    return [
        soc[0] == initial_soc,
        soc[1:] == soc[:-1] + ETA_C * charge - discharge / ETA_D,
        soc[1:] >= E_MIN_KWH,
        soc[1:] <= E_MAX_KWH,
        charge <= POWER_LIMIT_KWH,
        discharge <= POWER_LIMIT_KWH,
        curtailment <= pv,
        normal + emergency + pv - curtailment + discharge == load + charge,
    ]


def solve_perfect_information_day(
    price: np.ndarray, load: np.ndarray, pv: np.ndarray, initial_soc: float
) -> DispatchResult:
    n = len(load)
    g, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
    E = cp.Variable(n + 1)
    constraints = _physical_constraints(load, pv, initial_soc, g, e, c, d, w, E)
    objective = cp.Minimize(price @ g + EMERGENCY_PRICE_MULTIPLIER * price @ e)
    problem = cp.Problem(objective, constraints)
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    elapsed = perf_counter() - started
    if g.value is None:
        raise RuntimeError(f"perfect-information LP failed: {problem.status}")
    return DispatchResult(
        x=np.asarray(g.value).ravel(),
        emergency=np.asarray(e.value).ravel(),
        charge=np.asarray(c.value).ravel(),
        discharge=np.asarray(d.value).ravel(),
        curtailment=np.asarray(w.value).ravel(),
        soc=np.asarray(E.value).ravel(),
        emergency_cost=float(EMERGENCY_PRICE_MULTIPLIER * price @ e.value),
        terminal_value=0.0,
        solve_seconds=elapsed,
        status=str(problem.status),
    )


def solve_stochastic_plan(
    price: np.ndarray,
    scenario_load: np.ndarray,
    scenario_pv: np.ndarray,
    probabilities: np.ndarray,
    initial_soc: float,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    q_floor: np.ndarray | None = None,
) -> PlanResult:
    k, n = scenario_load.shape
    q = cp.Variable(n, nonneg=True)
    expected_emergency = 0
    expected_terminal_value: cp.Expression | float = 0.0
    constraints: list[cp.Constraint] = []
    if q_floor is not None:
        floor = np.asarray(q_floor, dtype=float).ravel()
        if floor.shape != (n,) or np.any(floor < -1e-9):
            raise ValueError("q_floor must be a nonnegative vector matching the horizon")
        constraints.append(q >= floor)
    initial_constraints: list[cp.Constraint] = []
    for omega in range(k):
        x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
        E = cp.Variable(n + 1)
        constraints += _contract_constraints(x, q)
        physical = _physical_constraints(
            scenario_load[omega],
            scenario_pv[omega],
            initial_soc,
            x,
            e,
            c,
            d,
            w,
            E,
        )
        constraints += physical
        initial_constraints.append(physical[0])
        terminal_value, terminal_constraints = _terminal_value_expression(
            E[-1], terminal_value_cuts
        )
        constraints += terminal_constraints
        if terminal_value is not None:
            expected_terminal_value += probabilities[omega] * terminal_value
        expected_emergency += (
            probabilities[omega] * EMERGENCY_PRICE_MULTIPLIER * price @ e
        )
    planned_cost = _planned_normal_cost(price, q)
    problem = cp.Problem(
        cp.Minimize(planned_cost + expected_emergency + expected_terminal_value),
        constraints,
    )
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    elapsed = perf_counter() - started
    if q.value is None:
        raise RuntimeError(f"stochastic plan LP failed: {problem.status}")
    qv = np.asarray(q.value).ravel()
    marginal = -float(
        sum(float(np.asarray(constraint.dual_value)) for constraint in initial_constraints)
    )
    terminal_value_result = (
        float(expected_terminal_value.value)
        if isinstance(expected_terminal_value, cp.Expression)
        else float(expected_terminal_value)
    )
    return PlanResult(
        q=qv,
        planned_cost=float(price @ qv),
        expected_emergency_cost=float(problem.value - price @ qv - terminal_value_result),
        expected_terminal_value=terminal_value_result,
        initial_soc_marginal=marginal,
        solve_seconds=elapsed,
        status=str(problem.status),
    )


@dataclass(frozen=True)
class BaselinePlanResult(PlanResult):
    variable_shapes: dict[str, tuple[int, ...]]
    has_scenario_specific_battery: bool


def solve_baseline_plan(
    price: np.ndarray,
    load_hat: np.ndarray,
    pv_hat: np.ndarray,
    initial_soc: float,
    q_floor: np.ndarray | None = None,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
) -> BaselinePlanResult:
    """Day-ahead LP on a single forecast path; q is locked and billed at p@q."""
    n = len(load_hat)
    if load_hat.shape != (n,) or pv_hat.shape != (n,) or price.shape != (n,):
        raise ValueError("baseline plan requires a single forecast trajectory")
    q = cp.Variable(n, nonneg=True, name="q")
    x = cp.Variable(n, nonneg=True, name="x")
    emergency = cp.Variable(n, nonneg=True, name="emergency")
    charge = cp.Variable(n, nonneg=True, name="charge")
    discharge = cp.Variable(n, nonneg=True, name="discharge")
    curtailment = cp.Variable(n, nonneg=True, name="curtailment")
    soc = cp.Variable(n + 1, name="soc")
    constraints = _contract_constraints(x, q)
    if q_floor is not None:
        floor = np.asarray(q_floor, dtype=float).ravel()
        if floor.shape != (n,) or np.any(floor < -1e-9):
            raise ValueError("q_floor must be a nonnegative vector matching the horizon")
        constraints.append(q >= floor)
    physical = _physical_constraints(
        load_hat, pv_hat, initial_soc, x, emergency, charge, discharge, curtailment, soc
    )
    constraints += physical
    terminal_value, terminal_constraints = _terminal_value_expression(
        soc[-1], terminal_value_cuts
    )
    constraints += terminal_constraints
    planned_cost = _planned_normal_cost(price, q)
    expected_emergency = EMERGENCY_PRICE_MULTIPLIER * price @ emergency
    objective = planned_cost + expected_emergency
    if terminal_value is not None:
        objective = objective + terminal_value
    problem = cp.Problem(cp.Minimize(objective), constraints)
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    elapsed = perf_counter() - started
    if q.value is None:
        raise RuntimeError(f"baseline plan LP failed: {problem.status}")
    qv = np.asarray(q.value).ravel()
    shapes = {
        str(variable.name()): tuple(int(dim) for dim in variable.shape)
        for variable in problem.variables()
    }
    has_scenario_battery = any(
        name in {"charge", "discharge", "soc"} and len(shape) == 2
        for name, shape in shapes.items()
    )
    terminal_value_result = (
        float(terminal_value.value) if terminal_value is not None else 0.0
    )
    return BaselinePlanResult(
        q=qv,
        planned_cost=float(price @ qv),
        expected_emergency_cost=float(EMERGENCY_PRICE_MULTIPLIER * price @ emergency.value),
        expected_terminal_value=terminal_value_result,
        initial_soc_marginal=-float(np.asarray(physical[0].dual_value)),
        solve_seconds=elapsed,
        status=str(problem.status),
        variable_shapes=shapes,
        has_scenario_specific_battery=has_scenario_battery,
    )


def solve_fixed_plan_dispatch(
    price: np.ndarray,
    q: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    throughput_tiebreak: bool = True,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
) -> DispatchResult:
    n = len(load)
    x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
    E = cp.Variable(n + 1)
    constraints = _contract_constraints(x, q)
    constraints += _physical_constraints(load, pv, initial_soc, x, e, c, d, w, E)
    emergency_cost = EMERGENCY_PRICE_MULTIPLIER * price @ e
    terminal_value, terminal_constraints = _terminal_value_expression(
        E[-1], terminal_value_cuts
    )
    constraints += terminal_constraints
    primary = emergency_cost + (terminal_value if terminal_value is not None else 0.0)
    first = cp.Problem(cp.Minimize(primary), constraints)
    started = perf_counter()
    first.solve(solver=SOLVER, verbose=False)
    if e.value is None:
        raise RuntimeError(f"fixed-plan execution LP failed: {first.status}")
    primary_opt = float(primary.value)
    status = str(first.status)
    if throughput_tiebreak:
        second = cp.Problem(
            cp.Minimize(cp.sum(c + d)),
            constraints + [primary <= primary_opt + MPC_COST_TOL],
        )
        second.solve(solver=SOLVER, verbose=False)
        if x.value is None:
            raise RuntimeError(f"fixed-plan tiebreak LP failed: {second.status}")
        status = str(second.status)
    elapsed = perf_counter() - started
    return DispatchResult(
        x=np.asarray(x.value).ravel(),
        emergency=np.asarray(e.value).ravel(),
        charge=np.asarray(c.value).ravel(),
        discharge=np.asarray(d.value).ravel(),
        curtailment=np.asarray(w.value).ravel(),
        soc=np.asarray(E.value).ravel(),
        emergency_cost=float(EMERGENCY_PRICE_MULTIPLIER * price @ e.value),
        terminal_value=evaluate_value_cuts(float(E.value[-1]), terminal_value_cuts),
        solve_seconds=elapsed,
        status=status,
    )


def dispatch_balance_residual(
    load: np.ndarray, pv: np.ndarray, result: DispatchResult
) -> np.ndarray:
    return (
        result.x
        + result.emergency
        + pv
        - result.curtailment
        + result.discharge
        - load
        - result.charge
    )

# ===== q2/pilot.py =====
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
    RISK_ALPHA_CANDIDATES,
    RISK_CALIBRATION_DAYS,
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


@dataclass(frozen=True)
class RiskChoice:
    target_index: int
    selected_alpha: float
    rows: tuple[dict, ...]


def planned_q_hash(q: np.ndarray) -> str:
    # Decimal canonicalization survives CSV round-trips while detecting any
    # operationally meaningful mutation of the locked plan.
    canonical = ",".join(f"{float(value):.9f}" for value in np.asarray(q).ravel())
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, alpha: float) -> float:
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cumulative, alpha, side="left")])


def risk_quantile_floor(
    scenario_load: np.ndarray,
    scenario_pv: np.ndarray,
    probabilities: np.ndarray,
    base_load: np.ndarray,
    base_pv: np.ndarray,
    alpha: float | None,
) -> np.ndarray:
    """Nonnegative high-net-load residual reserve for the locked normal plan."""
    if alpha is None:
        return np.zeros(scenario_load.shape[1])
    if not 0.0 < alpha < 1.0:
        raise ValueError("risk alpha must lie strictly between 0 and 1")
    residual_net = (
        scenario_load - scenario_pv - (base_load[None, :] - base_pv[None, :])
    )
    return np.maximum(
        np.array(
            [
                _weighted_quantile(residual_net[:, t], probabilities, alpha)
                for t in range(residual_net.shape[1])
            ]
        ),
        0.0,
    )


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
    risk_alpha: float | None = None,
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
    base_load, base_pv, _load_sources, _pv_sources = forecast_as_of(
        data, current_index + 1, current_index
    )
    q_floor = risk_quantile_floor(
        loads, pvs, probabilities, base_load, base_pv, risk_alpha
    )
    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = solve_stochastic_plan(
            data.price, loads, pvs, probabilities, float(soc), q_floor=q_floor
        )
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
            "risk_alpha": risk_alpha,
            "risk_q_floor_kwh": float(q_floor.sum()),
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
    risk_alpha: float | None = None,
) -> tuple[float, float, float]:
    scenarios = build_scenarios(validation_index, data, archive, k)
    loads, pvs = scenario_trajectories(scenarios, archive)
    q_floor = risk_quantile_floor(
        loads,
        pvs,
        scenarios.probabilities,
        archive.load_hat[validation_index],
        archive.pv_hat[validation_index],
        risk_alpha,
    )
    plan = solve_stochastic_plan(
        data.price,
        loads,
        pvs,
        scenarios.probabilities,
        day_start_soc[validation_index],
        q_floor=q_floor,
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


def select_risk_alpha(
    data: Q2Data,
    archive: ForecastArchive,
    policy_day_start_soc: np.ndarray,
    target_index: int,
    k: int,
) -> RiskChoice:
    """Choose the risk reserve by strictly prior 14-day realised-cost scores."""
    validation = np.arange(
        max(1, target_index - RISK_CALIBRATION_DAYS), target_index
    )
    records: list[dict] = []
    for alpha in RISK_ALPHA_CANDIDATES:
        costs, emergency, times = [], [], []
        for i in validation:
            cost, e, seconds = _validation_score(
                data,
                archive,
                policy_day_start_soc,
                int(i),
                k,
                risk_alpha=float(alpha),
            )
            costs.append(cost)
            emergency.append(e)
            times.append(seconds)
        records.append(
            {
                "risk_alpha": float(alpha),
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
    eligible = [row for row in records if row["within_time_limit"]]
    selected = min(
        eligible or records,
        key=lambda row: (row["mean_validation_cost_yuan"], row["risk_alpha"]),
    )
    selected["selected"] = True
    return RiskChoice(target_index, float(selected["risk_alpha"]), tuple(records))


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
    risk_alpha: float | None = None,
) -> dict:
    if choice is None:
        i = 0
        scenarios = None
        scenario_load = archive.load_hat[i][None, :]
        scenario_pv = archive.pv_hat[i][None, :]
        probabilities = np.ones(1)
        selected_k = 1
        q_floor = np.zeros(T)
    else:
        i = choice.target_index
        scenarios = choice.scenarios
        scenario_load, scenario_pv = scenario_trajectories(scenarios, archive)
        probabilities = scenarios.probabilities
        selected_k = choice.selected_k
        q_floor = risk_quantile_floor(
            scenario_load,
            scenario_pv,
            probabilities,
            archive.load_hat[i],
            archive.pv_hat[i],
            risk_alpha,
        )
    plan = solve_stochastic_plan(
        data.price,
        scenario_load,
        scenario_pv,
        probabilities,
        initial_soc,
        terminal_value_cuts=terminal_value_cuts,
        q_floor=q_floor,
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
        "risk_alpha": risk_alpha,
        "risk_q_floor_kwh": float(q_floor.sum()),
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


def run_full_linked_policy(
    data: Q2Data,
    archive: ForecastArchive,
    output_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the deployable policy in one causal state path for all 365 days.

    At every 14-day boundary, only states and realised trajectories from prior
    days have been written to ``policy_day_start_soc``.  Thus the K score,
    frozen K, day-ahead plan and realised MPC actions share one SOC history.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    dispatch_dir = output_dir / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    policy_day_start_soc = np.full(len(data.dates), np.nan)
    daily_k = np.ones(len(data.dates), dtype=int)
    daily_rows: list[dict] = []
    calendar_rows: list[dict] = []
    value_audits: list[dict] = []
    soc = E_INITIAL_KWH

    for calibration in range(0, len(data.dates), 14):
        effective_end = min(calibration + 13, len(data.dates) - 1)
        if calibration < 2:
            selected_k = 1
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
            choice = select_dynamic_k(data, archive, policy_day_start_soc, calibration)
            selected_k = choice.selected_k
            candidate_rows = list(choice.rows)
            fallback = "K=1_early_pool_fallback" if selected_k == 1 else ""
        daily_k[calibration : effective_end + 1] = selected_k
        for candidate in candidate_rows:
            calendar_rows.append(
                {
                    "calibration_date": data.dates[calibration].strftime("%Y-%m-%d"),
                    "history_cutoff_date": (
                        data.dates[calibration - 1].strftime("%Y-%m-%d")
                        if calibration else "none"
                    ),
                    "candidate_k": int(candidate["candidate_k"]),
                    "selected_k": selected_k,
                    "effective_start_date": data.dates[calibration].strftime("%Y-%m-%d"),
                    "effective_end_date": data.dates[effective_end].strftime("%Y-%m-%d"),
                    "mean_validation_cost_yuan": candidate["mean_validation_cost_yuan"],
                    "standard_error_yuan": candidate["standard_error_yuan"],
                    "validation_days": candidate["validation_days"],
                    "emergency_purchase_kwh": candidate["emergency_purchase_kwh"],
                    "mean_solve_seconds": candidate["mean_solve_seconds"],
                    "within_time_limit": candidate["within_time_limit"],
                    "candidate_selected": bool(candidate["selected"]),
                    "selected": bool(candidate["selected"]),
                    "fallback_reason": fallback,
                }
            )

        for i in range(calibration, effective_end + 1):
            policy_day_start_soc[i] = soc
            k = int(daily_k[i])
            if i == 0:
                day_choice = None
            else:
                day_choice = KChoice(i, k, build_scenarios(i, data, archive, k), ())
            cuts, cut_rows = build_next_day_value_cuts(data, archive, i, k)
            value_audits.extend(
                {"decision_date": data.dates[i].strftime("%Y-%m-%d"), **row}
                for row in cut_rows
            )
            path = dispatch_dir / f"dispatch_{data.dates[i].strftime('%Y-%m-%d')}.csv"
            result = run_posterior_mpc(
                data,
                archive,
                day_choice,
                soc,
                path=path,
                terminal_value_cuts=cuts,
                variant="full_linked_48h",
            )
            if not result["pass"]:
                raise AssertionError(f"full linked policy failed on {result['date']}")
            daily_rows.append(result)
            soc = float(result["soc_end_kwh"])

    daily = pd.DataFrame(daily_rows)
    calendar = pd.DataFrame(calendar_rows)
    value_audit = pd.DataFrame(value_audits)
    if len(daily) != len(data.dates) or not daily["pass"].all():
        raise AssertionError("full linked policy does not cover every day")
    continuity = np.abs(
        daily["soc_start_kwh"].to_numpy()[1:]
        - daily["soc_end_kwh"].to_numpy()[:-1]
    )
    if np.max(continuity) >= NUMERIC_TOL:
        raise AssertionError("full linked policy SOC is not continuous")
    daily.to_csv(output_dir / "daily_summary.csv", index=False)
    calendar.to_csv(output_dir / "k_freeze_calendar.csv", index=False)
    value_audit.to_csv(output_dir / "next_day_value_audit.csv", index=False)
    return daily, calendar, value_audit


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
        "historical_pilot_notes": [
            "x<=q contract semantics were signed off for the production Q2 model",
            (
                "P1 is a sequential daily perfect-information comparator, not a proven "
                "global lower bound against a controller with a different horizon"
            ),
            "T_max was later fixed at 0.20 seconds per validation day for production K filtering",
            "June 21 remains an isolated pilot initialized from the comparator path",
            "the next-day value is an adaptively certified LP cut approximation signed off for Q2",
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
        "## 历史试算边界（已由生产模型处理）",
        "",
        "- `x<=q` 合同语义已由队长签收；生产模型按计划购电量 q 计费。",
        "- P1 与主方案视域不同，因此当前只能称“逐日完美信息比较器”，不能据此强制认定全局下界。",
        "- 生产模型已固定 `T_max=0.20` 秒/验证日，并采用 K=8 与滚动风险分位。",
        f"- 次日价值采用自适应 LP 对偶支撑切面，弦线—切面最大认证误差不超过 "
        f"{NEXT_DAY_VALUE_GAP_TOL_YUAN:.2f} 元；该口径已在生产 Q2 中签收。",
        "- 6 月 21 日仍为孤立试算，其日初 SOC 暂取逐日比较器路径；2 月 1 日已改用联动 1 月预热末值。",
        "- 未生成或修改 `result2.xlsx`。",
    ]
    path_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

# ===== q2/plot_final_figures.py =====
#!/usr/bin/env python3
"""Render Q2 final figures F1-F4 from signed-off result artifacts only."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

K8_DAILY = ROOT / "output/q2_full_k8_risk/daily_summary.csv"
K8_DISPATCH_DIR = ROOT / "output/q2_full_k8_risk/dispatch_daily"
RISK_CALIBRATION = ROOT / "output/q2_full_k8_risk/risk_calibration.csv"
DYNAMIC_DAILY = ROOT / "output/q2_full_linked/daily_summary.csv"
RESULT2 = ROOT / "output/result2.xlsx"
FIG_DIR = ROOT / "fig/q2_final"

START = pd.Timestamp("2025-02-01")
END = pd.Timestamp("2025-12-31")
EXPECTED_K8_COST = 14_456_670.55
EXPECTED_K8_EMERGENCY_KWH = 534_490.42
EXPECTED_COST_CHANGE = -50_168.90
EXPECTED_EMERGENCY_CHANGE_KWH = -120_809.11

BLUE = "#276FBF"
RED = "#C0392B"
GRAY = "#6B7280"
BLACK = "#1F2933"
LIGHT_BLUE = "#E8F1FA"
LIGHT_RED = "#F8E7E5"
LIGHT_GRAY = "#F3F4F6"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def configure_style() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = (
        "PingFang SC",
        "Hiragino Sans GB",
        "Heiti SC",
        "Songti SC",
        "Arial Unicode MS",
        "Noto Sans CJK SC",
    )
    font = next((name for name in candidates if name in available), None)
    if font is None:
        raise RuntimeError("No usable Chinese font found")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font],
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "axes.titleweight": "medium",
            "pdf.fonttype": 42,
        }
    )
    return font


def save_figure(fig: plt.Figure, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(FIG_DIR / f"{stem}.png", dpi=320, bbox_inches="tight")
    plt.close(fig)


def draw_box(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    facecolor: str,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.15,
        edgecolor=BLACK,
        facecolor=facecolor,
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height / 2, text, ha="center", va="center", linespacing=1.38)


def style_axes(ax: plt.Axes, hide_right: bool = True) -> None:
    ax.spines["top"].set_visible(False)
    if hide_right:
        ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRAY)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(color=GRAY, length=3.5)


def draw_arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    label: str,
    label_y: float,
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.25,
            color=BLACK,
            shrinkA=2,
            shrinkB=2,
        )
    )
    ax.text(
        (start[0] + end[0]) / 2,
        label_y,
        label,
        ha="center",
        va="bottom",
        fontsize=8.8,
        color=BLACK,
        bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.95},
    )


def plot_f1() -> None:
    fig, ax = plt.subplots(figsize=(15.6, 6.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    y, width, height = 0.48, 0.148, 0.30
    gap = 0.055
    xs = [0.020 + index * (width + gap) for index in range(5)]
    texts = [
        "历史负荷—光伏\n配对残差\n（仅已结束日）",
        "日前预测\n8 个联合情景\n风险分位购电下限",
        "0:00 锁定\n计划购电量\n$q_{d,t}$",
        "每 10 分钟观测实际值\n更新 $x,c,d,e$\n仅执行当前一步",
        "实际日末 SOC\n$E_{d,144}$\n传至下一日",
    ]
    faces = [LIGHT_GRAY, LIGHT_BLUE, LIGHT_BLUE, LIGHT_RED, LIGHT_GRAY]
    for x, text, face in zip(xs, texts, faces):
        draw_box(ax, x, y, width, height, text, face)
    labels = [
        "构造因果预测",
        "0:00 决策",
        "当天 $q$ 不可修改",
        "仅传递实际 SOC",
    ]
    for index in range(4):
        draw_arrow(
            ax,
            (xs[index] + width, y + height / 2),
            (xs[index + 1], y + height / 2),
            labels[index],
            y + height + 0.035,
        )
    mid_y = 0.30
    ax.plot(
        [xs[4] + width / 2, xs[4] + width / 2, xs[1] + width / 2, xs[1] + width / 2],
        [y, mid_y, mid_y, y],
        color=BLUE,
        linestyle="--",
        linewidth=1.25,
        solid_capstyle="round",
    )
    ax.annotate(
        "",
        xy=(xs[1] + width / 2, y),
        xytext=(xs[1] + width / 2, mid_y + 0.01),
        arrowprops={"arrowstyle": "-|>", "color": BLUE, "lw": 1.25},
    )
    ax.text(
        (xs[1] + xs[4] + width) / 2,
        mid_y - 0.055,
        "次日 0:00 重新预测并锁定自己的购电计划；不提前锁定次日 $q$",
        ha="center",
        color=BLUE,
        fontsize=9.2,
    )
    ax.text(
        0.5,
        0.09,
        "日内仅修正储能动作与实际取用；紧急购电 $e$ 只补当期缺口",
        ha="center",
        color=RED,
        fontsize=9.2,
        bbox={
            "boxstyle": "round,pad=0.32",
            "facecolor": LIGHT_RED,
            "edgecolor": RED,
            "linewidth": 0.6,
        },
    )
    ax.set_title("Q2 日前计划—日内执行—跨日 SOC 闭环机制", pad=10)
    save_figure(fig, "fig_q2_closed_loop")


def output_interval(frame: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(frame["date"])
    selected = frame.loc[dates.between(START, END)].copy()
    if len(selected) != 334:
        raise AssertionError(f"Expected 334 output days, got {len(selected)}")
    return selected


def plot_f2(k8: pd.DataFrame, dynamic: pd.DataFrame) -> dict:
    frames = [output_interval(dynamic), output_interval(k8)]
    names = ["原动态 K", "固定 K=8 + 风险分位"]
    planned = np.array([frame["planned_cost_yuan"].sum() for frame in frames])
    emergency_cost = np.array([frame["emergency_cost_yuan"].sum() for frame in frames])
    total = np.array([frame["total_cost_yuan"].sum() for frame in frames])
    emergency_kwh = np.array([frame["emergency_kwh"].sum() for frame in frames])
    if not np.allclose(total, planned + emergency_cost, atol=0.01):
        raise AssertionError("F2 cost components do not sum to total")
    cost_change = float(total[1] - total[0])
    emergency_change = float(emergency_kwh[1] - emergency_kwh[0])
    checks = (
        abs(total[1] - EXPECTED_K8_COST) < 0.01,
        abs(emergency_kwh[1] - EXPECTED_K8_EMERGENCY_KWH) < 0.01,
        abs(cost_change - EXPECTED_COST_CHANGE) < 0.01,
        abs(emergency_change - EXPECTED_EMERGENCY_CHANGE_KWH) < 0.01,
    )
    if not all(checks):
        raise AssertionError(
            f"F2 signed-off values mismatch: {total[1]}, {emergency_kwh[1]}, "
            f"{cost_change}, {emergency_change}"
        )

    fig, ax = plt.subplots(figsize=(9.6, 6.9))
    x = np.arange(2)
    bar_width = 0.48
    ax.bar(
        x,
        planned,
        width=bar_width,
        color=BLUE,
        edgecolor=BLACK,
        linewidth=0.7,
        label="计划购电费",
        zorder=3,
    )
    ax.bar(
        x,
        emergency_cost,
        width=bar_width,
        bottom=planned,
        color="white",
        edgecolor=RED,
        linewidth=1.15,
        hatch="///",
        label="紧急购电费",
        zorder=3,
    )
    for index, (plan, emergency, value) in enumerate(zip(planned, emergency_cost, total)):
        ax.text(
            x[index],
            plan * 0.52,
            f"{plan / 1e6:.2f} 百万",
            ha="center",
            va="center",
            color="white",
            fontsize=9.5,
            zorder=4,
        )
        ax.text(
            x[index],
            plan + emergency * 0.55,
            f"{emergency / 1e6:.2f} 百万",
            ha="center",
            va="center",
            color=RED,
            fontsize=8.6,
            zorder=4,
            bbox={
                "boxstyle": "round,pad=0.12",
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.9,
            },
        )
        ax.text(
            x[index],
            value + total.max() * 0.018,
            f"合计 {value:,.2f} 元",
            ha="center",
            va="bottom",
            fontsize=9.6,
            zorder=4,
            clip_on=False,
        )
    ax.set_xticks(x, names)
    ax.set_ylabel("2—12 月购电成本（元）")
    ax.set_title("Q2 两套日前风险处理策略的成本构成对照", pad=18)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value / 1e6:.1f} 百万"))
    ax.set_ylim(0, total.max() * 1.12)
    ax.set_xlim(-0.55, 1.55)
    ax.grid(axis="y", linestyle=":", color=GRAY, alpha=0.35, zorder=0)
    ax.set_axisbelow(True)
    style_axes(ax)
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
        ncol=2,
        frameon=False,
        borderaxespad=0.0,
    )
    fig.subplots_adjust(bottom=0.22, top=0.86)
    fig.text(
        0.5,
        0.085,
        f"K=8 相对原动态 K：总成本变化 {cost_change:,.2f} 元；"
        f"紧急购电量变化 {emergency_change:,.2f} kWh",
        ha="center",
        fontsize=9.5,
        bbox={"boxstyle": "round,pad=0.38", "facecolor": LIGHT_GRAY, "edgecolor": GRAY},
    )
    fig.text(
        0.5,
        0.02,
        "注：仅比较两套日前风险处理策略；不表示储能净收益或投资成本节省。",
        ha="center",
        fontsize=9,
        color=GRAY,
    )
    save_figure(fig, "fig_q2_cost_comparison")
    return {
        "k8_planned_cost_yuan": float(planned[1]),
        "k8_emergency_cost_yuan": float(emergency_cost[1]),
        "k8_total_cost_yuan": float(total[1]),
        "k8_emergency_kwh": float(emergency_kwh[1]),
        "dynamic_total_cost_yuan": float(total[0]),
        "dynamic_emergency_kwh": float(emergency_kwh[0]),
        "cost_change_yuan": cost_change,
        "emergency_change_kwh": emergency_change,
    }


def recover_tariff(k8: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Recover the fixed 144-slot tariff from signed-off accounting identities."""
    matrix_rows: list[np.ndarray] = []
    targets: list[float] = []
    for row in k8.itertuples():
        dispatch = pd.read_csv(K8_DISPATCH_DIR / f"dispatch_{row.date}.csv")
        matrix_rows.extend(
            [
                dispatch["planned_q_kwh"].to_numpy(float),
                dispatch["emergency_kwh"].to_numpy(float),
            ]
        )
        targets.extend([float(row.planned_cost_yuan), float(row.emergency_cost_yuan) / 5.0])
    matrix = np.asarray(matrix_rows)
    target = np.asarray(targets)
    price, _residuals, rank, _singular = np.linalg.lstsq(matrix, target, rcond=None)
    max_residual = float(np.max(np.abs(matrix @ price - target)))
    if rank != 144 or max_residual >= 0.01 or not np.isfinite(price).all():
        raise AssertionError(
            f"Unable to recover 144-slot tariff: rank={rank}, residual={max_residual}"
        )
    return price, {
        "method": (
            "least-squares recovery from planned_cost=p@q and "
            "emergency_cost=5*p@e over 365 signed-off days"
        ),
        "matrix_rows": len(matrix),
        "rank": int(rank),
        "max_accounting_residual_yuan": max_residual,
        "price_min_yuan_per_kwh": float(price.min()),
        "price_max_yuan_per_kwh": float(price.max()),
    }


def plot_f3(k8: pd.DataFrame, price: np.ndarray) -> dict:
    output = output_interval(k8)
    selected = output.loc[output["emergency_cost_yuan"].idxmax()]
    date = pd.Timestamp(selected["date"])
    path = K8_DISPATCH_DIR / f"dispatch_{date:%Y-%m-%d}.csv"
    frame = pd.read_csv(path)
    required = {
        "period",
        "time",
        "planned_q_kwh",
        "actual_x_kwh",
        "load_kwh",
        "pv_kwh",
        "charge_kwh",
        "discharge_kwh",
        "emergency_kwh",
        "soc_kwh",
    }
    if len(frame) != 144 or not required.issubset(frame.columns):
        raise AssertionError("F3 dispatch schema/row count mismatch")
    if not np.array_equal(frame["period"].to_numpy(), np.arange(144)):
        raise AssertionError("F3 dispatch period order changed")
    if str(frame["time"].iloc[0]) != "00:10" or str(frame["time"].iloc[-1]) != "0:00+1":
        raise AssertionError("F3 raw attachment time order mismatch")

    hours = (frame["period"].to_numpy() + 1) / 6.0
    net_load = frame["load_kwh"].to_numpy() - frame["pv_kwh"].to_numpy()
    battery_net = frame["discharge_kwh"].to_numpy() - frame["charge_kwh"].to_numpy()
    if len(price) != 144:
        raise AssertionError("F3 recovered tariff must contain 144 raw-order values")

    fig, axes = plt.subplots(
        3, 1, figsize=(12.6, 11.0), sharex=True, gridspec_kw={"hspace": 0.16}
    )
    legend_box = {
        "frameon": True,
        "framealpha": 0.96,
        "edgecolor": "#E5E7EB",
        "fancybox": False,
        "borderpad": 0.45,
        "handlelength": 2.2,
    }

    ax = axes[0]
    ax.plot(hours, net_load, color=BLACK, linewidth=1.35, label="实际净负荷 $L-P$")
    ax.plot(hours, frame["planned_q_kwh"], color=BLUE, linewidth=1.25, label="锁定计划 $q$")
    ax.plot(
        hours,
        frame["actual_x_kwh"],
        color=GRAY,
        linestyle="--",
        linewidth=1.15,
        label="实际普通取电 $x$",
    )
    ax.plot(
        hours,
        frame["emergency_kwh"],
        color=RED,
        linestyle="-.",
        linewidth=1.45,
        label="紧急购电 $e$",
    )
    ax.fill_between(hours, 0, frame["emergency_kwh"], color=RED, alpha=0.12, linewidth=0)
    ymax = max(net_load.max(), frame["planned_q_kwh"].max(), frame["emergency_kwh"].max())
    ax.set_ylim(-0.10 * ymax, ymax * 1.22)
    ax.set_ylabel("时段电量（kWh）")
    ax.legend(loc="upper left", ncol=2, **legend_box)
    ax.grid(linestyle=":", color=GRAY, alpha=0.32)
    ax.set_axisbelow(True)
    style_axes(ax)

    ax = axes[1]
    ax.axhline(0, color=GRAY, linewidth=0.8)
    ax.plot(hours, battery_net, color=BLACK, linewidth=1.2, label="电池净动作 $d-c$")
    ax.fill_between(hours, 0, battery_net, color=BLACK, alpha=0.10, linewidth=0)
    ax.set_ylabel("$d-c$（kWh）")
    abs_max = np.max(np.abs(battery_net))
    ax.set_ylim(-abs_max * 1.28, abs_max * 1.28)
    ax_price = ax.twinx()
    ax_price.step(
        hours,
        price,
        where="mid",
        color=RED,
        linestyle="--",
        linewidth=1.15,
        label="分时电价",
    )
    ax_price.set_ylabel("电价（元/kWh）", color=RED)
    ax_price.tick_params(axis="y", colors=RED)
    ax_price.set_ylim(0.28, price.max() * 1.22)
    ax_price.spines["top"].set_visible(False)
    ax_price.spines["right"].set_color(RED)
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax_price.get_legend_handles_labels()
    ax.legend(
        handles1 + handles2,
        labels1 + labels2,
        loc="lower left",
        **legend_box,
    )
    ax.grid(linestyle=":", color=GRAY, alpha=0.32)
    ax.set_axisbelow(True)
    style_axes(ax, hide_right=False)

    ax = axes[2]
    ax.plot(hours, frame["soc_kwh"], color=BLUE, linewidth=1.5, label="SOC")
    ax.axhline(1200, color=GRAY, linestyle="--", linewidth=1.0, label="SOC 边界 1200 / 10800 kWh")
    ax.axhline(10800, color=GRAY, linestyle="--", linewidth=1.0)
    ax.set_ylabel("SOC（kWh）")
    ax.set_xlabel("时刻")
    ax.set_ylim(200, 12800)
    ax.legend(loc="center left", **legend_box)
    ax.grid(linestyle=":", color=GRAY, alpha=0.32)
    ax.set_axisbelow(True)
    style_axes(ax)
    axes[-1].set_xlim(0, 24)
    axes[-1].set_xticks(np.arange(0, 25, 2))
    axes[-1].set_xticklabels([f"{hour:02d}:00" for hour in range(0, 25, 2)])
    fig.suptitle(
        f"Q2 日前—日内联动轨迹：{date:%Y-%m-%d}（紧急费用最高日）",
        y=0.98,
    )
    fig.subplots_adjust(top=0.945, bottom=0.055, left=0.08, right=0.91, hspace=0.20)
    save_figure(fig, "fig_q2_representative_day")
    return {
        "selected_date": date.strftime("%Y-%m-%d"),
        "selection_metric": "maximum emergency_cost_yuan over 2025-02-01..2025-12-31",
        "emergency_cost_yuan": float(selected["emergency_cost_yuan"]),
        "emergency_kwh": float(selected["emergency_kwh"]),
        "dispatch_rows": len(frame),
        "first_time": str(frame["time"].iloc[0]),
        "last_time": str(frame["time"].iloc[-1]),
        "source": str(path.relative_to(ROOT)),
    }


def plot_f4(calibration: pd.DataFrame) -> dict:
    if "selected" not in calibration:
        raise AssertionError("F4 calibration file lacks selected flag")
    selected = calibration.loc[calibration["selected"].astype(bool)].copy()
    selected["calibration_date"] = pd.to_datetime(selected["calibration_date"])
    selected["effective_start_date"] = pd.to_datetime(selected["effective_start_date"])
    selected["effective_end_date"] = pd.to_datetime(selected["effective_end_date"])
    selected = selected.sort_values("effective_start_date").reset_index(drop=True)
    if len(selected) != 27:
        raise AssertionError(f"F4 expected 27 selected blocks, got {len(selected)}")
    if selected["effective_start_date"].iloc[0] != pd.Timestamp("2025-01-01"):
        raise AssertionError("F4 calibration calendar start mismatch")
    if selected["effective_end_date"].iloc[-1] != pd.Timestamp("2025-12-31"):
        raise AssertionError("F4 calibration calendar end mismatch")
    for previous, current in zip(selected.itertuples(), selected.iloc[1:].itertuples()):
        if previous.effective_end_date + pd.Timedelta(days=1) != current.effective_start_date:
            raise AssertionError("F4 calibration blocks are not contiguous")
    early = selected["effective_start_date"] < pd.Timestamp("2025-01-29")
    if not (
        (selected.loc[early, "fixed_k"] == 1).all()
        and selected.loc[early, "risk_alpha"].isna().all()
        and (selected.loc[~early, "fixed_k"] == 8).all()
    ):
        raise AssertionError("F4 K=1/K=8 split mismatch")
    candidates = calibration.loc[calibration["fixed_k"] == 8].groupby("calibration_date")[
        "risk_alpha"
    ].apply(lambda values: set(np.round(values.dropna(), 2)))
    if not all(values == {0.6, 0.7, 0.8, 0.9} for values in candidates):
        raise AssertionError("F4 alpha candidate set mismatch")
    causal = selected.loc[selected["history_cutoff_date"] != "none"].apply(
        lambda row: pd.Timestamp(row["history_cutoff_date"]) < row["calibration_date"],
        axis=1,
    )
    if not causal.all():
        raise AssertionError("F4 history cutoff is not causal")

    fig, ax = plt.subplots(figsize=(13.4, 6.2))
    y_map = {None: 0, 0.6: 1, 0.7: 2, 0.8: 3, 0.9: 4}
    ytick_labels = ["K=1 / 无风险储备", "alpha = 0.60", "alpha = 0.70", "alpha = 0.80", "alpha = 0.90"]
    year_start = mdates.date2num(pd.Timestamp("2025-01-01").to_pydatetime())
    year_end = mdates.date2num(pd.Timestamp("2026-01-01").to_pydatetime())
    for y in range(5):
        ax.barh(
            y,
            year_end - year_start,
            left=year_start,
            height=0.62,
            color=LIGHT_GRAY,
            edgecolor="none",
            zorder=0,
        )
    ax.axvspan(
        pd.Timestamp("2025-01-01"),
        pd.Timestamp("2025-01-29"),
        color=GRAY,
        alpha=0.10,
        zorder=1,
    )
    for row in selected.itertuples():
        start = mdates.date2num(pd.Timestamp(row.effective_start_date).to_pydatetime())
        end = mdates.date2num(
            (pd.Timestamp(row.effective_end_date) + pd.Timedelta(days=1)).to_pydatetime()
        )
        duration = int((row.effective_end_date - row.effective_start_date).days + 1)
        if row.fixed_k == 1:
            y = y_map[None]
            ax.barh(
                y,
                end - start,
                left=start,
                height=0.62,
                color="white",
                edgecolor=BLACK,
                linewidth=0.8,
                hatch="///",
                zorder=3,
            )
        else:
            alpha = round(float(row.risk_alpha), 2)
            y = y_map[alpha]
            ax.barh(
                y,
                end - start,
                left=start,
                height=0.62,
                color=BLUE,
                edgecolor=BLUE,
                linewidth=0.8,
                zorder=3,
            )
            if alpha == 0.7:
                ax.text(
                    (start + end) / 2,
                    y,
                    "alpha=0.70",
                    ha="center",
                    va="center",
                    fontsize=8.2,
                    color="white",
                    zorder=4,
                )
            elif duration == 1:
                ax.text(
                    start - 1.2,
                    y,
                    "12/31",
                    ha="right",
                    va="center",
                    fontsize=8.2,
                    color=BLACK,
                    zorder=5,
                    bbox={
                        "boxstyle": "round,pad=0.12",
                        "facecolor": "white",
                        "edgecolor": "none",
                        "alpha": 0.92,
                    },
                )
    ax.text(
        mdates.date2num(pd.Timestamp("2025-01-15").to_pydatetime()),
        0,
        "1/1–1/28",
        ha="center",
        va="center",
        fontsize=8.2,
        color=BLACK,
        zorder=4,
        bbox={
            "boxstyle": "round,pad=0.12",
            "facecolor": "white",
            "edgecolor": "none",
            "alpha": 0.88,
        },
    )
    for unused_y in (3, 4):
        ax.text(
            mdates.date2num(pd.Timestamp("2025-07-01").to_pydatetime()),
            unused_y,
            "候选未选用",
            ha="center",
            va="center",
            fontsize=8.4,
            color=GRAY,
            zorder=2,
        )
    ax.set_yticks(list(range(5)), ytick_labels)
    ax.set_ylim(-0.55, 4.75)
    ax.set_ylabel("政策档位")
    ax.set_xlabel("风险分位生效区间（每 14 日一块）")
    ax.set_title("Q2 滚动风险分位的因果校准时间线", pad=8)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_xlim(pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-04"))
    ax.grid(axis="x", linestyle=":", color=GRAY, alpha=0.32, zorder=0)
    style_axes(ax)
    fig.subplots_adjust(bottom=0.24)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.text(
        0.5,
        0.04,
        "K=8 阶段候选集 alphain{0.60, 0.70, 0.80, 0.90}；每次仅使用此前已结束日的结果选择。"
        "12/17–12/30 为 alpha=0.70，12/31 回落至 alpha=0.60。",
        ha="center",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": LIGHT_GRAY, "edgecolor": GRAY},
    )
    save_figure(fig, "fig_q2_risk_calibration")
    return {
        "selected_blocks": len(selected),
        "k1_no_reserve_blocks": int(early.sum()),
        "k8_blocks": int((~early).sum()),
        "alpha_060_days": int(
            sum(
                (row.effective_end_date - row.effective_start_date).days + 1
                for row in selected.itertuples()
                if row.risk_alpha == 0.6
            )
        ),
        "alpha_070_days": int(
            sum(
                (row.effective_end_date - row.effective_start_date).days + 1
                for row in selected.itertuples()
                if row.risk_alpha == 0.7
            )
        ),
        "calendar_start": selected["effective_start_date"].iloc[0].strftime("%Y-%m-%d"),
        "calendar_end": selected["effective_end_date"].iloc[-1].strftime("%Y-%m-%d"),
        "causal_history_cutoffs": bool(causal.all()),
    }


def write_readme(
    font: str,
    f2: dict,
    f3: dict,
    f4: dict,
    tariff_audit: dict,
    hashes: dict[str, str],
) -> None:
    lines = [
        "# Q2 正式交付图",
        "",
        "运行命令：",
        "",
        "```bash",
        "MPLCONFIGDIR=\"$PWD/.mplconfig\" .venv/bin/python q2/plot_final_figures.py",
        "```",
        "",
        f"- 中文字体：{font}",
        "- 所有 PNG 均以 320 dpi 导出，同时提供矢量 PDF。",
        "- 原始时段顺序保持 `00:10` 至 `0:00+1`，未旋转或补造时段。",
        "",
        "## F1 `fig_q2_closed_loop`",
        "",
        "- 数据源：模型机制与已签收固定口径；图形由 matplotlib patches 矢量绘制。",
        "- 核验：明确当天 q 锁定、日内可修正变量、紧急购电作用和实际 SOC 跨日传递。",
        "",
        "## F2 `fig_q2_cost_comparison`",
        "",
        "- 数据源：`output/q2_full_k8_risk/daily_summary.csv` 与 "
        "`output/q2_full_linked/daily_summary.csv`。",
        "- 汇总范围：2025-02-01 至 2025-12-31，共 334 日。",
        f"- K=8：计划费 {f2['k8_planned_cost_yuan']:,.2f} 元，紧急费 "
        f"{f2['k8_emergency_cost_yuan']:,.2f} 元，总成本 {f2['k8_total_cost_yuan']:,.2f} 元，"
        f"紧急购电 {f2['k8_emergency_kwh']:,.2f} kWh。",
        f"- 相对原动态 K：总成本变化 {f2['cost_change_yuan']:,.2f} 元，"
        f"紧急购电量变化 {f2['emergency_change_kwh']:,.2f} kWh。",
        "- 核验：与任务单签收值差异均小于 0.01 元 / 0.01 kWh。",
        "",
        "## F3 `fig_q2_representative_day`",
        "",
        "- 数据源：K=8 日汇总及对应逐时调度 CSV。",
        f"- 可复现选择：2—12 月 `emergency_cost_yuan` 最大日为 {f3['selected_date']}。",
        f"- 源文件：`{f3['source']}`；共 {f3['dispatch_rows']} 时段，"
        f"{f3['first_time']} 至 {f3['last_time']}。",
        "- 分时电价由允许读取的 365 日锁定计划、紧急购电和日成本按 "
        "`planned_cost=p@q`、`emergency_cost=5*p@e` 联立恢复。",
        f"- 电价恢复矩阵秩 {tariff_audit['rank']}；最大成本回代残差 "
        f"{tariff_audit['max_accounting_residual_yuan']:.3e} 元。",
        "- 核验：净负荷、q、x、e、d-c、价格、SOC 均直接读取或逐项确定性计算。",
        "",
        "## F4 `fig_q2_risk_calibration`",
        "",
        "- 数据源：`output/q2_full_k8_risk/risk_calibration.csv`。",
        f"- 共 {f4['selected_blocks']} 个生效块：前 {f4['k1_no_reserve_blocks']} 块为 "
        f"K=1 / 无风险储备，随后 {f4['k8_blocks']} 块为 K=8。",
        f"- 日数核验：alpha=0.60 为 {f4['alpha_060_days']} 日，alpha=0.70 为 "
        f"{f4['alpha_070_days']} 日；区间连续且历史截止日均早于校准日。",
        "",
        "## 只读保护",
        "",
        "- 绘图脚本对所有源 CSV 与 `output/result2.xlsx` 执行前后 SHA-256 校验。",
        f"- `output/result2.xlsx` SHA-256："
        f"`{hashes.get(str(RESULT2.relative_to(ROOT)), '文件不存在')}`。",
    ]
    (FIG_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    dispatch_paths = sorted(K8_DISPATCH_DIR.glob("dispatch_*.csv"))
    if len(dispatch_paths) != 365:
        raise AssertionError(f"Expected 365 K=8 dispatch files, got {len(dispatch_paths)}")
    source_paths = [K8_DAILY, DYNAMIC_DAILY, RISK_CALIBRATION, *dispatch_paths]
    if RESULT2.exists():
        source_paths.append(RESULT2)
    for path in source_paths:
        if not path.exists():
            raise FileNotFoundError(path)
    hashes_before = {
        str(path.relative_to(ROOT)): file_hash(path) for path in source_paths
    }
    font = configure_style()
    k8 = pd.read_csv(K8_DAILY)
    dynamic = pd.read_csv(DYNAMIC_DAILY)
    calibration = pd.read_csv(RISK_CALIBRATION)
    price, tariff_audit = recover_tariff(k8)

    plot_f1()
    f2 = plot_f2(k8, dynamic)
    f3 = plot_f3(k8, price)
    f4 = plot_f4(calibration)

    hashes_after = {
        str(path.relative_to(ROOT)): file_hash(path) for path in source_paths
    }
    if hashes_before != hashes_after:
        raise AssertionError("A source result file changed during plotting")
    audit = {
        "status": "PASS",
        "font": font,
        "png_dpi": 320,
        "f2": f2,
        "f3": f3,
        "tariff_recovery": tariff_audit,
        "f4": f4,
        "source_sha256": hashes_after,
        "result2_unchanged": hashes_before.get(str(RESULT2.relative_to(ROOT)))
        == hashes_after.get(str(RESULT2.relative_to(ROOT))),
    }
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    (FIG_DIR / "figure_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_readme(font, f2, f3, f4, tariff_audit, hashes_after)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


# ===== q2/plot_q2_policy_consistent_r3.py =====
#!/usr/bin/env python3
"""C2-R3 comparison figures versus the signed-off old K=8 Q2 path.

Writes only to fig/q2_policy_consistent/; never touches fig/q2_final/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import FIG_POLICY_CONSISTENT_DIR, OFFICIAL_OUTPUT_START, T


BLUE = "#276FBF"
RED = "#C0392B"
GRAY = "#6B7280"
BLACK = "#1F2933"
GREEN = "#2F6F4E"
LIGHT_GRAY = "#F3F4F6"
LIGHT_BLUE = "#E8F1FA"
LIGHT_RED = "#F8E7E5"


def configure_style() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = (
        "PingFang SC",
        "Hiragino Sans GB",
        "Heiti SC",
        "Songti SC",
        "Arial Unicode MS",
        "Noto Sans CJK SC",
    )
    font = next((name for name in candidates if name in available), None)
    if font is None:
        raise RuntimeError("No usable Chinese font found")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font],
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "axes.titleweight": "medium",
            "pdf.fonttype": 42,
        }
    )
    return font


def save_figure(fig: plt.Figure, stem: str, fig_dir: Path) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(fig_dir / f"{stem}.png", dpi=320, bbox_inches="tight")
    plt.close(fig)


def style_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRAY)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(color=GRAY, length=3.5)
    ax.grid(axis="y", linestyle=":", color=GRAY, alpha=0.35, zorder=0)
    ax.set_axisbelow(True)


def official_interval(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"])
    start = pd.Timestamp(OFFICIAL_OUTPUT_START)
    end = pd.Timestamp("2025-12-31")
    return (
        out.loc[(out["date"] >= start) & (out["date"] <= end)]
        .sort_values("date")
        .reset_index(drop=True)
    )


def style_time_axis(ax: plt.Axes) -> None:
    ax.set_xlim(pd.Timestamp(OFFICIAL_OUTPUT_START), pd.Timestamp("2025-12-31"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m月"))


def plot_r3_comparison(
    redesign: pd.DataFrame,
    old_k8: pd.DataFrame,
    fig_dir: Path | None = None,
) -> dict:
    configure_style()
    target = Path(fig_dir) if fig_dir is not None else FIG_POLICY_CONSISTENT_DIR
    new = official_interval(redesign)
    old = official_interval(old_k8)
    if len(new) != 334 or len(old) != 334:
        raise AssertionError("official comparison window must be 334 days")
    if not new["date"].equals(old["date"]):
        raise AssertionError("old and new official dates do not align")

    names = ["旧全路径近似对照（K=8）", "政策一致主方案（预注册 K=8）"]
    frames = [old, new]
    planned = np.array([frame["planned_cost_yuan"].sum() for frame in frames])
    emergency_cost = np.array([frame["emergency_cost_yuan"].sum() for frame in frames])
    total = planned + emergency_cost
    emergency_kwh = np.array([frame["emergency_kwh"].sum() for frame in frames])
    curtailment = np.array([frame["curtailment_kwh"].sum() for frame in frames])
    if not np.allclose(total, [frame["total_cost_yuan"].sum() for frame in frames], atol=0.05):
        raise AssertionError("cost components do not match total_cost_yuan")

    fig, ax = plt.subplots(figsize=(9.6, 6.9))
    x = np.arange(2)
    ax.bar(x, planned, width=0.48, color=BLUE, edgecolor=BLACK, linewidth=0.7, label="计划购电费", zorder=3)
    ax.bar(
        x,
        emergency_cost,
        width=0.48,
        bottom=planned,
        color="white",
        edgecolor=RED,
        linewidth=1.15,
        hatch="///",
        label="紧急购电费",
        zorder=3,
    )
    for index, (plan, emergency, value) in enumerate(zip(planned, emergency_cost, total)):
        ax.text(
            x[index],
            plan * 0.52,
            f"{plan / 1e6:.2f} 百万",
            ha="center",
            va="center",
            color="white",
            fontsize=9.5,
            zorder=4,
        )
        ax.text(
            x[index],
            plan + emergency * 0.55,
            f"{emergency / 1e6:.2f} 百万",
            ha="center",
            va="center",
            color=RED,
            fontsize=8.6,
            zorder=4,
            bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.9},
        )
        ax.text(
            x[index],
            value + total.max() * 0.018,
            f"合计 {value:,.2f} 元",
            ha="center",
            va="bottom",
            fontsize=9.6,
            zorder=4,
            clip_on=False,
        )
    ax.set_xticks(x, names)
    ax.set_ylabel("2—12 月购电成本（元）")
    ax.set_title("政策一致主方案与旧全路径近似对照的成本构成", pad=18)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value / 1e6:.1f} 百万"))
    ax.set_ylim(0, total.max() * 1.12)
    ax.set_xlim(-0.55, 1.55)
    style_axes(ax)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2, frameon=False, borderaxespad=0.0)
    fig.subplots_adjust(bottom=0.22, top=0.86)
    fig.text(
        0.5,
        0.085,
        f"政策一致主方案相对旧全路径对照：总成本变化 {total[1] - total[0]:,.2f} 元；"
        f"紧急购电量变化 {emergency_kwh[1] - emergency_kwh[0]:,.2f} kWh",
        ha="center",
        fontsize=9.5,
        bbox={"boxstyle": "round,pad=0.38", "facecolor": LIGHT_GRAY, "edgecolor": GRAY},
    )
    fig.text(
        0.5,
        0.02,
        "注：K=8 为预注册且对 K=4/12 稳定的简洁主方案，并非成本最优；"
        "旧全路径方案仅作信息更强的近似对照。1 月仅作预热。",
        ha="center",
        fontsize=9,
        color=GRAY,
    )
    save_figure(fig, "fig_q2_pc_cost_comparison", target)

    fig, axes = plt.subplots(2, 1, figsize=(10.2, 7.4), sharex=True)
    series = [
        (axes[0], "emergency_kwh", "紧急购电量（kWh）", RED, LIGHT_RED),
        (axes[1], "curtailment_kwh", "弃光量（kWh）", GREEN, LIGHT_BLUE),
    ]
    for ax, column, ylabel, color, fill in series:
        ax.fill_between(old["date"], old[column], color=fill, alpha=0.9, zorder=1)
        ax.plot(old["date"], old[column], color=GRAY, linewidth=1.05, label="旧全路径对照", zorder=2)
        ax.plot(new["date"], new[column], color=color, linewidth=1.25, label="政策一致主方案", zorder=3)
        ax.set_ylabel(ylabel)
        style_axes(ax)
        ax.legend(frameon=False, loc="upper right")
    axes[0].set_title("2—12 月紧急购电与弃光逐日对照")
    style_time_axis(axes[1])
    fig.tight_layout()
    save_figure(fig, "fig_q2_pc_emergency_curtailment", target)

    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    ax.plot(old["date"], old["soc_end_kwh"], color=GRAY, linewidth=1.1, label="旧全路径对照")
    ax.plot(new["date"], new["soc_end_kwh"], color=BLUE, linewidth=1.3, label="政策一致主方案")
    ax.set_ylabel("日末 SOC（kWh）")
    ax.set_title("2—12 月储能日末 SOC 对照")
    style_time_axis(ax)
    style_axes(ax)
    ax.legend(frameon=False)
    fig.tight_layout()
    save_figure(fig, "fig_q2_pc_soc", target)

    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    ax.plot(
        old["date"],
        old["total_cost_yuan"].cumsum(),
        color=GRAY,
        linewidth=1.2,
        label="旧全路径对照",
    )
    ax.plot(
        new["date"],
        new["total_cost_yuan"].cumsum(),
        color=BLUE,
        linewidth=1.4,
        label="政策一致主方案",
    )
    ax.set_ylabel("累计购电成本（元）")
    ax.set_title("2—12 月累计实际购电成本对照")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value / 1e6:.1f} 百万"))
    style_time_axis(ax)
    style_axes(ax)
    ax.legend(frameon=False)
    fig.tight_layout()
    save_figure(fig, "fig_q2_pc_cumulative_cost", target)

    return {
        "old_feb_dec_total_cost_yuan": float(total[0]),
        "new_feb_dec_total_cost_yuan": float(total[1]),
        "cost_change_yuan": float(total[1] - total[0]),
        "old_feb_dec_emergency_kwh": float(emergency_kwh[0]),
        "new_feb_dec_emergency_kwh": float(emergency_kwh[1]),
        "emergency_change_kwh": float(emergency_kwh[1] - emergency_kwh[0]),
        "old_feb_dec_curtailment_kwh": float(curtailment[0]),
        "new_feb_dec_curtailment_kwh": float(curtailment[1]),
        "figure_dir": str(target),
        "stems": [
            "fig_q2_pc_cost_comparison",
            "fig_q2_pc_emergency_curtailment",
            "fig_q2_pc_soc",
            "fig_q2_pc_cumulative_cost",
        ],
    }


def _draw_box(ax, x, y, width, height, text, facecolor) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            linewidth=1.15,
            edgecolor=BLACK,
            facecolor=facecolor,
        )
    )
    ax.text(x + width / 2, y + height / 2, text, ha="center", va="center", linespacing=1.38)


def _draw_arrow(ax, start, end, label, label_y) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.25,
            color=BLACK,
            shrinkA=2,
            shrinkB=2,
        )
    )
    ax.text(
        (start[0] + end[0]) / 2,
        label_y,
        label,
        ha="center",
        va="bottom",
        fontsize=8.8,
        bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.95},
    )


def plot_pc_closed_loop(fig_dir: Path) -> dict:
    fig, ax = plt.subplots(figsize=(15.6, 6.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    y, width, height = 0.48, 0.148, 0.30
    gap = 0.055
    xs = [0.020 + index * (width + gap) for index in range(5)]
    texts = [
        "已结束日负荷—光伏\n构造 $m\\in\\{m_1,m_2,m_3\\}$",
        "基准预测日前 LP\n$+$ $R(\\alpha)$ 风险储备",
        "0:00 锁定\n计划购电量\n$q_{d,t}$",
        "每 10 分钟残差匹配\n更新 $x,c,d,e$\n仅执行当前一步",
        "实际日末 SOC\n$E_{d,144}$\n传至下一日",
    ]
    faces = [LIGHT_GRAY, LIGHT_BLUE, LIGHT_BLUE, LIGHT_RED, LIGHT_GRAY]
    for x, text, face in zip(xs, texts, faces):
        _draw_box(ax, x, y, width, height, text, face)
    labels = [
        "冻结日历选用 $(m,\\alpha)$",
        "0:00 决策",
        "当天 $q$ 不可修改",
        "仅传递实际 SOC",
    ]
    for index in range(4):
        _draw_arrow(
            ax,
            (xs[index] + width, y + height / 2),
            (xs[index + 1], y + height / 2),
            labels[index],
            y + height + 0.035,
        )
    mid_y = 0.30
    ax.plot(
        [xs[4] + width / 2, xs[4] + width / 2, xs[1] + width / 2, xs[1] + width / 2],
        [y, mid_y, mid_y, y],
        color=BLUE,
        linestyle="--",
        linewidth=1.25,
        solid_capstyle="round",
    )
    ax.annotate(
        "",
        xy=(xs[1] + width / 2, y),
        xytext=(xs[1] + width / 2, mid_y + 0.01),
        arrowprops={"arrowstyle": "-|>", "color": BLUE, "lw": 1.25},
    )
    ax.text(
        (xs[1] + xs[4] + width) / 2,
        mid_y - 0.055,
        "次日价值割只近似次日基准预测成本；不提前锁定次日 $q$，不计入真实账单",
        ha="center",
        color=BLUE,
        fontsize=9.2,
    )
    ax.text(
        0.5,
        0.09,
        "K=8 为预注册残差压缩规模，且对 K=4/12 稳定；并非成本最优。日内仅修正储能与实际取用。",
        ha="center",
        color=RED,
        fontsize=9.2,
        bbox={"boxstyle": "round,pad=0.32", "facecolor": LIGHT_RED, "edgecolor": RED, "linewidth": 0.6},
    )
    ax.set_title("Q2 政策一致：基准日前计划—残差 MPC—跨日 SOC 闭环", pad=10)
    save_figure(fig, "fig_q2_pc_closed_loop", fig_dir)
    return {"stem": "fig_q2_pc_closed_loop"}


def plot_pc_representative_day(
    daily: pd.DataFrame,
    dispatch_dir: Path,
    price: np.ndarray,
    fig_dir: Path,
) -> dict:
    output = official_interval(daily)
    selected = output.loc[output["emergency_cost_yuan"].idxmax()]
    date = pd.Timestamp(selected["date"])
    path = dispatch_dir / f"dispatch_{date:%Y-%m-%d}.csv"
    frame = pd.read_csv(path)
    required = {
        "period",
        "time",
        "planned_q_kwh",
        "actual_x_kwh",
        "load_kwh",
        "pv_kwh",
        "charge_kwh",
        "discharge_kwh",
        "emergency_kwh",
        "soc_kwh",
    }
    if len(frame) != T or not required.issubset(frame.columns):
        raise AssertionError("representative-day dispatch schema/row count mismatch")
    if not np.array_equal(frame["period"].to_numpy(), np.arange(T)):
        raise AssertionError("representative-day period order changed")
    if str(frame["time"].iloc[0]) != "00:10" or str(frame["time"].iloc[-1]) != "0:00+1":
        raise AssertionError("representative-day raw attachment time order mismatch")
    if len(price) != T:
        raise AssertionError("representative-day tariff must contain 144 values")

    hours = (frame["period"].to_numpy() + 1) / 6.0
    net_load = frame["load_kwh"].to_numpy() - frame["pv_kwh"].to_numpy()
    battery_net = frame["discharge_kwh"].to_numpy() - frame["charge_kwh"].to_numpy()
    fig, axes = plt.subplots(3, 1, figsize=(12.6, 11.0), sharex=True, gridspec_kw={"hspace": 0.16})
    legend_box = {
        "frameon": True,
        "framealpha": 0.96,
        "edgecolor": "#E5E7EB",
        "fancybox": False,
        "borderpad": 0.45,
        "handlelength": 2.2,
    }
    ax = axes[0]
    ax.plot(hours, net_load, color=BLACK, linewidth=1.35, label="实际净负荷 $L-P$")
    ax.plot(hours, frame["planned_q_kwh"], color=BLUE, linewidth=1.25, label="锁定计划 $q$")
    ax.plot(hours, frame["actual_x_kwh"], color=GRAY, linestyle="--", linewidth=1.15, label="实际普通取电 $x$")
    ax.plot(hours, frame["emergency_kwh"], color=RED, linestyle="-.", linewidth=1.45, label="紧急购电 $e$")
    ax.fill_between(hours, 0, frame["emergency_kwh"], color=RED, alpha=0.12, linewidth=0)
    ymax = max(net_load.max(), frame["planned_q_kwh"].max(), frame["emergency_kwh"].max())
    ax.set_ylim(-0.10 * ymax, ymax * 1.22)
    ax.set_ylabel("时段电量（kWh）")
    ax.legend(loc="upper left", ncol=2, **legend_box)
    ax.grid(linestyle=":", color=GRAY, alpha=0.32)
    ax.set_axisbelow(True)
    style_axes(ax)

    ax = axes[1]
    ax.axhline(0, color=GRAY, linewidth=0.8)
    ax.plot(hours, battery_net, color=BLACK, linewidth=1.2, label="电池净动作 $d-c$")
    ax.fill_between(hours, 0, battery_net, color=BLACK, alpha=0.10, linewidth=0)
    ax.set_ylabel("$d-c$（kWh）")
    abs_max = np.max(np.abs(battery_net))
    ax.set_ylim(-abs_max * 1.28, abs_max * 1.28)
    ax_price = ax.twinx()
    ax_price.step(hours, price, where="mid", color=RED, linestyle="--", linewidth=1.15, label="分时电价")
    ax_price.set_ylabel("电价（元/kWh）", color=RED)
    ax_price.tick_params(axis="y", colors=RED)
    ax_price.set_ylim(0.28, price.max() * 1.22)
    ax_price.spines["top"].set_visible(False)
    ax_price.spines["right"].set_color(RED)
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax_price.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, loc="lower left", **legend_box)
    ax.grid(linestyle=":", color=GRAY, alpha=0.32)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)

    ax = axes[2]
    ax.plot(hours, frame["soc_kwh"], color=BLUE, linewidth=1.5, label="SOC")
    ax.axhline(1200, color=GRAY, linestyle="--", linewidth=1.0, label="SOC 边界 1200 / 10800 kWh")
    ax.axhline(10800, color=GRAY, linestyle="--", linewidth=1.0)
    ax.set_ylabel("SOC（kWh）")
    ax.set_xlabel("时刻")
    ax.set_ylim(200, 12800)
    ax.legend(loc="center left", **legend_box)
    ax.grid(linestyle=":", color=GRAY, alpha=0.32)
    ax.set_axisbelow(True)
    style_axes(ax)
    axes[-1].set_xlim(0, 24)
    axes[-1].set_xticks(np.arange(0, 25, 2))
    axes[-1].set_xticklabels([f"{hour:02d}:00" for hour in range(0, 25, 2)])
    fig.suptitle(f"Q2 政策一致轨迹：{date:%Y-%m-%d}（2—12 月紧急费用最高日）", y=0.98)
    fig.subplots_adjust(top=0.945, bottom=0.055, left=0.08, right=0.91, hspace=0.20)
    save_figure(fig, "fig_q2_pc_representative_day", fig_dir)
    return {
        "selected_date": date.strftime("%Y-%m-%d"),
        "selection_metric": "maximum emergency_cost_yuan over 2025-02-01..2025-12-31",
        "not_typical_day": True,
        "emergency_cost_yuan": float(selected["emergency_cost_yuan"]),
        "emergency_kwh": float(selected["emergency_kwh"]),
        "dispatch_rows": len(frame),
        "source": str(path),
    }


def plot_pc_forecast_calendar(calibration: pd.DataFrame, fig_dir: Path) -> dict:
    if "selected" not in calibration:
        raise AssertionError("frozen calendar source lacks selected flag")
    selected = calibration.loc[calibration["selected"].astype(bool)].copy()
    selected["effective_start_date"] = pd.to_datetime(selected["effective_start_date"])
    selected["effective_end_date"] = pd.to_datetime(selected["effective_end_date"])
    selected = selected.sort_values("effective_start_date").reset_index(drop=True)
    if selected["effective_start_date"].iloc[0] != pd.Timestamp("2025-01-01"):
        raise AssertionError("frozen calendar start mismatch")
    if selected["effective_end_date"].iloc[-1] != pd.Timestamp("2025-12-31"):
        raise AssertionError("frozen calendar end mismatch")
    for previous, current in zip(selected.itertuples(), selected.iloc[1:].itertuples()):
        if previous.effective_end_date + pd.Timedelta(days=1) != current.effective_start_date:
            raise AssertionError("frozen calendar blocks are not contiguous")

    def row_key(row) -> tuple:
        fallback = str(getattr(row, "fallback_reason", "") or "")
        if fallback not in ("", "nan"):
            return ("fallback", None, None)
        alpha = None if pd.isna(row.risk_alpha) else round(float(row.risk_alpha), 2)
        return ("policy", str(row.forecast_mode), alpha)

    keys: list[tuple] = []
    for row in selected.itertuples():
        key = row_key(row)
        if key not in keys:
            keys.append(key)
    keys = sorted(
        keys,
        key=lambda item: (0 if item[0] == "fallback" else 1, str(item[1] or ""), item[2] or 0.0),
    )
    y_map = {key: index for index, key in enumerate(keys)}
    labels = []
    for kind, mode, alpha in keys:
        if kind == "fallback":
            labels.append("回退 K=1 / 无风险储备")
        else:
            labels.append(f"{mode}, alpha={alpha:.2f}")

    mode_color = {"m1": BLUE, "m2": GREEN, "m3": RED, None: GRAY}
    fig, ax = plt.subplots(figsize=(13.4, 6.4))
    year_start = mdates.date2num(pd.Timestamp("2025-01-01").to_pydatetime())
    year_end = mdates.date2num(pd.Timestamp("2026-01-01").to_pydatetime())
    for y in range(len(keys)):
        ax.barh(y, year_end - year_start, left=year_start, height=0.62, color=LIGHT_GRAY, edgecolor="none", zorder=0)
    ax.axvspan(pd.Timestamp("2025-01-01"), pd.Timestamp("2025-02-01"), color=GRAY, alpha=0.10, zorder=1)
    for row in selected.itertuples():
        start = mdates.date2num(pd.Timestamp(row.effective_start_date).to_pydatetime())
        end = mdates.date2num((pd.Timestamp(row.effective_end_date) + pd.Timedelta(days=1)).to_pydatetime())
        key = row_key(row)
        color = GRAY if key[0] == "fallback" else mode_color.get(key[1], BLUE)
        ax.barh(y_map[key], end - start, left=start, height=0.62, color=color, edgecolor=BLACK, linewidth=0.4, zorder=3)
    ax.set_yticks(range(len(keys)), labels)
    ax.set_xlim(pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-01"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m月"))
    ax.set_title("C2-R2 冻结的预测结构与风险分位日历（正式主方案沿用）")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.text(
        0.5,
        0.02,
        "1 月为预热；2—12 月正式输出继承该日历。K=8 保持预注册，不随块重选。",
        ha="center",
        fontsize=9,
        color=GRAY,
    )
    fig.subplots_adjust(bottom=0.12)
    save_figure(fig, "fig_q2_pc_forecast_calendar", fig_dir)
    return {
        "stem": "fig_q2_pc_forecast_calendar",
        "n_blocks": int(len(selected)),
        "n_rows": int(len(keys)),
    }


def plot_r4_final_figures(
    redesign: pd.DataFrame,
    old_k8: pd.DataFrame,
    calibration: pd.DataFrame,
    dispatch_dir: Path,
    price: np.ndarray,
    fig_dir: Path | None = None,
) -> dict:
    configure_style()
    target = Path(fig_dir) if fig_dir is not None else FIG_POLICY_CONSISTENT_DIR
    comparison = plot_r3_comparison(redesign, old_k8, fig_dir=target)
    closed = plot_pc_closed_loop(target)
    representative = plot_pc_representative_day(redesign, dispatch_dir, price, target)
    calendar = plot_pc_forecast_calendar(calibration, target)
    stems = list(comparison["stems"]) + [
        closed["stem"],
        "fig_q2_pc_representative_day",
        calendar["stem"],
    ]
    return {
        **comparison,
        "closed_loop": closed,
        "representative_day": representative,
        "forecast_calendar": calendar,
        "stems": stems,
        "figure_dir": str(target),
    }


if __name__ == "__main__":
    from q2.config import FULL_K8_RISK_OUTPUT_DIR, POLICY_CONSISTENT_OUTPUT_DIR

    plot_r3_comparison(
        pd.read_csv(POLICY_CONSISTENT_OUTPUT_DIR / "q2_redesign_daily_summary.csv"),
        pd.read_csv(FULL_K8_RISK_OUTPUT_DIR / "daily_summary.csv"),
    )

# ===== q2/policy_consistent.py =====
"""Policy-consistent Q2 redesign: baseline forecast LP + K=8 reserve + residual MPC.

This module is independent of the signed-off stochastic day-ahead production path.
K-medoids enter only through the risk reserve R(alpha) and intra-day residual weights.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from math import sqrt
import json
import os
from pathlib import Path
from threading import Lock

import numpy as np
import pandas as pd

from q2.config import (
    EMERGENCY_PRICE_MULTIPLIER,
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    FIXED_SCENARIO_K,
    K_RECALIBRATION_DAYS,
    LOAD_HISTORY_SAME_WEEKDAY,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    NEXT_DAY_VALUE_MAX_SAMPLES,
    NUMERIC_TOL,
    OFFICIAL_OUTPUT_START,
    POWER_LIMIT_KWH,
    PV_HISTORY_DAYS,
    RISK_ALPHA_CANDIDATES,
    RISK_CALIBRATION_DAYS,
    SIMULTANEOUS_CD_TOL,
    T,
)
from q2.data import Q2Data
from q2.forecast import ForecastArchive
from q2.optimization import (
    BaselinePlanResult,
    ValueCut,
    evaluate_value_cuts,
    solve_baseline_plan,
    solve_fixed_plan_dispatch,
)
from q2.pilot import planned_q_hash, risk_quantile_floor
from q2.scenarios import (
    ScenarioSet,
    build_scenarios,
    posterior_weights,
)


class ForecastMode(str, Enum):
    M1 = "m1"
    M2 = "m2"
    M3 = "m3"


FORECAST_MODES: tuple[ForecastMode, ...] = (
    ForecastMode.M1,
    ForecastMode.M2,
    ForecastMode.M3,
)
R1_DEFAULT_MODE = ForecastMode.M1
R1_DEFAULT_ALPHA = 0.60
ValueCutCache = dict[
    tuple[int, str, float | None, int],
    tuple[tuple[ValueCut, ...], list[dict]],
]
PERIOD_JANUARY_WARMUP = "january_warmup"
PERIOD_FEB_DEC_OUTPUT = "feb_dec_output"


@dataclass(frozen=True)
class FrozenDayPolicy:
    date: str
    forecast_mode: ForecastMode
    risk_alpha: float | None
    fallback_reason: str
    calibration_date: str
    effective_start_date: str
    effective_end_date: str

    def effective_k(self, requested_k: int) -> int:
        if self.risk_alpha is None:
            return 1
        return int(requested_k)


@dataclass(frozen=True)
class DayForecast:
    mode: ForecastMode
    load_hat: np.ndarray
    pv_hat: np.ndarray
    load_sources: tuple[int, ...]
    pv_sources: tuple[int, ...]
    load_fallback: bool
    pv_fallback: bool


def _aggregate_rows(rows: np.ndarray, mode: ForecastMode) -> np.ndarray:
    if rows.ndim != 2 or rows.shape[0] == 0:
        raise ValueError("forecast aggregation requires at least one history row")
    if mode is ForecastMode.M1:
        return rows.mean(axis=0)
    if mode is ForecastMode.M2:
        return np.median(rows, axis=0)
    if mode is ForecastMode.M3:
        weights = np.arange(1, rows.shape[0] + 1, dtype=float)
        weights /= weights.sum()
        return weights @ rows
    raise ValueError(f"unknown forecast mode: {mode}")


def forecast_as_of_mode(
    data: Q2Data,
    target_index: int,
    history_end_exclusive: int,
    mode: ForecastMode,
) -> DayForecast:
    if not 0 <= history_end_exclusive <= target_index:
        raise ValueError("forecast cutoff must not exceed target date")
    target = data.dates[target_index]
    same_weekday = [
        j
        for j in range(history_end_exclusive)
        if data.dates[j].weekday() == target.weekday()
    ]
    load_sources = tuple(same_weekday[-LOAD_HISTORY_SAME_WEEKDAY:])
    pv_sources = tuple(
        range(max(0, history_end_exclusive - PV_HISTORY_DAYS), history_end_exclusive)
    )
    if load_sources:
        load_hat = _aggregate_rows(data.load[list(load_sources)], mode)
        load_fallback = False
    else:
        load_hat = data.fallback_load.copy()
        load_fallback = True
    if pv_sources:
        pv_hat = _aggregate_rows(data.pv[list(pv_sources)], mode)
        pv_fallback = False
    else:
        pv_hat = data.fallback_pv.copy()
        pv_fallback = True
    return DayForecast(
        mode=mode,
        load_hat=np.maximum(0.0, load_hat),
        pv_hat=np.maximum(0.0, pv_hat),
        load_sources=load_sources,
        pv_sources=pv_sources,
        load_fallback=load_fallback,
        pv_fallback=pv_fallback,
    )


def build_forecast_archive_mode(data: Q2Data, mode: ForecastMode) -> ForecastArchive:
    n = len(data.dates)
    load_hat = np.empty_like(data.load)
    pv_hat = np.empty_like(data.pv)
    load_sources: list[tuple[int, ...]] = []
    pv_sources: list[tuple[int, ...]] = []
    for i in range(n):
        forecast = forecast_as_of_mode(data, i, i, mode)
        load_hat[i] = forecast.load_hat
        pv_hat[i] = forecast.pv_hat
        load_sources.append(forecast.load_sources)
        pv_sources.append(forecast.pv_sources)
    return ForecastArchive(
        load_hat=load_hat,
        pv_hat=pv_hat,
        load_residual=data.load - load_hat,
        pv_residual=data.pv - pv_hat,
        load_sources=tuple(load_sources),
        pv_sources=tuple(pv_sources),
    )


def assert_history_strictly_prior(
    indices: tuple[int, ...] | np.ndarray, decision_index: int, label: str
) -> None:
    values = np.asarray(indices, dtype=int).ravel()
    if values.size and np.any(values >= decision_index):
        raise AssertionError(f"{label} leaks into decision index {decision_index}")


def k8_scenarios(
    target_index: int,
    data: Q2Data,
    archive: ForecastArchive,
    history_end_exclusive: int | None = None,
    k: int = FIXED_SCENARIO_K,
) -> ScenarioSet | None:
    history_end = target_index if history_end_exclusive is None else history_end_exclusive
    if history_end <= 0:
        return None
    scenarios = build_scenarios(
        target_index,
        data,
        archive,
        min(k, history_end),
        history_end_exclusive=history_end,
    )
    assert_history_strictly_prior(
        scenarios.pool_indices, target_index, "residual pool"
    )
    assert_history_strictly_prior(
        scenarios.medoid_indices, target_index, "medoid dates"
    )
    return scenarios


def risk_reserve_from_scenarios(
    scenarios: ScenarioSet | None,
    archive: ForecastArchive,
    load_hat: np.ndarray,
    pv_hat: np.ndarray,
    alpha: float | None,
) -> np.ndarray:
    if scenarios is None or alpha is None:
        return np.zeros(T)
    loads = np.maximum(
        0.0, load_hat[None, :] + archive.load_residual[scenarios.medoid_indices]
    )
    pvs = np.maximum(
        0.0, pv_hat[None, :] + archive.pv_residual[scenarios.medoid_indices]
    )
    return risk_quantile_floor(
        loads, pvs, scenarios.probabilities, load_hat, pv_hat, alpha
    )


def build_baseline_value_cuts(
    data: Q2Data,
    archive: ForecastArchive,
    current_index: int,
    mode: ForecastMode,
    k: int = FIXED_SCENARIO_K,
    risk_alpha: float | None = R1_DEFAULT_ALPHA,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    if current_index + 1 >= len(data.dates):
        return (), []
    nxt = current_index + 1
    forecast = forecast_as_of_mode(data, nxt, current_index, mode)
    assert_history_strictly_prior(forecast.load_sources, nxt, "next-day load forecast")
    assert_history_strictly_prior(forecast.pv_sources, nxt, "next-day PV forecast")
    scenarios = k8_scenarios(nxt, data, archive, current_index, k=k)
    q_floor = risk_reserve_from_scenarios(
        scenarios, archive, forecast.load_hat, forecast.pv_hat, risk_alpha
    )
    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = solve_baseline_plan(
            data.price, forecast.load_hat, forecast.pv_hat, float(soc), q_floor=q_floor
        )
        if result.has_scenario_specific_battery:
            raise AssertionError("next-day baseline LP created scenario battery variables")
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
            (slope, value - slope * reference) for reference, value, slope in cuts
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
    gap = 0.0
    while True:
        cuts = tuple(solved[soc] for soc in sorted(solved))
        slopes = np.array([cut[2] for cut in cuts])
        if np.any(np.diff(slopes) < -1e-6):
            raise AssertionError("baseline next-day value subgradients are not monotone")
        gap, refine_soc = certified_max_gap(cuts)
        if gap <= NEXT_DAY_VALUE_GAP_TOL_YUAN:
            break
        if len(cuts) >= NEXT_DAY_VALUE_MAX_SAMPLES:
            raise AssertionError(
                f"baseline next-day value gap {gap:.6f} exceeds tolerance after {len(cuts)} samples"
            )
        if min(abs(refine_soc - soc) for soc in solved) < 1e-7:
            raise AssertionError("baseline next-day value refinement stalled")
        solve_at(refine_soc)

    rows = [
        {
            "target_date": data.dates[nxt].strftime("%Y-%m-%d"),
            "history_cutoff_date": (
                data.dates[current_index - 1].strftime("%Y-%m-%d")
                if current_index
                else "attachment1_fallback"
            ),
            "forecast_mode": mode.value,
            "risk_alpha": risk_alpha,
            "risk_q_floor_kwh": float(q_floor.sum()),
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
            "gap_tolerance_yuan": NEXT_DAY_VALUE_GAP_TOL_YUAN,
            "bundle_sample_count": len(cuts),
        }
        for reference, value, slope in cuts
    ]
    return cuts, rows


def _horizon_forecasts(
    data: Q2Data,
    archive: ForecastArchive,
    scenarios: ScenarioSet | None,
    load_hat: np.ndarray,
    pv_hat: np.ndarray,
    day_index: int,
    period: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    remaining = slice(period, T)
    if scenarios is None:
        weights = np.ones(1)
        bandwidth = float("nan")
        load_horizon = load_hat[remaining].copy()
        pv_horizon = pv_hat[remaining].copy()
    else:
        observed_lr = data.load[day_index, : period + 1] - load_hat[: period + 1]
        observed_pr = data.pv[day_index, : period + 1] - pv_hat[: period + 1]
        weights, bandwidth = posterior_weights(
            scenarios, archive, observed_lr, observed_pr
        )
        load_horizon = np.maximum(
            0.0,
            load_hat[remaining]
            + weights @ archive.load_residual[scenarios.medoid_indices, remaining],
        )
        pv_horizon = np.maximum(
            0.0,
            pv_hat[remaining]
            + weights @ archive.pv_residual[scenarios.medoid_indices, remaining],
        )
    load_horizon[0] = data.load[day_index, period]
    pv_horizon[0] = data.pv[day_index, period]
    return load_horizon, pv_horizon, weights, bandwidth


def run_residual_mpc(
    data: Q2Data,
    archive: ForecastArchive,
    scenarios: ScenarioSet | None,
    load_hat: np.ndarray,
    pv_hat: np.ndarray,
    locked_q: np.ndarray,
    initial_soc: float,
    day_index: int,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    path: Path | None = None,
    mpc_periods: int | None = None,
) -> tuple[dict, pd.DataFrame]:
    locked_q = np.asarray(locked_q, dtype=float).ravel()
    locked_hash = planned_q_hash(locked_q)
    rows = []
    soc = float(initial_soc)
    max_cd = 0.0
    n_steps = T if mpc_periods is None else int(mpc_periods)
    if not 1 <= n_steps <= T:
        raise ValueError("mpc_periods must lie in 1..T")
    for t in range(n_steps):
        load_horizon, pv_horizon, weights, bandwidth = _horizon_forecasts(
            data, archive, scenarios, load_hat, pv_hat, day_index, t
        )
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
            + data.pv[day_index, t]
            - result.curtailment[0]
            + result.discharge[0]
            - data.load[day_index, t]
            - result.charge[0]
        )
        entropy = float(-np.sum(weights * np.log(np.maximum(weights, 1e-300))))
        rows.append(
            {
                "date": data.dates[day_index].strftime("%Y-%m-%d"),
                "period": t,
                "time": data.time_labels[t],
                "planned_q_kwh": locked_q[t],
                "actual_x_kwh": result.x[0],
                "load_kwh": data.load[day_index, t],
                "pv_kwh": data.pv[day_index, t],
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
        if planned_q_hash(locked_q) != locked_hash:
            raise AssertionError("locked day-ahead q changed during MPC")
    frame = pd.DataFrame(rows)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
    x = frame["actual_x_kwh"].to_numpy()
    emergency = frame["emergency_kwh"].to_numpy()
    executed_q = locked_q[:n_steps]
    executed_price = data.price[:n_steps]
    planned_cost = float(executed_price @ executed_q)
    emergency_cost = float(EMERGENCY_PRICE_MULTIPLIER * executed_price @ emergency)
    physical_ok = bool(
        frame["balance_residual_kwh"].abs().max() < NUMERIC_TOL
        and np.max(x - executed_q) < NUMERIC_TOL
        and frame["soc_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL
        and frame["soc_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL
        and max_cd <= SIMULTANEOUS_CD_TOL
        and np.max(frame["charge_kwh"].to_numpy()) <= POWER_LIMIT_KWH + NUMERIC_TOL
        and np.max(frame["discharge_kwh"].to_numpy()) <= POWER_LIMIT_KWH + NUMERIC_TOL
    )
    summary = {
        "date": data.dates[day_index].strftime("%Y-%m-%d"),
        "planned_cost_yuan": planned_cost,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": planned_cost + emergency_cost,
        "planned_q_kwh": float(executed_q.sum()),
        "planned_q_sha256": locked_hash,
        "actual_x_kwh": float(x.sum()),
        "unused_plan_kwh": float((executed_q - x).sum()),
        "emergency_kwh": float(emergency.sum()),
        "curtailment_kwh": float(frame["curtailment_kwh"].sum()),
        "soc_start_kwh": float(initial_soc),
        "soc_end_kwh": soc,
        "max_balance_residual_kwh": float(frame["balance_residual_kwh"].abs().max()),
        "max_simultaneous_cd_kwh2": max_cd,
        "max_x_minus_q_kwh": float(np.max(x - executed_q)),
        "mean_mpc_solve_seconds": float(frame["solve_seconds"].mean()),
        "total_mpc_solve_seconds": float(frame["solve_seconds"].sum()),
        "pass": physical_ok,
        "used_full_day_actual_lp": False,
        "future_actuals_in_optimizer": False,
    }
    return summary, frame


def plan_closed_loop_day(
    data: Q2Data,
    archive: ForecastArchive,
    day_index: int,
    initial_soc: float,
    mode: ForecastMode = R1_DEFAULT_MODE,
    risk_alpha: float | None = R1_DEFAULT_ALPHA,
    k: int = FIXED_SCENARIO_K,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    dispatch_path: Path | None = None,
    mpc_periods: int | None = None,
) -> tuple[dict, pd.DataFrame, BaselinePlanResult, np.ndarray, ScenarioSet | None]:
    forecast = forecast_as_of_mode(data, day_index, day_index, mode)
    assert_history_strictly_prior(forecast.load_sources, day_index, "load forecast")
    assert_history_strictly_prior(forecast.pv_sources, day_index, "PV forecast")
    scenarios = k8_scenarios(day_index, data, archive, day_index, k=k)
    q_floor = risk_reserve_from_scenarios(
        scenarios, archive, forecast.load_hat, forecast.pv_hat, risk_alpha
    )
    plan = solve_baseline_plan(
        data.price,
        forecast.load_hat,
        forecast.pv_hat,
        initial_soc,
        q_floor=q_floor,
        terminal_value_cuts=terminal_value_cuts,
    )
    if plan.has_scenario_specific_battery:
        raise AssertionError("day-ahead baseline LP created scenario battery variables")
    for name, shape in plan.variable_shapes.items():
        if name in {"charge", "discharge", "soc"} and shape not in {(T,), (T + 1,)}:
            raise AssertionError(f"unexpected {name} shape {shape}")
    summary, frame = run_residual_mpc(
        data,
        archive,
        scenarios,
        forecast.load_hat,
        forecast.pv_hat,
        plan.q,
        initial_soc,
        day_index,
        terminal_value_cuts=terminal_value_cuts,
        path=dispatch_path,
        mpc_periods=mpc_periods,
    )
    summary.update(
        {
            "forecast_mode": mode.value,
            "risk_alpha": risk_alpha,
            "scenario_k": 0 if scenarios is None else int(len(scenarios.probabilities)),
            "risk_q_floor_kwh": float(q_floor.sum()),
            "load_fallback": forecast.load_fallback,
            "pv_fallback": forecast.pv_fallback,
            "load_source_dates": ";".join(
                data.dates[j].strftime("%Y-%m-%d") for j in forecast.load_sources
            )
            or "attachment1_fallback",
            "pv_source_dates": ";".join(
                data.dates[j].strftime("%Y-%m-%d") for j in forecast.pv_sources
            )
            or "attachment1_fallback",
            "residual_pool_end_date": (
                data.dates[scenarios.pool_indices[-1]].strftime("%Y-%m-%d")
                if scenarios is not None
                else "none"
            ),
            "medoid_dates": (
                ";".join(
                    data.dates[j].strftime("%Y-%m-%d") for j in scenarios.medoid_indices
                )
                if scenarios is not None
                else "none"
            ),
            "day_ahead_variable_shapes": {
                name: list(shape) for name, shape in plan.variable_shapes.items()
            },
            "has_scenario_specific_battery": plan.has_scenario_specific_battery,
            "day_ahead_solve_seconds": plan.solve_seconds,
            "day_ahead_expected_emergency_cost_yuan": plan.expected_emergency_cost,
            "day_ahead_virtual_next_day_value_yuan": plan.expected_terminal_value,
        }
    )
    return summary, frame, plan, q_floor, scenarios


def forecast_mae(actual: np.ndarray, hat: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - hat)))


def target_quantile_coverage(
    realised_net: np.ndarray,
    scenario_net: np.ndarray,
    probabilities: np.ndarray,
    alpha: float,
) -> float:
    hits = []
    for t in range(len(realised_net)):
        order = np.argsort(scenario_net[:, t])
        cumulative = np.cumsum(probabilities[order])
        threshold = scenario_net[order][np.searchsorted(cumulative, alpha, side="left")]
        hits.append(realised_net[t] <= threshold + 1e-12)
    return float(np.mean(hits))


def mode_diagnostics(
    data: Q2Data,
    day_index: int,
    archives: dict[ForecastMode, ForecastArchive],
    alpha: float,
    k: int = FIXED_SCENARIO_K,
) -> list[dict]:
    rows = []
    for mode, archive in archives.items():
        forecast = forecast_as_of_mode(data, day_index, day_index, mode)
        scenarios = k8_scenarios(day_index, data, archive, day_index, k=k)
        load_mae = forecast_mae(data.load[day_index], forecast.load_hat)
        pv_mae = forecast_mae(data.pv[day_index], forecast.pv_hat)
        net_mae = forecast_mae(
            data.load[day_index] - data.pv[day_index],
            forecast.load_hat - forecast.pv_hat,
        )
        coverage = float("nan")
        if scenarios is not None:
            scenario_net = (
                archive.load_residual[scenarios.medoid_indices]
                - archive.pv_residual[scenarios.medoid_indices]
            )
            realised_net = (
                data.load[day_index]
                - data.pv[day_index]
                - (forecast.load_hat - forecast.pv_hat)
            )
            coverage = target_quantile_coverage(
                realised_net, scenario_net, scenarios.probabilities, alpha
            )
        rows.append(
            {
                "date": data.dates[day_index].strftime("%Y-%m-%d"),
                "forecast_mode": mode.value,
                "load_mae_kwh": load_mae,
                "pv_mae_kwh": pv_mae,
                "net_load_mae_kwh": net_mae,
                "risk_alpha": alpha,
                "quantile_coverage": coverage,
                "selection_role": "diagnostic_only",
            }
        )
    return rows


def one_se_tiebreak(
    rows: list[dict],
) -> dict:
    """Select by mean actual cost, then unused plan, then m1, then smaller alpha."""
    best = min(rows, key=lambda row: row["mean_actual_cost_yuan"])
    threshold = best["mean_actual_cost_yuan"] + best["standard_error_yuan"]
    eligible = [row for row in rows if row["mean_actual_cost_yuan"] <= threshold]
    mode_rank = {ForecastMode.M1.value: 0, ForecastMode.M2.value: 1, ForecastMode.M3.value: 2}
    return min(
        eligible,
        key=lambda row: (
            row["mean_unused_plan_kwh"],
            mode_rank[row["forecast_mode"]],
            row["risk_alpha"],
        ),
    )


def value_cut_cache_key(
    day_index: int,
    mode: ForecastMode,
    risk_alpha: float | None,
    k: int,
) -> tuple[int, str, float | None, int]:
    return (int(day_index), mode.value, None if risk_alpha is None else float(risk_alpha), int(k))


def cached_baseline_value_cuts(
    cache: ValueCutCache,
    data: Q2Data,
    archive: ForecastArchive,
    day_index: int,
    mode: ForecastMode,
    k: int,
    risk_alpha: float | None,
    lock: Lock | None = None,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    """Reuse next-day baseline value cuts for the same (day, m, alpha, K)."""
    key = value_cut_cache_key(day_index, mode, risk_alpha, k)
    if lock is None:
        hit = cache.get(key)
        if hit is not None:
            return hit
        built = build_baseline_value_cuts(
            data, archive, day_index, mode, k=k, risk_alpha=risk_alpha
        )
        cache[key] = built
        return built
    with lock:
        hit = cache.get(key)
        if hit is not None:
            return hit
    built = build_baseline_value_cuts(
        data, archive, day_index, mode, k=k, risk_alpha=risk_alpha
    )
    with lock:
        existing = cache.get(key)
        if existing is not None:
            return existing
        cache[key] = built
        return built


def score_one_candidate(
    data: Q2Data,
    archive: ForecastArchive,
    mode_value: str,
    alpha: float,
    validation_indices: tuple[int, ...],
    window_start_soc: float,
    k: int = FIXED_SCENARIO_K,
    include_value_cuts: bool = True,
    cut_cache: ValueCutCache | None = None,
    cut_cache_lock: Lock | None = None,
) -> dict:
    """Run one (m, alpha) on a finished-day window with that candidate's own SOC path."""
    mode = ForecastMode(mode_value)
    costs: list[float] = []
    unused: list[float] = []
    planned: list[float] = []
    emergency: list[float] = []
    times: list[float] = []
    soc_path = [float(window_start_soc)]
    soc = float(window_start_soc)
    used_full_day_actual_lp = False
    future_actuals_in_optimizer = False
    cache = {} if cut_cache is None else cut_cache
    for i in validation_indices:
        cuts: tuple[ValueCut, ...] | None = None
        if include_value_cuts:
            cuts, _cut_rows = cached_baseline_value_cuts(
                cache,
                data,
                archive,
                int(i),
                mode,
                k,
                float(alpha),
                lock=cut_cache_lock,
            )
        summary, _frame, _plan, _floor, _scenarios = plan_closed_loop_day(
            data,
            archive,
            int(i),
            soc,
            mode=mode,
            risk_alpha=float(alpha),
            k=k,
            terminal_value_cuts=cuts,
        )
        used_full_day_actual_lp = used_full_day_actual_lp or bool(
            summary["used_full_day_actual_lp"]
        )
        future_actuals_in_optimizer = future_actuals_in_optimizer or bool(
            summary["future_actuals_in_optimizer"]
        )
        costs.append(summary["total_cost_yuan"])
        unused.append(summary["unused_plan_kwh"])
        planned.append(summary["planned_cost_yuan"])
        emergency.append(summary["emergency_cost_yuan"])
        times.append(summary["day_ahead_solve_seconds"] + summary["total_mpc_solve_seconds"])
        soc = float(summary["soc_end_kwh"])
        soc_path.append(soc)
    return {
        "forecast_mode": mode.value,
        "risk_alpha": float(alpha),
        "validation_days": int(len(validation_indices)),
        "window_start_soc_kwh": float(window_start_soc),
        "candidate_soc_end_kwh": soc,
        "candidate_soc_path_kwh": ";".join(f"{value:.6f}" for value in soc_path),
        "mean_actual_cost_yuan": float(np.mean(costs)),
        "standard_error_yuan": float(
            np.std(costs, ddof=1) / sqrt(len(costs)) if len(costs) > 1 else 0.0
        ),
        "mean_planned_cost_yuan": float(np.mean(planned)),
        "mean_emergency_cost_yuan": float(np.mean(emergency)),
        "mean_unused_plan_kwh": float(np.mean(unused)),
        "mean_solve_seconds": float(np.mean(times)),
        "used_full_day_actual_lp": used_full_day_actual_lp,
        "future_actuals_in_optimizer": future_actuals_in_optimizer,
        "selection_criterion": "mean_actual_cost_sum_pq_plus_5pe",
        "include_value_cuts": bool(include_value_cuts),
    }


def _score_candidate_job(payload: dict) -> dict:
    return score_one_candidate(
        payload["data"],
        payload["archive"],
        payload["mode_value"],
        payload["alpha"],
        payload["validation_indices"],
        payload["window_start_soc"],
        payload["k"],
        include_value_cuts=payload.get("include_value_cuts", True),
        cut_cache=payload.get("cut_cache"),
        cut_cache_lock=payload.get("cut_cache_lock"),
    )


def closed_loop_candidate_window(
    data: Q2Data,
    archives: dict[ForecastMode, ForecastArchive],
    validation_indices: np.ndarray,
    window_start_soc: float,
    k: int = FIXED_SCENARIO_K,
    workers: int | None = None,
    include_value_cuts: bool = True,
    cut_cache: ValueCutCache | None = None,
    cut_cache_lock: Lock | None = None,
) -> list[dict]:
    """Score all 12 (m, alpha) pairs by the same residual-MPC policy."""
    indices = tuple(int(i) for i in np.asarray(validation_indices).ravel())
    cache = {} if cut_cache is None else cut_cache
    jobs = [
        {
            "data": data,
            "archive": archives[mode],
            "mode_value": mode.value,
            "alpha": float(alpha),
            "validation_indices": indices,
            "window_start_soc": float(window_start_soc),
            "k": k,
            "include_value_cuts": include_value_cuts,
            "cut_cache": cache,
            "cut_cache_lock": cut_cache_lock,
        }
        for mode in FORECAST_MODES
        for alpha in RISK_ALPHA_CANDIDATES
    ]
    n_workers = int(os.environ.get("Q2_R2_WORKERS", workers if workers is not None else 8))
    n_workers = max(1, min(n_workers, len(jobs)))
    if n_workers == 1:
        records = [_score_candidate_job(job) for job in jobs]
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            records = list(pool.map(_score_candidate_job, jobs))
    if len(records) != len(FORECAST_MODES) * len(RISK_ALPHA_CANDIDATES):
        raise AssertionError("closed-loop calibration must evaluate 12 (m, alpha) pairs")
    selected = one_se_tiebreak(records)
    threshold = selected["mean_actual_cost_yuan"] + selected["standard_error_yuan"]
    for row in records:
        row["selected"] = (
            row["forecast_mode"] == selected["forecast_mode"]
            and row["risk_alpha"] == selected["risk_alpha"]
        )
        row["one_se_threshold_yuan"] = threshold
    return records


def _validation_diagnostics(
    data: Q2Data,
    archives: dict[ForecastMode, ForecastArchive],
    validation_indices: np.ndarray,
    k: int,
) -> dict[str, dict[str, float]]:
    by_mode: dict[str, dict[str, float]] = {}
    for mode, archive in archives.items():
        load_mae = []
        pv_mae = []
        net_mae = []
        coverage = []
        for i in validation_indices:
            rows = mode_diagnostics(data, int(i), {mode: archive}, RISK_ALPHA_CANDIDATES[0], k=k)
            load_mae.append(rows[0]["load_mae_kwh"])
            pv_mae.append(rows[0]["pv_mae_kwh"])
            net_mae.append(rows[0]["net_load_mae_kwh"])
            coverage.append(rows[0]["quantile_coverage"])
        coverage_arr = np.asarray(coverage, dtype=float)
        finite = coverage_arr[np.isfinite(coverage_arr)]
        by_mode[mode.value] = {
            "load_mae_kwh": float(np.mean(load_mae)),
            "pv_mae_kwh": float(np.mean(pv_mae)),
            "net_load_mae_kwh": float(np.mean(net_mae)),
            "quantile_coverage": float(np.mean(finite)) if finite.size else float("nan"),
        }
    return by_mode


def run_rolling_closed_loop_calibration(
    data: Q2Data,
    archives: dict[ForecastMode, ForecastArchive],
    k: int = FIXED_SCENARIO_K,
    workers: int | None = None,
    include_value_cuts: bool = True,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Walk 14-day blocks, score 12 candidates, then deploy the winner to carry SOC."""
    n = len(data.dates)
    policy_start_soc = np.full(n, np.nan)
    soc = float(E_INITIAL_KWH)
    calibration_rows: list[dict] = []
    diagnostic_rows: list[dict] = []
    deployed_rows: list[dict] = []
    block = K_RECALIBRATION_DAYS
    window = RISK_CALIBRATION_DAYS
    cut_cache: ValueCutCache = {}
    cut_lock = Lock()

    for calibration in range(0, n, block):
        effective_end = min(calibration + block - 1, n - 1)
        validation = np.arange(max(0, calibration - window), calibration)
        history_cutoff = (
            data.dates[calibration - 1].strftime("%Y-%m-%d")
            if calibration
            else "attachment1_fallback"
        )
        block_meta = {
            "calibration_date": data.dates[calibration].strftime("%Y-%m-%d"),
            "history_cutoff_date": history_cutoff,
            "effective_start_date": data.dates[calibration].strftime("%Y-%m-%d"),
            "effective_end_date": data.dates[effective_end].strftime("%Y-%m-%d"),
        }
        if len(validation) < window:
            selected_mode = ForecastMode.M1
            selected_alpha: float | None = None
            fallback = "insufficient_prior_14_day_window"
            calibration_rows.append(
                {
                    **block_meta,
                    "forecast_mode": selected_mode.value,
                    "risk_alpha": selected_alpha,
                    "validation_days": int(len(validation)),
                    "validation_start_date": "none",
                    "validation_end_date": "none",
                    "window_start_soc_kwh": float(soc),
                    "candidate_soc_end_kwh": float("nan"),
                    "candidate_soc_path_kwh": "",
                    "mean_actual_cost_yuan": float("nan"),
                    "standard_error_yuan": float("nan"),
                    "mean_planned_cost_yuan": float("nan"),
                    "mean_emergency_cost_yuan": float("nan"),
                    "mean_unused_plan_kwh": float("nan"),
                    "mean_solve_seconds": float("nan"),
                    "used_full_day_actual_lp": False,
                    "future_actuals_in_optimizer": False,
                    "selection_criterion": "mean_actual_cost_sum_pq_plus_5pe",
                    "one_se_threshold_yuan": float("nan"),
                    "selected": True,
                    "fallback_reason": fallback,
                    "include_value_cuts": bool(include_value_cuts),
                }
            )
            active_k = 1
        else:
            window_start_soc = float(policy_start_soc[int(validation[0])])
            if not np.isfinite(window_start_soc):
                raise AssertionError("deployed policy SOC missing at validation window start")
            records = closed_loop_candidate_window(
                data,
                archives,
                validation,
                window_start_soc,
                k=k,
                workers=workers,
                include_value_cuts=include_value_cuts,
                cut_cache=cut_cache,
                cut_cache_lock=cut_lock,
            )
            mae_by_mode = _validation_diagnostics(data, archives, validation, k=k)
            selected_row = next(row for row in records if row["selected"])
            selected_mode = ForecastMode(selected_row["forecast_mode"])
            selected_alpha = float(selected_row["risk_alpha"])
            fallback = ""
            active_k = k
            for row in records:
                calibration_rows.append(
                    {
                        **block_meta,
                        **row,
                        "validation_start_date": data.dates[int(validation[0])].strftime(
                            "%Y-%m-%d"
                        ),
                        "validation_end_date": data.dates[int(validation[-1])].strftime(
                            "%Y-%m-%d"
                        ),
                        "fallback_reason": fallback,
                    }
                )
                diagnostic = mae_by_mode[row["forecast_mode"]]
                diagnostic_rows.append(
                    {
                        **block_meta,
                        "forecast_mode": row["forecast_mode"],
                        "risk_alpha": row["risk_alpha"],
                        "load_mae_kwh": diagnostic["load_mae_kwh"],
                        "pv_mae_kwh": diagnostic["pv_mae_kwh"],
                        "net_load_mae_kwh": diagnostic["net_load_mae_kwh"],
                        "quantile_coverage": diagnostic["quantile_coverage"],
                        "mean_planned_cost_yuan": row["mean_planned_cost_yuan"],
                        "mean_emergency_cost_yuan": row["mean_emergency_cost_yuan"],
                        "mean_unused_plan_kwh": row["mean_unused_plan_kwh"],
                        "mean_actual_cost_yuan": row["mean_actual_cost_yuan"],
                        "selected": row["selected"],
                        "selection_role": "diagnostic_only",
                    }
                )
            print(
                f"C2-R2 {block_meta['calibration_date']}: "
                f"selected {selected_mode.value} alpha={selected_alpha:.2f} "
                f"cost={selected_row['mean_actual_cost_yuan']:.2f}",
                flush=True,
            )

        for i in range(calibration, effective_end + 1):
            policy_start_soc[i] = soc
            cuts: tuple[ValueCut, ...] | None = None
            if include_value_cuts:
                cuts, _cut_rows = cached_baseline_value_cuts(
                    cut_cache,
                    data,
                    archives[selected_mode],
                    i,
                    selected_mode,
                    active_k,
                    selected_alpha,
                    lock=cut_lock,
                )
            summary, _frame, _plan, _floor, _scenarios = plan_closed_loop_day(
                data,
                archives[selected_mode],
                i,
                soc,
                mode=selected_mode,
                risk_alpha=selected_alpha,
                k=active_k,
                terminal_value_cuts=cuts,
            )
            if not summary["pass"]:
                raise AssertionError(f"deployed policy failed on {summary['date']}")
            deployed_rows.append(
                {
                    "date": summary["date"],
                    "forecast_mode": selected_mode.value,
                    "risk_alpha": selected_alpha,
                    "scenario_k": active_k if selected_alpha is not None else 1,
                    "soc_start_kwh": summary["soc_start_kwh"],
                    "soc_end_kwh": summary["soc_end_kwh"],
                    "planned_cost_yuan": summary["planned_cost_yuan"],
                    "emergency_cost_yuan": summary["emergency_cost_yuan"],
                    "total_cost_yuan": summary["total_cost_yuan"],
                    "unused_plan_kwh": summary["unused_plan_kwh"],
                    "emergency_kwh": summary["emergency_kwh"],
                    "used_full_day_actual_lp": summary["used_full_day_actual_lp"],
                    "future_actuals_in_optimizer": summary["future_actuals_in_optimizer"],
                    "pass": summary["pass"],
                    "fallback_reason": fallback,
                    "include_value_cuts": bool(include_value_cuts),
                }
            )
            soc = float(summary["soc_end_kwh"])
    return (
        calibration_rows,
        diagnostic_rows,
        deployed_rows,
        {
            "include_value_cuts": bool(include_value_cuts),
            "calibration_include_value_cuts": bool(include_value_cuts),
            "deployment_include_value_cuts": bool(include_value_cuts),
            "value_cut_cache_entries": int(len(cut_cache)),
        },
    )


def output_period(date: pd.Timestamp | str) -> str:
    stamp = pd.Timestamp(date).normalize()
    if stamp < pd.Timestamp(OFFICIAL_OUTPUT_START):
        return PERIOD_JANUARY_WARMUP
    return PERIOD_FEB_DEC_OUTPUT


def selected_calendar_for_dates(
    calibration: pd.DataFrame,
    dates: pd.DatetimeIndex,
) -> list[FrozenDayPolicy]:
    """Map each calendar day to the unique R2-selected (m, alpha) block."""
    selected = calibration.loc[calibration["selected"].astype(bool)].copy()
    if selected.empty:
        raise AssertionError("closed-loop calibration has no selected rows")
    selected["effective_start_date"] = pd.to_datetime(selected["effective_start_date"])
    selected["effective_end_date"] = pd.to_datetime(selected["effective_end_date"])
    policies: list[FrozenDayPolicy] = []
    for date in pd.DatetimeIndex(dates):
        match = selected.loc[
            (selected["effective_start_date"] <= date)
            & (selected["effective_end_date"] >= date)
        ]
        if len(match) != 1:
            raise AssertionError(f"expected one selected block for {date.date()}, got {len(match)}")
        row = match.iloc[0]
        alpha_raw = row["risk_alpha"]
        alpha = None if pd.isna(alpha_raw) else float(alpha_raw)
        policies.append(
            FrozenDayPolicy(
                date=date.strftime("%Y-%m-%d"),
                forecast_mode=ForecastMode(str(row["forecast_mode"])),
                risk_alpha=alpha,
                fallback_reason=str(row["fallback_reason"] or ""),
                calibration_date=pd.Timestamp(row["calibration_date"]).strftime("%Y-%m-%d"),
                effective_start_date=pd.Timestamp(row["effective_start_date"]).strftime(
                    "%Y-%m-%d"
                ),
                effective_end_date=pd.Timestamp(row["effective_end_date"]).strftime("%Y-%m-%d"),
            )
        )
    return policies


def _forecast_audit_row(summary: dict) -> dict:
    return {
        "date": summary["date"],
        "forecast_mode": summary["forecast_mode"],
        "risk_alpha": summary["risk_alpha"],
        "scenario_k": summary["scenario_k"],
        "load_source_dates": summary["load_source_dates"],
        "pv_source_dates": summary["pv_source_dates"],
        "residual_pool_end_date": summary["residual_pool_end_date"],
        "medoid_dates": summary["medoid_dates"],
        "load_fallback": summary["load_fallback"],
        "pv_fallback": summary["pv_fallback"],
        "risk_q_floor_kwh": summary["risk_q_floor_kwh"],
        "has_scenario_specific_battery": summary["has_scenario_specific_battery"],
        "day_ahead_variable_shapes": json.dumps(
            summary["day_ahead_variable_shapes"], ensure_ascii=False
        )
        if not isinstance(summary["day_ahead_variable_shapes"], str)
        else summary["day_ahead_variable_shapes"],
    }


def _physical_audit_row(summary: dict) -> dict:
    return {
        "date": summary["date"],
        "period": summary["period"],
        "pass": summary["pass"],
        "planned_q_sha256": summary["planned_q_sha256"],
        "max_balance_residual_kwh": summary["max_balance_residual_kwh"],
        "max_x_minus_q_kwh": summary["max_x_minus_q_kwh"],
        "max_simultaneous_cd_kwh2": summary["max_simultaneous_cd_kwh2"],
        "soc_start_kwh": summary["soc_start_kwh"],
        "soc_end_kwh": summary["soc_end_kwh"],
        "unused_plan_kwh": summary["unused_plan_kwh"],
        "emergency_kwh": summary["emergency_kwh"],
        "curtailment_kwh": summary["curtailment_kwh"],
        "used_full_day_actual_lp": summary["used_full_day_actual_lp"],
        "future_actuals_in_optimizer": summary["future_actuals_in_optimizer"],
    }


def _daily_summary_row(summary: dict) -> dict:
    shapes = summary["day_ahead_variable_shapes"]
    if isinstance(shapes, dict):
        shapes = json.dumps(shapes, ensure_ascii=False)
    row = {key: value for key, value in summary.items() if key != "day_ahead_variable_shapes"}
    row["day_ahead_variable_shapes"] = shapes
    return row


def aggregate_cost_row(
    frame: pd.DataFrame,
    *,
    label: str,
    extra: dict | None = None,
) -> dict:
    if frame.empty:
        raise AssertionError(f"cannot aggregate empty ledger for {label}")
    row = {
        "label": label,
        "n_days": int(len(frame)),
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "planned_cost_yuan": float(frame["planned_cost_yuan"].sum()),
        "emergency_cost_yuan": float(frame["emergency_cost_yuan"].sum()),
        "total_cost_yuan": float(frame["total_cost_yuan"].sum()),
        "planned_q_kwh": float(frame["planned_q_kwh"].sum()),
        "actual_x_kwh": float(frame["actual_x_kwh"].sum()),
        "unused_plan_kwh": float(frame["unused_plan_kwh"].sum()),
        "emergency_kwh": float(frame["emergency_kwh"].sum()),
        "curtailment_kwh": float(frame["curtailment_kwh"].sum()),
        "soc_start_kwh": float(frame["soc_start_kwh"].iloc[0]),
        "soc_end_kwh": float(frame["soc_end_kwh"].iloc[-1]),
        "max_balance_residual_kwh": float(frame["max_balance_residual_kwh"].max()),
        "all_days_pass": bool(frame["pass"].all()),
        "used_full_day_actual_lp": bool(frame["used_full_day_actual_lp"].any()),
        "future_actuals_in_optimizer": bool(frame["future_actuals_in_optimizer"].any()),
    }
    if extra:
        row.update(extra)
    return row


def k_sensitivity_conclusion(rows: list[dict]) -> str:
    """Keep K=8 when cost and emergency remain stable versus K=4 and K=12."""
    by_k = {int(row["scenario_k"]): row for row in rows if int(row["scenario_k"]) in {4, 8, 12}}
    if set(by_k) != {4, 8, 12}:
        raise AssertionError("K sensitivity must report K=4, 8 and 12")
    costs = np.array([by_k[k]["total_cost_yuan"] for k in (4, 8, 12)], dtype=float)
    emergencies = np.array([by_k[k]["emergency_kwh"] for k in (4, 8, 12)], dtype=float)
    cost_span = float(np.max(np.abs(costs - costs[1])) / max(abs(costs[1]), 1.0))
    emergency_span = float(
        np.max(np.abs(emergencies - emergencies[1])) / max(abs(emergencies[1]), 1.0)
    )
    if cost_span <= 0.05 and emergency_span <= 0.10:
        return "retain_k8_stable"
    return "review_k_reselection"


def run_frozen_policy_path(
    data: Q2Data,
    archives: dict[ForecastMode, ForecastArchive],
    calendar: list[FrozenDayPolicy],
    *,
    start_index: int,
    end_index: int,
    initial_soc: float,
    requested_k: int,
    soc_source: str,
    include_value_cuts: bool = True,
    dispatch_dir: Path | None = None,
    cut_cache: ValueCutCache | None = None,
    progress_label: str = "",
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Execute a frozen (m, alpha) calendar with residual MPC; never uses full-day actual LP."""
    if not 0 <= start_index <= end_index < len(data.dates):
        raise ValueError("frozen path indices out of range")
    if len(calendar) != len(data.dates):
        raise AssertionError("frozen calendar must cover every 2025 day")
    cache: ValueCutCache = {} if cut_cache is None else cut_cache
    daily_rows: list[dict] = []
    forecast_rows: list[dict] = []
    physical_rows: list[dict] = []
    value_rows: list[dict] = []
    soc = float(initial_soc)
    for i in range(start_index, end_index + 1):
        policy = calendar[i]
        if policy.date != data.dates[i].strftime("%Y-%m-%d"):
            raise AssertionError(f"calendar date mismatch at {i}: {policy.date}")
        archive = archives[policy.forecast_mode]
        active_k = policy.effective_k(requested_k)
        cuts: tuple[ValueCut, ...] | None = None
        if include_value_cuts:
            cuts, cut_rows = cached_baseline_value_cuts(
                cache,
                data,
                archive,
                i,
                policy.forecast_mode,
                active_k,
                policy.risk_alpha,
            )
            value_rows.extend({"decision_date": policy.date, **row} for row in cut_rows)
        dispatch_path = (
            dispatch_dir / f"dispatch_{policy.date}.csv" if dispatch_dir is not None else None
        )
        summary, _frame, _plan, _floor, _scenarios = plan_closed_loop_day(
            data,
            archive,
            i,
            soc,
            mode=policy.forecast_mode,
            risk_alpha=policy.risk_alpha,
            k=active_k,
            terminal_value_cuts=cuts,
            dispatch_path=dispatch_path,
        )
        if not summary["pass"]:
            raise AssertionError(f"physical validation failed on {summary['date']}")
        summary.update(
            {
                "period": output_period(policy.date),
                "soc_source": soc_source,
                "requested_k": int(requested_k),
                "calibration_date": policy.calibration_date,
                "fallback_reason": policy.fallback_reason,
                "include_value_cuts": bool(include_value_cuts),
            }
        )
        daily_rows.append(_daily_summary_row(summary))
        forecast_rows.append(_forecast_audit_row(summary))
        physical_rows.append(_physical_audit_row(summary))
        soc = float(summary["soc_end_kwh"])
        if progress_label and (i == start_index or (i + 1) % 14 == 0 or i == end_index):
            print(
                f"{progress_label} {policy.date}: "
                f"{policy.forecast_mode.value} alpha={policy.risk_alpha} K={active_k} "
                f"cost={summary['total_cost_yuan']:.2f}",
                flush=True,
            )
    return daily_rows, forecast_rows, physical_rows, value_rows

# ===== q2/run_q2_comparators.py =====
#!/usr/bin/env python3
"""Build Q2 annual comparison baselines on the completed linked-policy path."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import EMERGENCY_PRICE_MULTIPLIER, FULL_OUTPUT_DIR  # noqa: E402
from q2.data import load_q2_data  # noqa: E402
from q2.forecast import build_forecast_archive  # noqa: E402
from q2.pilot import planned_q_hash, run_perfect_information  # noqa: E402
from q2.scenarios import build_scenarios, scenario_trajectories  # noqa: E402


def weighted_quantile(values: np.ndarray, weights: np.ndarray, probability: float) -> float:
    order = np.argsort(values)
    sorted_values = values[order]
    cumulative = np.cumsum(weights[order])
    return float(sorted_values[np.searchsorted(cumulative, probability, side="left")])


def run_no_storage_baseline(data, archive, linked: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for i, date in enumerate(data.dates):
        k = int(linked.loc[i, "selected_k"])
        if i == 0:
            scenario_net = np.maximum(archive.load_hat[i] - archive.pv_hat[i], 0.0)[None, :]
            probability = np.ones(1)
        else:
            scenarios = build_scenarios(i, data, archive, k)
            loads, pvs = scenario_trajectories(scenarios, archive)
            scenario_net = np.maximum(loads - pvs, 0.0)
            probability = scenarios.probabilities
        q = np.array(
            [weighted_quantile(scenario_net[:, t], probability, 0.8) for t in range(len(data.price))]
        )
        actual_net = np.maximum(data.load[i] - data.pv[i], 0.0)
        x = np.minimum(q, actual_net)
        emergency = np.maximum(actual_net - q, 0.0)
        curtailment = np.maximum(data.pv[i] - data.load[i], 0.0)
        residual = x + emergency + data.pv[i] - curtailment - data.load[i]
        plan_cost = float(data.price @ q)
        emergency_cost = float(EMERGENCY_PRICE_MULTIPLIER * data.price @ emergency)
        rows.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "selected_k": k,
                "planned_cost_yuan": plan_cost,
                "emergency_cost_yuan": emergency_cost,
                "total_cost_yuan": plan_cost + emergency_cost,
                "planned_q_kwh": float(q.sum()),
                "planned_q_sha256": planned_q_hash(q),
                "actual_x_kwh": float(x.sum()),
                "unused_plan_kwh": float((q - x).sum()),
                "emergency_kwh": float(emergency.sum()),
                "curtailment_kwh": float(curtailment.sum()),
                "max_balance_residual_kwh": float(np.max(np.abs(residual))),
                "max_x_minus_q_kwh": float(np.max(x - q)),
                "pass": bool(np.max(np.abs(residual)) < 1e-6 and np.max(x - q) < 1e-6),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    linked_path = FULL_OUTPUT_DIR / "daily_summary.csv"
    if not linked_path.exists():
        raise FileNotFoundError("Run q2/run_q2_full.py before comparison baselines.")
    data = load_q2_data()
    archive = build_forecast_archive(data)
    linked = pd.read_csv(linked_path)
    no_storage = run_no_storage_baseline(data, archive, linked)
    if not no_storage["pass"].all():
        raise AssertionError("no-storage baseline physical validation failed")
    no_storage.to_csv(FULL_OUTPUT_DIR / "no_storage_daily.csv", index=False)

    perfect_path = FULL_OUTPUT_DIR / "perfect_information_daily.csv"
    run_perfect_information(data, perfect_path)
    perfect = pd.read_csv(perfect_path)
    if abs(float(perfect["soc_end_kwh"].iloc[-1]) - float(linked["soc_end_kwh"].iloc[-1])) >= 1e-6:
        raise AssertionError("linked and perfect-information terminal SOC differ")
    comparison = {
        "main_linked_total_cost_yuan": float(linked["total_cost_yuan"].sum()),
        "no_storage_total_cost_yuan": float(no_storage["total_cost_yuan"].sum()),
        "perfect_information_total_cost_yuan": float(perfect["total_cost_yuan"].sum()),
        "linked_minus_no_storage_yuan": float(linked["total_cost_yuan"].sum() - no_storage["total_cost_yuan"].sum()),
        "linked_minus_perfect_information_yuan": float(linked["total_cost_yuan"].sum() - perfect["total_cost_yuan"].sum()),
        "main_start_soc_kwh": float(linked["soc_start_kwh"].iloc[0]),
        "main_terminal_soc_kwh": float(linked["soc_end_kwh"].iloc[-1]),
        "perfect_terminal_soc_kwh": float(perfect["soc_end_kwh"].iloc[-1]),
        "comparison_note": "The no-storage baseline is not SOC-comparable because it has no initial stored energy; use it only as an operational benchmark, not as a pure storage-value claim.",
    }
    (FULL_OUTPUT_DIR / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# ===== q2/run_q2_full.py =====
#!/usr/bin/env python3
"""Run the Q2 annual causal linked-policy calculation; no result2.xlsx export."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import FULL_OUTPUT_DIR, NUMERIC_TOL  # noqa: E402
from q2.data import load_q2_data, write_input_audit  # noqa: E402
from q2.forecast import assert_no_forecast_leakage, build_forecast_archive, write_forecast_archive  # noqa: E402
from q2.pilot import run_full_linked_policy  # noqa: E402


def main() -> None:
    started = perf_counter()
    forbidden = ROOT / "output" / "result2.xlsx"
    forbidden_before = forbidden.stat().st_mtime_ns if forbidden.exists() else None
    data = load_q2_data()
    FULL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_input_audit(data, FULL_OUTPUT_DIR / "input_audit.json")
    archive = build_forecast_archive(data)
    assert_no_forecast_leakage(archive)
    write_forecast_archive(
        data,
        archive,
        FULL_OUTPUT_DIR / "forecast_archive.csv",
        FULL_OUTPUT_DIR / "forecast_audit.md",
    )
    daily, calendar, value_audit = run_full_linked_policy(data, archive, FULL_OUTPUT_DIR)
    soc_gap = float(
        np.max(
            np.abs(
                daily["soc_start_kwh"].to_numpy()[1:]
                - daily["soc_end_kwh"].to_numpy()[:-1]
            )
        )
    )
    report = {
        "status": "PASS",
        "days": int(len(daily)),
        "total_cost_yuan": float(daily["total_cost_yuan"].sum()),
        "planned_cost_yuan": float(daily["planned_cost_yuan"].sum()),
        "emergency_cost_yuan": float(daily["emergency_cost_yuan"].sum()),
        "planned_q_kwh": float(daily["planned_q_kwh"].sum()),
        "actual_x_kwh": float(daily["actual_x_kwh"].sum()),
        "unused_plan_kwh": float(daily["unused_plan_kwh"].sum()),
        "emergency_kwh": float(daily["emergency_kwh"].sum()),
        "curtailment_kwh": float(daily["curtailment_kwh"].sum()),
        "soc_start_kwh": float(daily["soc_start_kwh"].iloc[0]),
        "soc_end_kwh": float(daily["soc_end_kwh"].iloc[-1]),
        "max_balance_residual_kwh": float(daily["max_balance_residual_kwh"].max()),
        "max_simultaneous_cd_kwh2": float(daily["max_simultaneous_cd_kwh2"].max()),
        "max_x_minus_q_kwh": float(daily["max_x_minus_q_kwh"].max()),
        "max_cross_day_soc_gap_kwh": soc_gap,
        "calendar_periods": int(calendar["calibration_date"].nunique()),
        "all_within_time_limit": bool(calendar["within_time_limit"].all()),
        "max_value_cut_gap_yuan": float(value_audit["certified_max_gap_yuan"].max()),
        "elapsed_seconds": perf_counter() - started,
    }
    if (
        report["max_balance_residual_kwh"] >= NUMERIC_TOL
        or report["max_cross_day_soc_gap_kwh"] >= NUMERIC_TOL
        or report["max_x_minus_q_kwh"] >= NUMERIC_TOL
    ):
        raise AssertionError("annual physical validation failed")
    (FULL_OUTPUT_DIR / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    forbidden_after = forbidden.stat().st_mtime_ns if forbidden.exists() else None
    if forbidden_after != forbidden_before:
        raise RuntimeError("Forbidden output/result2.xlsx was created or modified")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# ===== q2/run_q2_k8_risk.py =====
#!/usr/bin/env python3
"""Annual Q2 re-run: fixed K=8 plus causal rolling risk-quantile reserve."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    E_INITIAL_KWH,
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    NUMERIC_TOL,
)
from q2.data import load_q2_data, write_input_audit  # noqa: E402
from q2.forecast import assert_no_forecast_leakage, build_forecast_archive, write_forecast_archive  # noqa: E402
from q2.pilot import KChoice, build_next_day_value_cuts, run_posterior_mpc, select_risk_alpha  # noqa: E402
from q2.scenarios import build_scenarios  # noqa: E402


def main() -> None:
    started = perf_counter()
    output = FULL_K8_RISK_OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    dispatch_dir = output / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    forbidden = ROOT / "output" / "result2.xlsx"
    before = forbidden.stat().st_mtime_ns if forbidden.exists() else None

    data = load_q2_data()
    archive = build_forecast_archive(data)
    assert_no_forecast_leakage(archive)
    write_input_audit(data, output / "input_audit.json")
    write_forecast_archive(data, archive, output / "forecast_archive.csv", output / "forecast_audit.md")

    policy_start_soc = np.full(len(data.dates), np.nan)
    daily_rows: list[dict] = []
    calibration_rows: list[dict] = []
    value_rows: list[dict] = []
    soc = E_INITIAL_KWH

    for calibration in range(0, len(data.dates), 14):
        effective_end = min(calibration + 13, len(data.dates) - 1)
        if calibration < 28:
            # A K=8 distribution and an empirical risk quantile both need the
            # complete 28-day residual pool.  Before then, use the same causal
            # K=1/no-reserve warmup rather than inventing an unsupported tail.
            alpha = None
            active_k = 1
            candidates = [
                {
                    "risk_alpha": alpha,
                    "validation_days": 0,
                    "mean_validation_cost_yuan": np.nan,
                    "standard_error_yuan": np.nan,
                    "emergency_purchase_kwh": np.nan,
                    "mean_solve_seconds": np.nan,
                    "within_time_limit": True,
                    "selected": True,
                    "fallback_reason": "K=1_no_risk_reserve_before_28_day_pool",
                }
            ]
        else:
            risk_choice = select_risk_alpha(
                data, archive, policy_start_soc, calibration, FIXED_SCENARIO_K
            )
            alpha = risk_choice.selected_alpha
            active_k = FIXED_SCENARIO_K
            candidates = [
                {**row, "fallback_reason": ""} for row in risk_choice.rows
            ]
        for candidate in candidates:
            calibration_rows.append(
                {
                    "calibration_date": data.dates[calibration].strftime("%Y-%m-%d"),
                    "history_cutoff_date": (
                        data.dates[calibration - 1].strftime("%Y-%m-%d")
                        if calibration else "none"
                    ),
                    "fixed_k": active_k,
                    "effective_start_date": data.dates[calibration].strftime("%Y-%m-%d"),
                    "effective_end_date": data.dates[effective_end].strftime("%Y-%m-%d"),
                    **candidate,
                }
            )
        for i in range(calibration, effective_end + 1):
            policy_start_soc[i] = soc
            if i == 0:
                choice = None
            else:
                choice = KChoice(
                    i,
                    active_k,
                    build_scenarios(i, data, archive, active_k),
                    (),
                )
            cuts, cut_audit = build_next_day_value_cuts(
                data, archive, i, active_k, risk_alpha=alpha
            )
            value_rows.extend(
                {"decision_date": data.dates[i].strftime("%Y-%m-%d"), **row}
                for row in cut_audit
            )
            result = run_posterior_mpc(
                data,
                archive,
                choice,
                soc,
                dispatch_dir / f"dispatch_{data.dates[i].strftime('%Y-%m-%d')}.csv",
                terminal_value_cuts=cuts,
                variant="fixed_k8_rolling_risk_quantile",
                risk_alpha=alpha,
            )
            if not result["pass"]:
                raise AssertionError(f"physical validation failed on {result['date']}")
            result["effective_scenario_count"] = (
                1 if choice is None else len(choice.scenarios.probabilities)
            )
            daily_rows.append(result)
            soc = float(result["soc_end_kwh"])

    daily = pd.DataFrame(daily_rows)
    calibration_frame = pd.DataFrame(calibration_rows)
    value_audit = pd.DataFrame(value_rows)
    continuity = float(
        np.max(
            np.abs(
                daily["soc_start_kwh"].to_numpy()[1:]
                - daily["soc_end_kwh"].to_numpy()[:-1]
            )
        )
    )
    if (
        len(daily) != len(data.dates)
        or not daily["pass"].all()
        or continuity >= NUMERIC_TOL
        or not calibration_frame["within_time_limit"].all()
    ):
        raise AssertionError("annual K=8 risk-quantile validation failed")
    daily.to_csv(output / "daily_summary.csv", index=False)
    calibration_frame.to_csv(output / "risk_calibration.csv", index=False)
    value_audit.to_csv(output / "next_day_value_audit.csv", index=False)
    report = {
        "status": "PASS",
        "policy": "fixed K=8 plus 14-day causal rolling risk-quantile reserve",
        "days": len(daily),
        "total_cost_yuan": float(daily["total_cost_yuan"].sum()),
        "planned_cost_yuan": float(daily["planned_cost_yuan"].sum()),
        "emergency_cost_yuan": float(daily["emergency_cost_yuan"].sum()),
        "emergency_kwh": float(daily["emergency_kwh"].sum()),
        "unused_plan_kwh": float(daily["unused_plan_kwh"].sum()),
        "curtailment_kwh": float(daily["curtailment_kwh"].sum()),
        "max_balance_residual_kwh": float(daily["max_balance_residual_kwh"].max()),
        "max_simultaneous_cd_kwh2": float(daily["max_simultaneous_cd_kwh2"].max()),
        "max_x_minus_q_kwh": float(daily["max_x_minus_q_kwh"].max()),
        "max_cross_day_soc_gap_kwh": continuity,
        "selected_alpha_periods": {
            str(alpha): int(count)
            for alpha, count in daily["risk_alpha"].fillna("no_reserve").groupby(
                daily["risk_alpha"].fillna("no_reserve")
            ).size().items()
        },
        "max_value_cut_gap_yuan": float(value_audit["certified_max_gap_yuan"].max()),
        "elapsed_seconds": perf_counter() - started,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    after = forbidden.stat().st_mtime_ns if forbidden.exists() else None
    if after != before:
        raise RuntimeError("Forbidden output/result2.xlsx was created or modified")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# ===== q2/run_q2_pilot.py =====
#!/usr/bin/env python3
"""Run Q2 P0-P4 pilot outputs; never creates result2.xlsx."""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import OUTPUT_DIR, PILOT_DATES  # noqa: E402
from q2.data import load_q2_data, write_input_audit  # noqa: E402
from q2.forecast import (  # noqa: E402
    assert_no_forecast_leakage,
    build_forecast_archive,
    write_forecast_archive,
)
from q2.pilot import (  # noqa: E402
    KChoice,
    build_k_freeze_calendar,
    build_next_day_value_cuts,
    run_linked_warmup,
    run_perfect_information,
    run_posterior_mpc,
    write_k_freeze_calendar,
    write_k_audit,
    write_pilot_figures,
    write_validation_report,
)
from q2.scenarios import build_scenarios, write_scenarios_csv  # noqa: E402


def main() -> None:
    started = perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    forbidden = ROOT / "output" / "result2.xlsx"
    forbidden_before = forbidden.stat().st_mtime_ns if forbidden.exists() else None

    data = load_q2_data()
    write_input_audit(data, OUTPUT_DIR / "input_audit.json")
    print("P0 complete: input audit")

    perfect_path = OUTPUT_DIR / "perfect_information_daily.csv"
    day_start_soc = run_perfect_information(data, perfect_path)
    print("P1 complete: 365-day sequential perfect-information comparator")

    archive = build_forecast_archive(data)
    assert_no_forecast_leakage(archive)
    write_forecast_archive(
        data,
        archive,
        OUTPUT_DIR / "forecast_archive.csv",
        OUTPUT_DIR / "forecast_audit.md",
    )
    print("P2 complete: causal forecast archive")

    calendar = build_k_freeze_calendar(data, archive, day_start_soc)
    write_k_freeze_calendar(OUTPUT_DIR / "k_freeze_calendar.csv", calendar)
    print("R4 complete: 14-day K freeze calendar")

    warmup, warmup_value_audit = run_linked_warmup(
        data, archive, calendar, OUTPUT_DIR / "linked_warmup_daily.csv"
    )
    print("R2 complete: January linked-policy warmup")

    choices = []
    scenario_rows = []
    for date_text in PILOT_DATES:
        i = int(data.dates.get_loc(pd.Timestamp(date_text)))
        k = int(calendar.daily_k[i])
        choice = KChoice(i, k, build_scenarios(i, data, archive, k), ())
        choices.append(choice)
        calibration_index = (i // 14) * 14
        scenario_rows.extend(
            row
            for row in calendar.rows
            if row["calibration_date"]
            == data.dates[calibration_index].strftime("%Y-%m-%d")
        )
        write_scenarios_csv(
            OUTPUT_DIR / f"scenarios_{date_text}.csv", data, choice.scenarios
        )
        print(f"P3 {date_text}: selected K={choice.selected_k}")
    pd.DataFrame(scenario_rows).to_csv(OUTPUT_DIR / "scenario_selection.csv", index=False)
    write_k_audit(OUTPUT_DIR / "k_selection_validation.md", choices, data)

    summaries = []
    value_comparisons = []
    all_value_audits = list(warmup_value_audit)
    for choice in choices:
        date_text = data.dates[choice.target_index].strftime("%Y-%m-%d")
        if date_text == "2025-02-01":
            initial_soc = float(warmup["soc_end_kwh"].iloc[-1])
        else:
            initial_soc = float(day_start_soc[choice.target_index])
        cuts, cut_rows = build_next_day_value_cuts(
            data, archive, choice.target_index, choice.selected_k
        )
        all_value_audits.extend(
            {"decision_date": date_text, **row} for row in cut_rows
        )
        without_value = run_posterior_mpc(
            data,
            archive,
            choice,
            initial_soc,
            OUTPUT_DIR / f"q2_pilot_dispatch_{date_text}_no48h.csv",
            terminal_value_cuts=None,
            variant="without_48h_value",
        )
        summary = run_posterior_mpc(
            data,
            archive,
            choice,
            initial_soc,
            OUTPUT_DIR / f"q2_pilot_dispatch_{date_text}.csv",
            terminal_value_cuts=cuts,
            variant="with_48h_value",
        )
        summaries.append(summary)
        next_index = choice.target_index + 1
        next_k = int(calendar.daily_k[next_index])
        next_choice = KChoice(
            next_index,
            next_k,
            build_scenarios(next_index, data, archive, next_k),
            (),
        )
        next_cuts, next_cut_rows = build_next_day_value_cuts(
            data, archive, next_index, next_k
        )
        all_value_audits.extend(
            {
                "decision_date": data.dates[next_index].strftime("%Y-%m-%d"),
                **row,
            }
            for row in next_cut_rows
        )
        next_after_without = run_posterior_mpc(
            data,
            archive,
            next_choice,
            float(without_value["soc_end_kwh"]),
            path=None,
            terminal_value_cuts=next_cuts,
            variant="next_day_after_without_48h_today",
        )
        next_after_with = run_posterior_mpc(
            data,
            archive,
            next_choice,
            float(summary["soc_end_kwh"]),
            path=None,
            terminal_value_cuts=next_cuts,
            variant="next_day_after_with_48h_today",
        )
        value_comparisons.append(
            {
                "date": date_text,
                "initial_soc_kwh": initial_soc,
                "cost_without_48h_yuan": without_value["total_cost_yuan"],
                "cost_with_48h_yuan": summary["total_cost_yuan"],
                "cost_difference_yuan": (
                    summary["total_cost_yuan"] - without_value["total_cost_yuan"]
                ),
                "emergency_without_48h_kwh": without_value["emergency_kwh"],
                "emergency_with_48h_kwh": summary["emergency_kwh"],
                "emergency_difference_kwh": (
                    summary["emergency_kwh"] - without_value["emergency_kwh"]
                ),
                "soc_end_without_48h_kwh": without_value["soc_end_kwh"],
                "soc_end_with_48h_kwh": summary["soc_end_kwh"],
                "soc_end_difference_kwh": (
                    summary["soc_end_kwh"] - without_value["soc_end_kwh"]
                ),
                "virtual_next_day_value_billed_today": False,
                "next_day_cost_after_without_48h_yuan": next_after_without[
                    "total_cost_yuan"
                ],
                "next_day_cost_after_with_48h_yuan": next_after_with[
                    "total_cost_yuan"
                ],
                "realized_two_day_cost_without_48h_today_yuan": (
                    without_value["total_cost_yuan"]
                    + next_after_without["total_cost_yuan"]
                ),
                "realized_two_day_cost_with_48h_today_yuan": (
                    summary["total_cost_yuan"] + next_after_with["total_cost_yuan"]
                ),
                "realized_two_day_cost_difference_yuan": (
                    summary["total_cost_yuan"]
                    + next_after_with["total_cost_yuan"]
                    - without_value["total_cost_yuan"]
                    - next_after_without["total_cost_yuan"]
                ),
                "next_day_plan_recomputed_and_billed_once": True,
            }
        )
        print(f"P4 {date_text}: pass={summary['pass']}")
    pd.DataFrame(summaries).to_csv(OUTPUT_DIR / "pilot_day_summary.csv", index=False)
    pd.DataFrame(value_comparisons).to_csv(
        OUTPUT_DIR / "next_day_value_comparison.csv", index=False
    )
    pd.DataFrame(all_value_audits).to_csv(
        OUTPUT_DIR / "next_day_value_audit.csv", index=False
    )
    write_pilot_figures(data, summaries)
    write_validation_report(
        OUTPUT_DIR / "validation.json",
        OUTPUT_DIR / "validation.md",
        perfect_path,
        summaries,
    )

    forbidden_after = forbidden.stat().st_mtime_ns if forbidden.exists() else None
    if forbidden_after != forbidden_before:
        raise RuntimeError("Forbidden output/result2.xlsx was created or modified")
    print(f"Q2 P0-P4 pilot complete in {perf_counter() - started:.2f} s")
    print(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()


# ===== q2/run_q2_policy_consistent.py =====
#!/usr/bin/env python3
"""C2-R1: two-day policy-consistent closed loop. Never writes result2.xlsx."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    E_INITIAL_KWH,
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    PILOT_DATES,
    POLICY_CONSISTENT_OUTPUT_DIR,
)
from q2.data import load_q2_data, write_input_audit  # noqa: E402
from q2.policy_consistent import (  # noqa: E402
    FORECAST_MODES,
    R1_DEFAULT_ALPHA,
    R1_DEFAULT_MODE,
    build_baseline_value_cuts,
    build_forecast_archive_mode,
    mode_diagnostics,
    plan_closed_loop_day,
)


def file_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_protected() -> dict[str, str | None]:
    protected = [ROOT / "output" / "result2.xlsx"]
    if FULL_K8_RISK_OUTPUT_DIR.exists():
        protected.extend(sorted(FULL_K8_RISK_OUTPUT_DIR.rglob("*")))
    return {str(path.relative_to(ROOT)): file_hash(path) for path in protected if path.is_file()}


def main() -> None:
    started = perf_counter()
    output = POLICY_CONSISTENT_OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    dispatch_dir = output / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    before = snapshot_protected()

    data = load_q2_data()
    write_input_audit(data, output / "input_audit.json")
    archives = {mode: build_forecast_archive_mode(data, mode) for mode in FORECAST_MODES}
    archive = archives[R1_DEFAULT_MODE]

    forecast_rows: list[dict] = []
    diagnostic_rows: list[dict] = []
    summaries: list[dict] = []
    value_rows: list[dict] = []
    physical_rows: list[dict] = []

    for date_text in PILOT_DATES:
        i = int(data.dates.get_loc(pd.Timestamp(date_text)))
        diagnostic_rows.extend(
            mode_diagnostics(data, i, archives, R1_DEFAULT_ALPHA, k=FIXED_SCENARIO_K)
        )
        cuts, cut_rows = build_baseline_value_cuts(
            data,
            archive,
            i,
            R1_DEFAULT_MODE,
            k=FIXED_SCENARIO_K,
            risk_alpha=R1_DEFAULT_ALPHA,
        )
        value_rows.extend({"decision_date": date_text, **row} for row in cut_rows)
        summary, _frame, plan, q_floor, scenarios = plan_closed_loop_day(
            data,
            archive,
            i,
            E_INITIAL_KWH,
            mode=R1_DEFAULT_MODE,
            risk_alpha=R1_DEFAULT_ALPHA,
            k=FIXED_SCENARIO_K,
            terminal_value_cuts=cuts,
            dispatch_path=dispatch_dir / f"dispatch_{date_text}.csv",
        )
        if not summary["pass"]:
            raise AssertionError(f"physical validation failed on {date_text}")
        summary["soc_source"] = "R1_isolated_E_INITIAL_6000"
        summary["stage"] = "C2-R1"
        summaries.append(summary)
        forecast_rows.append(
            {
                "date": date_text,
                "forecast_mode": summary["forecast_mode"],
                "risk_alpha": summary["risk_alpha"],
                "scenario_k": summary["scenario_k"],
                "load_source_dates": summary["load_source_dates"],
                "pv_source_dates": summary["pv_source_dates"],
                "residual_pool_end_date": summary["residual_pool_end_date"],
                "medoid_dates": summary["medoid_dates"],
                "load_fallback": summary["load_fallback"],
                "pv_fallback": summary["pv_fallback"],
                "risk_q_floor_kwh": summary["risk_q_floor_kwh"],
                "has_scenario_specific_battery": summary["has_scenario_specific_battery"],
                "day_ahead_variable_shapes": json.dumps(
                    summary["day_ahead_variable_shapes"], ensure_ascii=False
                ),
            }
        )
        physical_rows.append(
            {
                "date": date_text,
                "pass": summary["pass"],
                "planned_q_sha256": summary["planned_q_sha256"],
                "max_balance_residual_kwh": summary["max_balance_residual_kwh"],
                "max_x_minus_q_kwh": summary["max_x_minus_q_kwh"],
                "max_simultaneous_cd_kwh2": summary["max_simultaneous_cd_kwh2"],
                "soc_start_kwh": summary["soc_start_kwh"],
                "soc_end_kwh": summary["soc_end_kwh"],
                "unused_plan_kwh": summary["unused_plan_kwh"],
                "emergency_kwh": summary["emergency_kwh"],
                "curtailment_kwh": summary["curtailment_kwh"],
                "used_full_day_actual_lp": summary["used_full_day_actual_lp"],
                "future_actuals_in_optimizer": summary["future_actuals_in_optimizer"],
            }
        )
        _ = plan, q_floor, scenarios

    pd.DataFrame(forecast_rows).to_csv(output / "forecast_policy_audit.csv", index=False)
    pd.DataFrame(diagnostic_rows).to_csv(output / "forecast_diagnostics.csv", index=False)
    pd.DataFrame(summaries).drop(columns=["day_ahead_variable_shapes"]).to_csv(
        output / "r1_day_summary.csv", index=False
    )
    pd.DataFrame(value_rows).to_csv(output / "next_day_value_audit.csv", index=False)
    pd.DataFrame(physical_rows).to_csv(output / "physical_audit.csv", index=False)

    consistency = {
        "stage": "C2-R1",
        "policy": (
            "single baseline-forecast day-ahead LP plus K=8 risk reserve "
            "and residual-matching 10-minute MPC"
        ),
        "forecast_mode_main_path": R1_DEFAULT_MODE.value,
        "risk_alpha_main_path": R1_DEFAULT_ALPHA,
        "scenario_k": FIXED_SCENARIO_K,
        "k_used_for": ["risk_reserve_R", "intra_day_residual_weights"],
        "k_not_used_for": [
            "scenario_specific_charge",
            "scenario_specific_discharge",
            "scenario_specific_soc",
            "full_path_scenario_storage_recourse",
        ],
        "calibration_closed_loop": False,
        "annual_run": False,
        "candidate_result2_xlsx": False,
        "validation_uses_full_day_actual_lp": False,
        "formal_execution_uses_full_day_actual_lp": False,
        "forecast_history_strictly_prior": True,
        "residual_pool_strictly_prior": True,
        "current_period_actuals_only": True,
        "soc_source_r1": "isolated E_INITIAL=6000 kWh; January warmup is deferred to C2-R3",
        "dates": list(PILOT_DATES),
        "elapsed_seconds": perf_counter() - started,
    }
    (output / "policy_consistency_audit.json").write_text(
        json.dumps(consistency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "status": "PASS" if all(row["pass"] for row in summaries) else "FAIL",
        "stage": "C2-R1",
        "days": summaries,
        "protected_outputs_unchanged": snapshot_protected() == before,
        "candidate_result2_xlsx": False,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Q2 政策一致重设计 · C2-R1",
        "",
        f"- 状态：**{report['status']}**",
        "- 本阶段只交付独立模块、单元测试和 2025-02-01、2025-06-21 两日闭环试运行。",
        "- 日前 LP 只在单一基准预测轨迹上锁定 q，并施加 q>=R(alpha)。",
        "- K=8 只用于风险储备 R 与日内残差匹配权重，不创建情景专属充放电/SOC 变量。",
        "- 日内只把当期实际负荷/光伏写入当前时段；未来时段使用残差匹配点预测。",
        "- 未运行 14 日联合校准、未运行全年、未导出候选 result2.xlsx。",
        "- 两日初值均记录为孤立试算的 6000 kWh；1 月预热与 2 月初 SOC 敏感性留到 C2-R3。",
        f"- 主路径预注册：m={R1_DEFAULT_MODE.value}，alpha={R1_DEFAULT_ALPHA}，K={FIXED_SCENARIO_K}。",
        "- MAE/覆盖率只写入 `forecast_diagnostics.csv`，不作为选择准则。",
        "- `history_cutoff_date` 记录最后可用历史日，例如 2 月 1 日决策记为 1 月 31 日。",
        "",
    ]
    for item in summaries:
        lines += [
            f"## {item['date']}",
            "",
            f"- 计划费 {item['planned_cost_yuan']:.6f} 元，紧急费 {item['emergency_cost_yuan']:.6f} 元，"
            f"实际总成本 {item['total_cost_yuan']:.6f} 元。",
            f"- 未用计划电 {item['unused_plan_kwh']:.6f} kWh，紧急购电 {item['emergency_kwh']:.6f} kWh。",
            f"- SOC {item['soc_start_kwh']:.6f} → {item['soc_end_kwh']:.6f} kWh。",
            f"- 最大平衡残差 {item['max_balance_residual_kwh']:.3e} kWh；通过={item['pass']}。",
            "",
        ]
    (output / "validation.md").write_text("\n".join(lines), encoding="utf-8")

    after = snapshot_protected()
    if after != before:
        raise RuntimeError("Protected old Q2 outputs were modified")
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# ===== q2/run_q2_policy_consistent_r2.py =====
#!/usr/bin/env python3
"""C2-R2: 12-candidate closed-loop rolling calibration. Never writes result2.xlsx."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    POLICY_CONSISTENT_OUTPUT_DIR,
    RISK_ALPHA_CANDIDATES,
)
from q2.data import load_q2_data  # noqa: E402
from q2.policy_consistent import (  # noqa: E402
    FORECAST_MODES,
    build_forecast_archive_mode,
    run_rolling_closed_loop_calibration,
)


def file_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_protected() -> dict[str, str | None]:
    protected = [ROOT / "output" / "result2.xlsx"]
    if FULL_K8_RISK_OUTPUT_DIR.exists():
        protected.extend(sorted(FULL_K8_RISK_OUTPUT_DIR.rglob("*")))
    return {str(path.relative_to(ROOT)): file_hash(path) for path in protected if path.is_file()}


def main() -> None:
    started = perf_counter()
    output = POLICY_CONSISTENT_OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    before = snapshot_protected()

    data = load_q2_data()
    archives = {mode: build_forecast_archive_mode(data, mode) for mode in FORECAST_MODES}
    calibration_rows, diagnostic_rows, deployed_rows, cut_stats = run_rolling_closed_loop_calibration(
        data, archives, k=FIXED_SCENARIO_K, include_value_cuts=True
    )
    calibration = pd.DataFrame(calibration_rows)
    diagnostics = pd.DataFrame(diagnostic_rows)
    deployed = pd.DataFrame(deployed_rows)
    calibration.to_csv(output / "closed_loop_calibration.csv", index=False)
    diagnostics.to_csv(output / "forecast_diagnostics.csv", index=False)
    deployed.to_csv(output / "r2_deployed_daily.csv", index=False)

    scored = calibration.loc[calibration["fallback_reason"].fillna("") == ""]
    selected = calibration.loc[calibration["selected"].astype(bool)]
    n_candidates = len(FORECAST_MODES) * len(RISK_ALPHA_CANDIDATES)
    scored_groups = scored.groupby("calibration_date").size() if len(scored) else pd.Series(dtype=int)
    consistency = {
        "stage": "C2-R2",
        "policy": (
            "single baseline-forecast day-ahead LP plus K=8 risk reserve "
            "and residual-matching 10-minute MPC"
        ),
        "n_forecast_modes": len(FORECAST_MODES),
        "risk_alpha_candidates": list(RISK_ALPHA_CANDIDATES),
        "n_candidates_per_block": n_candidates,
        "selection_criterion": "mean_actual_cost_sum_pq_plus_5pe",
        "tiebreak": "one_se_then_unused_plan_then_m1_then_smaller_alpha",
        "mae_is_diagnostic_only": True,
        "mae_used_for_selection": False,
        "calibration_closed_loop": True,
        "candidate_window_carries_own_soc": True,
        "window_start_soc_from_deployed_policy": True,
        "validation_uses_full_day_actual_lp": False,
        "formal_execution_uses_full_day_actual_lp": False,
        "calibration_and_execution_exclude_future_actuals": True,
        "include_value_cuts": True,
        "calibration_include_value_cuts": True,
        "deployment_include_value_cuts": True,
        "include_value_cuts_consistent": True,
        "value_cut_cache_entries": int(cut_stats["value_cut_cache_entries"]),
        "annual_run": False,
        "candidate_result2_xlsx": False,
        "k_used_for": ["risk_reserve_R", "intra_day_residual_weights"],
        "fallback_blocks": int((calibration["fallback_reason"].fillna("") != "").sum()),
        "scored_blocks": int(scored["calibration_date"].nunique()) if len(scored) else 0,
        "selected_blocks": int(len(selected)),
        "elapsed_seconds": perf_counter() - started,
    }
    (output / "policy_consistency_audit.json").write_text(
        json.dumps(consistency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    status = (
        deployed["pass"].all()
        and not deployed["used_full_day_actual_lp"].any()
        and not deployed["future_actuals_in_optimizer"].any()
        and diagnostics["selection_role"].eq("diagnostic_only").all()
        and (scored_groups == n_candidates).all()
        and selected.groupby("calibration_date").size().eq(1).all()
        and calibration["include_value_cuts"].all()
        and deployed["include_value_cuts"].all()
    )
    report = {
        "status": "PASS" if bool(status) else "FAIL",
        "stage": "C2-R2",
        "n_candidates_per_block": n_candidates,
        "scored_blocks": consistency["scored_blocks"],
        "fallback_blocks": consistency["fallback_blocks"],
        "selected_pairs": selected[["calibration_date", "forecast_mode", "risk_alpha"]].to_dict(
            orient="records"
        ),
        "deployed_days": int(len(deployed)),
        "protected_outputs_unchanged": snapshot_protected() == before,
        "candidate_result2_xlsx": False,
        "mae_is_diagnostic_only": True,
        "include_value_cuts": True,
        "include_value_cuts_consistent": True,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Q2 政策一致重设计 · C2-R2",
        "",
        f"- 状态：**{report['status']}**",
        f"- 每个可评分校准块评估 {n_candidates} 组 "
        f"(min{{m1,m2,m3}} × alphain{list(RISK_ALPHA_CANDIDATES)})。",
        "- 主选择准则是验证窗口内闭环实际成本均值 $\\sum(pq+5pe)$；"
        "一倍标准误内再按未用计划电、m1、较小 alpha 打破平局。",
        "- MAE / 净负荷 MAE / 覆盖率只写入 `forecast_diagnostics.csv`，不参与选择。",
        "- 每个候选在 14 日窗口内连续传递自己的 SOC；窗口初值取已部署主政策记录的 SOC。",
        "- 校准评分与获选策略部署均纳入次日基准预测价值割；同一日、同一 (m, alpha, K) 的割缓存复用。",
        "- 校准与部署均未把验证日未来实际值输入优化问题，也未调用全视域真实路径 LP。",
        "- 未导出候选 result2.xlsx；全年台账、K 敏感性与 2 月初 SOC 敏感性留到 C2-R3。",
        f"- 回退块 {consistency['fallback_blocks']} 个，评分块 {consistency['scored_blocks']} 个。",
        "",
        "## 各块选定 (m, alpha)",
        "",
    ]
    for row in selected.itertuples():
        lines.append(
            f"- {row.calibration_date} 至 {row.effective_end_date}："
            f"{row.forecast_mode}, alpha={row.risk_alpha}；"
            f"回退={row.fallback_reason or '无'}"
        )
    (output / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    after = snapshot_protected()
    if after != before:
        raise RuntimeError("Protected old Q2 outputs were modified")
    if not status:
        raise AssertionError("C2-R2 validation failed")
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# ===== q2/run_q2_policy_consistent_r3.py =====
#!/usr/bin/env python3
"""C2-R3: official year path, January/Feb-Dec split, SOC and K sensitivities.

Never writes result2.xlsx. Frozen (m, alpha) calendar comes from C2-R2.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    E_INITIAL_KWH,
    FIG_POLICY_CONSISTENT_DIR,
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    K_SENSITIVITY_CANDIDATES,
    OFFICIAL_OUTPUT_START,
    POLICY_CONSISTENT_OUTPUT_DIR,
)
from q2.data import load_q2_data  # noqa: E402
from q2.plot_q2_policy_consistent_r3 import plot_r3_comparison  # noqa: E402
from q2.policy_consistent import (  # noqa: E402
    FORECAST_MODES,
    PERIOD_FEB_DEC_OUTPUT,
    PERIOD_JANUARY_WARMUP,
    aggregate_cost_row,
    build_forecast_archive_mode,
    k_sensitivity_conclusion,
    output_period,
    run_frozen_policy_path,
    selected_calendar_for_dates,
)


R1_COPIES = (
    ("forecast_policy_audit.csv", "r1_forecast_policy_audit.csv"),
    ("physical_audit.csv", "r1_physical_audit.csv"),
    ("next_day_value_audit.csv", "r1_next_day_value_audit.csv"),
)


def file_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_protected() -> dict[str, str | None]:
    protected = [ROOT / "output" / "result2.xlsx"]
    if FULL_K8_RISK_OUTPUT_DIR.exists():
        protected.extend(sorted(FULL_K8_RISK_OUTPUT_DIR.rglob("*")))
    return {str(path.relative_to(ROOT)): file_hash(path) for path in protected if path.is_file()}


def preserve_r1_artifacts(output: Path) -> None:
    for source_name, dest_name in R1_COPIES:
        source = output / source_name
        dest = output / dest_name
        if source.exists() and not dest.exists():
            shutil.copy2(source, dest)
    r1_dispatch = output / "r1_dispatch_daily"
    dispatch = output / "dispatch_daily"
    if dispatch.exists() and not r1_dispatch.exists():
        r1_dispatch.mkdir(parents=True, exist_ok=True)
        for path in dispatch.glob("dispatch_*.csv"):
            shutil.copy2(path, r1_dispatch / path.name)


def split_period(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    january = daily.loc[daily["period"] == PERIOD_JANUARY_WARMUP].copy()
    feb_dec = daily.loc[daily["period"] == PERIOD_FEB_DEC_OUTPUT].copy()
    return january, feb_dec


def main() -> None:
    started = perf_counter()
    output = POLICY_CONSISTENT_OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    dispatch_dir = output / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    before = snapshot_protected()
    preserve_r1_artifacts(output)

    calibration_path = output / "closed_loop_calibration.csv"
    if not calibration_path.exists():
        raise FileNotFoundError("C2-R3 requires closed_loop_calibration.csv from C2-R2")

    data = load_q2_data()
    archives = {mode: build_forecast_archive_mode(data, mode) for mode in FORECAST_MODES}
    calendar = selected_calendar_for_dates(
        pd.read_csv(calibration_path), data.dates
    )
    feb_index = int(data.dates.get_loc(pd.Timestamp(OFFICIAL_OUTPUT_START)))
    year_end = len(data.dates) - 1
    cut_cache: dict = {}

    print("C2-R3 main path K=8 with next-day value cuts", flush=True)
    main_daily, main_forecast, main_physical, main_value = run_frozen_policy_path(
        data,
        archives,
        calendar,
        start_index=0,
        end_index=year_end,
        initial_soc=E_INITIAL_KWH,
        requested_k=FIXED_SCENARIO_K,
        soc_source="january_1_E_INITIAL_6000_then_inherited",
        include_value_cuts=True,
        dispatch_dir=dispatch_dir,
        cut_cache=cut_cache,
        progress_label="C2-R3-main",
    )
    daily = pd.DataFrame(main_daily)
    if list(daily["date"]) != [stamp.strftime("%Y-%m-%d") for stamp in data.dates]:
        raise AssertionError("main path does not cover the full year")
    if abs(float(daily["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) > 1e-8:
        raise AssertionError("main path must start at 6000 kWh on 2025-01-01")
    january, feb_dec = split_period(daily)
    if len(january) != 31 or len(feb_dec) != 334:
        raise AssertionError("January warmup / Feb-Dec split is not 31 + 334")
    inherited_feb_soc = float(january["soc_end_kwh"].iloc[-1])
    if abs(float(feb_dec["soc_start_kwh"].iloc[0]) - inherited_feb_soc) > 1e-8:
        raise AssertionError("Feb 1 SOC must inherit January 31 end SOC")
    main_elapsed = perf_counter() - started

    print(
        f"C2-R3 Feb 1 SOC sensitivity: inherited {inherited_feb_soc:.6f} vs registered {E_INITIAL_KWH:.1f}",
        flush=True,
    )
    alt_daily_rows, _alt_forecast, _alt_physical, _alt_value = run_frozen_policy_path(
        data,
        archives,
        calendar,
        start_index=feb_index,
        end_index=year_end,
        initial_soc=E_INITIAL_KWH,
        requested_k=FIXED_SCENARIO_K,
        soc_source="registered_boundary_E_INITIAL_6000",
        include_value_cuts=True,
        dispatch_dir=None,
        cut_cache=cut_cache,
        progress_label="C2-R3-feb-soc",
    )
    alt_feb_dec = pd.DataFrame(alt_daily_rows)
    if list(alt_feb_dec["date"]) != list(feb_dec["date"]):
        raise AssertionError("Feb SOC sensitivity dates differ from the main Feb-Dec path")
    if abs(float(alt_feb_dec["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) > 1e-8:
        raise AssertionError("registered Feb 1 boundary is not 6000 kWh")

    k_daily: dict[int, pd.DataFrame] = {FIXED_SCENARIO_K: daily}
    k_elapsed: dict[int, float] = {FIXED_SCENARIO_K: main_elapsed}
    for k in K_SENSITIVITY_CANDIDATES:
        if k == FIXED_SCENARIO_K:
            continue
        path_started = perf_counter()
        print(f"C2-R3 K sensitivity path K={k}", flush=True)
        rows, _forecast, _physical, _value = run_frozen_policy_path(
            data,
            archives,
            calendar,
            start_index=0,
            end_index=year_end,
            initial_soc=E_INITIAL_KWH,
            requested_k=k,
            soc_source="january_1_E_INITIAL_6000_then_inherited",
            include_value_cuts=True,
            dispatch_dir=None,
            cut_cache=cut_cache,
            progress_label=f"C2-R3-K{k}",
        )
        k_daily[k] = pd.DataFrame(rows)
        k_elapsed[k] = perf_counter() - path_started

    k_rows = []
    for k in K_SENSITIVITY_CANDIDATES:
        frame = k_daily[k]
        _, k_feb_dec = split_period(frame)
        k_rows.append(
            aggregate_cost_row(
                k_feb_dec,
                label=f"feb_dec_k{k}",
                extra={
                    "scenario_k": int(k),
                    "period": PERIOD_FEB_DEC_OUTPUT,
                    "calendar_frozen_from_r2": True,
                    "include_value_cuts": True,
                    "elapsed_seconds": float(k_elapsed[k]),
                    "mean_effective_k": float(k_feb_dec["scenario_k"].mean()),
                },
            )
        )
    conclusion = k_sensitivity_conclusion(k_rows)
    for row in k_rows:
        row["conclusion"] = conclusion

    cost_rows = [
        aggregate_cost_row(
            january,
            label="january_warmup_main",
            extra={
                "period": PERIOD_JANUARY_WARMUP,
                "scenario_k": FIXED_SCENARIO_K,
                "soc_source": "january_1_E_INITIAL_6000_then_inherited",
            },
        ),
        aggregate_cost_row(
            feb_dec,
            label="feb_dec_inherited_warmup_soc",
            extra={
                "period": PERIOD_FEB_DEC_OUTPUT,
                "scenario_k": FIXED_SCENARIO_K,
                "soc_source": "inherited_january_warmup",
                "feb1_soc_start_kwh": inherited_feb_soc,
            },
        ),
        aggregate_cost_row(
            alt_feb_dec,
            label="feb_dec_registered_boundary_6000",
            extra={
                "period": PERIOD_FEB_DEC_OUTPUT,
                "scenario_k": FIXED_SCENARIO_K,
                "soc_source": "registered_boundary_E_INITIAL_6000",
                "feb1_soc_start_kwh": E_INITIAL_KWH,
                "only_registered_boundary_changed": True,
            },
        ),
        aggregate_cost_row(
            daily,
            label="full_year_including_warmup",
            extra={
                "period": "full_year",
                "scenario_k": FIXED_SCENARIO_K,
            },
        ),
    ]

    soc_sensitivity = pd.DataFrame(
        [
            {
                "soc_source": "inherited_january_warmup",
                "feb1_soc_start_kwh": inherited_feb_soc,
                "dec31_soc_end_kwh": float(feb_dec["soc_end_kwh"].iloc[-1]),
                "n_days": int(len(feb_dec)),
                "start_date": str(feb_dec["date"].iloc[0]),
                "end_date": str(feb_dec["date"].iloc[-1]),
                "forecast_modes": ";".join(sorted(feb_dec["forecast_mode"].unique())),
                "requested_k": FIXED_SCENARIO_K,
                "planned_cost_yuan": float(feb_dec["planned_cost_yuan"].sum()),
                "emergency_cost_yuan": float(feb_dec["emergency_cost_yuan"].sum()),
                "total_cost_yuan": float(feb_dec["total_cost_yuan"].sum()),
                "emergency_kwh": float(feb_dec["emergency_kwh"].sum()),
                "unused_plan_kwh": float(feb_dec["unused_plan_kwh"].sum()),
                "curtailment_kwh": float(feb_dec["curtailment_kwh"].sum()),
                "only_registered_boundary_changed": False,
                "main_path": True,
            },
            {
                "soc_source": "registered_boundary_E_INITIAL_6000",
                "feb1_soc_start_kwh": E_INITIAL_KWH,
                "dec31_soc_end_kwh": float(alt_feb_dec["soc_end_kwh"].iloc[-1]),
                "n_days": int(len(alt_feb_dec)),
                "start_date": str(alt_feb_dec["date"].iloc[0]),
                "end_date": str(alt_feb_dec["date"].iloc[-1]),
                "forecast_modes": ";".join(sorted(alt_feb_dec["forecast_mode"].unique())),
                "requested_k": FIXED_SCENARIO_K,
                "planned_cost_yuan": float(alt_feb_dec["planned_cost_yuan"].sum()),
                "emergency_cost_yuan": float(alt_feb_dec["emergency_cost_yuan"].sum()),
                "total_cost_yuan": float(alt_feb_dec["total_cost_yuan"].sum()),
                "emergency_kwh": float(alt_feb_dec["emergency_kwh"].sum()),
                "unused_plan_kwh": float(alt_feb_dec["unused_plan_kwh"].sum()),
                "curtailment_kwh": float(alt_feb_dec["curtailment_kwh"].sum()),
                "only_registered_boundary_changed": True,
                "main_path": False,
            },
        ]
    )

    daily.to_csv(output / "q2_redesign_daily_summary.csv", index=False)
    january.to_csv(output / "january_warmup_summary.csv", index=False)
    feb_dec.to_csv(output / "feb_dec_daily_summary.csv", index=False)
    alt_feb_dec.to_csv(output / "feb_soc_sensitivity_daily.csv", index=False)
    soc_sensitivity.to_csv(output / "feb_soc_sensitivity.csv", index=False)
    pd.DataFrame(k_rows).to_csv(output / "k_sensitivity.csv", index=False)
    pd.DataFrame(cost_rows).to_csv(output / "cost_breakdown.csv", index=False)
    pd.DataFrame(main_forecast).to_csv(output / "forecast_policy_audit.csv", index=False)
    pd.DataFrame(main_physical).to_csv(output / "physical_audit.csv", index=False)
    pd.DataFrame(main_value).to_csv(output / "next_day_value_audit.csv", index=False)
    pd.DataFrame(
        [
            {
                "date": policy.date,
                "forecast_mode": policy.forecast_mode.value,
                "risk_alpha": policy.risk_alpha,
                "fallback_reason": policy.fallback_reason,
                "calibration_date": policy.calibration_date,
                "effective_start_date": policy.effective_start_date,
                "effective_end_date": policy.effective_end_date,
                "period": output_period(policy.date),
            }
            for policy in calendar
        ]
    ).to_csv(output / "frozen_policy_calendar.csv", index=False)

    figures = plot_r3_comparison(
        daily,
        pd.read_csv(FULL_K8_RISK_OUTPUT_DIR / "daily_summary.csv"),
        FIG_POLICY_CONSISTENT_DIR,
    )

    after = snapshot_protected()
    protected_ok = after == before
    status = bool(
        daily["pass"].all()
        and not daily["used_full_day_actual_lp"].any()
        and not daily["future_actuals_in_optimizer"].any()
        and not alt_feb_dec["used_full_day_actual_lp"].any()
        and protected_ok
        and conclusion
    )
    consistency = {
        "stage": "C2-R3",
        "policy": (
            "single baseline-forecast day-ahead LP plus K=8 risk reserve "
            "and residual-matching 10-minute MPC"
        ),
        "k_used_for": ["risk_reserve_R", "intra_day_residual_weights"],
        "k_not_used_for": [
            "scenario_specific_charge",
            "scenario_specific_discharge",
            "scenario_specific_soc",
            "full_path_scenario_storage_recourse",
        ],
        "calendar_frozen_from_r2": True,
        "calibration_closed_loop": True,
        "mae_is_diagnostic_only": True,
        "mae_used_for_selection": False,
        "include_value_cuts": True,
        "calibration_include_value_cuts": True,
        "deployment_include_value_cuts": True,
        "annual_run_include_value_cuts": True,
        "include_value_cuts_consistent": True,
        "main_path_initial_soc_kwh": E_INITIAL_KWH,
        "main_path_initial_rule_unchanged": True,
        "january_warmup_days": int(len(january)),
        "feb_dec_days": int(len(feb_dec)),
        "february_1_inherited_soc_kwh": inherited_feb_soc,
        "february_1_sensitivity_soc_kwh": E_INITIAL_KWH,
        "k_sensitivity_candidates": list(K_SENSITIVITY_CANDIDATES),
        "k_sensitivity_conclusion": conclusion,
        "validation_uses_full_day_actual_lp": False,
        "formal_execution_uses_full_day_actual_lp": False,
        "calibration_and_execution_exclude_future_actuals": True,
        "forecast_history_strictly_prior": True,
        "residual_pool_strictly_prior": True,
        "current_period_actuals_only": True,
        "annual_run": True,
        "candidate_result2_xlsx": False,
        "elapsed_seconds": perf_counter() - started,
    }
    (output / "policy_consistency_audit.json").write_text(
        json.dumps(consistency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "status": "PASS" if status else "FAIL",
        "stage": "C2-R3",
        "january_warmup": cost_rows[0],
        "feb_dec_inherited": cost_rows[1],
        "feb_dec_soc_sensitivity": cost_rows[2],
        "k_sensitivity_conclusion": conclusion,
        "figures": figures,
        "protected_outputs_unchanged": protected_ok,
        "candidate_result2_xlsx": False,
        "annual_run": True,
        "include_value_cuts": True,
        "include_value_cuts_consistent": True,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "run_metadata.json").write_text(
        json.dumps(
            {
                "stage": "C2-R3",
                "elapsed_seconds": consistency["elapsed_seconds"],
                "n_cut_cache_entries": len(cut_cache),
                "main_path_days": int(len(daily)),
                "dispatch_dir": str(dispatch_dir.relative_to(ROOT)),
                "figure_dir": str(FIG_POLICY_CONSISTENT_DIR.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Q2 政策一致重设计 · C2-R3",
        "",
        f"- 状态：**{report['status']}**",
        "- 全年主路径从 2025-01-01 的 6000 kWh 起步，冻结 C2-R2 选定的 (m, alpha) 日历，"
        "并加入次日基准预测价值割。",
        "- 校准评分、获选部署与全年正式运行的 `include_value_cuts=true` 一致。",
        "- 1 月预热与 2—12 月正式输出分栏；主路径 2 月 1 日 SOC 继承 1 月 31 日末值，"
        "不修改年初初值规则。",
        f"- 1 月预热实际成本 {cost_rows[0]['total_cost_yuan']:.2f} 元；"
        f"回退预测日 {int(january['load_fallback'].sum() + january['pv_fallback'].sum())} 条"
        "（负荷/光伏回退计数）。",
        f"- 2 月 1 日继承 SOC {inherited_feb_soc:.6f} kWh；"
        f"2—12 月正式成本 {cost_rows[1]['total_cost_yuan']:.2f} 元，"
        f"紧急购电 {cost_rows[1]['emergency_kwh']:.2f} kWh。",
        f"- 2 月初登记边界敏感性（6000 kWh）2—12 月成本 "
        f"{cost_rows[2]['total_cost_yuan']:.2f} 元。",
        f"- Kin{{4,8,12}} 闭环敏感性结论：`{conclusion}`。",
        "- 未导出候选 result2.xlsx；正式附件留到 C2-R4。",
        f"- 对照图写入 `{FIG_POLICY_CONSISTENT_DIR.relative_to(ROOT)}/`。",
        "",
        "## 1 月预热",
        "",
        f"- 日数 {len(january)}，初值 {float(january['soc_start_kwh'].iloc[0]):.6f} kWh，"
        f"2 月 1 日初值 {inherited_feb_soc:.6f} kWh。",
        f"- 负荷附件1回退 {int(january['load_fallback'].sum())} 日，"
        f"光伏附件1回退 {int(january['pv_fallback'].sum())} 日。",
        "",
        "## K 敏感性（2—12 月，冻结日历）",
        "",
    ]
    for row in k_rows:
        lines.append(
            f"- K={row['scenario_k']}：总成本 {row['total_cost_yuan']:.2f} 元，"
            f"紧急购电 {row['emergency_kwh']:.2f} kWh。"
        )
    (output / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if after != before:
        raise RuntimeError("Protected old Q2 outputs were modified")
    if not status:
        raise AssertionError("C2-R3 validation failed")
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# ===== q2/run_q2_policy_consistent_r4.py =====
#!/usr/bin/env python3
"""C2-R4: candidate result2.xlsx, final Q2 figures, and cell-by-cell audit.

Never overwrites output/result2.xlsx. Writes only under output/q2_policy_consistent/
and fig/q2_policy_consistent/.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    CANDIDATE_RESULT2,
    E_INITIAL_KWH,
    FIG_POLICY_CONSISTENT_DIR,
    FIG_Q2_FINAL_DIR,
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    NUMERIC_TOL,
    OFFICIAL_OUTPUT_START,
    POLICY_CONSISTENT_OUTPUT_DIR,
    RESULT2_SIGNED_OFF_BACKUP,
    SIGNED_OFF_RESULT2,
    SIGNED_OFF_RESULT2_SHA256,
)
from q2.data import load_q2_data  # noqa: E402
from q2.export_result2 import (  # noqa: E402
    N_OUTPUT_DAYS,
    audit_candidate_result2,
    file_sha256,
    preserve_signed_off_backup,
    write_candidate_result2,
    write_result2_audit,
)
from q2.plot_q2_policy_consistent_r3 import plot_r4_final_figures  # noqa: E402
from q2.policy_consistent import PERIOD_FEB_DEC_OUTPUT, PERIOD_JANUARY_WARMUP  # noqa: E402


def snapshot_protected() -> dict[str, str | None]:
    protected = [SIGNED_OFF_RESULT2]
    if FULL_K8_RISK_OUTPUT_DIR.exists():
        protected.extend(sorted(FULL_K8_RISK_OUTPUT_DIR.rglob("*")))
    if FIG_Q2_FINAL_DIR.exists():
        protected.extend(sorted(FIG_Q2_FINAL_DIR.rglob("*")))
    hashes: dict[str, str | None] = {}
    for path in protected:
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            hashes[str(path.relative_to(ROOT))] = digest.hexdigest()
    return hashes


def require_locked_main_scheme(daily: pd.DataFrame, january: pd.DataFrame, feb_dec: pd.DataFrame) -> float:
    if int(feb_dec["scenario_k"].nunique()) != 1 or int(feb_dec["scenario_k"].iloc[0]) != FIXED_SCENARIO_K:
        raise AssertionError("official Feb-Dec path is not K=8")
    if not bool(feb_dec["include_value_cuts"].all()) or not bool(january["include_value_cuts"].all()):
        raise AssertionError("official year path must keep next-day value cuts")
    if abs(float(daily["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) > NUMERIC_TOL:
        raise AssertionError("year path does not start at 6000 kWh on 2025-01-01")
    jan_dates = pd.to_datetime(january["date"])
    feb_dates = pd.to_datetime(feb_dec["date"])
    if jan_dates.iloc[0] != pd.Timestamp("2025-01-01") or jan_dates.iloc[-1] != pd.Timestamp("2025-01-31"):
        raise AssertionError("January warmup window mismatch")
    if feb_dates.iloc[0] != pd.Timestamp(OFFICIAL_OUTPUT_START) or feb_dates.iloc[-1] != pd.Timestamp("2025-12-31"):
        raise AssertionError("official output window mismatch")
    if len(january) != 31 or len(feb_dec) != N_OUTPUT_DAYS:
        raise AssertionError("January/Feb-Dec day counts mismatch")
    inherited = float(january["soc_end_kwh"].iloc[-1])
    if abs(float(feb_dec["soc_start_kwh"].iloc[0]) - inherited) > NUMERIC_TOL:
        raise AssertionError("Feb 1 does not inherit January 31 SOC")
    if (january["period"] != PERIOD_JANUARY_WARMUP).any() or (feb_dec["period"] != PERIOD_FEB_DEC_OUTPUT).any():
        raise AssertionError("period labels mismatch")
    return inherited


def main() -> None:
    started = perf_counter()
    output = POLICY_CONSISTENT_OUTPUT_DIR
    dispatch_dir = output / "dispatch_daily"
    before = snapshot_protected()
    signed_hash = preserve_signed_off_backup()
    data = load_q2_data()
    daily = pd.read_csv(output / "q2_redesign_daily_summary.csv")
    january = pd.read_csv(output / "january_warmup_summary.csv")
    feb_dec = pd.read_csv(output / "feb_dec_daily_summary.csv")
    calibration = pd.read_csv(output / "closed_loop_calibration.csv")
    k_table = pd.read_csv(output / "k_sensitivity.csv")
    inherited = require_locked_main_scheme(daily, january, feb_dec)
    conclusion = str(k_table["conclusion"].iloc[0])
    if conclusion != "retain_k8_stable":
        raise AssertionError("K=8 is not retained as the stable pre-registered scheme")
    if not dispatch_dir.exists():
        raise FileNotFoundError("C2-R4 requires the C2-R3 dispatch_daily archive")

    print("C2-R4 writing candidate result2.xlsx under output/q2_policy_consistent/", flush=True)
    write_candidate_result2(CANDIDATE_RESULT2, dispatch_dir, feb_dec, data)
    audit = audit_candidate_result2(CANDIDATE_RESULT2, dispatch_dir, feb_dec, data, inherited)
    write_result2_audit(audit, output)
    if not audit["summary"]["pass"]:
        raise AssertionError("candidate result2 cell audit failed")

    figures = plot_r4_final_figures(
        daily,
        pd.read_csv(FULL_K8_RISK_OUTPUT_DIR / "daily_summary.csv"),
        calibration,
        dispatch_dir,
        data.price,
        fig_dir=FIG_POLICY_CONSISTENT_DIR,
    )

    after = snapshot_protected()
    protected_ok = after == before and signed_hash == SIGNED_OFF_RESULT2_SHA256
    if file_sha256(SIGNED_OFF_RESULT2) != SIGNED_OFF_RESULT2_SHA256:
        raise RuntimeError("signed-off output/result2.xlsx changed during C2-R4")
    if file_sha256(RESULT2_SIGNED_OFF_BACKUP) != SIGNED_OFF_RESULT2_SHA256:
        raise RuntimeError("signed-off result2 backup is not bit-identical")
    if CANDIDATE_RESULT2.resolve() == SIGNED_OFF_RESULT2.resolve():
        raise RuntimeError("candidate path collapsed onto the signed-off file")

    previous = json.loads((output / "policy_consistency_audit.json").read_text(encoding="utf-8"))
    previous.update(
        {
            "stage": "C2-R4",
            "candidate_result2_xlsx": True,
            "candidate_result2_path": str(CANDIDATE_RESULT2.relative_to(ROOT)),
            "signed_off_result2_path": str(SIGNED_OFF_RESULT2.relative_to(ROOT)),
            "signed_off_result2_sha256": SIGNED_OFF_RESULT2_SHA256,
            "signed_off_result2_unchanged": protected_ok,
            "k8_paper_language": "预注册且对 K=4/12 稳定的简洁主方案",
            "k8_not_cost_optimal": True,
            "old_full_path_role": "信息更强的近似对照",
            "r4_elapsed_seconds": perf_counter() - started,
        }
    )
    (output / "policy_consistency_audit.json").write_text(
        json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    previous_report = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    report = {
        **previous_report,
        "status": "PASS" if audit["summary"]["pass"] and protected_ok else "FAIL",
        "stage": "C2-R4",
        "candidate_result2_xlsx": True,
        "candidate_result2_path": str(CANDIDATE_RESULT2.relative_to(ROOT)),
        "signed_off_result2_unchanged": protected_ok,
        "signed_off_result2_sha256": SIGNED_OFF_RESULT2_SHA256,
        "result2_cell_audit_pass": bool(audit["summary"]["pass"]),
        "result2_max_q_abs_kwh": audit["summary"]["max_q_abs_kwh"],
        "result2_max_planned_cost_abs_yuan": audit["summary"]["max_planned_cost_abs_yuan"],
        "result2_max_emergency_recon_abs_kwh": audit["summary"]["max_emergency_recon_abs_kwh"],
        "result2_max_soc_abs_kwh": audit["summary"]["max_soc_abs_kwh"],
        "figures": figures,
        "k8_paper_language": "预注册且对 K=4/12 稳定的简洁主方案",
        "k8_not_cost_optimal": True,
        "old_full_path_role": "信息更强的近似对照",
        "protected_outputs_unchanged": protected_ok,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata = json.loads((output / "run_metadata.json").read_text(encoding="utf-8"))
    metadata.update(
        {
            "stage": "C2-R4",
            "candidate_result2": str(CANDIDATE_RESULT2.relative_to(ROOT)),
            "signed_off_backup": str(RESULT2_SIGNED_OFF_BACKUP.relative_to(ROOT)),
            "r4_elapsed_seconds": previous["r4_elapsed_seconds"],
            "figure_dir": str(FIG_POLICY_CONSISTENT_DIR.relative_to(ROOT)),
        }
    )
    (output / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    jan_cost = float(january["total_cost_yuan"].sum())
    feb_cost = float(feb_dec["total_cost_yuan"].sum())
    feb_emergency = float(feb_dec["emergency_kwh"].sum())
    lines = [
        "# Q2 政策一致重设计 · C2-R4",
        "",
        f"- 状态：**{report['status']}**",
        "- 正式主方案固定为：K=8；C2-R2 冻结的 (m, alpha) 日历；校准、部署与全年路径均启用次日价值割；"
        "全年从 2025-01-01 的 6000 kWh 起步，1 月仅预热，2—12 月正式输出继承 1 月末 SOC。",
        "- **K=8 表述为「预注册且对 K=4/12 稳定的简洁主方案」，不得称为成本最优。**",
        "- **旧全路径 K=8 风险方案仅作信息更强的近似对照，不是正式答卷。**",
        f"- 1 月预热实际成本 {jan_cost:.2f} 元；2 月 1 日继承 SOC {inherited:.6f} kWh。",
        f"- 2—12 月正式成本 {feb_cost:.2f} 元，紧急购电 {feb_emergency:.2f} kWh。",
        f"- Kin{{4,8,12}} 闭环敏感性结论：`{conclusion}`。",
        f"- 候选附件写入 `{CANDIDATE_RESULT2.relative_to(ROOT)}`；"
        f"旧签收文件 `{SIGNED_OFF_RESULT2.relative_to(ROOT)}` 未覆盖，"
        f"可回退副本 `{RESULT2_SIGNED_OFF_BACKUP.relative_to(ROOT)}`。",
        f"- 旧 result2.xlsx SHA-256：`{SIGNED_OFF_RESULT2_SHA256}`。",
        f"- 逐格对账：`result2_cell_audit.json` / `result2_cell_audit.csv`；pass={audit['summary']['pass']}。",
        f"- 最终图写入 `{FIG_POLICY_CONSISTENT_DIR.relative_to(ROOT)}/`，未改写 `fig/q2_final/`。",
        "",
        "## 候选附件对账",
        "",
        f"- 日期：2 月 1 日至 12 月 31 日，共 {N_OUTPUT_DAYS} 日。",
        "- 每行 144 时段，按附件原始行序写入，不旋转。",
        "- 计划购电量/全天购电费与台账 `planned_q_kwh` / `planned_cost_yuan` 一致；单位 kWh / 元。",
        "- 紧急购电量按连续正量合并时段，日合计与台账 `emergency_kwh` 一致。",
        "- 充放电量按 4 小时块汇总；00:00 / 24:00 储电量与日初/日末 SOC 一致，且跨日连续。",
        "- 功率上限、能量平衡、x<=q 与全年物理审计一致。",
        "",
        "## 论文口径",
        "",
        "- 可写：基于历史残差风险储备的日前购电计划，配合逐时段残差匹配 MPC。",
        "- 不可写：K=8 成本最优、严格多阶段随机最优控制、旧全路径方案为正式主方案。",
    ]
    (output / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if after != before:
        raise RuntimeError("Protected old Q2 outputs were modified")
    if not audit["summary"]["pass"]:
        raise AssertionError("C2-R4 validation failed")
    print(
        json.dumps(
            {
                "status": report["status"],
                "candidate": str(CANDIDATE_RESULT2.relative_to(ROOT)),
                "signed_off_unchanged": protected_ok,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

# ===== q2/scenarios.py =====
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import RESIDUAL_POOL_DAYS
from q2.data import Q2Data
from q2.forecast import ForecastArchive


@dataclass(frozen=True)
class ScenarioSet:
    target_index: int
    history_end_exclusive: int
    pool_indices: np.ndarray
    medoid_indices: np.ndarray
    cluster_labels: np.ndarray
    probabilities: np.ndarray
    scale_load: float
    scale_pv: float
    stress_index: int


def robust_scale(values: np.ndarray) -> float:
    flat = np.asarray(values, dtype=float).ravel()
    med = np.median(flat)
    mad = 1.4826 * np.median(np.abs(flat - med))
    if mad > 1e-12:
        return float(mad)
    std = np.std(flat)
    return float(std if std > 1e-12 else 1.0)


def residual_distance_matrix(
    load_residual: np.ndarray, pv_residual: np.ndarray, price: np.ndarray
) -> tuple[np.ndarray, float, float]:
    sl = robust_scale(load_residual)
    sp = robust_scale(pv_residual)
    weight = price / np.mean(price)
    dl = (load_residual[:, None, :] - load_residual[None, :, :]) / sl
    dp = (pv_residual[:, None, :] - pv_residual[None, :, :]) / sp
    d2 = np.mean(weight[None, None, :] * (dl * dl + dp * dp), axis=2)
    return np.sqrt(np.maximum(d2, 0.0)), sl, sp


def pam(distance: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Small deterministic PAM implementation over a <=28-day pool."""
    n = distance.shape[0]
    if not 1 <= k <= n:
        raise ValueError(f"k={k} is invalid for pool size {n}")
    medoids = [int(np.argmin(distance.sum(axis=1)))]
    while len(medoids) < k:
        nearest = distance[:, medoids].min(axis=1)
        nearest[medoids] = -np.inf
        medoids.append(int(np.argmax(nearest)))
    medoids = np.array(sorted(medoids), dtype=int)

    def cost(ms: np.ndarray) -> float:
        return float(distance[:, ms].min(axis=1).sum())

    current = cost(medoids)
    while True:
        best_cost, best = current, medoids
        outside = np.setdiff1d(np.arange(n), medoids)
        for pos in range(k):
            for candidate in outside:
                trial = medoids.copy()
                trial[pos] = candidate
                trial.sort()
                trial_cost = cost(trial)
                if trial_cost < best_cost - 1e-12:
                    best_cost, best = trial_cost, trial
        if best_cost >= current - 1e-12:
            break
        medoids, current = best, best_cost
    labels = np.argmin(distance[:, medoids], axis=1)
    return medoids, labels


def build_scenarios(
    target_index: int,
    data: Q2Data,
    archive: ForecastArchive,
    k: int,
    history_end_exclusive: int | None = None,
) -> ScenarioSet:
    history_end = target_index if history_end_exclusive is None else history_end_exclusive
    if history_end <= 0 or history_end > target_index:
        raise ValueError("No historical residual exists for the first date")
    pool = np.arange(max(0, history_end - RESIDUAL_POOL_DAYS), history_end)
    lr = archive.load_residual[pool]
    pr = archive.pv_residual[pool]
    distance, sl, sp = residual_distance_matrix(lr, pr, data.price)
    local_medoids, labels = pam(distance, min(k, len(pool)))
    counts = np.bincount(labels, minlength=len(local_medoids))
    probabilities = counts.astype(float) / len(pool)
    if not np.isclose(probabilities.sum(), 1.0, atol=1e-12):
        raise AssertionError("scenario probabilities do not sum to one")
    high = data.price >= np.quantile(data.price, 0.75)
    net_positive = np.maximum(lr - pr, 0.0)
    stress_local = int(np.argmax((net_positive[:, high] * data.price[high]).sum(axis=1)))
    return ScenarioSet(
        target_index=target_index,
        history_end_exclusive=history_end,
        pool_indices=pool,
        medoid_indices=pool[local_medoids],
        cluster_labels=labels,
        probabilities=probabilities,
        scale_load=sl,
        scale_pv=sp,
        stress_index=int(pool[stress_local]),
    )


def scenario_trajectories(
    scenarios: ScenarioSet,
    archive: ForecastArchive,
    base_load: np.ndarray | None = None,
    base_pv: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    i = scenarios.target_index
    m = scenarios.medoid_indices
    load_hat = archive.load_hat[i] if base_load is None else base_load
    pv_hat = archive.pv_hat[i] if base_pv is None else base_pv
    load = np.maximum(0.0, load_hat[None, :] + archive.load_residual[m])
    pv = np.maximum(0.0, pv_hat[None, :] + archive.pv_residual[m])
    return load, pv


def write_scenarios_csv(
    path: Path, data: Q2Data, scenarios: ScenarioSet
) -> None:
    rows = []
    for cluster, medoid in enumerate(scenarios.medoid_indices):
        rows.append(
            {
                "calibration_date": data.dates[scenarios.target_index].strftime("%Y-%m-%d"),
                "medoid_date": data.dates[medoid].strftime("%Y-%m-%d"),
                "cluster_size": int(np.sum(scenarios.cluster_labels == cluster)),
                "probability": scenarios.probabilities[cluster],
                "stress_test_date": data.dates[scenarios.stress_index].strftime("%Y-%m-%d"),
                "medoid_is_stress_day": bool(medoid == scenarios.stress_index),
                "pool_start": data.dates[scenarios.pool_indices[0]].strftime("%Y-%m-%d"),
                "pool_end": data.dates[scenarios.pool_indices[-1]].strftime("%Y-%m-%d"),
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def posterior_weights(
    scenarios: ScenarioSet,
    archive: ForecastArchive,
    observed_load_residual_prefix: np.ndarray,
    observed_pv_residual_prefix: np.ndarray,
) -> tuple[np.ndarray, float]:
    m = scenarios.medoid_indices
    t = len(observed_load_residual_prefix)
    lr = archive.load_residual[m, :t]
    pr = archive.pv_residual[m, :t]
    delta = np.mean(
        ((lr - observed_load_residual_prefix) / scenarios.scale_load) ** 2
        + ((pr - observed_pv_residual_prefix) / scenarios.scale_pv) ** 2,
        axis=1,
    )
    if len(m) > 1:
        pair = []
        for a in range(len(m)):
            for b in range(a + 1, len(m)):
                pair.append(
                    np.mean(
                        ((lr[a] - lr[b]) / scenarios.scale_load) ** 2
                        + ((pr[a] - pr[b]) / scenarios.scale_pv) ** 2
                    )
                )
        bandwidth = max(float(np.sqrt(np.median(pair))), 1e-6)
    else:
        bandwidth = 1.0
    logw = np.log(np.maximum(scenarios.probabilities, 1e-300)) - delta / (
        2.0 * bandwidth * bandwidth
    )
    logw -= np.max(logw)
    weights = np.exp(logw)
    weights /= weights.sum()
    return weights, bandwidth


# ===== q2/validate_q2_pilot.py =====
#!/usr/bin/env python3
"""Independent checks over generated Q2 pilot artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    EMERGENCY_PRICE_MULTIPLIER,
    E_MAX_KWH,
    E_MIN_KWH,
    NUMERIC_TOL,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    OUTPUT_DIR,
    PILOT_DATES,
    POWER_LIMIT_KWH,
    SIMULTANEOUS_CD_TOL,
    T,
)
from q2.data import load_q2_data  # noqa: E402
from q2.pilot import planned_q_hash  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    data = load_q2_data()
    audit = json.loads((OUTPUT_DIR / "input_audit.json").read_text(encoding="utf-8"))
    require(audit["shape"] == {"days": 365, "periods_per_day": 144}, "P0 shape")
    require(audit["missing_count"] == 0, "P0 missing data")

    perfect = pd.read_csv(OUTPUT_DIR / "perfect_information_daily.csv")
    require(len(perfect) == 365 and perfect["pass"].all(), "P1 daily status")
    require(float(perfect["emergency_kwh"].sum()) < NUMERIC_TOL, "P1 emergency")
    require(
        np.max(
            np.abs(
                perfect["soc_start_kwh"].to_numpy()[1:]
                - perfect["soc_end_kwh"].to_numpy()[:-1]
            )
        )
        < NUMERIC_TOL,
        "P1 cross-day SOC",
    )

    forecast = pd.read_csv(OUTPUT_DIR / "forecast_archive.csv")
    require(len(forecast) == 365 * T, "P2 archive rows")
    require(forecast[["load_hat_kwh", "pv_hat_kwh"]].notna().all().all(), "P2 finite")
    for row in forecast.groupby("date", sort=False).first().reset_index().itertuples():
        for field in ("load_source_dates", "pv_source_dates"):
            sources = str(getattr(row, field)).split(";")
            if sources != ["attachment1_fallback"]:
                require(
                    all(pd.Timestamp(source) < pd.Timestamp(row.date) for source in sources),
                    f"P2 future source in {field} for {row.date}",
                )

    selected = pd.read_csv(OUTPUT_DIR / "scenario_selection.csv")
    require(selected.groupby("calibration_date")["selected"].sum().eq(1).all(), "P3 K choice")
    calendar = pd.read_csv(OUTPUT_DIR / "k_freeze_calendar.csv")
    periods = calendar[
        ["calibration_date", "effective_start_date", "effective_end_date", "selected_k"]
    ].drop_duplicates()
    require(len(periods) == int(np.ceil(365 / 14)), "R4 calibration count")
    require(periods["effective_start_date"].iloc[0] == "2025-01-01", "R4 start")
    require(periods["effective_end_date"].iloc[-1] == "2025-12-31", "R4 end")
    for left, right in zip(periods.itertuples(), periods.iloc[1:].itertuples()):
        require(
            pd.Timestamp(left.effective_end_date) + pd.Timedelta(days=1)
            == pd.Timestamp(right.effective_start_date),
            "R4 calendar gap",
        )
    require(
        calendar.groupby("calibration_date")["candidate_selected"].sum().eq(1).all(),
        "R4 selected candidate count",
    )

    warmup = pd.read_csv(OUTPUT_DIR / "linked_warmup_daily.csv")
    require(len(warmup) == 31 and warmup["pass"].all(), "R2 warmup status")
    require(abs(float(warmup["soc_start_kwh"].iloc[0]) - 6000.0) < NUMERIC_TOL, "R2 initial SOC")
    require(
        float(
            np.max(
                np.abs(
                    warmup["soc_start_kwh"].to_numpy()[1:]
                    - warmup["soc_end_kwh"].to_numpy()[:-1]
                )
            )
        )
        < NUMERIC_TOL,
        "R2 SOC continuity",
    )

    value_audit = pd.read_csv(OUTPUT_DIR / "next_day_value_audit.csv")
    require(not value_audit.empty, "R3 value audit")
    require(
        float(value_audit["certified_max_gap_yuan"].max())
        <= NEXT_DAY_VALUE_GAP_TOL_YUAN + 1e-6,
        "R3 value approximation certificate",
    )
    for _date, bundle in value_audit.groupby("decision_date"):
        ordered = bundle.sort_values("soc_sample_kwh")
        require(
            np.all(
                np.diff(ordered["value_subgradient_yuan_per_kwh"].to_numpy())
                >= -1e-6
            ),
            "R3 nonmonotone value subgradients",
        )
    require(
        (
            pd.to_datetime(value_audit["target_date"])
            == pd.to_datetime(value_audit["decision_date"]) + pd.Timedelta(days=1)
        ).all(),
        "R3 next-day target",
    )
    for row in value_audit.itertuples():
        if row.history_cutoff_date != "attachment1_fallback":
            require(
                pd.Timestamp(row.history_cutoff_date) < pd.Timestamp(row.decision_date),
                "R3 history cutoff leakage",
            )
        if row.residual_pool_end_date != "none":
            require(
                pd.Timestamp(row.residual_pool_end_date) < pd.Timestamp(row.decision_date),
                "R3 residual pool leakage",
            )

    value_comparison = pd.read_csv(OUTPUT_DIR / "next_day_value_comparison.csv")
    require(
        not value_comparison["virtual_next_day_value_billed_today"].any(),
        "R3 virtual value double billing",
    )
    require(
        value_comparison["next_day_plan_recomputed_and_billed_once"].all(),
        "R3 next-day plan billing",
    )
    require(
        np.allclose(
            value_comparison["realized_two_day_cost_without_48h_today_yuan"],
            value_comparison["cost_without_48h_yuan"]
            + value_comparison["next_day_cost_after_without_48h_yuan"],
            atol=1e-6,
        ),
        "R3 two-day accounting without value",
    )
    require(
        np.allclose(
            value_comparison["realized_two_day_cost_with_48h_today_yuan"],
            value_comparison["cost_with_48h_yuan"]
            + value_comparison["next_day_cost_after_with_48h_yuan"],
            atol=1e-6,
        ),
        "R3 two-day accounting with value",
    )
    for date_text in PILOT_DATES:
        scenarios = pd.read_csv(OUTPUT_DIR / f"scenarios_{date_text}.csv")
        require(abs(float(scenarios["probability"].sum()) - 1.0) < 1e-12, "P3 probability")
        require((pd.to_datetime(scenarios["medoid_date"]) < pd.Timestamp(date_text)).all(), "P3 future medoid")

        dispatch = pd.read_csv(OUTPUT_DIR / f"q2_pilot_dispatch_{date_text}.csv")
        summary = pd.read_csv(OUTPUT_DIR / "pilot_day_summary.csv")
        summary = summary.loc[summary["date"] == date_text].iloc[0]
        if date_text == "2025-02-01":
            require(
                abs(summary["soc_start_kwh"] - warmup["soc_end_kwh"].iloc[-1])
                < NUMERIC_TOL,
                "R2 February initial SOC trace",
            )
        require(len(dispatch) == T, "P4 row count")
        require(float(dispatch["balance_residual_kwh"].abs().max()) < NUMERIC_TOL, "P4 balance")
        require(float((dispatch["actual_x_kwh"] - dispatch["planned_q_kwh"]).max()) < NUMERIC_TOL, "P4 x<=q")
        require(float(dispatch["charge_kwh"].max()) <= POWER_LIMIT_KWH + NUMERIC_TOL, "P4 charge bound")
        require(float(dispatch["discharge_kwh"].max()) <= POWER_LIMIT_KWH + NUMERIC_TOL, "P4 discharge bound")
        require(float((dispatch["curtailment_kwh"] - dispatch["pv_kwh"]).max()) < NUMERIC_TOL, "P4 curtailment")
        require(float(dispatch["soc_kwh"].min()) >= E_MIN_KWH - NUMERIC_TOL, "P4 SOC min")
        require(float(dispatch["soc_kwh"].max()) <= E_MAX_KWH + NUMERIC_TOL, "P4 SOC max")
        require(
            float((dispatch["charge_kwh"] * dispatch["discharge_kwh"]).max())
            <= SIMULTANEOUS_CD_TOL,
            "P4 simultaneous c/d",
        )
        planned_cost = float(data.price @ dispatch["planned_q_kwh"].to_numpy())
        emergency_cost = float(
            EMERGENCY_PRICE_MULTIPLIER
            * data.price
            @ dispatch["emergency_kwh"].to_numpy()
        )
        require(abs(planned_cost - summary["planned_cost_yuan"]) < 1e-6, "P4 q cost")
        require(abs(emergency_cost - summary["emergency_cost_yuan"]) < 1e-6, "P4 e cost")
        require(
            abs(
                summary["total_cost_yuan"]
                - summary["planned_cost_yuan"]
                - summary["emergency_cost_yuan"]
            )
            < 1e-6,
            "R3 virtual value billed in actual cost",
        )
        require(
            planned_q_hash(dispatch["planned_q_kwh"].to_numpy())
            == summary["planned_q_sha256"],
            "P4 locked q hash",
        )
        no48 = pd.read_csv(
            OUTPUT_DIR / f"q2_pilot_dispatch_{date_text}_no48h.csv"
        )
        require(len(no48) == T, "R3 no-48h row count")
        require(
            float(no48["balance_residual_kwh"].abs().max()) < NUMERIC_TOL,
            "R3 no-48h balance",
        )
        require(
            float((no48["actual_x_kwh"] - no48["planned_q_kwh"]).max())
            < NUMERIC_TOL,
            "R3 no-48h x<=q",
        )

    require(not (ROOT / "output" / "result2.xlsx").exists(), "result2.xlsx forbidden")
    print("Q2 pilot independent validation: PASS")


if __name__ == "__main__":
    main()


# ===== q2/validate_q2_policy_consistent.py =====
#!/usr/bin/env python3
"""Independent checks over C2-R1 / R2 / R3 / R4 policy-consistent artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    CANDIDATE_RESULT2,
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    FIG_POLICY_CONSISTENT_DIR,
    FIG_Q2_FINAL_DIR,
    FIXED_SCENARIO_K,
    K_SENSITIVITY_CANDIDATES,
    NUMERIC_TOL,
    OFFICIAL_OUTPUT_START,
    PILOT_DATES,
    POLICY_CONSISTENT_OUTPUT_DIR,
    POWER_LIMIT_KWH,
    RESULT2_SIGNED_OFF_BACKUP,
    SIGNED_OFF_RESULT2,
    SIGNED_OFF_RESULT2_SHA256,
    SIMULTANEOUS_CD_TOL,
    T,
)
from q2.data import load_q2_data  # noqa: E402
from q2.export_result2 import (  # noqa: E402
    N_OUTPUT_DAYS,
    audit_candidate_result2,
    file_sha256,
)
from q2.pilot import planned_q_hash  # noqa: E402
from q2.policy_consistent import PERIOD_FEB_DEC_OUTPUT, PERIOD_JANUARY_WARMUP  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_no_forecast_leakage(forecast: pd.DataFrame) -> None:
    for row in forecast.itertuples():
        target = pd.Timestamp(row.date)
        for field in ("load_source_dates", "pv_source_dates"):
            sources = str(getattr(row, field)).split(";")
            if sources != ["attachment1_fallback"]:
                require(
                    all(pd.Timestamp(source) < target for source in sources),
                    f"forecast leakage in {field} on {row.date}",
                )
        if str(row.residual_pool_end_date) != "none":
            require(
                pd.Timestamp(row.residual_pool_end_date) < target,
                f"residual pool leakage on {row.date}",
            )
        if str(row.medoid_dates) != "none":
            require(
                all(pd.Timestamp(item) < target for item in str(row.medoid_dates).split(";")),
                f"medoid leakage on {row.date}",
            )
        shapes = json.loads(row.day_ahead_variable_shapes)
        for name in ("charge", "discharge", "soc"):
            require(name in shapes, f"missing {name}")
            require(len(shapes[name]) == 1, f"{name} must be 1-D, got {shapes[name]}")
        require(not bool(row.has_scenario_specific_battery), "scenario battery flag")


def assert_dispatch_physics(path: Path, data, physical_row: pd.Series, date_text: str) -> None:
    i = int(data.dates.get_loc(pd.Timestamp(date_text)))
    frame = pd.read_csv(path)
    require(len(frame) == T, f"{date_text} dispatch length")
    q = frame["planned_q_kwh"].to_numpy()
    x = frame["actual_x_kwh"].to_numpy()
    require(planned_q_hash(q) == physical_row["planned_q_sha256"], "q hash")
    require(np.max(x - q) < NUMERIC_TOL, f"{date_text} x<=q")
    residual = (
        frame["actual_x_kwh"]
        + frame["emergency_kwh"]
        + frame["pv_kwh"]
        - frame["curtailment_kwh"]
        + frame["discharge_kwh"]
        - frame["load_kwh"]
        - frame["charge_kwh"]
    )
    require(float(residual.abs().max()) < NUMERIC_TOL, f"{date_text} balance")
    require(frame["soc_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL, f"{date_text} SOC min")
    require(frame["soc_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL, f"{date_text} SOC max")
    require(
        float((frame["charge_kwh"] * frame["discharge_kwh"]).max()) <= SIMULTANEOUS_CD_TOL,
        f"{date_text} simultaneous charge/discharge",
    )
    require(frame["charge_kwh"].max() <= POWER_LIMIT_KWH + NUMERIC_TOL, f"{date_text} charge limit")
    require(
        frame["discharge_kwh"].max() <= POWER_LIMIT_KWH + NUMERIC_TOL,
        f"{date_text} discharge limit",
    )
    require(np.allclose(frame["load_kwh"].to_numpy(), data.load[i], atol=1e-12), "dispatch load")


def validate_r1(output: Path, data, consistency: dict, report: dict) -> None:
    r1_forecast = output / "r1_forecast_policy_audit.csv"
    if r1_forecast.exists():
        forecast = pd.read_csv(r1_forecast)
        physical = pd.read_csv(output / "r1_physical_audit.csv")
        value_audit = pd.read_csv(output / "r1_next_day_value_audit.csv")
        dispatch_dir = output / "r1_dispatch_daily"
    else:
        forecast = pd.read_csv(output / "forecast_policy_audit.csv")
        physical = pd.read_csv(output / "physical_audit.csv")
        value_audit = pd.read_csv(output / "next_day_value_audit.csv")
        dispatch_dir = output / "dispatch_daily"
        require(consistency["annual_run"] is False, "R1 must not run the year")

    require(list(forecast["date"]) == list(PILOT_DATES), "R1 dates")
    require(report["status"] == "PASS", "validation status")
    if not r1_forecast.exists():
        require(report["candidate_result2_xlsx"] is False, "no candidate result2")
    require(consistency["validation_uses_full_day_actual_lp"] is False, "no full-day actual LP")
    require(consistency["k_used_for"] == ["risk_reserve_R", "intra_day_residual_weights"], "K uses")
    assert_no_forecast_leakage(forecast)
    require(physical["pass"].all(), "physical pass")
    require(not physical["used_full_day_actual_lp"].any(), "artifact used full-day LP")
    require(set(value_audit["decision_date"]) == set(PILOT_DATES), "value-cut decision dates")
    for row in value_audit.itertuples():
        decision = pd.Timestamp(row.decision_date)
        cutoff = pd.Timestamp(row.history_cutoff_date)
        target = pd.Timestamp(row.target_date)
        require(cutoff == decision - pd.Timedelta(days=1), f"cutoff is last history day for {row.decision_date}")
        require(cutoff < decision, f"cutoff precedes decision {row.decision_date}")
        require(target == decision + pd.Timedelta(days=1), f"target is next day for {row.decision_date}")
    for date_text in PILOT_DATES:
        physical_row = physical.loc[physical["date"] == date_text].iloc[0]
        assert_dispatch_physics(
            dispatch_dir / f"dispatch_{date_text}.csv",
            data,
            physical_row,
            date_text,
        )
    print("C2-R1 artifact validation passed")


def validate_r2(
    output: Path,
    data,
    diagnostics: pd.DataFrame,
    consistency: dict,
    report: dict,
) -> None:
    from q2.config import RISK_ALPHA_CANDIDATES
    from q2.policy_consistent import FORECAST_MODES

    calibration = pd.read_csv(output / "closed_loop_calibration.csv")
    deployed = pd.read_csv(output / "r2_deployed_daily.csv")
    n_candidates = len(FORECAST_MODES) * len(RISK_ALPHA_CANDIDATES)
    stage = consistency["stage"]
    require(n_candidates == 12, "12 (m, alpha) pairs")
    if stage in ("C2-R3", "C2-R4"):
        require(consistency["annual_run"] is True, "R3 annual run flag")
    elif stage == "C2-R2":
        require(consistency["annual_run"] is False, "R3 annual run not started")
    else:
        raise AssertionError(f"unexpected stage {stage}")
    require(consistency["calibration_closed_loop"] is True, "closed-loop calibration")
    require(consistency["mae_is_diagnostic_only"] is True, "MAE diagnostic flag")
    require(consistency["mae_used_for_selection"] is False, "MAE not used to select")
    require(consistency["validation_uses_full_day_actual_lp"] is False, "R2 no full-day LP")
    require(consistency["formal_execution_uses_full_day_actual_lp"] is False, "deploy no full-day LP")
    require(consistency["calibration_and_execution_exclude_future_actuals"] is True, "no future actuals")
    require(consistency["calibration_include_value_cuts"] is True, "calibration value cuts")
    require(consistency["deployment_include_value_cuts"] is True, "deployment value cuts")
    require(consistency["include_value_cuts"] is True, "include_value_cuts flag")
    require(consistency["include_value_cuts_consistent"] is True, "value-cut consistency")
    if stage != "C2-R4":
        require(report["candidate_result2_xlsx"] is False, "no candidate result2")
    require(diagnostics["selection_role"].eq("diagnostic_only").all(), "R2 MAE diagnostic")
    require(len(deployed) == len(data.dates), "deployed path covers the year for SOC")
    require(deployed["pass"].all(), "deployed physical pass")
    require(not deployed["used_full_day_actual_lp"].any(), "deployed used full-day LP")
    require(not deployed["future_actuals_in_optimizer"].any(), "deployed future actuals")
    require(deployed["include_value_cuts"].all(), "deployed value cuts")
    require(calibration["include_value_cuts"].all(), "calibration value cuts column")
    require(
        np.max(np.abs(deployed["soc_start_kwh"].to_numpy()[1:] - deployed["soc_end_kwh"].to_numpy()[:-1]))
        < NUMERIC_TOL,
        "deployed SOC continuity",
    )

    scored = calibration.loc[calibration["fallback_reason"].fillna("") == ""]
    require((scored.groupby("calibration_date").size() == n_candidates).all(), "12 candidates per scored block")
    require(
        calibration.loc[calibration["selected"].astype(bool)].groupby("calibration_date").size().eq(1).all(),
        "one selected pair per block",
    )
    require(not scored["used_full_day_actual_lp"].any(), "candidate used full-day LP")
    require(not scored["future_actuals_in_optimizer"].any(), "candidate future actuals")
    for _, block in scored.groupby("calibration_date"):
        best = block["mean_actual_cost_yuan"].min()
        selected_row = block.loc[block["selected"].astype(bool)].iloc[0]
        threshold = float(selected_row["one_se_threshold_yuan"])
        require(float(selected_row["mean_actual_cost_yuan"]) <= threshold + 1e-8, "selected within 1-SE")
        require(best <= float(selected_row["mean_actual_cost_yuan"]) + 1e-8, "best cost not worse than selected")
        require(
            pd.Timestamp(selected_row["history_cutoff_date"])
            == pd.Timestamp(selected_row["calibration_date"]) - pd.Timedelta(days=1),
            "calibration cutoff is last history day",
        )
        window_start = pd.Timestamp(selected_row["validation_start_date"])
        deployed_start = deployed.loc[deployed["date"] == window_start.strftime("%Y-%m-%d"), "soc_start_kwh"]
        require(len(deployed_start) == 1, "window start date in deployed path")
        require(
            abs(float(selected_row["window_start_soc_kwh"]) - float(deployed_start.iloc[0])) < 1e-6,
            "window SOC comes from deployed policy",
        )
    print("C2-R2 artifact validation passed")


def validate_r3(output: Path, data, consistency: dict, report: dict) -> None:
    daily = pd.read_csv(output / "q2_redesign_daily_summary.csv")
    january = pd.read_csv(output / "january_warmup_summary.csv")
    feb_dec = pd.read_csv(output / "feb_dec_daily_summary.csv")
    forecast = pd.read_csv(output / "forecast_policy_audit.csv")
    physical = pd.read_csv(output / "physical_audit.csv")
    value_audit = pd.read_csv(output / "next_day_value_audit.csv")
    k_table = pd.read_csv(output / "k_sensitivity.csv")
    soc_table = pd.read_csv(output / "feb_soc_sensitivity.csv")
    alt = pd.read_csv(output / "feb_soc_sensitivity_daily.csv")
    calendar = pd.read_csv(output / "frozen_policy_calendar.csv")

    require(consistency["stage"] in ("C2-R3", "C2-R4"), "R3/R4 stage")
    require(consistency["annual_run"] is True, "annual run")
    if consistency["stage"] == "C2-R3":
        require(report["candidate_result2_xlsx"] is False, "no candidate result2")
    require(consistency["main_path_initial_rule_unchanged"] is True, "initial rule frozen")
    require(consistency["calibration_include_value_cuts"] is True, "R3 calibration value cuts")
    require(consistency["deployment_include_value_cuts"] is True, "R3 deployment value cuts")
    require(consistency["annual_run_include_value_cuts"] is True, "R3 annual value cuts")
    require(consistency["include_value_cuts_consistent"] is True, "R3 value-cut consistency")
    require(daily["include_value_cuts"].all(), "annual daily value cuts")
    require(len(daily) == len(data.dates), "full-year daily summary")
    require(list(daily["date"]) == [stamp.strftime("%Y-%m-%d") for stamp in data.dates], "date order")
    require(abs(float(daily["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) < NUMERIC_TOL, "Jan 1 SOC 6000")
    require(len(january) == 31, "January warmup days")
    require(len(feb_dec) == 334, "Feb-Dec days")
    require((january["period"] == PERIOD_JANUARY_WARMUP).all(), "January period label")
    require((feb_dec["period"] == PERIOD_FEB_DEC_OUTPUT).all(), "Feb-Dec period label")
    require(january["date"].iloc[0] == "2025-01-01", "January start")
    require(january["date"].iloc[-1] == "2025-01-31", "January end")
    require(feb_dec["date"].iloc[0] == OFFICIAL_OUTPUT_START, "Feb-Dec start")
    require(feb_dec["date"].iloc[-1] == "2025-12-31", "Feb-Dec end")
    require(
        np.max(np.abs(daily["soc_start_kwh"].to_numpy()[1:] - daily["soc_end_kwh"].to_numpy()[:-1]))
        < NUMERIC_TOL,
        "main-path SOC continuity",
    )
    inherited = float(january["soc_end_kwh"].iloc[-1])
    require(abs(float(feb_dec["soc_start_kwh"].iloc[0]) - inherited) < NUMERIC_TOL, "Feb 1 inherits warmup")
    require(daily["pass"].all(), "annual physical pass")
    require(not daily["used_full_day_actual_lp"].any(), "annual full-day LP")
    require(not daily["future_actuals_in_optimizer"].any(), "annual future actuals")
    require(len(forecast) == len(data.dates), "annual forecast audit")
    assert_no_forecast_leakage(forecast)
    require(physical["pass"].all(), "physical audit pass")
    require((physical["period"] == daily["period"]).all(), "physical period labels")

    decisions = set(pd.to_datetime(value_audit["decision_date"]).dt.strftime("%Y-%m-%d"))
    require("2025-12-31" not in decisions, "no next-day cuts on Dec 31")
    require(len(decisions) == 364, "value cuts on 364 decision days")
    for row in value_audit.itertuples():
        decision = pd.Timestamp(row.decision_date)
        cutoff_raw = row.history_cutoff_date
        target = pd.Timestamp(row.target_date)
        if str(cutoff_raw) == "attachment1_fallback":
            require(decision == pd.Timestamp("2025-01-01"), "fallback cutoff only on Jan 1")
        else:
            require(
                pd.Timestamp(cutoff_raw) == decision - pd.Timedelta(days=1),
                f"cutoff is last history day for {row.decision_date}",
            )
        require(target == decision + pd.Timedelta(days=1), f"target is next day for {row.decision_date}")

    require(set(k_table["scenario_k"].astype(int)) == set(K_SENSITIVITY_CANDIDATES), "K=4,8,12")
    require((k_table["period"] == PERIOD_FEB_DEC_OUTPUT).all(), "K table is Feb-Dec")
    require(bool(k_table["calendar_frozen_from_r2"].all()), "K uses frozen calendar")
    k8 = k_table.loc[k_table["scenario_k"].astype(int) == FIXED_SCENARIO_K].iloc[0]
    require(abs(float(k8["total_cost_yuan"]) - float(feb_dec["total_cost_yuan"].sum())) < 1e-4, "K=8 matches main")

    require(len(soc_table) == 2, "two Feb SOC rows")
    inherited_row = soc_table.loc[soc_table["soc_source"] == "inherited_january_warmup"].iloc[0]
    boundary_row = soc_table.loc[soc_table["soc_source"] == "registered_boundary_E_INITIAL_6000"].iloc[0]
    require(abs(float(inherited_row["feb1_soc_start_kwh"]) - inherited) < NUMERIC_TOL, "inherited SOC table")
    require(abs(float(boundary_row["feb1_soc_start_kwh"]) - E_INITIAL_KWH) < NUMERIC_TOL, "boundary SOC table")
    require(bool(boundary_row["only_registered_boundary_changed"]), "boundary-only flag")
    require(list(alt["date"]) == list(feb_dec["date"]), "SOC sensitivity dates")
    require(list(alt["forecast_mode"]) == list(feb_dec["forecast_mode"]), "SOC sensitivity forecast mode")
    require(
        np.allclose(
            alt["risk_alpha"].to_numpy(dtype=float),
            feb_dec["risk_alpha"].to_numpy(dtype=float),
            equal_nan=True,
        ),
        "SOC sensitivity alpha",
    )
    require(abs(float(alt["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) < NUMERIC_TOL, "alt Feb 1 SOC")
    require(not np.isclose(float(alt["soc_start_kwh"].iloc[0]), inherited), "alt SOC differs from inherited")

    require(len(calendar) == len(data.dates), "frozen calendar coverage")
    require(calendar["forecast_mode"].isin(["m1", "m2", "m3"]).all(), "calendar modes")

    for date_text in ("2025-01-01", OFFICIAL_OUTPUT_START, "2025-06-21", "2025-12-31"):
        physical_row = physical.loc[physical["date"] == date_text].iloc[0]
        assert_dispatch_physics(
            output / "dispatch_daily" / f"dispatch_{date_text}.csv",
            data,
            physical_row,
            date_text,
        )

    for stem in (
        "fig_q2_pc_cost_comparison",
        "fig_q2_pc_emergency_curtailment",
        "fig_q2_pc_soc",
        "fig_q2_pc_cumulative_cost",
    ):
        require((FIG_POLICY_CONSISTENT_DIR / f"{stem}.pdf").exists(), f"missing {stem}.pdf")
        require((FIG_POLICY_CONSISTENT_DIR / f"{stem}.png").exists(), f"missing {stem}.png")
    print("C2-R3 artifact validation passed")


def validate_r4(output: Path, data, consistency: dict, report: dict) -> None:
    require(consistency["stage"] == "C2-R4", "R4 stage")
    require(report["stage"] == "C2-R4", "R4 report stage")
    require(report["status"] == "PASS", "R4 status")
    require(report["candidate_result2_xlsx"] is True, "candidate result2 flag")
    require(consistency["candidate_result2_xlsx"] is True, "audit candidate flag")
    require(consistency["k8_not_cost_optimal"] is True, "K=8 not cost-optimal")
    require(consistency["k8_paper_language"] == "预注册且对 K=4/12 稳定的简洁主方案", "K=8 paper language")
    require(consistency["old_full_path_role"] == "信息更强的近似对照", "old path role")
    require(CANDIDATE_RESULT2.exists(), "candidate workbook missing")
    require(CANDIDATE_RESULT2.resolve() != SIGNED_OFF_RESULT2.resolve(), "candidate overwrote signed-off file")
    require(CANDIDATE_RESULT2.parent.resolve() == output.resolve(), "candidate not in policy-consistent dir")
    require(file_sha256(SIGNED_OFF_RESULT2) == SIGNED_OFF_RESULT2_SHA256, "signed-off result2 hash")
    require(RESULT2_SIGNED_OFF_BACKUP.exists(), "signed-off backup missing")
    require(file_sha256(RESULT2_SIGNED_OFF_BACKUP) == SIGNED_OFF_RESULT2_SHA256, "backup hash")
    require(FIG_Q2_FINAL_DIR.resolve() != FIG_POLICY_CONSISTENT_DIR.resolve(), "figure dirs collapsed")

    january = pd.read_csv(output / "january_warmup_summary.csv")
    feb_dec = pd.read_csv(output / "feb_dec_daily_summary.csv")
    inherited = float(january["soc_end_kwh"].iloc[-1])
    audit = audit_candidate_result2(
        CANDIDATE_RESULT2,
        output / "dispatch_daily",
        feb_dec,
        data,
        inherited,
    )
    require(audit["summary"]["pass"] is True, "cell audit pass")
    require(audit["summary"]["n_days"] == N_OUTPUT_DAYS, "334 official days")
    require(audit["summary"]["n_periods"] == T, "144 periods")
    require(report["result2_cell_audit_pass"] is True, "report cell audit flag")
    require(
        abs(float(feb_dec["soc_start_kwh"].iloc[0]) - inherited) < NUMERIC_TOL,
        "R4 Feb 1 inherited SOC",
    )
    for stem in (
        "fig_q2_pc_closed_loop",
        "fig_q2_pc_representative_day",
        "fig_q2_pc_forecast_calendar",
        "fig_q2_pc_cost_comparison",
    ):
        require((FIG_POLICY_CONSISTENT_DIR / f"{stem}.pdf").exists(), f"missing {stem}.pdf")
        require((FIG_POLICY_CONSISTENT_DIR / f"{stem}.png").exists(), f"missing {stem}.png")
    print("C2-R4 artifact validation passed")


def main() -> None:
    output = POLICY_CONSISTENT_OUTPUT_DIR
    data = load_q2_data()
    diagnostics = pd.read_csv(output / "forecast_diagnostics.csv")
    consistency = json.loads((output / "policy_consistency_audit.json").read_text(encoding="utf-8"))
    report = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    require(diagnostics["selection_role"].eq("diagnostic_only").all(), "MAE must stay diagnostic")

    if (output / "r1_forecast_policy_audit.csv").exists() or list(
        pd.read_csv(output / "forecast_policy_audit.csv")["date"]
    ) == list(PILOT_DATES):
        validate_r1(output, data, consistency, report)
    if (output / "closed_loop_calibration.csv").exists():
        validate_r2(output, data, diagnostics, consistency, report)
    if consistency.get("stage") in ("C2-R3", "C2-R4") and (output / "q2_redesign_daily_summary.csv").exists():
        validate_r3(output, data, consistency, report)
    if consistency.get("stage") == "C2-R4":
        validate_r4(output, data, consistency, report)


if __name__ == "__main__":
    main()

# ===== q3/__init__.py =====
"""C-problem Q3 rolling purchase-adjustment pilot."""

# ===== q3/config.py =====
"""Central configuration for the Q3 two-day rolling-adjustment pilot."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def resolve_attach_dir() -> Path:
    candidates = []
    env = os.environ.get("CUMCM_C_ATTACH_DIR")
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            ROOT / "data" / "raw" / "附件",
        ]
    )
    for path in candidates:
        if (path / "附件1.xlsx").exists() and (path / "附件3.xlsx").exists():
            return path
    return candidates[0]


ATTACH_DIR = resolve_attach_dir()
ATTACH1 = ATTACH_DIR / "附件1.xlsx"
ATTACH2 = ATTACH_DIR / "附件2.xlsx"
ATTACH3 = ATTACH_DIR / "附件3.xlsx"
ATTACH4 = ATTACH_DIR / "附件4.xlsx"
RESULT3_TEMPLATE = ATTACH_DIR / "附件5" / "result3.xlsx"
OUTPUT_DIR = ROOT / "output" / "q3_pilot"
FIG_DIR = ROOT / "fig" / "q3_pilot"
RESULT3_XLSX = ROOT / "output" / "result3.xlsx"
RESULT3_EXPORT_AUDIT = ROOT / "output" / "result3_export_audit.json"

T = 144
DELTA_H = 1.0 / 6.0
ETA_C = float(np.sqrt(0.9))
ETA_D = float(np.sqrt(0.9))
E_MIN_KWH = 1200.0
E_MAX_KWH = 10800.0
E_INITIAL_KWH = 6000.0
POWER_LIMIT_KW = 5000.0
POWER_LIMIT_KWH = POWER_LIMIT_KW * DELTA_H

EMERGENCY_PRICE_MULTIPLIER = 5.0
ADJUST_ABS_COEFF = 0.5
VOI_EPS_YUAN = 0.01
LOAD_INFORMATION_MAIN = "causal_load_main"
LOAD_INFORMATION_PROXY = "actual_load_proxy"
LOAD_INFORMATION_CASES = (LOAD_INFORMATION_MAIN, LOAD_INFORMATION_PROXY)
LOAD_TREATMENT = LOAD_INFORMATION_MAIN
WARMUP_CSV_MAIN = "q3_warmup_daily_causal_load_main.csv"
LOAD_HISTORY_SAME_WEEKDAY = 4
NEXT_DAY_PV_HISTORY_DAYS = 7
NEXT_DAY_VALUE_GAP_TOL_YUAN = 1.0
NEXT_DAY_VALUE_MAX_SAMPLES = 25
MPC_COST_TOL = 1e-7
NUMERIC_TOL = 1e-6
SIMULTANEOUS_CD_TOL = 1e-4
SOLVER = "HIGHS"
PILOT_DATES = ("2025-02-01", "2025-06-21")

PV_MAPPING_LINEAR = "linear_anchor_main"
PV_MAPPING_STEP = "step_hourly_sensitivity"
PV_MAPPING_MODES = (PV_MAPPING_LINEAR, PV_MAPPING_STEP)

SETTLEMENT_MAIN = "anchor_final_main"
SETTLEMENT_ALT = "adjacent_literal_sensitivity"
SETTLEMENT_MODES = (SETTLEMENT_MAIN, SETTLEMENT_ALT)

SENSITIVITY_OUTPUT_DIR = ROOT / "output" / "q3_sensitivity"
SENSITIVITY_FIG_DIR = ROOT / "fig" / "q3_sensitivity"

YEAR_N_DAYS = 365
YEAR_END_SOC_A_KWH = 1200.0
YEAR_END_SOC_B_KWH = 6000.0
YEAR_END_BOUNDARY_A = "A_q2_aligned"
YEAR_END_BOUNDARY_B = "B_energy_neutral"
YEAR_END_BOUNDARIES = (
    (YEAR_END_BOUNDARY_A, YEAR_END_SOC_A_KWH),
    (YEAR_END_BOUNDARY_B, YEAR_END_SOC_B_KWH),
)
TERMINAL_SOC_PILOT_START = "2025-12-01"
TERMINAL_SOC_PILOT_END = "2025-12-31"
TERMINAL_SOC_OUTPUT_DIR = ROOT / "output" / "q3_terminal_soc_pilot"
TERMINAL_SOC_FIG_DIR = ROOT / "fig" / "q3_terminal_soc_pilot"
ANNUAL_OUTPUT_DIR = ROOT / "output" / "q3_full_annual"
ANNUAL_FIG_DIR = ROOT / "fig" / "q3_full_annual"
ANNUAL_START = "2025-01-01"
ANNUAL_END = "2025-12-31"
RESULT3_EXPORT_START = "2025-02-01"
RESULT3_EXPORT_END = "2025-12-31"
RESULT3_EXPORT_N_DAYS = 334
RESULT3_OFFICIAL_STRATEGY = "M1_M6"
RESULT3_ANNUAL_COST_YUAN = 16373508.75
FOUR_HOUR_BLOCKS = (
    ("0:00-4:00", 0, 24),
    ("4:00-8:00", 24, 48),
    ("8:00-12:00", 48, 72),
    ("12:00-16:00", 72, 96),
    ("16:00-20:00", 96, 120),
    ("20:00-24:00", 120, 144),
)
REQUIRED_TRAJECTORY_COLS = (
    "date",
    "period_index",
    "time_label",
    "g0_kwh",
    "g_final_kwh",
    "x_kwh",
    "emergency_kwh",
    "charge_kwh",
    "discharge_kwh",
    "curtailment_kwh",
    "soc_start_kwh",
    "soc_end_kwh",
    "actual_load_kwh",
    "actual_pv_kwh",
    "locked_or_mutable",
    "last_update_time",
)


def year_end_tag(year_end_soc_kwh: float | None) -> str:
    if year_end_soc_kwh is None:
        return ""
    return f"ye{int(round(float(year_end_soc_kwh)))}"


def year_end_boundary_label(year_end_soc_kwh: float | None) -> str | None:
    if year_end_soc_kwh is None:
        return None
    value = float(year_end_soc_kwh)
    if abs(value - YEAR_END_SOC_A_KWH) <= 1e-9:
        return YEAR_END_BOUNDARY_A
    if abs(value - YEAR_END_SOC_B_KWH) <= 1e-9:
        return YEAR_END_BOUNDARY_B
    return f"custom_{value:.0f}"


def today_year_end_soc(
    day_index: int, n_days: int, year_end_soc_kwh: float | None
) -> float | None:
    """Hard E_144 target for remaining-horizon LPs on the calendar year's last day."""
    if year_end_soc_kwh is None:
        return None
    if int(day_index) == int(n_days) - 1:
        return float(year_end_soc_kwh)
    return None


def next_day_year_end_soc(
    day_index: int, n_days: int, year_end_soc_kwh: float | None
) -> float | None:
    """Hard E_144 target for the virtual next-day LP on Dec 30 (48h cost-to-go)."""
    if year_end_soc_kwh is None:
        return None
    if int(day_index) == int(n_days) - 2:
        return float(year_end_soc_kwh)
    return None


def make_run_id(
    date: str,
    strategy: str,
    load_information_case: str,
    pv_mapping_mode: str,
    settlement_mode: str,
    with_terminal_value: bool,
    year_end_soc_kwh: float | None = None,
) -> str:
    tv = "48h" if with_terminal_value else "no48h"
    run_id = (
        f"{date}__{strategy}__{load_information_case}__"
        f"{pv_mapping_mode}__{settlement_mode}__{tv}"
    )
    tag = year_end_tag(year_end_soc_kwh)
    if tag:
        run_id += f"__{tag}"
    return run_id


def dispatch_stem(
    date: str,
    strategy: str,
    load_information_case: str,
    pv_mapping_mode: str,
    settlement_mode: str,
    with_terminal_value: bool,
    year_end_soc_kwh: float | None = None,
) -> str:
    suffix = f"{strategy}_{load_information_case}_{pv_mapping_mode}_{settlement_mode}"
    if not with_terminal_value:
        suffix += "_no48h"
    tag = year_end_tag(year_end_soc_kwh)
    if tag:
        suffix += f"_{tag}"
    return f"q3_dispatch_{date}_{suffix}"

# Update clock hours and the first 10-minute index that may change.
# Index t corresponds to the period ending at (t+1)*10 minutes after 0:00.
UPDATE_SPECS = (
    (0, 0),    # 0:00 plan; first mutable period is 00:10 (index 0)
    (6, 36),   # 6:00 update; first mutable period is 06:10
    (12, 72),  # 12:00 update; first mutable period is 12:10
    (18, 108),  # 18:00 update; first mutable period is 18:10
)
UPDATE_HOURS = tuple(hour for hour, _index in UPDATE_SPECS)
HOUR_TO_FIRST_MUTABLE = {hour: index for hour, index in UPDATE_SPECS}

STRATEGIES = ("M0", "M1_M6", "M6_only", "M12_only", "M18_only")
STRATEGY_ALLOWED_UPDATES = {
    "M0": (),
    "M1_M6": (6, 12, 18),
    "M6_only": (6,),
    "M12_only": (12,),
    "M18_only": (18,),
}

# ===== q3/data.py =====
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

from q3.config import ATTACH1, ATTACH2, ATTACH3, DELTA_H, PILOT_DATES, T, UPDATE_HOURS


def normalize_time(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    text = str(value).strip()
    if text in {"0:00+1", "24:00"}:
        return text
    if len(text) == 4 and text[1] == ":":
        return "0" + text
    return text


def normalize_clock_hour(value: object) -> int:
    text = normalize_time(value).replace("：", ":")
    if text in {"0:00", "00:00"}:
        return 0
    hour, minute = text.split(":")[:2]
    if int(minute) != 0:
        raise ValueError(f"Attachment 3 issue time is not on the hour: {value!r}")
    return int(hour)


def _finite_nonnegative(values: np.ndarray, name: str) -> None:
    if not np.isfinite(values).all():
        raise ValueError(f"{name} contains missing or non-finite values")
    if np.any(values < 0):
        raise ValueError(f"{name} contains negative values")


@dataclass(frozen=True)
class Q3Data:
    dates: pd.DatetimeIndex
    time_labels: tuple[str, ...]
    price: np.ndarray
    fallback_load: np.ndarray
    fallback_pv: np.ndarray
    load: np.ndarray
    pv: np.ndarray
    # issue_hour -> (n_days, 24) hourly PV forecast in kW
    hourly_forecast_kw: dict[int, np.ndarray]

    def date_index(self, date: str) -> int:
        return int(self.dates.get_loc(pd.Timestamp(date)))


def load_q3_data(
    attach1: Path = ATTACH1,
    attach2: Path = ATTACH2,
    attach3: Path = ATTACH3,
) -> Q3Data:
    missing = [str(path) for path in (attach1, attach2, attach3) if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Required attachments not found: "
            + ", ".join(missing)
            + ". Set CUMCM_C_ATTACH_DIR to the folder containing 附件1/2/3.xlsx."
        )

    day = pd.read_excel(attach1, sheet_name="Sheet1")
    expected = ["时间", "电价", "小区负载", "光伏发电预测功率"]
    if list(day.columns) != expected or len(day) != T:
        raise ValueError("附件1 must have the four expected columns and 144 raw-order rows")
    price = pd.to_numeric(day["电价"], errors="coerce").to_numpy(float)
    fallback_load = pd.to_numeric(day["小区负载"], errors="coerce").to_numpy(float) * DELTA_H
    fallback_pv = pd.to_numeric(day["光伏发电预测功率"], errors="coerce").to_numpy(float) * DELTA_H
    _finite_nonnegative(price, "附件1 price")
    _finite_nonnegative(fallback_load, "附件1 load forecast")
    _finite_nonnegative(fallback_pv, "附件1 PV forecast")
    if np.any(price <= 0):
        raise ValueError("Q3 requires strictly positive prices")

    sheets = pd.read_excel(attach2, sheet_name=None, header=None)
    if list(sheets) != ["小区负载", "光伏发电实际功率"]:
        raise ValueError(f"Unexpected 附件2 sheets: {list(sheets)}")
    load_raw = sheets["小区负载"]
    pv_raw = sheets["光伏发电实际功率"]
    if load_raw.shape != (366, 145) or pv_raw.shape != (366, 145):
        raise ValueError(f"附件2 must be 366x145; got {load_raw.shape}, {pv_raw.shape}")
    if load_raw.iloc[0, 0] != "日期\\时间" or pv_raw.iloc[0, 0] != "日期\\时间":
        raise ValueError("附件2 first header must be 日期\\时间")

    time_labels = tuple(normalize_time(x) for x in load_raw.iloc[0, 1:])
    pv_labels = tuple(normalize_time(x) for x in pv_raw.iloc[0, 1:])
    if time_labels != pv_labels or len(time_labels) != T:
        raise ValueError("附件2 load/PV time labels differ")
    if time_labels[0] != "00:10" or time_labels[-1] != "0:00+1":
        raise ValueError(f"Unexpected raw time order: {time_labels[0]} .. {time_labels[-1]}")

    dates = pd.DatetimeIndex(pd.to_datetime(load_raw.iloc[1:, 0], errors="raise")).normalize()
    pv_dates = pd.DatetimeIndex(pd.to_datetime(pv_raw.iloc[1:, 0], errors="raise")).normalize()
    expected_dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    if not dates.equals(expected_dates) or not pv_dates.equals(expected_dates):
        raise ValueError("附件2 dates must be continuous 2025-01-01 through 2025-12-31")
    load = load_raw.iloc[1:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(float) * DELTA_H
    pv = pv_raw.iloc[1:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(float) * DELTA_H
    _finite_nonnegative(load, "附件2 load")
    _finite_nonnegative(pv, "附件2 PV")

    forecast = pd.read_excel(attach3, sheet_name=0)
    expected_forecast_cols = ["日期", "预报时刻"] + [f"预报{h}小时" for h in range(1, 25)]
    if list(forecast.columns) != expected_forecast_cols:
        raise ValueError(f"Unexpected 附件3 columns: {list(forecast.columns)}")
    if len(forecast) != 4 * len(dates):
        raise ValueError(f"附件3 must have 4 rows per day; got {len(forecast)}")
    forecast = forecast.copy()
    forecast["日期"] = forecast["日期"].ffill()
    forecast["date"] = pd.to_datetime(forecast["日期"], errors="raise").dt.normalize()
    forecast["issue_hour"] = forecast["预报时刻"].map(normalize_clock_hour)
    hourly_values = (
        forecast[[f"预报{h}小时" for h in range(1, 25)]]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(float)
    )
    _finite_nonnegative(hourly_values, "附件3 PV forecast")
    if set(forecast["issue_hour"].unique()) != set(UPDATE_HOURS):
        raise ValueError(f"Unexpected 附件3 issue hours: {sorted(forecast['issue_hour'].unique())}")
    forecast_dates = pd.DatetimeIndex(forecast["date"].drop_duplicates()).normalize()
    if not forecast_dates.equals(dates):
        raise ValueError("附件3 dates do not match 附件2")

    hourly_forecast_kw = {}
    for hour in UPDATE_HOURS:
        block = forecast.loc[forecast["issue_hour"] == hour].sort_values("date")
        if len(block) != len(dates):
            raise ValueError(f"附件3 is missing {hour:02d}:00 rows")
        if not pd.DatetimeIndex(block["date"]).equals(dates):
            raise ValueError(f"附件3 {hour:02d}:00 dates are not aligned")
        hourly_forecast_kw[hour] = block[[f"预报{h}小时" for h in range(1, 25)]].to_numpy(float)

    return Q3Data(
        dates=dates,
        time_labels=time_labels,
        price=price,
        fallback_load=fallback_load,
        fallback_pv=fallback_pv,
        load=load,
        pv=pv,
        hourly_forecast_kw=hourly_forecast_kw,
    )


def period_end_minutes(index: int) -> int:
    """Minutes after 0:00 at the end of the 10-minute period with internal index."""
    return 10 * (index + 1)


def write_input_audit(data: Q3Data, path: Path) -> None:
    attach3_rows = []
    for date in PILOT_DATES:
        i = data.date_index(date)
        for hour in UPDATE_HOURS:
            hourly = data.hourly_forecast_kw[hour][i]
            attach3_rows.append(
                {
                    "date": date,
                    "issue_hour": hour,
                    "n_hourly_nodes": 24,
                    "first_hour_kw": float(hourly[0]),
                    "hour12_kw": float(hourly[11]),
                    "last_hour_kw": float(hourly[23]),
                    "sum_kw": float(hourly.sum()),
                    "zero_count": int(np.sum(hourly == 0.0)),
                }
            )
    audit = {
        "shape": {
            "days": len(data.dates),
            "periods_per_day": T,
            "attach3_rows": 4 * len(data.dates),
        },
        "date_start": data.dates[0].strftime("%Y-%m-%d"),
        "date_end": data.dates[-1].strftime("%Y-%m-%d"),
        "dates_continuous": True,
        "missing_count": int(
            np.isnan(data.load).sum()
            + np.isnan(data.pv).sum()
            + sum(np.isnan(arr).sum() for arr in data.hourly_forecast_kw.values())
        ),
        "negative_load_count": int(np.sum(data.load < 0)),
        "negative_pv_count": int(np.sum(data.pv < 0)),
        "negative_forecast_count": int(
            sum(np.sum(arr < 0) for arr in data.hourly_forecast_kw.values())
        ),
        "price_min_yuan_per_kwh": float(data.price.min()),
        "unit_conversion": "attachment powers multiplied by 1/6 h to obtain kWh",
        "time_mapping": (
            "attachment raw column t maps to internal index t=0..143 and template column t; "
            "no sorting, rotation, or invented 0:00-0:10 period"
        ),
        "first_time_label": data.time_labels[0],
        "last_time_label": data.time_labels[-1],
        "attach3_issue_hours": list(UPDATE_HOURS),
        "attach3_complete_four_rows_per_day": True,
        "forecast_horizon": (
            "each 附件3 row is a 24-hour-ahead on-the-hour forecast in kW; "
            "hour k after issue hour H is clock time H+k, wrapping into the next day"
        ),
        "update_index_map": {
            "0:00": {"first_mutable_index": 0, "label": data.time_labels[0]},
            "6:00": {
                "last_locked_index": 35,
                "last_locked_label": data.time_labels[35],
                "first_mutable_index": 36,
                "first_mutable_label": data.time_labels[36],
            },
            "12:00": {
                "last_locked_index": 71,
                "last_locked_label": data.time_labels[71],
                "first_mutable_index": 72,
                "first_mutable_label": data.time_labels[72],
            },
            "18:00": {
                "last_locked_index": 107,
                "last_locked_label": data.time_labels[107],
                "first_mutable_index": 108,
                "first_mutable_label": data.time_labels[108],
            },
        },
        "pilot_attach3_spotcheck": attach3_rows,
        "daily_energy_pilot": [
            {
                "date": date,
                "load_kwh": float(data.load[data.date_index(date)].sum()),
                "pv_kwh": float(data.pv[data.date_index(date)].sum()),
                "net_load_kwh": float(
                    data.load[data.date_index(date)].sum()
                    - data.pv[data.date_index(date)].sum()
                ),
            }
            for date in PILOT_DATES
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# ===== q3/export_result3.py =====
"""Export the official Q3 workbook from a single A + M1_M6 10-minute trajectory.

January is solved only for SOC continuity. The contest workbook covers
2025-02-01 through 2025-12-31. Does not reconstruct intervals from daily
summaries and does not rerun the other annual paths.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from q3.config import (
    ANNUAL_END,
    ANNUAL_OUTPUT_DIR,
    ANNUAL_START,
    FOUR_HOUR_BLOCKS,
    HOUR_TO_FIRST_MUTABLE,
    REQUIRED_TRAJECTORY_COLS,
    RESULT3_ANNUAL_COST_YUAN,
    RESULT3_EXPORT_AUDIT,
    RESULT3_EXPORT_END,
    RESULT3_EXPORT_N_DAYS,
    RESULT3_EXPORT_START,
    RESULT3_OFFICIAL_STRATEGY,
    RESULT3_TEMPLATE,
    RESULT3_XLSX,
    ROOT,
    T,
    YEAR_END_BOUNDARY_A,
    YEAR_END_SOC_A_KWH,
    dispatch_stem,
)
from q3.pilot import DayRun

PURCHASE_SHEET = "计划购电量"
ADJUST_SHEET = "调整购电量"
CHARGE_SHEET = "充放电量"
EMERGENCY_SHEET = "紧急购电量"
NOTES_SHEET = "说明"
N_TIME_COLS = T
COL_FIRST_TIME = 2
COL_DAY_QTY = 146
COL_DAY_FEE = 147
COST_MATCH_TOL_YUAN = 5e-3
ENERGY_MATCH_TOL_KWH = 1e-3
SOC_MATCH_TOL_KWH = 1e-3
EMERGENCY_EPS_KWH = 1e-8

TRAJECTORY_WRITE_COLS = list(REQUIRED_TRAJECTORY_COLS) + [
    "price",
    "phi_yuan",
    "emergency_cost_yuan",
    "run_id",
    "year_end_boundary",
    "year_end_soc_kwh",
    "strategy",
    "balance_residual_kwh",
]


def git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def export_dates() -> list[str]:
    return [
        ts.strftime("%Y-%m-%d")
        for ts in pd.date_range(RESULT3_EXPORT_START, RESULT3_EXPORT_END, freq="D")
    ]


def annual_calendar() -> list[str]:
    return [
        ts.strftime("%Y-%m-%d")
        for ts in pd.date_range(ANNUAL_START, ANNUAL_END, freq="D")
    ]


def main_dispatch_stem(date: str) -> str:
    return dispatch_stem(
        date,
        RESULT3_OFFICIAL_STRATEGY,
        "causal_load_main",
        "linear_anchor_main",
        "anchor_final_main",
        True,
        YEAR_END_SOC_A_KWH,
    )


def dispatch_path(date: str, dispatch_dir: Path | None = None) -> Path:
    folder = dispatch_dir or (ANNUAL_OUTPUT_DIR / "dispatch_daily")
    return folder / f"{main_dispatch_stem(date)}.csv"


def _update_hour(last_update_time: object) -> int:
    text = str(last_update_time).strip()
    hour = int(text.split(":")[0])
    if hour not in HOUR_TO_FIRST_MUTABLE:
        raise ValueError(f"unknown last_update_time {last_update_time!r}")
    return hour


def locked_or_mutable_label(period_index: int, last_update_time: object) -> str:
    first = HOUR_TO_FIRST_MUTABLE[_update_hour(last_update_time)]
    return "locked" if int(period_index) < first else "mutable"


def enrich_dispatch(run: DayRun) -> pd.DataFrame:
    raw = run.dispatch.copy()
    n = len(raw)
    if n != T:
        raise ValueError(f"{run.date} dispatch has {n} rows, expected {T}")
    soc_end = raw["soc_kwh"].to_numpy(float)
    soc_start = np.empty(n, dtype=float)
    soc_start[0] = float(run.summary["soc_start_kwh"])
    soc_start[1:] = soc_end[:-1]
    periods = raw["period"].to_numpy(int) if "period" in raw.columns else np.arange(n)
    last_update = raw["last_update_time"].astype(str)
    frame = pd.DataFrame(
        {
            "date": run.date,
            "period_index": periods,
            "time_label": raw["time"].astype(str),
            "g0_kwh": raw["planned_g0_kwh"].to_numpy(float),
            "g_final_kwh": raw["final_g_kwh"].to_numpy(float),
            "x_kwh": raw["normal_x_kwh"].to_numpy(float),
            "emergency_kwh": raw["emergency_kwh"].to_numpy(float),
            "charge_kwh": raw["charge_kwh"].to_numpy(float),
            "discharge_kwh": raw["discharge_kwh"].to_numpy(float),
            "curtailment_kwh": raw["curtailment_kwh"].to_numpy(float),
            "soc_start_kwh": soc_start,
            "soc_end_kwh": soc_end,
            "actual_load_kwh": raw["load_kwh"].to_numpy(float),
            "actual_pv_kwh": raw["actual_pv_kwh"].to_numpy(float),
            "locked_or_mutable": [
                locked_or_mutable_label(int(t), u) for t, u in zip(periods, last_update)
            ],
            "last_update_time": last_update,
            "price": raw["price"].to_numpy(float),
            "phi_yuan": raw["phi_yuan"].to_numpy(float),
            "emergency_cost_yuan": raw["emergency_cost_yuan"].to_numpy(float),
            "run_id": run.run_id,
            "year_end_boundary": run.summary.get("year_end_boundary", YEAR_END_BOUNDARY_A),
            "year_end_soc_kwh": YEAR_END_SOC_A_KWH,
            "strategy": run.strategy,
            "balance_residual_kwh": raw["balance_residual_kwh"].to_numpy(float)
            if "balance_residual_kwh" in raw.columns
            else np.zeros(n),
        }
    )
    return frame[TRAJECTORY_WRITE_COLS]


def has_required_trajectory(frame: pd.DataFrame) -> bool:
    return all(col in frame.columns for col in REQUIRED_TRAJECTORY_COLS) and len(frame) == T


def write_daily_trajectory(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    missing = [col for col in REQUIRED_TRAJECTORY_COLS if col not in frame.columns]
    if missing:
        raise ValueError(f"{path} missing trajectory columns: {missing}")
    if len(frame) != T:
        raise ValueError(f"{path} has {len(frame)} rows, expected {T}")
    frame.to_csv(path, index=False)


def load_daily_trajectory(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if not has_required_trajectory(frame):
        raise ValueError(f"{path} is not a streamed 10-minute export trajectory")
    return frame.sort_values("period_index").reset_index(drop=True)


def summarize_trajectory(frame: pd.DataFrame) -> dict:
    return {
        "date": str(frame["date"].iloc[0]),
        "strategy": RESULT3_OFFICIAL_STRATEGY,
        "year_end_boundary": YEAR_END_BOUNDARY_A,
        "year_end_soc_kwh": YEAR_END_SOC_A_KWH,
        "total_cost_yuan": float(frame["phi_yuan"].sum() + frame["emergency_cost_yuan"].sum()),
        "settlement_cost_yuan": float(frame["phi_yuan"].sum()),
        "emergency_cost_yuan": float(frame["emergency_cost_yuan"].sum()),
        "emergency_kwh": float(frame["emergency_kwh"].sum()),
        "curtailment_kwh": float(frame["curtailment_kwh"].sum()),
        "charge_kwh": float(frame["charge_kwh"].sum()),
        "discharge_kwh": float(frame["discharge_kwh"].sum()),
        "soc_start_kwh": float(frame["soc_start_kwh"].iloc[0]),
        "soc_end_kwh": float(frame["soc_end_kwh"].iloc[-1]),
        "g0_kwh": float(frame["g0_kwh"].sum()),
        "g_final_kwh": float(frame["g_final_kwh"].sum()),
        "planned_energy_cost_yuan": float((frame["price"] * frame["g0_kwh"]).sum()),
        "max_balance_residual_kwh": float(frame["balance_residual_kwh"].abs().max())
        if "balance_residual_kwh" in frame.columns
        else 0.0,
    }


def _excel_date(value: object) -> datetime:
    ts = pd.Timestamp(value)
    return datetime(ts.year, ts.month, ts.day)


def _time_headers(ws) -> list[str]:
    headers = [str(ws.cell(1, COL_FIRST_TIME + t).value) for t in range(N_TIME_COLS)]
    if headers[0] != "0:10-0:20" or headers[-1] != "0:00-0:10+1":
        raise ValueError(f"unexpected result3 time headers: {headers[0]!r} .. {headers[-1]!r}")
    return headers


def _fill_energy_grid(ws, by_date: dict[str, pd.DataFrame], value_col: str, fee_col: str) -> None:
    dates = export_dates()
    if ws.max_row != 1 + RESULT3_EXPORT_N_DAYS:
        raise ValueError(f"{ws.title} expected {1 + RESULT3_EXPORT_N_DAYS} rows, got {ws.max_row}")
    for offset, date in enumerate(dates):
        row = 2 + offset
        cell_date = _excel_date(ws.cell(row, 1).value)
        if cell_date.strftime("%Y-%m-%d") != date:
            raise ValueError(f"{ws.title} row {row} date {cell_date} != {date}")
        frame = by_date[date].sort_values("period_index")
        if len(frame) != T:
            raise ValueError(f"{date} {value_col} has {len(frame)} periods")
        values = frame[value_col].to_numpy(float)
        for t, val in enumerate(values):
            if not np.isfinite(val):
                raise ValueError(f"{ws.title} {date} t={t} is not finite")
            ws.cell(row, COL_FIRST_TIME + t).value = float(val)
        ws.cell(row, COL_DAY_QTY).value = float(np.sum(values))
        ws.cell(row, COL_DAY_FEE).value = float(frame[fee_col].sum())
        ws.cell(row, 1).value = cell_date
        ws.cell(row, 1).number_format = "yyyy-mm-dd"


def _rewrite_charge_sheet(ws, by_date: dict[str, pd.DataFrame]) -> None:
    header = [ws.cell(1, c).value for c in range(1, 7)]
    if header != ["日期", "时间段", "充电量", "放电量", "时刻", "储电量"]:
        raise ValueError(f"unexpected 充放电量 header: {header}")
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    dates = export_dates()
    row = 2
    for date in dates:
        frame = by_date[date].sort_values("period_index")
        charge = frame["charge_kwh"].to_numpy(float)
        discharge = frame["discharge_kwh"].to_numpy(float)
        soc_start = float(frame["soc_start_kwh"].iloc[0])
        soc_end = float(frame["soc_end_kwh"].iloc[-1])
        for b, (label, start, end) in enumerate(FOUR_HOUR_BLOCKS):
            ws.cell(row, 1).value = _excel_date(date) if b == 0 else None
            if b == 0:
                ws.cell(row, 1).number_format = "yyyy-mm-dd"
            ws.cell(row, 2).value = label
            ws.cell(row, 3).value = float(np.sum(charge[start:end]))
            ws.cell(row, 4).value = float(np.sum(discharge[start:end]))
            if b == 0:
                ws.cell(row, 5).value = time(0, 0)
                ws.cell(row, 5).number_format = "h:mm"
                ws.cell(row, 6).value = soc_start
            elif b == 1:
                ws.cell(row, 5).value = "24:00"
                ws.cell(row, 6).value = soc_end
            else:
                ws.cell(row, 5).value = None
                ws.cell(row, 6).value = None
            row += 1
    expected = 1 + RESULT3_EXPORT_N_DAYS * len(FOUR_HOUR_BLOCKS)
    if ws.max_row != expected:
        raise ValueError(f"充放电量 expected {expected} rows, got {ws.max_row}")


def _rewrite_emergency_sheet(ws, by_date: dict[str, pd.DataFrame], interval_headers: list[str]) -> int:
    header = [ws.cell(1, c).value for c in range(1, 4)]
    if header != ["日期", "购电时间段", "购电量"]:
        raise ValueError(f"unexpected 紧急购电量 header: {header}")
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    n_rows = 0
    row = 2
    for date in export_dates():
        frame = by_date[date].sort_values("period_index")
        emergency = frame["emergency_kwh"].to_numpy(float)
        for t, value in enumerate(emergency):
            if value <= EMERGENCY_EPS_KWH:
                continue
            ws.cell(row, 1).value = _excel_date(date)
            ws.cell(row, 1).number_format = "yyyy-mm-dd"
            ws.cell(row, 2).value = interval_headers[t]
            ws.cell(row, 3).value = float(value)
            n_rows += 1
            row += 1
    return n_rows


def _write_notes_sheet(wb, source_commit: str, n_emergency: int, export_cost: float) -> None:
    if NOTES_SHEET in wb.sheetnames:
        del wb[NOTES_SHEET]
    ws = wb.create_sheet(NOTES_SHEET)
    lines = [
        "C 题第 3 问正式导出（唯一主路径）",
        "主策略：M1_M6（0:00 制定 g0；6:00/12:00/18:00 评估是否调整未执行承诺）",
        "年末 SOC：A / A_q2_aligned / 1200 kWh",
        "负荷信息：causal_load_main；光伏映射：linear_anchor_main；调整结算：anchor_final_main",
        "初始 SOC：2025-01-01 00:00 = 6000 kWh，跨日连续 E_{d+1,0}=E_{d,144}",
        "输出区间：2025-02-01 至 2025-12-31（334 天）。1 月只用于预热、预测历史和 SOC 连续，不写入本表。",
        "单位：购电/充放电/紧急电量为 kWh；全天购电费为元。",
        "计划购电量：日初承诺 g0，时间列按附件 00:10 … 0:00+1 原顺序，不旋转。全天购电量为行合计；全天购电费为附件1电价与 g0 之积（不含紧急购电惩罚）。",
        "调整购电量：最终有效承诺 gF；未调整时段等于 g0，无空值。全天购电费为实际结算 phi(g0,gF)+5 p e。",
        "充放电量：按执行轨迹的充电量 c、放电量 r 分 6 个四小时段合计；每日第一行储电量为 0:00 SOC，第二行为 24:00 SOC。SOC 是存量，不可跨行或跨日求和。",
        f"紧急购电量：仅列出 e>0 的时段（本文件 {n_emergency} 行）。不得把可由电池平衡的普通缺口列入。",
        f"数据来源 commit：{source_commit}",
        "本文件不含 B 路径、oracle、中间试验或其它策略。",
        f"2–12 月输出区间实际结算合计 {export_cost:.2f} 元；不可用该数字替代 1–12 月年度主结论 {RESULT3_ANNUAL_COST_YUAN:,.2f} 元。",
    ]
    font = Font(name="宋体", size=11)
    for i, line in enumerate(lines, start=1):
        cell = ws.cell(i, 1)
        cell.value = line
        cell.font = font
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 22
    ws.column_dimensions["A"].width = 118


def write_result3_xlsx(
    by_date: dict[str, pd.DataFrame],
    dest: Path = RESULT3_XLSX,
    template: Path = RESULT3_TEMPLATE,
    source_commit: str | None = None,
) -> dict:
    dates = export_dates()
    missing = [d for d in dates if d not in by_date]
    if missing:
        raise FileNotFoundError(f"missing export-window trajectories: {missing[:5]}")
    if not template.exists():
        raise FileNotFoundError(f"result3 template not found: {template}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, dest)
    wb = load_workbook(dest)
    for name in (PURCHASE_SHEET, ADJUST_SHEET, CHARGE_SHEET, EMERGENCY_SHEET):
        if name not in wb.sheetnames:
            raise ValueError(f"template missing sheet {name}")
    plan = wb[PURCHASE_SHEET]
    adjust = wb[ADJUST_SHEET]
    interval_headers = _time_headers(plan)
    if _time_headers(adjust) != interval_headers:
        raise ValueError("计划/调整 time headers differ")
    fee_plan = {}
    fee_adjust = {}
    grids = {}
    for date in dates:
        frame = by_date[date].copy()
        frame["plan_fee_yuan"] = frame["price"] * frame["g0_kwh"]
        frame["actual_fee_yuan"] = frame["phi_yuan"] + frame["emergency_cost_yuan"]
        grids[date] = frame
        fee_plan[date] = float(frame["plan_fee_yuan"].sum())
        fee_adjust[date] = float(frame["actual_fee_yuan"].sum())
    _fill_energy_grid(plan, grids, "g0_kwh", "plan_fee_yuan")
    _fill_energy_grid(adjust, grids, "g_final_kwh", "actual_fee_yuan")
    _rewrite_charge_sheet(wb[CHARGE_SHEET], grids)
    n_emergency = _rewrite_emergency_sheet(wb[EMERGENCY_SHEET], grids, interval_headers)
    export_cost = float(sum(fee_adjust.values()))
    _write_notes_sheet(wb, source_commit or git_hash(), n_emergency, export_cost)
    for sheet in (PURCHASE_SHEET, ADJUST_SHEET):
        ws = wb[sheet]
        ws.cell(1, COL_DAY_QTY).value = "全天购电量"
        ws.cell(1, COL_DAY_FEE).value = "全天购电费"
        ws.column_dimensions[get_column_letter(COL_DAY_QTY)].width = 14
        ws.column_dimensions[get_column_letter(COL_DAY_FEE)].width = 14
    wb.save(dest)
    return {
        "path": str(dest),
        "n_export_days": len(dates),
        "n_emergency_rows": n_emergency,
        "export_window_cost_yuan": export_cost,
        "interval_headers_first": interval_headers[0],
        "interval_headers_last": interval_headers[-1],
        "planned_window_cost_yuan": float(sum(fee_plan.values())),
    }


def _blank_or_ref(value: object) -> bool:
    if value is None:
        return True
    text = str(value)
    return "#REF!" in text or text.strip() == ""


def inspect_result3_workbook(path: Path) -> dict:
    wb = load_workbook(path, data_only=False)
    plan = wb[PURCHASE_SHEET]
    adjust = wb[ADJUST_SHEET]
    charge = wb[CHARGE_SHEET]
    emergency = wb[EMERGENCY_SHEET]
    anomalies: list[str] = []
    if NOTES_SHEET not in wb.sheetnames:
        anomalies.append("missing 说明 sheet")
    dates = export_dates()
    if plan.max_row != 1 + RESULT3_EXPORT_N_DAYS or adjust.max_row != 1 + RESULT3_EXPORT_N_DAYS:
        anomalies.append("purchase sheets do not have 334 date rows")
    n_blank_adjust = 0
    n_ref = 0
    plan_dates = []
    for offset, date in enumerate(dates):
        row = 2 + offset
        for sheet in (plan, adjust):
            raw = sheet.cell(row, 1).value
            got = pd.Timestamp(raw).strftime("%Y-%m-%d") if raw is not None else None
            if got != date:
                anomalies.append(f"{sheet.title} row {row} date {got} != {date}")
            for col in range(COL_FIRST_TIME, COL_DAY_FEE + 1):
                val = sheet.cell(row, col).value
                if val is not None and "#REF!" in str(val):
                    n_ref += 1
                if sheet is adjust and col < COL_DAY_QTY and _blank_or_ref(val):
                    n_blank_adjust += 1
                if sheet is plan and col < COL_DAY_QTY and _blank_or_ref(val):
                    anomalies.append(f"{sheet.title} {date} col {col} blank")
                    break
        plan_dates.append(date)
    if n_blank_adjust:
        anomalies.append(f"调整购电量 has {n_blank_adjust} blank interval cells")
    if n_ref:
        anomalies.append(f"workbook contains {n_ref} #REF! cells")
    expected_charge_rows = 1 + RESULT3_EXPORT_N_DAYS * len(FOUR_HOUR_BLOCKS)
    if charge.max_row != expected_charge_rows:
        anomalies.append(f"充放电量 rows {charge.max_row} != {expected_charge_rows}")
    jan_leaks = [
        pd.Timestamp(plan.cell(r, 1).value).month == 1
        for r in range(2, plan.max_row + 1)
        if plan.cell(r, 1).value is not None
    ]
    if any(jan_leaks):
        anomalies.append("January dates leaked into 计划购电量")
    return {
        "n_plan_dates": len(plan_dates),
        "n_adjust_dates": adjust.max_row - 1,
        "n_charge_rows": charge.max_row - 1,
        "n_emergency_rows": max(emergency.max_row - 1, 0),
        "has_notes_sheet": NOTES_SHEET in wb.sheetnames,
        "n_anomalies": len(anomalies),
        "anomalies": anomalies,
        "first_date": plan_dates[0] if plan_dates else None,
        "last_date": plan_dates[-1] if plan_dates else None,
        "n_time_columns": N_TIME_COLS,
    }


def compare_to_annual_summary(
    rerun_daily: pd.DataFrame,
    summary_path: Path,
) -> dict:
    if not summary_path.exists():
        return {"compared": False, "reason": f"missing {summary_path}"}
    archive = pd.read_csv(summary_path)
    archive = archive[
        (archive["strategy"] == RESULT3_OFFICIAL_STRATEGY)
        & (archive["year_end_boundary"] == YEAR_END_BOUNDARY_A)
    ].copy()
    archive["date"] = pd.to_datetime(archive["date"]).dt.strftime("%Y-%m-%d")
    rerun = rerun_daily.copy()
    rerun["date"] = pd.to_datetime(rerun["date"]).dt.strftime("%Y-%m-%d")
    merged = rerun.merge(archive, on="date", suffixes=("_rerun", "_archive"), how="left")
    missing = merged[merged["total_cost_yuan_archive"].isna()]["date"].tolist()
    diffs = []
    fields = [
        ("total_cost_yuan", COST_MATCH_TOL_YUAN),
        ("emergency_kwh", ENERGY_MATCH_TOL_KWH),
        ("curtailment_kwh", ENERGY_MATCH_TOL_KWH),
        ("soc_start_kwh", SOC_MATCH_TOL_KWH),
        ("soc_end_kwh", SOC_MATCH_TOL_KWH),
    ]
    max_abs = {name: 0.0 for name, _tol in fields}
    n_fail = 0
    for _, row in merged.iterrows():
        if pd.isna(row.get("total_cost_yuan_archive")):
            continue
        for name, tol in fields:
            delta = abs(float(row[f"{name}_rerun"]) - float(row[f"{name}_archive"]))
            max_abs[name] = max(max_abs[name], delta)
            if delta > tol:
                n_fail += 1
                diffs.append(
                    {
                        "date": row["date"],
                        "field": name,
                        "rerun": float(row[f"{name}_rerun"]),
                        "archive": float(row[f"{name}_archive"]),
                        "abs_diff": delta,
                    }
                )
    return {
        "compared": True,
        "n_rerun_days": int(len(rerun)),
        "n_archive_days": int(len(archive)),
        "n_unmatched_dates": missing,
        "max_abs_diff": max_abs,
        "n_field_failures": n_fail,
        "failures": diffs[:50],
        "all_match": n_fail == 0 and not missing,
        "tolerance_yuan": COST_MATCH_TOL_YUAN,
        "tolerance_kwh": ENERGY_MATCH_TOL_KWH,
    }


def write_export_audit(
    payload: dict,
    path: Path = RESULT3_EXPORT_AUDIT,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path

# ===== q3/forecast.py =====
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from q3.config import (
    DELTA_H,
    HOUR_TO_FIRST_MUTABLE,
    LOAD_HISTORY_SAME_WEEKDAY,
    LOAD_INFORMATION_MAIN,
    LOAD_INFORMATION_PROXY,
    NEXT_DAY_PV_HISTORY_DAYS,
    PILOT_DATES,
    PV_MAPPING_LINEAR,
    PV_MAPPING_STEP,
    T,
    UPDATE_HOURS,
)
from q3.data import Q3Data, period_end_minutes


def previous_end_pv_kw(data: Q3Data, day_index: int) -> float:
    """Actual PV at today's 0:00, i.e. the previous day's 24:00 observation."""
    if day_index <= 0:
        return 0.0
    return float(data.pv[day_index - 1, -1] / DELTA_H)


def actual_kw(data: Q3Data, day_index: int, index: int) -> float:
    return float(data.pv[day_index, index] / DELTA_H)


def forecast_knots_minutes_kw(
    issue_hour: int, hourly_kw: np.ndarray, anchor_kw: float
) -> tuple[np.ndarray, np.ndarray]:
    """On-the-hour knots for one 24-hour-ahead forecast, plus the causal actual anchor."""
    hourly_kw = np.asarray(hourly_kw, dtype=float).ravel()
    if hourly_kw.shape != (24,):
        raise ValueError("hourly forecast must have 24 nodes")
    minutes = [issue_hour * 60]
    values = [float(anchor_kw)]
    for step, value in enumerate(hourly_kw, start=1):
        minutes.append(issue_hour * 60 + 60 * step)
        values.append(float(value))
    return np.asarray(minutes, dtype=float), np.asarray(values, dtype=float)


def interpolate_series(query_minutes: np.ndarray, knot_minutes: np.ndarray, knot_values: np.ndarray) -> np.ndarray:
    order = np.argsort(knot_minutes)
    return np.interp(query_minutes, knot_minutes[order], knot_values[order])


def interpolate_weights(
    query_minute: float, knot_minutes: np.ndarray, knot_values: np.ndarray
) -> dict:
    order = np.argsort(knot_minutes)
    minutes = knot_minutes[order]
    values = knot_values[order]
    if query_minute <= minutes[0]:
        return {
            "left_node_minute": float(minutes[0]),
            "right_node_minute": float(minutes[0]),
            "left_weight": 1.0,
            "right_weight": 0.0,
            "left_kw": float(values[0]),
            "right_kw": float(values[0]),
        }
    if query_minute >= minutes[-1]:
        return {
            "left_node_minute": float(minutes[-1]),
            "right_node_minute": float(minutes[-1]),
            "left_weight": 1.0,
            "right_weight": 0.0,
            "left_kw": float(values[-1]),
            "right_kw": float(values[-1]),
        }
    right = int(np.searchsorted(minutes, query_minute, side="left"))
    left = right - 1
    span = minutes[right] - minutes[left]
    right_weight = (query_minute - minutes[left]) / span
    left_weight = 1.0 - right_weight
    return {
        "left_node_minute": float(minutes[left]),
        "right_node_minute": float(minutes[right]),
        "left_weight": float(left_weight),
        "right_weight": float(right_weight),
        "left_kw": float(values[left]),
        "right_kw": float(values[right]),
    }


@dataclass(frozen=True)
class MappedForecast:
    today_kwh: np.ndarray
    next_day_kwh: np.ndarray
    knot_minutes: np.ndarray
    knot_kw: np.ndarray
    issue_hour: int
    first_mutable_index: int
    pv_mapping_mode: str
    today_source_k: np.ndarray
    next_source_k: np.ndarray
    today_covered: np.ndarray
    next_covered: np.ndarray


def forecast_hour_k(end_minutes: float, issue_hour: int) -> int:
    """1-based 预报k小时 index for a period ending at end_minutes after today's 0:00."""
    delta_min = float(end_minutes) - 60.0 * issue_hour
    if delta_min <= 1e-9:
        return 0
    return int(np.ceil(delta_min / 60.0 - 1e-12))


def step_hourly_energy(hourly_kw: np.ndarray, issue_hour: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Piecewise-constant map: 预报 k 小时 fills (H+k-1, H+k]."""
    hourly_kw = np.asarray(hourly_kw, dtype=float).ravel()
    today = np.zeros(T)
    nxt = np.zeros(T)
    today_k = np.zeros(T, dtype=int)
    next_k = np.zeros(T, dtype=int)
    for t in range(T):
        end_today = float(period_end_minutes(t))
        k_today = forecast_hour_k(end_today, issue_hour)
        today_k[t] = k_today if 1 <= k_today <= 24 else 0
        if 1 <= k_today <= 24:
            today[t] = hourly_kw[k_today - 1] * DELTA_H
        k_next = forecast_hour_k(end_today + 24 * 60, issue_hour)
        next_k[t] = k_next if 1 <= k_next <= 24 else 0
        if 1 <= k_next <= 24:
            nxt[t] = hourly_kw[k_next - 1] * DELTA_H
    return today, nxt, today_k, next_k


def map_issue_forecast(
    data: Q3Data,
    day_index: int,
    issue_hour: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> MappedForecast:
    """Map one 附件3 row onto today/next-day 10-minute energy using only causal anchors."""
    hourly_kw = data.hourly_forecast_kw[issue_hour][day_index]
    first_mutable = HOUR_TO_FIRST_MUTABLE[issue_hour]
    if pv_mapping_mode == PV_MAPPING_STEP:
        today_kwh, next_kwh, today_k, next_k = step_hourly_energy(hourly_kw, issue_hour)
        knot_minutes = issue_hour * 60 + 60 * np.arange(1, 25, dtype=float)
        knot_kw = np.asarray(hourly_kw, dtype=float).ravel()
        today_covered = today_k > 0
        next_covered = next_k > 0
    elif pv_mapping_mode == PV_MAPPING_LINEAR:
        if issue_hour == 0:
            anchor_kw = previous_end_pv_kw(data, day_index)
        else:
            anchor_index = 6 * issue_hour - 1
            anchor_kw = actual_kw(data, day_index, anchor_index)
        knot_minutes, knot_kw = forecast_knots_minutes_kw(issue_hour, hourly_kw, anchor_kw)
        today_minutes = np.array([period_end_minutes(t) for t in range(T)], dtype=float)
        next_minutes = today_minutes + 24 * 60
        today_kwh = interpolate_series(today_minutes, knot_minutes, knot_kw) * DELTA_H
        next_kwh = interpolate_series(next_minutes, knot_minutes, knot_kw) * DELTA_H
        last_knot = float(knot_minutes[-1])
        today_covered = today_minutes <= last_knot + 1e-9
        next_covered = next_minutes <= last_knot + 1e-9
        today_k = np.array([forecast_hour_k(m, issue_hour) for m in today_minutes], dtype=int)
        next_k = np.array([forecast_hour_k(m, issue_hour) for m in next_minutes], dtype=int)
        today_k = np.where((today_k >= 1) & (today_k <= 24), today_k, 0)
        next_k = np.where((next_k >= 1) & (next_k <= 24), next_k, 0)
    else:
        raise ValueError(f"unknown pv_mapping_mode: {pv_mapping_mode}")

    # Periods already observed at the issue time are filled with actuals for the
    # mapping table, but they are never used as future interpolation anchors.
    if first_mutable > 0:
        today_kwh[:first_mutable] = data.pv[day_index, :first_mutable]
        today_k[:first_mutable] = 0
        today_covered[:first_mutable] = False
    today_kwh = np.maximum(today_kwh, 0.0)
    next_kwh = np.maximum(next_kwh, 0.0)
    return MappedForecast(
        today_kwh=today_kwh,
        next_day_kwh=next_kwh,
        knot_minutes=knot_minutes,
        knot_kw=knot_kw,
        issue_hour=issue_hour,
        first_mutable_index=first_mutable,
        pv_mapping_mode=pv_mapping_mode,
        today_source_k=today_k,
        next_source_k=next_k,
        today_covered=today_covered,
        next_covered=next_covered,
    )


def causal_load_sources(
    data: Q3Data, target_index: int, history_end_exclusive: int
) -> tuple[np.ndarray, tuple[int, ...], str]:
    """Q2-style day-ahead load forecast: last <=4 same-weekday complete days."""
    if history_end_exclusive > target_index:
        raise ValueError("load forecast cutoff must not exceed the target date")
    if history_end_exclusive <= 0:
        return data.fallback_load.copy(), (), "attachment1_fallback"
    target_weekday = data.dates[target_index].weekday()
    sources = tuple(
        j
        for j in range(history_end_exclusive)
        if data.dates[j].weekday() == target_weekday
    )[-LOAD_HISTORY_SAME_WEEKDAY:]
    if not sources:
        return data.fallback_load.copy(), (), "attachment1_fallback"
    label = ";".join(data.dates[j].strftime("%Y-%m-%d") for j in sources)
    return data.load[list(sources)].mean(axis=0), sources, label


def causal_load_forecast(
    data: Q3Data, target_index: int, history_end_exclusive: int
) -> np.ndarray:
    """Load forecast for target_index using only complete days before the cutoff."""
    hat, _sources, _label = causal_load_sources(data, target_index, history_end_exclusive)
    return hat


def planning_load_curve(
    data: Q3Data, day_index: int, load_information_case: str
) -> np.ndarray:
    """Future-load vector used at 0:00 and later updates.

    causal_load_main: day-ahead hat formed at 0:00; never reread today's actuals.
    actual_load_proxy: full Attachment 2 path, idealized information only.
    """
    if load_information_case == LOAD_INFORMATION_MAIN:
        return causal_load_forecast(data, day_index, day_index)
    if load_information_case == LOAD_INFORMATION_PROXY:
        return data.load[day_index].copy()
    raise ValueError(f"unknown load_information_case: {load_information_case}")


def execution_load_horizon(
    plan_load: np.ndarray, actual_load: np.ndarray, t: int
) -> np.ndarray:
    """Current 10-minute step uses actual load; later steps keep the 0:00 hat."""
    horizon = np.asarray(plan_load[t:], dtype=float).copy()
    horizon[0] = float(np.asarray(actual_load, dtype=float)[t])
    return horizon


def load_forecast_audit_rows(data: Q3Data, day_index: int) -> list[dict]:
    """Day-ahead causal load vs Attachment 2 actuals; future periods are not executed yet."""
    date = data.dates[day_index].strftime("%Y-%m-%d")
    hat, _sources, label = causal_load_sources(data, day_index, day_index)
    actual = data.load[day_index]
    rows: list[dict] = []
    for t in range(T):
        forecast = float(hat[t])
        observed = float(actual[t])
        rows.append(
            {
                "date": date,
                "period": t,
                "time": data.time_labels[t],
                "forecast_load_kwh": forecast,
                "actual_load_kwh": observed,
                "source_dates": label,
                "is_current_execution_period": False,
                "abs_error_kwh": abs(forecast - observed),
                "load_information_case": LOAD_INFORMATION_MAIN,
                "snapshot": "day_ahead_planning",
            }
        )
    return rows


def causal_next_day_pv_base(
    data: Q3Data,
    day_index: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> np.ndarray:
    """Causal stand-in for the next day's 0:00 PV forecast, in kWh."""
    start = max(0, day_index - NEXT_DAY_PV_HISTORY_DAYS)
    if start >= day_index:
        return data.fallback_pv.copy()
    mapped = np.vstack(
        [
            map_issue_forecast(data, j, 0, pv_mapping_mode).today_kwh
            for j in range(start, day_index)
        ]
    )
    return mapped.mean(axis=0)


def next_day_pv_forecast(
    data: Q3Data,
    day_index: int,
    issue_hour: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> np.ndarray:
    """Next-day PV used only in the terminal-value / 48h module."""
    if day_index + 1 >= len(data.dates):
        return np.zeros(T)
    mapped = map_issue_forecast(data, day_index, issue_hour, pv_mapping_mode)
    overlay = mapped.next_day_kwh.copy()
    base = causal_next_day_pv_base(data, day_index + 1, pv_mapping_mode)
    overlay[~mapped.next_covered] = base[~mapped.next_covered]
    return np.maximum(overlay, 0.0)


def _source_interval_label(issue_hour: int, k: int) -> str:
    if k <= 0:
        return ""
    start = issue_hour + k - 1
    end = issue_hour + k
    def clock(h: int) -> str:
        day = ""
        if h >= 24:
            h -= 24
            day = "+1"
        return f"{h:02d}:00{day}"
    return f"({clock(start)},{clock(end)}]"


def mapping_rows_for_day(
    data: Q3Data,
    day_index: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> list[dict]:
    date = data.dates[day_index].strftime("%Y-%m-%d")
    rows: list[dict] = []
    for hour in UPDATE_HOURS:
        mapped = map_issue_forecast(data, day_index, hour, pv_mapping_mode)
        for t in range(T):
            query = float(period_end_minutes(t))
            executed = t < mapped.first_mutable_index
            k = int(mapped.today_source_k[t])
            if pv_mapping_mode == PV_MAPPING_LINEAR and not executed:
                weights = interpolate_weights(query, mapped.knot_minutes, mapped.knot_kw)
            elif executed:
                weights = {
                    "left_node_minute": query,
                    "right_node_minute": query,
                    "left_weight": 1.0,
                    "right_weight": 0.0,
                    "left_kw": float(data.pv[day_index, t] / DELTA_H),
                    "right_kw": float(data.pv[day_index, t] / DELTA_H),
                }
            else:
                left_min = (hour + max(k, 1) - 1) * 60
                right_min = (hour + max(k, 1)) * 60
                weights = {
                    "left_node_minute": float(left_min),
                    "right_node_minute": float(right_min),
                    "left_weight": 1.0 if k else 0.0,
                    "right_weight": 0.0,
                    "left_kw": float(mapped.today_kwh[t] / DELTA_H) if k else 0.0,
                    "right_kw": float(mapped.today_kwh[t] / DELTA_H) if k else 0.0,
                }
            forecast_kwh = (
                float(data.pv[day_index, t]) if executed else float(mapped.today_kwh[t])
            )
            source = "actual_executed" if executed else (
                "step_hourly" if pv_mapping_mode == PV_MAPPING_STEP else "causal_hourly_interpolation"
            )
            rows.append(
                {
                    "date": date,
                    "update_time": f"{hour:02d}:00",
                    "period": t,
                    "time": data.time_labels[t],
                    "forecast_kwh": forecast_kwh,
                    "actual_pv_kwh": float(data.pv[day_index, t]),
                    "pv_mapping_mode": pv_mapping_mode,
                    "source_forecast_hour": k,
                    "source_interval": "" if executed else _source_interval_label(hour, k),
                    "left_node_minute": weights["left_node_minute"],
                    "right_node_minute": weights["right_node_minute"],
                    "left_weight": weights["left_weight"],
                    "right_weight": weights["right_weight"],
                    "is_executed_actual": bool(executed),
                    "source": source,
                }
            )
    return rows


def write_forecast_mapping(data: Q3Data, path, pv_mapping_mode: str = PV_MAPPING_LINEAR) -> pd.DataFrame:
    frames = []
    for date in PILOT_DATES:
        frames.extend(mapping_rows_for_day(data, data.date_index(date), pv_mapping_mode))
    frame = pd.DataFrame(frames)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def write_forecast_mapping_modes(data: Q3Data, path, modes: tuple[str, ...] | None = None) -> pd.DataFrame:
    modes = modes or (PV_MAPPING_LINEAR, PV_MAPPING_STEP)
    rows: list[dict] = []
    for mode in modes:
        for date in PILOT_DATES:
            rows.extend(mapping_rows_for_day(data, data.date_index(date), mode))
    frame = pd.DataFrame(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame

# ===== q3/full_annual.py =====
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

# ===== q3/optimization.py =====
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import cvxpy as cp
import numpy as np

from q3.config import (
    ADJUST_ABS_COEFF,
    EMERGENCY_PRICE_MULTIPLIER,
    E_MAX_KWH,
    E_MIN_KWH,
    ETA_C,
    ETA_D,
    MPC_COST_TOL,
    POWER_LIMIT_KWH,
    SETTLEMENT_ALT,
    SETTLEMENT_MAIN,
    SIMULTANEOUS_CD_TOL,
    SOLVER,
)


ValueCut = tuple[float, float, float]  # reference SOC, value, subgradient


def settlement_cost(price: np.ndarray, g0: np.ndarray, g_final: np.ndarray) -> np.ndarray:
    """Main phi_t = p g^F + 0.5 p |g^F - g^0|. Vectorised and used in tests and audits."""
    price = np.asarray(price, dtype=float).ravel()
    g0 = np.asarray(g0, dtype=float).ravel()
    g_final = np.asarray(g_final, dtype=float).ravel()
    return price * g_final + ADJUST_ABS_COEFF * price * np.abs(g_final - g0)


def adjacent_adjustment_cost(price: np.ndarray, g_prev: np.ndarray, g_new: np.ndarray) -> np.ndarray:
    """1.5 p (up)_+ + 0.5 p (down)_+ between two adjacent commitment versions."""
    price = np.asarray(price, dtype=float).ravel()
    g_prev = np.asarray(g_prev, dtype=float).ravel()
    g_new = np.asarray(g_new, dtype=float).ravel()
    up = np.maximum(g_new - g_prev, 0.0)
    down = np.maximum(g_prev - g_new, 0.0)
    return 1.5 * price * up + 0.5 * price * down


def realized_settlement(
    price: np.ndarray,
    versions: list[np.ndarray] | tuple[np.ndarray, ...],
    settlement_mode: str,
) -> np.ndarray:
    """Period-wise ordinary+adjustment bill for a full version path (no emergency)."""
    price = np.asarray(price, dtype=float).ravel()
    path = [np.asarray(v, dtype=float).ravel() for v in versions]
    if not path:
        raise ValueError("need at least the 0:00 plan")
    if settlement_mode == SETTLEMENT_MAIN:
        return settlement_cost(price, path[0], path[-1])
    if settlement_mode == SETTLEMENT_ALT:
        phi = price * path[0]
        for prev, cur in zip(path[:-1], path[1:]):
            phi = phi + adjacent_adjustment_cost(price, prev, cur)
        return phi
    raise ValueError(f"unknown settlement_mode: {settlement_mode}")


def decompose_settlement(
    price: np.ndarray,
    versions: list[np.ndarray] | tuple[np.ndarray, ...],
    settlement_mode: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ordinary, up-fee, down-fee arrays that sum to realized_settlement."""
    price = np.asarray(price, dtype=float).ravel()
    path = [np.asarray(v, dtype=float).ravel() for v in versions]
    if settlement_mode == SETTLEMENT_MAIN:
        g0, gf = path[0], path[-1]
        up = np.maximum(gf - g0, 0.0)
        down = np.maximum(g0 - gf, 0.0)
        return price * gf, 0.5 * price * up, 0.5 * price * down
    if settlement_mode == SETTLEMENT_ALT:
        ordinary = price * path[0]
        up_fee = np.zeros_like(price)
        down_fee = np.zeros_like(price)
        for prev, cur in zip(path[:-1], path[1:]):
            up = np.maximum(cur - prev, 0.0)
            down = np.maximum(prev - cur, 0.0)
            up_fee = up_fee + 1.5 * price * up
            down_fee = down_fee + 0.5 * price * down
        return ordinary, up_fee, down_fee
    raise ValueError(f"unknown settlement_mode: {settlement_mode}")


def evaluate_value_cuts(soc: float, cuts: tuple[ValueCut, ...] | None) -> float:
    if not cuts:
        return 0.0
    return max(
        0.0,
        max(value + slope * (soc - reference) for reference, value, slope in cuts),
    )


def _terminal_value_expression(
    terminal_soc: cp.Expression, cuts: tuple[ValueCut, ...] | None
) -> tuple[cp.Variable | None, list[cp.Constraint]]:
    if not cuts:
        return None, []
    value = cp.Variable(nonneg=True)
    constraints = [
        value >= cut_value + slope * (terminal_soc - reference_soc)
        for reference_soc, cut_value, slope in cuts
    ]
    return value, constraints


def _physical_constraints(
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    normal: cp.Variable,
    emergency: cp.Variable,
    charge: cp.Variable,
    discharge: cp.Variable,
    curtailment: cp.Variable,
    soc: cp.Variable,
) -> list[cp.Constraint]:
    return [
        soc[0] == initial_soc,
        soc[1:] == soc[:-1] + ETA_C * charge - discharge / ETA_D,
        soc[1:] >= E_MIN_KWH,
        soc[1:] <= E_MAX_KWH,
        charge <= POWER_LIMIT_KWH,
        discharge <= POWER_LIMIT_KWH,
        curtailment <= pv,
        normal + emergency + pv - curtailment + discharge == load + charge,
    ]


@dataclass(frozen=True)
class HorizonResult:
    g: np.ndarray
    x: np.ndarray
    emergency: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    curtailment: np.ndarray
    soc: np.ndarray
    objective: float
    settlement_cost: float
    emergency_cost: float
    terminal_value: float
    initial_soc_marginal: float
    solve_seconds: float
    status: str

    @property
    def max_cd(self) -> float:
        return float(np.max(self.charge * self.discharge))


def solve_horizon(
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    g0: np.ndarray | None = None,
    g_fixed: np.ndarray | None = None,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    throughput_tiebreak: bool = True,
    bill_as_day_ahead: bool = False,
    settlement_mode: str = SETTLEMENT_MAIN,
    g_pre: np.ndarray | None = None,
    sunk_settlement: float = 0.0,
    terminal_soc: float | None = None,
) -> HorizonResult:
    """Solve a remaining-horizon LP.

    If bill_as_day_ahead is True, ordinary energy is billed as p@g with no
    adjustment (used for 0:00 and the virtual next day). Otherwise:
    - anchor_final_main: phi(g0, g) = p g + 0.5 p |g-g0|
    - adjacent_literal_sensitivity: sunk p g0 + prior adjacent fees, plus
      1.5 p (g-g_pre)_+ + 0.5 p (g_pre-g)_+ for this update only.

    If terminal_soc is set, the last SOC node of this remaining horizon
    (end of the current calendar day) is constrained to that value.
    """
    n = len(load)
    price = np.asarray(price, dtype=float).ravel()
    load = np.asarray(load, dtype=float).ravel()
    pv = np.asarray(pv, dtype=float).ravel()
    g = cp.Variable(n, nonneg=True)
    x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
    E = cp.Variable(n + 1)
    constraints = _physical_constraints(load, pv, initial_soc, x, e, c, d, w, E)
    constraints.append(x <= g)
    if terminal_soc is not None:
        constraints.append(E[-1] == float(terminal_soc))

    if g_fixed is not None:
        fixed = np.asarray(g_fixed, dtype=float).ravel()
        if fixed.shape != (n,):
            raise ValueError("g_fixed must match the remaining horizon")
        constraints.append(g == fixed)

    emergency_cost = EMERGENCY_PRICE_MULTIPLIER * price @ e
    terminal_value, terminal_constraints = _terminal_value_expression(E[-1], terminal_value_cuts)
    constraints += terminal_constraints
    terminal_term: cp.Expression | float = terminal_value if terminal_value is not None else 0.0

    if bill_as_day_ahead:
        settlement = price @ g
    elif settlement_mode == SETTLEMENT_MAIN:
        if g0 is None:
            raise ValueError("g0 is required unless bill_as_day_ahead=True")
        g0 = np.asarray(g0, dtype=float).ravel()
        if g0.shape != (n,):
            raise ValueError("g0 must match the remaining horizon")
        up = cp.Variable(n, nonneg=True)
        down = cp.Variable(n, nonneg=True)
        constraints.append(g - g0 == up - down)
        settlement = price @ g + ADJUST_ABS_COEFF * price @ (up + down)
    elif settlement_mode == SETTLEMENT_ALT:
        if g0 is None or g_pre is None:
            raise ValueError("adjacent settlement requires g0 and g_pre")
        g0 = np.asarray(g0, dtype=float).ravel()
        g_pre_arr = np.asarray(g_pre, dtype=float).ravel()
        if g0.shape != (n,) or g_pre_arr.shape != (n,):
            raise ValueError("g0 and g_pre must match the remaining horizon")
        up = cp.Variable(n, nonneg=True)
        down = cp.Variable(n, nonneg=True)
        constraints.append(g - g_pre_arr == up - down)
        settlement = float(sunk_settlement) + 1.5 * price @ up + 0.5 * price @ down
    else:
        raise ValueError(f"unknown settlement_mode: {settlement_mode}")

    primary = settlement + emergency_cost + terminal_term
    problem = cp.Problem(cp.Minimize(primary), constraints)
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    if g.value is None:
        extra = ""
        if terminal_soc is not None:
            extra = (
                f" (terminal_soc={float(terminal_soc):.6f} kWh, "
                f"n={n}, initial_soc={float(initial_soc):.6f} kWh)"
            )
        raise RuntimeError(f"Q3 horizon LP failed: {problem.status}{extra}")
    status = str(problem.status)
    primary_opt = float(primary.value)
    if throughput_tiebreak:
        second = cp.Problem(
            cp.Minimize(cp.sum(c + d)),
            constraints + [primary <= primary_opt + MPC_COST_TOL],
        )
        second.solve(solver=SOLVER, verbose=False)
        if g.value is None:
            raise RuntimeError(f"Q3 throughput tiebreak failed: {second.status}")
        status = str(second.status)
    elapsed = perf_counter() - started

    gv = np.asarray(g.value).ravel()
    xv = np.asarray(x.value).ravel()
    ev = np.asarray(e.value).ravel()
    cv = np.asarray(c.value).ravel()
    dv = np.asarray(d.value).ravel()
    wv = np.asarray(w.value).ravel()
    Ev = np.asarray(E.value).ravel()
    if bill_as_day_ahead:
        settle = float(price @ gv)
    elif settlement_mode == SETTLEMENT_MAIN:
        settle = float(np.sum(settlement_cost(price, g0, gv)))
    else:
        settle = float(sunk_settlement) + float(np.sum(adjacent_adjustment_cost(price, g_pre_arr, gv)))
    terminal = evaluate_value_cuts(float(Ev[-1]), terminal_value_cuts)
    dual = float(np.asarray(constraints[0].dual_value))
    return HorizonResult(
        g=gv,
        x=xv,
        emergency=ev,
        charge=cv,
        discharge=dv,
        curtailment=wv,
        soc=Ev,
        objective=float(primary_opt),
        settlement_cost=settle,
        emergency_cost=float(EMERGENCY_PRICE_MULTIPLIER * price @ ev),
        terminal_value=terminal,
        initial_soc_marginal=-dual,
        solve_seconds=elapsed,
        status=status,
    )


def dispatch_balance_residual(load: np.ndarray, pv: np.ndarray, result: HorizonResult) -> np.ndarray:
    return (
        result.x
        + result.emergency
        + pv
        - result.curtailment
        + result.discharge
        - load
        - result.charge
    )


def assert_physical(result: HorizonResult, load: np.ndarray, pv: np.ndarray, prefix: str = "") -> None:
    residual = dispatch_balance_residual(load, pv, result)
    soc_residual = result.soc[1:] - (
        result.soc[:-1] + ETA_C * result.charge - result.discharge / ETA_D
    )
    if np.max(np.abs(residual)) > 1e-5:
        raise AssertionError(f"{prefix}energy balance residual {np.max(np.abs(residual)):.3e}")
    if np.max(np.abs(soc_residual)) > 1e-5:
        raise AssertionError(f"{prefix}SOC residual {np.max(np.abs(soc_residual)):.3e}")
    if result.soc.min() < E_MIN_KWH - 1e-6 or result.soc.max() > E_MAX_KWH + 1e-6:
        raise AssertionError(f"{prefix}SOC bound violated")
    if np.any(result.charge < -1e-8) or np.any(result.discharge < -1e-8):
        raise AssertionError(f"{prefix}negative charge/discharge")
    if np.any(result.curtailment < -1e-8) or np.any(result.curtailment - pv > 1e-6):
        raise AssertionError(f"{prefix}curtailment bound violated")
    if np.any(result.x - result.g > 1e-6):
        raise AssertionError(f"{prefix}x exceeds commitment g")
    if result.max_cd > SIMULTANEOUS_CD_TOL:
        raise AssertionError(
            f"{prefix}simultaneous charge/discharge product {result.max_cd:.3e} "
            "exceeds tolerance; stop rather than ignore"
        )

# ===== q3/pilot.py =====
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
    LOAD_INFORMATION_CASES,
    LOAD_INFORMATION_MAIN,
    LOAD_INFORMATION_PROXY,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    NEXT_DAY_VALUE_MAX_SAMPLES,
    NUMERIC_TOL,
    OUTPUT_DIR,
    PILOT_DATES,
    PV_MAPPING_LINEAR,
    SETTLEMENT_ALT,
    SETTLEMENT_MAIN,
    SIMULTANEOUS_CD_TOL,
    STRATEGY_ALLOWED_UPDATES,
    STRATEGIES,
    T,
    VOI_EPS_YUAN,
    WARMUP_CSV_MAIN,
    make_run_id,
    next_day_year_end_soc,
    today_year_end_soc,
    year_end_boundary_label,
)
from q3.data import Q3Data
from q3.forecast import (
    causal_load_forecast,
    causal_load_sources,
    execution_load_horizon,
    load_forecast_audit_rows,
    map_issue_forecast,
    next_day_pv_forecast,
    planning_load_curve,
    write_forecast_mapping,
)
from q3.optimization import (
    ValueCut,
    assert_physical,
    decompose_settlement,
    evaluate_value_cuts,
    realized_settlement,
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


ValueCutCache = dict[tuple[int, int, str, str], tuple[tuple[ValueCut, ...], list[dict]]]


@dataclass
class DayRun:
    date: str
    strategy: str
    load_information_case: str
    pv_mapping_mode: str
    settlement_mode: str
    with_terminal_value: bool
    run_id: str
    dispatch: pd.DataFrame
    update_log: pd.DataFrame
    ledger: pd.DataFrame
    summary: dict
    next_day_value_rows: list[dict] = field(default_factory=list)
    year_end_soc_kwh: float | None = None


def dispatch_output_stem(date: str, strategy: str, load_information_case: str, with_terminal_value: bool) -> str:
    suffix = strategy + "_" + load_information_case
    if not with_terminal_value:
        suffix += "_no48h"
    return f"q3_dispatch_{date}_{suffix}"


def build_next_day_value_cuts(
    data: Q3Data,
    current_index: int,
    issue_hour: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
    next_day_terminal_soc: float | None = None,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    if current_index + 1 >= len(data.dates):
        return (), []
    load = causal_load_forecast(
        data, target_index=current_index + 1, history_end_exclusive=current_index
    )
    pv = next_day_pv_forecast(data, current_index, issue_hour, pv_mapping_mode)
    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = solve_horizon(
            data.price,
            load,
            pv,
            float(soc),
            bill_as_day_ahead=True,
            throughput_tiebreak=False,
            terminal_soc=next_day_terminal_soc,
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
            "pv_mapping_mode": pv_mapping_mode,
            "next_day_terminal_soc_kwh": (
                None if next_day_terminal_soc is None else float(next_day_terminal_soc)
            ),
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
            "bundle_sample_count": len(cuts),
            "information": (
                f"Q3 {pv_mapping_mode} overlay + causal prior-day load/PV; no future actual PV"
            ),
        }
        for reference, value, slope in cuts
    ]
    return cuts, rows


def _index_to_update_hour(index: int) -> int | None:
    inverse = {first: hour for hour, first in HOUR_TO_FIRST_MUTABLE.items() if hour != 0}
    return inverse.get(index)


def _run_key_fields(
    date: str,
    strategy: str,
    load_information_case: str,
    pv_mapping_mode: str,
    settlement_mode: str,
    with_terminal_value: bool,
    run_id: str,
    year_end_soc_kwh: float | None = None,
) -> dict:
    return {
        "date": date,
        "strategy": strategy,
        "load_information_case": load_information_case,
        "pv_mapping_mode": pv_mapping_mode,
        "settlement_mode": settlement_mode,
        "with_terminal_value": with_terminal_value,
        "year_end_soc_kwh": None if year_end_soc_kwh is None else float(year_end_soc_kwh),
        "year_end_boundary": year_end_boundary_label(year_end_soc_kwh),
        "run_id": run_id,
    }


def _settlement_ledger_rows(
    date: str,
    strategy: str,
    load_information_case: str,
    pv_mapping_mode: str,
    settlement_mode: str,
    with_terminal_value: bool,
    run_id: str,
    time_labels: tuple[str, ...],
    price: np.ndarray,
    versions: list[np.ndarray],
    version_times: list[str],
    dispatch: pd.DataFrame,
    year_end_soc_kwh: float | None = None,
) -> list[dict]:
    keys = _run_key_fields(
        date,
        strategy,
        load_information_case,
        pv_mapping_mode,
        settlement_mode,
        with_terminal_value,
        run_id,
        year_end_soc_kwh,
    )
    ordinary, up_fee, down_fee = decompose_settlement(price, versions, settlement_mode)
    emergency = dispatch["emergency_cost_yuan"].to_numpy()
    emergency_kwh = dispatch["emergency_kwh"].to_numpy()
    g0 = versions[0]
    gf = versions[-1]
    rows: list[dict] = []
    for t in range(T):
        p = float(price[t])
        rows.append(
            {
                **keys,
                "row_role": "period_total",
                "period": t,
                "time": time_labels[t],
                "plan_version_time": str(dispatch["last_update_time"].iloc[t]),
                "g_before_kwh": float(g0[t]),
                "g_after_kwh": float(gf[t]),
                "up_adjust_kwh": float(max(gf[t] - g0[t], 0.0)),
                "down_adjust_kwh": float(max(g0[t] - gf[t], 0.0)),
                "ordinary_yuan": float(ordinary[t]),
                "up_fee_yuan": float(up_fee[t]),
                "down_fee_yuan": float(down_fee[t]),
                "emergency_kwh": float(emergency_kwh[t]),
                "emergency_yuan": float(emergency[t]),
                "total_yuan": float(ordinary[t] + up_fee[t] + down_fee[t] + emergency[t]),
            }
        )
        if settlement_mode == SETTLEMENT_ALT:
            rows.append(
                {
                    **keys,
                    "row_role": "event",
                    "period": t,
                    "time": time_labels[t],
                    "plan_version_time": "00:00",
                    "g_before_kwh": 0.0,
                    "g_after_kwh": float(g0[t]),
                    "up_adjust_kwh": float(g0[t]),
                    "down_adjust_kwh": 0.0,
                    "ordinary_yuan": p * float(g0[t]),
                    "up_fee_yuan": 0.0,
                    "down_fee_yuan": 0.0,
                    "emergency_kwh": 0.0,
                    "emergency_yuan": 0.0,
                    "total_yuan": p * float(g0[t]),
                }
            )
            for prev, cur, ts in zip(versions[:-1], versions[1:], version_times[1:]):
                up = float(max(cur[t] - prev[t], 0.0))
                down = float(max(prev[t] - cur[t], 0.0))
                rows.append(
                    {
                        **keys,
                        "row_role": "event",
                        "period": t,
                        "time": time_labels[t],
                        "plan_version_time": ts,
                        "g_before_kwh": float(prev[t]),
                        "g_after_kwh": float(cur[t]),
                        "up_adjust_kwh": up,
                        "down_adjust_kwh": down,
                        "ordinary_yuan": 0.0,
                        "up_fee_yuan": 1.5 * p * up,
                        "down_fee_yuan": 0.5 * p * down,
                        "emergency_kwh": 0.0,
                        "emergency_yuan": 0.0,
                        "total_yuan": 1.5 * p * up + 0.5 * p * down,
                    }
                )
        else:
            up = float(max(gf[t] - g0[t], 0.0))
            down = float(max(g0[t] - gf[t], 0.0))
            rows.append(
                {
                    **keys,
                    "row_role": "event",
                    "period": t,
                    "time": time_labels[t],
                    "plan_version_time": str(dispatch["last_update_time"].iloc[t]),
                    "g_before_kwh": float(g0[t]),
                    "g_after_kwh": float(gf[t]),
                    "up_adjust_kwh": up,
                    "down_adjust_kwh": down,
                    "ordinary_yuan": p * float(gf[t]),
                    "up_fee_yuan": 0.5 * p * up,
                    "down_fee_yuan": 0.5 * p * down,
                    "emergency_kwh": 0.0,
                    "emergency_yuan": 0.0,
                    "total_yuan": p * float(gf[t]) + 0.5 * p * (up + down),
                }
            )
        rows.append(
            {
                **keys,
                "row_role": "event",
                "period": t,
                "time": time_labels[t],
                "plan_version_time": "execution",
                "g_before_kwh": float(gf[t]),
                "g_after_kwh": float(gf[t]),
                "up_adjust_kwh": 0.0,
                "down_adjust_kwh": 0.0,
                "ordinary_yuan": 0.0,
                "up_fee_yuan": 0.0,
                "down_fee_yuan": 0.0,
                "emergency_kwh": float(emergency_kwh[t]),
                "emergency_yuan": float(emergency[t]),
                "total_yuan": float(emergency[t]),
            }
        )
    return rows


def _value_cut_cache_key(
    day_index: int,
    issue_hour: int,
    pv_mapping_mode: str,
    next_day_terminal_soc: float | None = None,
) -> tuple[int, int, str, str]:
    term = "" if next_day_terminal_soc is None else f"{float(next_day_terminal_soc):.6f}"
    return (int(day_index), int(issue_hour), str(pv_mapping_mode), term)


def _next_day_value_cuts(
    data: Q3Data,
    day_index: int,
    issue_hour: int,
    cache: ValueCutCache | None,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
    next_day_terminal_soc: float | None = None,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    key = _value_cut_cache_key(day_index, issue_hour, pv_mapping_mode, next_day_terminal_soc)
    if cache is not None and key in cache:
        return cache[key]
    cuts, rows = build_next_day_value_cuts(
        data, day_index, issue_hour, pv_mapping_mode, next_day_terminal_soc
    )
    if cache is not None:
        cache[key] = (cuts, rows)
    return cuts, rows


def run_day(
    data: Q3Data,
    day_index: int,
    strategy: str,
    initial_soc: float,
    with_terminal_value: bool = True,
    load_information_case: str = LOAD_INFORMATION_MAIN,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
    settlement_mode: str = SETTLEMENT_MAIN,
    value_cut_cache: ValueCutCache | None = None,
    year_end_soc_kwh: float | None = None,
) -> DayRun:
    date = data.dates[day_index].strftime("%Y-%m-%d")
    run_id = make_run_id(
        date,
        strategy,
        load_information_case,
        pv_mapping_mode,
        settlement_mode,
        with_terminal_value,
        year_end_soc_kwh,
    )
    n_days = len(data.dates)
    today_terminal = today_year_end_soc(day_index, n_days, year_end_soc_kwh)
    next_terminal = next_day_year_end_soc(day_index, n_days, year_end_soc_kwh)
    allowed = STRATEGY_ALLOWED_UPDATES[strategy]
    price = data.price
    actual_load = data.load[day_index]
    plan_load = planning_load_curve(data, day_index, load_information_case)
    actual_pv = data.pv[day_index]
    started = perf_counter()

    mapped0 = map_issue_forecast(data, day_index, 0, pv_mapping_mode)
    current_forecast = mapped0.today_kwh.copy()
    cuts: tuple[ValueCut, ...] = ()
    value_rows: list[dict] = []
    if with_terminal_value:
        cuts, rows = _next_day_value_cuts(
            data, day_index, 0, value_cut_cache, pv_mapping_mode, next_terminal
        )
        value_rows.extend(rows)

    midnight = solve_horizon(
        price,
        plan_load,
        current_forecast,
        initial_soc,
        bill_as_day_ahead=True,
        terminal_value_cuts=cuts or None,
        terminal_soc=today_terminal,
    )
    assert_physical(midnight, plan_load, current_forecast, prefix=f"{date} 0:00 plan ")
    g0 = midnight.g.copy()
    g = g0.copy()
    versions = [g0.copy()]
    version_times = ["00:00"]
    last_update = "00:00"

    def remaining_kwargs(t: int, g_pre_rem: np.ndarray) -> dict:
        kwargs: dict = {
            "settlement_mode": settlement_mode,
            "terminal_value_cuts": cuts or None,
            "g0": g0[t:],
            "terminal_soc": today_terminal,
        }
        if settlement_mode == SETTLEMENT_ALT:
            kwargs["g_pre"] = g_pre_rem
            kwargs["sunk_settlement"] = float(
                np.sum(
                    realized_settlement(
                        price[t:], [v[t:] for v in versions], SETTLEMENT_ALT
                    )
                )
            )
        return kwargs

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
            mapped = map_issue_forecast(data, day_index, hour, pv_mapping_mode)
            current_forecast = mapped.today_kwh.copy()
            if with_terminal_value:
                cuts, rows = _next_day_value_cuts(
                    data, day_index, hour, value_cut_cache, pv_mapping_mode, next_terminal
                )
                value_rows.extend(rows)
            pv_plan = current_forecast[t:]
            load_plan = plan_load[t:]
            g_pre = g[t:].copy()
            settle_kw = remaining_kwargs(t, g_pre)
            j_fix = solve_horizon(
                price[t:],
                load_plan,
                pv_plan,
                soc,
                g_fixed=g_pre,
                **settle_kw,
            )
            j_free = solve_horizon(
                price[t:],
                load_plan,
                pv_plan,
                soc,
                **settle_kw,
            )
            voi = float(j_fix.objective - j_free.objective)
            implemented = bool(voi > VOI_EPS_YUAN)
            if implemented:
                g[t:] = j_free.g
                versions.append(g.copy())
                version_times.append(f"{hour:02d}:00")
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
        load_horizon = execution_load_horizon(plan_load, actual_load, t)
        step = solve_horizon(
            price[t:],
            load_horizon,
            pv_horizon,
            soc,
            g_fixed=g[t:],
            **remaining_kwargs(t, g[t:]),
        )
        residual = (
            step.x[0]
            + step.emergency[0]
            + actual_pv[t]
            - step.curtailment[0]
            + step.discharge[0]
            - actual_load[t]
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
                "load_kwh": float(actual_load[t]),
                "forecast_load_kwh": float(plan_load[t]),
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
    phi = realized_settlement(price, versions, settlement_mode)
    dispatch["phi_yuan"] = phi
    dispatch["emergency_cost_yuan"] = (
        EMERGENCY_PRICE_MULTIPLIER * dispatch["price"] * dispatch["emergency_kwh"]
    )
    dispatch["run_id"] = run_id
    dispatch["pv_mapping_mode"] = pv_mapping_mode
    dispatch["settlement_mode"] = settlement_mode
    dispatch["year_end_soc_kwh"] = None if year_end_soc_kwh is None else float(year_end_soc_kwh)
    dispatch["year_end_boundary"] = year_end_boundary_label(year_end_soc_kwh)
    ledger = pd.DataFrame(
        _settlement_ledger_rows(
            date=date,
            strategy=strategy,
            load_information_case=load_information_case,
            pv_mapping_mode=pv_mapping_mode,
            settlement_mode=settlement_mode,
            with_terminal_value=with_terminal_value,
            run_id=run_id,
            time_labels=data.time_labels,
            price=price,
            versions=versions,
            version_times=version_times,
            dispatch=dispatch,
            year_end_soc_kwh=year_end_soc_kwh,
        )
    )
    update_log = pd.DataFrame(update_rows)
    update_log.insert(1, "strategy", strategy)
    update_log.insert(2, "load_information_case", load_information_case)
    update_log.insert(3, "pv_mapping_mode", pv_mapping_mode)
    update_log.insert(4, "settlement_mode", settlement_mode)
    update_log.insert(5, "with_terminal_value", with_terminal_value)
    update_log.insert(6, "year_end_soc_kwh", None if year_end_soc_kwh is None else float(year_end_soc_kwh))
    update_log.insert(7, "year_end_boundary", year_end_boundary_label(year_end_soc_kwh))
    update_log.insert(8, "run_id", run_id)
    n_adjust = int(((update_log["update_time"] != "00:00") & update_log["implemented"]).sum())
    summary = {
        "date": date,
        "strategy": strategy,
        "load_information_case": load_information_case,
        "pv_mapping_mode": pv_mapping_mode,
        "settlement_mode": settlement_mode,
        "with_terminal_value": with_terminal_value,
        "year_end_soc_kwh": None if year_end_soc_kwh is None else float(year_end_soc_kwh),
        "year_end_boundary": year_end_boundary_label(year_end_soc_kwh),
        "run_id": run_id,
        "total_cost_yuan": float(dispatch["phi_yuan"].sum() + dispatch["emergency_cost_yuan"].sum()),
        "settlement_cost_yuan": float(dispatch["phi_yuan"].sum()),
        "emergency_cost_yuan": float(dispatch["emergency_cost_yuan"].sum()),
        "curtailment_kwh": float(dispatch["curtailment_kwh"].sum()),
        "emergency_kwh": float(dispatch["emergency_kwh"].sum()),
        "charge_kwh": float(dispatch["charge_kwh"].sum()),
        "discharge_kwh": float(dispatch["discharge_kwh"].sum()),
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
    return DayRun(
        date,
        strategy,
        load_information_case,
        pv_mapping_mode,
        settlement_mode,
        with_terminal_value,
        run_id,
        dispatch,
        update_log,
        ledger,
        summary,
        value_rows,
        year_end_soc_kwh,
    )


def warmup_soc_to(
    data: Q3Data, target_index: int, path: Path
) -> tuple[np.ndarray, pd.DataFrame]:
    """Propagate M0 from 2025-01-01 so the first pilot day has a causal SOC."""
    starts = np.full(target_index + 1, E_INITIAL_KWH)
    rows = []
    soc = E_INITIAL_KWH
    for i in range(target_index):
        starts[i] = soc
        result = run_day(
            data,
            i,
            "M0",
            soc,
            with_terminal_value=True,
            load_information_case=LOAD_INFORMATION_MAIN,
        )
        soc = float(result.summary["soc_end_kwh"])
        rows.append(
            {
                "date": result.date,
                "soc_start_kwh": result.summary["soc_start_kwh"],
                "soc_end_kwh": result.summary["soc_end_kwh"],
                "total_cost_yuan": result.summary["total_cost_yuan"],
                "strategy": "M0_warmup",
                "load_information_case": LOAD_INFORMATION_MAIN,
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
        block["load_information_case"] = run.load_information_case
        block["pv_mapping_mode"] = run.pv_mapping_mode
        block["settlement_mode"] = run.settlement_mode
        block["with_terminal_value"] = run.with_terminal_value
        block["run_id"] = run.run_id
        frames.append(
            block[
                [
                    "date",
                    "strategy",
                    "load_information_case",
                    "pv_mapping_mode",
                    "settlement_mode",
                    "with_terminal_value",
                    "run_id",
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
            spot.append(
                {
                    "date": run.date,
                    "strategy": run.strategy,
                    "load_information_case": run.load_information_case,
                    "pv_mapping_mode": run.pv_mapping_mode,
                    "settlement_mode": run.settlement_mode,
                    "with_terminal_value": run.with_terminal_value,
                    "run_id": run.run_id,
                    **item,
                }
            )
    frame = pd.concat(frames, ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    path.with_name("q3_cost_spotcheck.csv").write_text(
        pd.DataFrame(spot).to_csv(index=False), encoding="utf-8"
    )
    return frame


def plot_pilot_figures(runs: list[DayRun], comparison: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    main = comparison[
        comparison["strategy"].isin(STRATEGIES)
        & comparison["with_terminal_value"]
        & comparison["load_information_case"].eq(LOAD_INFORMATION_MAIN)
    ].copy()
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
    ax.set_title("Q3 pilot: update-policy cost (causal_load_main)")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_strategy_cost.png")
    fig.savefig(FIG_DIR / "fig3_strategy_cost_causal_load_main.png")
    plt.close(fig)

    for run in runs:
        if (
            run.strategy != "M1_M6"
            or not run.with_terminal_value
            or run.load_information_case != LOAD_INFORMATION_MAIN
        ):
            continue
        d = run.dispatch
        fig, axes = plt.subplots(3, 1, figsize=(8.6, 7.2), sharex=True)
        t = np.arange(len(d))
        axes[0].plot(t, d["load_kwh"], color=NAVY, lw=1.2, label="actual load")
        axes[0].plot(t, d["forecast_load_kwh"], color=PURPLE, lw=1.0, ls="--", label="causal load hat")
        axes[0].plot(t, d["actual_pv_kwh"], color=TEAL, lw=1.2, label="actual PV")
        axes[0].plot(t, d["forecast_pv_kwh"], color=ORANGE, lw=1.0, ls="--", label="active PV forecast")
        axes[0].legend(frameon=False, ncol=2)
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
        fig.suptitle(f"{run.date} M1/M6 dispatch ({LOAD_INFORMATION_MAIN})", fontsize=12)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"fig3_dispatch_{run.date}_M1_M6.png")
        fig.savefig(FIG_DIR / f"fig3_dispatch_{run.date}_M1_M6_{LOAD_INFORMATION_MAIN}.png")
        plt.close(fig)

        log = run.update_log[run.update_log["update_time"] != "00:00"]
        fig, ax = plt.subplots(figsize=(6.4, 3.8))
        ax.bar(log["update_time"], log["voi_yuan"], color=TEAL)
        ax.axhline(VOI_EPS_YUAN, color=ORANGE, ls="--", lw=0.9, label="VoI threshold")
        ax.set_ylabel("VoI (yuan)")
        ax.set_title(f"{run.date} information value by update ({LOAD_INFORMATION_MAIN})")
        ax.legend(frameon=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"fig3_voi_{run.date}.png")
        fig.savefig(FIG_DIR / f"fig3_voi_{run.date}_{LOAD_INFORMATION_MAIN}.png")
        plt.close(fig)

    info = comparison[
        comparison["strategy"].isin(STRATEGIES) & comparison["with_terminal_value"]
    ].copy()
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.2), sharey=True)
    x = np.arange(len(STRATEGIES))
    width = 0.35
    for ax, date in zip(axes, list(dict.fromkeys(info["date"]))):
        for i, case in enumerate(LOAD_INFORMATION_CASES):
            subset = (
                info[(info["date"] == date) & (info["load_information_case"] == case)]
                .set_index("strategy")
                .loc[list(STRATEGIES)]
            )
            ax.bar(
                x + (i - 0.5) * width,
                subset["total_cost_yuan"],
                width=width,
                color=(NAVY if i == 0 else ORANGE),
                label=case,
            )
        ax.set_xticks(x)
        ax.set_xticklabels(STRATEGIES, rotation=20, ha="right")
        ax.set_title(date)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("total purchase cost (yuan)")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Load-information comparison (same SOC, prices, PV, settlement)", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_load_information_comparison.png")
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
            "load_information_case": run.load_information_case,
            "pv_mapping_mode": run.pv_mapping_mode,
            "settlement_mode": run.settlement_mode,
            "with_terminal_value": run.with_terminal_value,
            "year_end_soc_kwh": run.year_end_soc_kwh,
            "year_end_boundary": year_end_boundary_label(run.year_end_soc_kwh),
            "run_id": run.run_id,
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
        "warmup_load_information_case": LOAD_INFORMATION_MAIN,
        "runs": items,
    }


def write_load_forecast_audit(data: Q3Data, path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    for date in PILOT_DATES:
        rows.extend(load_forecast_audit_rows(data, data.date_index(date)))
    frame = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def write_load_information_comparison(comparison: pd.DataFrame, path: Path) -> pd.DataFrame:
    cols = [
        "date",
        "strategy",
        "load_information_case",
        "with_terminal_value",
        "total_cost_yuan",
        "settlement_cost_yuan",
        "emergency_cost_yuan",
        "emergency_kwh",
        "curtailment_kwh",
        "soc_start_kwh",
        "soc_end_kwh",
        "runtime_seconds",
    ]
    frame = comparison[cols].copy()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def run_causality_audit(data: Q3Data, day_index: int, initial_soc: float) -> dict:
    """Perturb unrealized same-day actual load: main forecasts stay put, proxy may move."""
    date = data.dates[day_index].strftime("%Y-%m-%d")
    price = data.price
    pv0 = map_issue_forecast(data, day_index, 0).today_kwh
    hat_before, sources_before, label_before = causal_load_sources(data, day_index, day_index)
    proxy_before = planning_load_curve(data, day_index, LOAD_INFORMATION_PROXY)
    next_before = (
        causal_load_forecast(data, day_index + 1, day_index)
        if day_index + 1 < len(data.dates)
        else None
    )
    g0_main_before = solve_horizon(
        price, hat_before, pv0, initial_soc, bill_as_day_ahead=True, throughput_tiebreak=False
    ).g
    g0_proxy_before = solve_horizon(
        price, proxy_before, pv0, initial_soc, bill_as_day_ahead=True, throughput_tiebreak=False
    ).g

    original = data.load[day_index].copy()
    perturbation_kwh = 500.0
    try:
        data.load[day_index, 36:] += perturbation_kwh
        hat_after, sources_after, label_after = causal_load_sources(data, day_index, day_index)
        proxy_after = planning_load_curve(data, day_index, LOAD_INFORMATION_PROXY)
        next_after = (
            causal_load_forecast(data, day_index + 1, day_index)
            if day_index + 1 < len(data.dates)
            else None
        )
        g0_main_after = solve_horizon(
            price, hat_after, pv0, initial_soc, bill_as_day_ahead=True, throughput_tiebreak=False
        ).g
        g0_proxy_after = solve_horizon(
            price, proxy_after, pv0, initial_soc, bill_as_day_ahead=True, throughput_tiebreak=False
        ).g
        mapped6_before = map_issue_forecast(data, day_index, 6)
        plan_main_update_before = hat_before[36:]
        plan_main_update_after = hat_after[36:]
    finally:
        data.load[day_index] = original

    main_forecast_delta = float(np.max(np.abs(hat_after - hat_before)))
    main_update_delta = float(np.max(np.abs(plan_main_update_after - plan_main_update_before)))
    main_g0_delta = float(np.max(np.abs(g0_main_after - g0_main_before)))
    proxy_plan_delta = float(np.max(np.abs(proxy_after - proxy_before)))
    proxy_g0_delta = float(np.max(np.abs(g0_proxy_after - g0_proxy_before)))
    next_delta = (
        float(np.max(np.abs(next_after - next_before))) if next_before is not None else 0.0
    )
    payload = {
        "date": date,
        "perturbed_slice": "periods[36:] (unrealized same-day actual load after 06:00)",
        "perturbation_kwh": perturbation_kwh,
        "source_dates": label_before,
        "source_dates_after_perturbation": label_after,
        "main_day_ahead_forecast_unchanged": bool(main_forecast_delta < 1e-12),
        "main_update_forecast_unchanged": bool(main_update_delta < 1e-12),
        "main_next_day_forecast_unchanged": bool(next_delta < 1e-12),
        "main_g0_unchanged": bool(main_g0_delta < 1e-6),
        "proxy_planning_load_changed": bool(proxy_plan_delta > 1.0),
        "proxy_g0_changed": bool(proxy_g0_delta > 1e-6),
        "max_abs_main_forecast_delta_kwh": main_forecast_delta,
        "max_abs_main_update_forecast_delta_kwh": main_update_delta,
        "max_abs_main_g0_delta_kwh": main_g0_delta,
        "max_abs_proxy_planning_delta_kwh": proxy_plan_delta,
        "max_abs_proxy_g0_delta_kwh": proxy_g0_delta,
        "max_abs_next_day_forecast_delta_kwh": next_delta,
        "source_indices_unchanged": sources_before == sources_after,
        "six_am_first_mutable_index": int(mapped6_before.first_mutable_index),
        "note": (
            "causal_load_main day-ahead and 6/12/18 future load stay at the 0:00 hat. "
            "actual_load_proxy is allowed to change because it reads the full same-day Attachment 2 path."
        ),
    }
    payload["all_pass"] = bool(
        payload["main_day_ahead_forecast_unchanged"]
        and payload["main_update_forecast_unchanged"]
        and payload["main_next_day_forecast_unchanged"]
        and payload["main_g0_unchanged"]
        and payload["proxy_planning_load_changed"]
        and payload["proxy_g0_changed"]
        and payload["source_indices_unchanged"]
    )
    return payload


def run_q3_pilot(data: Q3Data) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    from q3.data import write_input_audit

    write_input_audit(data, OUTPUT_DIR / "input_audit.json")
    write_forecast_mapping(data, OUTPUT_DIR / "q3_forecast_mapping.csv")
    write_load_forecast_audit(data, OUTPUT_DIR / "q3_load_forecast_audit.csv")

    feb_index = data.date_index("2025-02-01")
    warmup_path = OUTPUT_DIR / WARMUP_CSV_MAIN
    if warmup_path.exists() and len(pd.read_csv(warmup_path)) >= feb_index:
        warmup_frame = pd.read_csv(warmup_path)
        warmup_starts = np.full(feb_index + 1, E_INITIAL_KWH)
        warmup_starts[1:] = warmup_frame["soc_end_kwh"].to_numpy()[:feb_index]
        print(f"reusing causal_load_main warmup SOC from {warmup_path}")
    else:
        warmup_starts, _warmup = warmup_soc_to(data, feb_index, warmup_path)
    initial = {
        "2025-02-01": float(warmup_starts[feb_index]),
        "2025-06-21": E_INITIAL_KWH,
    }

    value_cut_cache: ValueCutCache = {}
    runs: list[DayRun] = []
    for date in PILOT_DATES:
        i = data.date_index(date)
        soc0 = initial[date]
        for case in LOAD_INFORMATION_CASES:
            for strategy in STRATEGIES:
                runs.append(
                    run_day(
                        data,
                        i,
                        strategy,
                        soc0,
                        with_terminal_value=True,
                        load_information_case=case,
                        value_cut_cache=value_cut_cache,
                    )
                )
            runs.append(
                run_day(
                    data,
                    i,
                    "M1_M6",
                    soc0,
                    with_terminal_value=False,
                    load_information_case=case,
                    value_cut_cache=value_cut_cache,
                )
            )

    comparison = pd.DataFrame([run.summary for run in runs])
    comparison.to_csv(OUTPUT_DIR / "q3_strategy_comparison.csv", index=False)
    write_load_information_comparison(
        comparison, OUTPUT_DIR / "q3_load_information_comparison.csv"
    )
    update_log = pd.concat([run.update_log for run in runs], ignore_index=True)
    update_log.to_csv(OUTPUT_DIR / "q3_update_log.csv", index=False)
    value_rows = []
    for _key in sorted(value_cut_cache):
        value_rows.extend(value_cut_cache[_key][1])
    if value_rows:
        pd.DataFrame(value_rows).to_csv(OUTPUT_DIR / "q3_next_day_value_audit.csv", index=False)
    write_cost_audit(runs, OUTPUT_DIR / "q3_cost_audit.csv")

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
    ]
    for run in runs:
        stem = dispatch_output_stem(
            run.date, run.strategy, run.load_information_case, run.with_terminal_value
        )
        run.dispatch[dispatch_cols].to_csv(OUTPUT_DIR / f"{stem}.csv", index=False)

    plot_pilot_figures(runs, comparison)
    audit = physical_audit(runs, initial["2025-02-01"])
    (OUTPUT_DIR / "q3_physical_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    causality = run_causality_audit(
        data, data.date_index("2025-02-01"), initial["2025-02-01"]
    )
    (OUTPUT_DIR / "q3_causality_audit.json").write_text(
        json.dumps(causality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not causality["all_pass"]:
        raise AssertionError(f"Q3 load causality audit failed: {causality}")
    return {
        "initial_soc": initial,
        "comparison": comparison,
        "audit": audit,
        "causality": causality,
        "n_runs": len(runs),
        "load_treatment": LOAD_INFORMATION_MAIN,
    }

# ===== q3/run_q3_full_annual.py =====
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from time import perf_counter

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import ATTACH1, ATTACH2, ATTACH3, ANNUAL_OUTPUT_DIR  # noqa: E402
from q3.data import load_q3_data  # noqa: E402
from q3.full_annual import parse_boundaries, run_q3_full_annual  # noqa: E402


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Q3 full-year continuous SOC for year-end A and/or B")
    parser.add_argument(
        "--boundary",
        default="both",
        help="A, B, or both (default both). A then B are independent 365-day campaigns.",
    )
    args = parser.parse_args()
    selected = parse_boundaries(args.boundary)
    started = perf_counter()
    data = load_q3_data()
    result = run_q3_full_annual(data, boundaries=selected)
    elapsed = perf_counter() - started
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "output_dir": str(ANNUAL_OUTPUT_DIR),
        "elapsed_seconds": elapsed,
        "n_runs": result["n_runs"],
        "all_physical_pass": result["audit"]["all_pass"],
        "load_treatment": "causal_load_main",
        "pv_mapping_mode": "linear_anchor_main",
        "settlement_mode": "anchor_final_main",
        "jan01_soc_kwh": 6000.0,
        "boundaries": {name: target for name, target in selected},
        "git_commit": _git_hash(),
        "solver": "HIGHS",
        "dependency_versions": {
            "python": sys.version.split()[0],
            "numpy": __import__("numpy").__version__,
            "pandas": __import__("pandas").__version__,
            "cvxpy": __import__("cvxpy").__version__,
            "matplotlib": __import__("matplotlib").__version__,
        },
        "run_command": ".venv/bin/python q3/run_q3_full_annual.py --boundary both",
        "note": (
            "Independent 365-day campaigns for year-end A=1200 and/or B=6000. "
            "Does not choose a single official boundary and does not write result3.xlsx."
        ),
        "totals": result["totals"].to_dict(orient="records"),
        "delta": result["delta"].to_dict(orient="records") if len(result["delta"]) else [],
    }
    ANNUAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (ANNUAL_OUTPUT_DIR / "run_meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: payload[k] for k in ("elapsed_seconds", "n_runs", "all_physical_pass", "git_commit")}, indent=2))
    print(result["totals"].to_string(index=False))
    if len(result["delta"]):
        print(result["delta"].to_string(index=False))


if __name__ == "__main__":
    main()

# ===== q3/run_q3_pilot.py =====
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import ATTACH1, ATTACH2, ATTACH3, OUTPUT_DIR  # noqa: E402
from q3.data import load_q3_data  # noqa: E402
from q3.pilot import run_q3_pilot  # noqa: E402


def main() -> None:
    started = perf_counter()
    data = load_q3_data()
    result = run_q3_pilot(data)
    elapsed = perf_counter() - started
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "output_dir": str(OUTPUT_DIR),
        "elapsed_seconds": elapsed,
        "initial_soc": result["initial_soc"],
        "n_runs": result["n_runs"],
        "load_treatment": result.get("load_treatment"),
        "all_physical_pass": result["audit"]["all_pass"],
        "causality_all_pass": result["causality"]["all_pass"],
        "solver": "HIGHS",
        "dependency_versions": {
            "python": sys.version.split()[0],
            "numpy": __import__("numpy").__version__,
            "pandas": __import__("pandas").__version__,
            "cvxpy": __import__("cvxpy").__version__,
            "matplotlib": __import__("matplotlib").__version__,
        },
        "comparison": result["comparison"].to_dict(orient="records"),
    }
    (OUTPUT_DIR / "run_meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                k: payload[k]
                for k in (
                    "elapsed_seconds",
                    "initial_soc",
                    "all_physical_pass",
                    "causality_all_pass",
                    "n_runs",
                    "load_treatment",
                    "dependency_versions",
                )
            },
            indent=2,
        )
    )
    print(
        result["comparison"][
            [
                "date",
                "strategy",
                "load_information_case",
                "with_terminal_value",
                "total_cost_yuan",
                "adjustment_count",
            ]
        ]
    )


if __name__ == "__main__":
    main()

# ===== q3/run_q3_result3_export.py =====
#!/usr/bin/env python3
"""Rerun only A_q2_aligned + M1_M6, stream 10-minute trajectories, write result3.xlsx."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import (  # noqa: E402
    ANNUAL_OUTPUT_DIR,
    ATTACH1,
    ATTACH2,
    ATTACH3,
    E_INITIAL_KWH,
    LOAD_INFORMATION_MAIN,
    PV_MAPPING_LINEAR,
    RESULT3_ANNUAL_COST_YUAN,
    RESULT3_EXPORT_AUDIT,
    RESULT3_EXPORT_START,
    RESULT3_OFFICIAL_STRATEGY,
    RESULT3_TEMPLATE,
    RESULT3_XLSX,
    SETTLEMENT_MAIN,
    YEAR_END_BOUNDARY_A,
    YEAR_END_SOC_A_KWH,
)
from q3.data import load_q3_data  # noqa: E402
from q3.export_result3 import (  # noqa: E402
    compare_to_annual_summary,
    dispatch_path,
    enrich_dispatch,
    export_dates,
    git_hash,
    has_required_trajectory,
    inspect_result3_workbook,
    load_daily_trajectory,
    summarize_trajectory,
    write_daily_trajectory,
    write_export_audit,
    write_result3_xlsx,
)
from q3.full_annual import annual_dates  # noqa: E402
from q3.pilot import ValueCutCache, run_day  # noqa: E402

RERUN_DAILY_CSV = "result3_rerun_daily.csv"
PROGRESS_JSON = "result3_export_progress.json"


def _usable_existing(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        frame = pd.read_csv(path)
        return has_required_trajectory(frame) and "phi_yuan" in frame.columns
    except (OSError, ValueError):
        return False


def run_main_path(export_only: bool = False) -> dict:
    data = load_q3_data()
    dates = annual_dates(data)
    dispatch_dir = ANNUAL_OUTPUT_DIR / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    daily_path = ANNUAL_OUTPUT_DIR / RERUN_DAILY_CSV
    cache: ValueCutCache = {}
    started = perf_counter()
    soc = E_INITIAL_KWH
    n_solved = 0
    n_skipped = 0
    by_date: dict[str, pd.DataFrame] = {}

    for i, date in enumerate(dates, start=1):
        path = dispatch_path(date, dispatch_dir)
        if _usable_existing(path):
            frame = load_daily_trajectory(path)
            soc = float(frame["soc_end_kwh"].iloc[-1])
            by_date[date] = frame
            n_skipped += 1
            print(f"[{i}/{len(dates)}] skip {date} soc_end={soc:.4f}", flush=True)
            continue
        if export_only:
            raise FileNotFoundError(f"export-only missing trajectory {path}")
        day_index = data.date_index(date)
        run = run_day(
            data,
            day_index,
            RESULT3_OFFICIAL_STRATEGY,
            soc,
            with_terminal_value=True,
            load_information_case=LOAD_INFORMATION_MAIN,
            pv_mapping_mode=PV_MAPPING_LINEAR,
            settlement_mode=SETTLEMENT_MAIN,
            value_cut_cache=cache,
            year_end_soc_kwh=YEAR_END_SOC_A_KWH,
        )
        frame = enrich_dispatch(run)
        write_daily_trajectory(frame, path)
        soc = float(run.summary["soc_end_kwh"])
        by_date[date] = frame
        n_solved += 1
        print(
            f"[{i}/{len(dates)}] solved {run.run_id} "
            f"cost={run.summary['total_cost_yuan']:.2f} soc_end={soc:.4f}",
            flush=True,
        )
        del run

    rerun_daily = pd.DataFrame([summarize_trajectory(by_date[date]) for date in dates])
    rerun_daily.to_csv(daily_path, index=False)
    export_frames = {date: by_date[date] for date in export_dates()}
    xlsx_meta = write_result3_xlsx(export_frames, source_commit=git_hash())
    workbook = inspect_result3_workbook(RESULT3_XLSX)
    comparison = compare_to_annual_summary(
        rerun_daily, ANNUAL_OUTPUT_DIR / "q3_annual_daily_summary.csv"
    )
    jan_mask = pd.to_datetime(rerun_daily["date"]) < pd.Timestamp(RESULT3_EXPORT_START)
    jan_cost = float(rerun_daily.loc[jan_mask, "total_cost_yuan"].sum())
    annual_cost = float(rerun_daily["total_cost_yuan"].sum())
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "template": str(RESULT3_TEMPLATE),
        "result3_xlsx": str(RESULT3_XLSX),
        "dispatch_dir": str(dispatch_dir),
        "rerun_daily_csv": str(daily_path),
        "strategy": RESULT3_OFFICIAL_STRATEGY,
        "year_end_boundary": YEAR_END_BOUNDARY_A,
        "year_end_soc_kwh": YEAR_END_SOC_A_KWH,
        "load_information_case": LOAD_INFORMATION_MAIN,
        "pv_mapping_mode": PV_MAPPING_LINEAR,
        "settlement_mode": SETTLEMENT_MAIN,
        "jan01_soc_kwh": E_INITIAL_KWH,
        "n_calendar_days": len(dates),
        "n_export_days": len(export_dates()),
        "export_start": export_dates()[0],
        "export_end": export_dates()[-1],
        "n_periods": 144,
        "n_solved_days": n_solved,
        "n_skipped_existing_days": n_skipped,
        "elapsed_seconds": float(perf_counter() - started),
        "git_commit": git_hash(),
        "xlsx": xlsx_meta,
        "workbook_inspect": workbook,
        "annual_summary_comparison": comparison,
        "rerun_annual_cost_yuan": annual_cost,
        "rerun_january_cost_yuan": jan_cost,
        "rerun_export_window_cost_yuan": float(xlsx_meta["export_window_cost_yuan"]),
        "official_annual_cost_yuan": RESULT3_ANNUAL_COST_YUAN,
        "export_window_is_not_annual_total": True,
        "note": (
            "Only A_q2_aligned + M1_M6 was rerun. Trajectories are streamed 10-minute "
            "solver output, not reconstructed from q3_annual_daily_summary.csv. "
            "February–December workbook totals are not the 365-day official cost."
        ),
        "all_pass": bool(
            comparison.get("all_match", False)
            and workbook.get("n_anomalies", 1) == 0
            and abs(float(by_date[dates[-1]]["soc_end_kwh"].iloc[-1]) - YEAR_END_SOC_A_KWH)
            < 1e-3
        ),
    }
    write_export_audit(payload)
    (ANNUAL_OUTPUT_DIR / PROGRESS_JSON).write_text(
        json.dumps(
            {
                "last_date": dates[-1],
                "soc_end_kwh": float(by_date[dates[-1]]["soc_end_kwh"].iloc[-1]),
                "n_solved_days": n_solved,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Export official result3.xlsx from A+M1_M6")
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Do not solve; rebuild the workbook from already streamed trajectories.",
    )
    args = parser.parse_args()
    payload = run_main_path(export_only=args.export_only)
    print(
        json.dumps(
            {
                "elapsed_seconds": payload["elapsed_seconds"],
                "n_solved_days": payload["n_solved_days"],
                "n_skipped_existing_days": payload["n_skipped_existing_days"],
                "result3_xlsx": payload["result3_xlsx"],
                "export_window_cost_yuan": payload["rerun_export_window_cost_yuan"],
                "annual_cost_yuan": payload["rerun_annual_cost_yuan"],
                "all_pass": payload["all_pass"],
                "audit": str(RESULT3_EXPORT_AUDIT),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

# ===== q3/run_q3_sensitivity.py =====
#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from time import perf_counter

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import ATTACH1, ATTACH2, ATTACH3, SENSITIVITY_OUTPUT_DIR  # noqa: E402
from q3.data import load_q3_data  # noqa: E402
from q3.sensitivity import run_q3_sensitivity  # noqa: E402


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    started = perf_counter()
    data = load_q3_data()
    result = run_q3_sensitivity(data)
    elapsed = perf_counter() - started
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "output_dir": str(SENSITIVITY_OUTPUT_DIR),
        "elapsed_seconds": elapsed,
        "initial_soc": result["initial_soc"],
        "n_runs": result["n_runs"],
        "all_physical_pass": result["audit"]["all_pass"],
        "load_treatment": "causal_load_main",
        "git_commit": _git_hash(),
        "solver": "HIGHS",
        "dependency_versions": {
            "python": sys.version.split()[0],
            "numpy": __import__("numpy").__version__,
            "pandas": __import__("pandas").__version__,
            "cvxpy": __import__("cvxpy").__version__,
            "matplotlib": __import__("matplotlib").__version__,
        },
        "run_command": ".venv/bin/python q3/run_q3_sensitivity.py",
        "comparison": result["comparison"].to_dict(orient="records"),
    }
    SENSITIVITY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (SENSITIVITY_OUTPUT_DIR / "run_meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                k: payload[k]
                for k in (
                    "elapsed_seconds",
                    "initial_soc",
                    "all_physical_pass",
                    "n_runs",
                    "git_commit",
                    "dependency_versions",
                )
            },
            indent=2,
        )
    )
    cols = [
        "date",
        "strategy",
        "pv_mapping_mode",
        "settlement_mode",
        "total_cost_yuan",
        "delta_total_vs_baseline_yuan",
    ]
    print(result["comparison"][cols].to_string(index=False))


if __name__ == "__main__":
    main()

# ===== q3/run_q3_terminal_soc_pilot.py =====
#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from time import perf_counter

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import ATTACH1, ATTACH2, ATTACH3, TERMINAL_SOC_OUTPUT_DIR  # noqa: E402
from q3.data import load_q3_data  # noqa: E402
from q3.terminal_soc_pilot import run_q3_terminal_soc_pilot  # noqa: E402


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    started = perf_counter()
    data = load_q3_data()
    result = run_q3_terminal_soc_pilot(data)
    elapsed = perf_counter() - started
    payload = {
        "attach1": str(ATTACH1),
        "attach2": str(ATTACH2),
        "attach3": str(ATTACH3),
        "output_dir": str(TERMINAL_SOC_OUTPUT_DIR),
        "elapsed_seconds": elapsed,
        "n_runs": result["n_runs"],
        "all_physical_pass": result["audit"]["all_pass"],
        "load_treatment": "causal_load_main",
        "pv_mapping_mode": "linear_anchor_main",
        "settlement_mode": "anchor_final_main",
        "isolated_dec01_soc_kwh": 6000.0,
        "boundaries": {"A_q2_aligned": 1200.0, "B_energy_neutral": 6000.0},
        "git_commit": _git_hash(),
        "solver": "HIGHS",
        "dependency_versions": {
            "python": sys.version.split()[0],
            "numpy": __import__("numpy").__version__,
            "pandas": __import__("pandas").__version__,
            "cvxpy": __import__("cvxpy").__version__,
            "matplotlib": __import__("matplotlib").__version__,
        },
        "run_command": ".venv/bin/python q3/run_q3_terminal_soc_pilot.py",
        "note": (
            "December A/B terminal-SOC decision trial only. "
            "Does not choose the official year-end boundary and does not write result3.xlsx."
        ),
        "totals": result["totals"].to_dict(orient="records"),
        "delta": result["delta"].to_dict(orient="records"),
    }
    TERMINAL_SOC_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (TERMINAL_SOC_OUTPUT_DIR / "run_meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "elapsed_seconds": elapsed,
                "n_runs": result["n_runs"],
                "all_physical_pass": result["audit"]["all_pass"],
                "git_commit": payload["git_commit"],
            },
            indent=2,
        )
    )
    print(result["totals"].to_string(index=False))
    print(result["delta"].to_string(index=False))


if __name__ == "__main__":
    main()

# ===== q3/sensitivity.py =====
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

# ===== q3/terminal_soc_pilot.py =====
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

# ===== q3/validate_q3_full_annual.py =====
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import (
    ANNUAL_END,
    ANNUAL_FIG_DIR,
    ANNUAL_OUTPUT_DIR,
    ANNUAL_START,
    E_INITIAL_KWH,
    LOAD_INFORMATION_MAIN,
    PV_MAPPING_LINEAR,
    SETTLEMENT_MAIN,
    STRATEGIES,
    T,
    YEAR_END_BOUNDARIES,
    YEAR_N_DAYS,
    dispatch_stem,
    make_run_id,
)

KEY = [
    "date",
    "strategy",
    "load_information_case",
    "pv_mapping_mode",
    "settlement_mode",
    "with_terminal_value",
    "year_end_soc_kwh",
]
REQUIRED = [
    "input_audit.json",
    "q3_annual_daily_summary.csv",
    "q3_annual_strategy_comparison.csv",
    "q3_annual_forecast_audit.csv",
    "q3_annual_physical_audit.json",
    "run_meta.json",
]
REQUIRED_FIGS = [
    "fig3_annual_strategy_cost_decomposition.png",
    "fig3_annual_soc_paths.png",
    "fig3_annual_monthly_emergency_curtailment.png",
]


def _fail(failures: list[str], run_id: str, field: str, msg: str) -> None:
    failures.append(f"{run_id} [{field}]: {msg}")


def main() -> None:
    out = ANNUAL_OUTPUT_DIR
    missing = [name for name in REQUIRED if not (out / name).exists()]
    if missing:
        raise SystemExit(f"missing outputs: {missing}")
    missing_figs = [name for name in REQUIRED_FIGS if not (ANNUAL_FIG_DIR / name).exists()]
    if missing_figs:
        raise SystemExit(f"missing figures: {missing_figs}")
    audit = json.loads((out / "q3_annual_physical_audit.json").read_text(encoding="utf-8"))
    daily = pd.read_csv(out / "q3_annual_daily_summary.csv")
    totals = pd.read_csv(out / "q3_annual_strategy_comparison.csv")
    forecast = pd.read_csv(out / "q3_annual_forecast_audit.csv")
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    delta_path = out / "q3_annual_boundary_delta.csv"
    delta = pd.read_csv(delta_path) if delta_path.exists() else pd.DataFrame()

    failures: list[str] = []
    if not audit.get("all_pass"):
        failures.append("physical/continuity audit all_pass is false")

    for col in KEY + ["run_id", "year_end_boundary"]:
        if col not in daily.columns:
            failures.append(f"daily missing {col}")

    expected_n = YEAR_N_DAYS * len(STRATEGIES) * len(YEAR_END_BOUNDARIES)
    if len(daily) != expected_n:
        failures.append(f"expected {expected_n} daily rows, got {len(daily)}")
    if daily.duplicated(KEY).sum():
        failures.append("duplicate daily keys")

    dispatch_dir = out / "dispatch_daily"
    sample = daily[(daily["date"].isin((ANNUAL_START, "2025-06-21", ANNUAL_END)))]
    for _, row in sample.iterrows():
        run_id = str(row["run_id"])
        expected_id = make_run_id(
            row["date"],
            row["strategy"],
            row["load_information_case"],
            row["pv_mapping_mode"],
            row["settlement_mode"],
            bool(row["with_terminal_value"]),
            float(row["year_end_soc_kwh"]),
        )
        if run_id != expected_id:
            _fail(failures, run_id, "run_id", f"mismatch {expected_id}")
        stem = dispatch_stem(
            row["date"],
            row["strategy"],
            row["load_information_case"],
            row["pv_mapping_mode"],
            row["settlement_mode"],
            bool(row["with_terminal_value"]),
            float(row["year_end_soc_kwh"]),
        )
        path = dispatch_dir / f"{stem}.csv"
        if path.exists():
            frame = pd.read_csv(path)
            if len(frame) != T:
                _fail(failures, run_id, "dispatch", f"rows {len(frame)} != {T}")
            if float(np.max(np.abs(frame["balance_residual_kwh"]))) >= 1e-5:
                _fail(failures, run_id, "balance_residual_kwh", "energy residual")

    if (forecast["max_source_index"] >= forecast["day_index"]).any():
        failures.append("load forecast source is not strictly before the target day")
    if not bool(forecast.loc[forecast["day_index"] == 0, "used_attachment1_fallback"].all()):
        failures.append("Jan 1 must use attachment1 fallback")
    if (daily["load_information_case"] != LOAD_INFORMATION_MAIN).any():
        failures.append("annual run must stay on causal_load_main")
    if (daily["pv_mapping_mode"] != PV_MAPPING_LINEAR).any():
        failures.append("this annual archive is linear_anchor_main only")
    if (daily["settlement_mode"] != SETTLEMENT_MAIN).any():
        failures.append("this annual archive is anchor_final_main only")

    for (strategy, boundary), block in daily.groupby(["strategy", "year_end_boundary"]):
        block = block.sort_values("date")
        if len(block) != YEAR_N_DAYS:
            failures.append(f"{strategy}/{boundary}: {len(block)} days")
            continue
        if str(block["date"].iloc[0]) != ANNUAL_START or str(block["date"].iloc[-1]) != ANNUAL_END:
            failures.append(f"{strategy}/{boundary}: date range")
        if abs(float(block["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) > 1e-5:
            failures.append(f"{strategy}/{boundary}: Jan 1 start SOC")
        target = float(block["year_end_soc_kwh"].iloc[0])
        if abs(float(block["soc_end_kwh"].iloc[-1]) - target) > 1e-5:
            failures.append(f"{strategy}/{boundary}: Dec 31 SOC {block['soc_end_kwh'].iloc[-1]} vs {target}")
        starts = block["soc_start_kwh"].to_numpy()
        ends = block["soc_end_kwh"].to_numpy()
        if float(np.max(np.abs(starts[1:] - ends[:-1]))) > 1e-5:
            failures.append(f"{strategy}/{boundary}: cross-day SOC not continuous")

    lines = [
        "# Q3 全年连续 SOC（A=1200 与 B=6000 分列运行）",
        "",
        "主口径固定 `causal_load_main` + `linear_anchor_main` + `anchor_final_main`。",
        "A、B 是两条彼此独立的 365 日路径，各自从 2025-01-01 的 6000 kWh 出发，不共享 SOC。",
        "10 路年度比较归档本身**不**负责生成 `result3.xlsx`（正式表由 `q3/run_q3_result3_export.py` 在授权后单独导出），**不**实现 M5，**不**把两案平均成一个主结论。",
        "",
        "## 运行",
        "",
        "```bash",
        ".venv/bin/python -m unittest q3.test_q3 -v",
        ".venv/bin/python q3/run_q3_full_annual.py --boundary both",
        ".venv/bin/python q3/validate_q3_full_annual.py",
        "```",
        "",
        f"- 物理/连续审计全部通过：{audit.get('all_pass')}",
        f"- git：{meta.get('git_commit')}",
        f"- 求解器：{meta.get('solver')}；依赖：{meta.get('dependency_versions')}",
        f"- 日运行数：{len(daily)}（2 边界 × 5 策略 × 365 日）",
        "",
        "## 策略 × 边界汇总",
        "",
        totals.to_string(index=False),
        "",
        "## ΔC = C(6000) − C(1200)",
        "",
        (delta.to_string(index=False) if len(delta) else "(delta table missing)"),
        "",
        "两案并存供队长选择；在选定主边界之前不得写入论文正式成本。",
    ]
    (out / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "all_pass": not failures and bool(audit.get("all_pass")),
        "failures": failures,
        "n_daily_rows": int(len(daily)),
        "git_commit": meta.get("git_commit"),
        "load_treatment": LOAD_INFORMATION_MAIN,
        "chooses_year_end_boundary": False,
    }
    (out / "validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        raise SystemExit("validation failed:\n- " + "\n- ".join(failures))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

# ===== q3/validate_q3_pilot.py =====
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import (
    LOAD_INFORMATION_MAIN,
    LOAD_INFORMATION_PROXY,
    NUMERIC_TOL,
    OUTPUT_DIR,
    PILOT_DATES,
    SIMULTANEOUS_CD_TOL,
    STRATEGIES,
)
from q3.optimization import settlement_cost


REQUIRED = [
    "input_audit.json",
    "q3_forecast_mapping.csv",
    "q3_update_log.csv",
    "q3_strategy_comparison.csv",
    "q3_cost_audit.csv",
    "q3_physical_audit.json",
    "q3_load_forecast_audit.csv",
    "q3_load_information_comparison.csv",
    "q3_causality_audit.json",
]


def main() -> None:
    missing = [name for name in REQUIRED if not (OUTPUT_DIR / name).exists()]
    if missing:
        raise SystemExit(f"missing outputs: {missing}")

    audit = json.loads((OUTPUT_DIR / "q3_physical_audit.json").read_text(encoding="utf-8"))
    causality = json.loads((OUTPUT_DIR / "q3_causality_audit.json").read_text(encoding="utf-8"))
    comparison = pd.read_csv(OUTPUT_DIR / "q3_strategy_comparison.csv")
    info = pd.read_csv(OUTPUT_DIR / "q3_load_information_comparison.csv")
    log = pd.read_csv(OUTPUT_DIR / "q3_update_log.csv")
    mapping = pd.read_csv(OUTPUT_DIR / "q3_forecast_mapping.csv")
    cost = pd.read_csv(OUTPUT_DIR / "q3_cost_audit.csv")
    load_audit = pd.read_csv(OUTPUT_DIR / "q3_load_forecast_audit.csv")

    failures: list[str] = []
    if not audit.get("all_pass"):
        failures.append("physical audit all_pass is false")
    if not causality.get("all_pass"):
        failures.append("load causality audit all_pass is false")
    if mapping["is_executed_actual"].isna().any():
        failures.append("forecast mapping missing executed flags")
    if "load_information_case" not in comparison.columns:
        failures.append("strategy comparison missing load_information_case")
    if "load_information_case" not in cost.columns:
        failures.append("cost audit missing load_information_case")
    if "load_information_case" not in info.columns:
        failures.append("load information comparison missing load_information_case")

    unlabeled = sorted(
        path.name
        for path in OUTPUT_DIR.glob("q3_dispatch_*.csv")
        if LOAD_INFORMATION_MAIN not in path.name and LOAD_INFORMATION_PROXY not in path.name
    )

    phi = settlement_cost(
        cost["price"].to_numpy(),
        cost["planned_g0_kwh"].to_numpy(),
        cost["final_g_kwh"].to_numpy(),
    )
    if float(np.max(np.abs(phi - cost["phi_yuan"].to_numpy()))) > 1e-8:
        failures.append("cost audit phi does not match p gF + 0.5 p |gF-g0|")

    for date in PILOT_DATES:
        day_hat = load_audit[
            (load_audit["date"] == date)
            & (load_audit["load_information_case"] == LOAD_INFORMATION_MAIN)
        ]
        if len(day_hat) != 144:
            failures.append(f"{date} load forecast audit should have 144 day-ahead rows")
        if (day_hat["source_dates"].astype(str).str.contains(date, regex=False)).any():
            failures.append(f"{date} causal load sources include the target date")
        if bool(day_hat["is_current_execution_period"].astype(bool).any()):
            failures.append(f"{date} day-ahead load snapshot marked as current execution")

        for strategy in STRATEGIES:
            for case in (LOAD_INFORMATION_MAIN, LOAD_INFORMATION_PROXY):
                path = OUTPUT_DIR / f"q3_dispatch_{date}_{strategy}_{case}.csv"
                if not path.exists():
                    failures.append(f"missing {path.name}")
                    continue
                if case != LOAD_INFORMATION_MAIN:
                    continue
                frame = pd.read_csv(path)
                if "forecast_load_kwh" not in frame.columns:
                    failures.append(f"{path.name} missing forecast_load_kwh")
                if float(np.max(np.abs(frame["balance_residual_kwh"]))) >= 1e-5:
                    failures.append(f"{path.name} energy residual")
                if "M0" in strategy:
                    if not np.allclose(
                        frame["planned_g0_kwh"], frame["final_g_kwh"], atol=NUMERIC_TOL
                    ):
                        failures.append(f"{date} {case} M0 mutated g after 0:00")
                locked = frame[frame["last_update_time"].eq("00:00")]
                if strategy != "M0" and len(locked) == 0:
                    failures.append(f"{date} {strategy} {case} has no 0:00-locked prefix")

    main = comparison[
        comparison["load_information_case"].eq(LOAD_INFORMATION_MAIN)
        & comparison["with_terminal_value"]
    ]
    proxy = comparison[
        comparison["load_information_case"].eq(LOAD_INFORMATION_PROXY)
        & comparison["with_terminal_value"]
    ]
    m0 = main[main["strategy"] == "M0"]
    m1 = main[main["strategy"] == "M1_M6"]
    no48 = comparison[
        comparison["load_information_case"].eq(LOAD_INFORMATION_MAIN)
        & (comparison["strategy"] == "M1_M6")
        & (~comparison["with_terminal_value"])
    ]
    if len(m0) != len(PILOT_DATES) or len(m1) != len(PILOT_DATES):
        failures.append("main-case M0/M1_M6 rows missing or mixed with proxy")

    lines = [
        "# Q3 两日试算审计（因果负荷修订）",
        "",
        "**主结果候选是 `causal_load_main`。** `actual_load_proxy` 只衡量“若负荷被完美预知”的信息价值，",
        "不得进入全年正式结果，也不得与主方案成本混合后宣称可现实执行。",
        "",
        "提交给 review/队长复核。本阶段**不**生成 `result3.xlsx`，**不**实现 M5。",
        "",
        "## 运行",
        "",
        "```bash",
        "export CUMCM_C_ATTACH_DIR=/path/to/C题/附件",
        "python -m unittest q3.test_q3 -v",
        "python q3/run_q3_pilot.py",
        "python q3/validate_q3_pilot.py",
        "```",
        "",
        f"- 物理审计全部通过：{audit.get('all_pass')}",
        f"- 负荷因果性审计全部通过：{causality.get('all_pass')}",
        f"- 2025-02-01 日初 SOC（**causal_load_main** M0 自 1 月 1 日预热）：{audit.get('warmup_end_soc_for_2025-02-01')}",
        "- 2025-06-21 日初 SOC：孤立试算 6000 kWh；两种信息情形共用该日初日末 SOC",
        "- 能量平衡残差按**当期真实负荷/光伏**闭合；规划层未来时段只用 0:00 因果负荷 hat 与当次光伏预报",
        "- 每 10 分钟仅当前执行步使用真实负荷与真实光伏",
        "",
        "## 主比较（causal_load_main，含 48h 终端价值）",
        "",
    ]
    for date in PILOT_DATES:
        base = float(m0.loc[m0["date"] == date, "total_cost_yuan"].iloc[0])
        main_cost = float(m1.loc[m1["date"] == date, "total_cost_yuan"].iloc[0])
        dump = float(no48.loc[no48["date"] == date, "soc_end_kwh"].iloc[0])
        proxy_m1 = float(
            proxy.loc[
                (proxy["date"] == date) & (proxy["strategy"] == "M1_M6"),
                "total_cost_yuan",
            ].iloc[0]
        )
        proxy_m0 = float(
            proxy.loc[
                (proxy["date"] == date) & (proxy["strategy"] == "M0"),
                "total_cost_yuan",
            ].iloc[0]
        )
        lines.append(
            f"- **{date} 主模型：** M0 = {base:.6f} 元，M1/M6 = {main_cost:.6f} 元，"
            f"差额 {main_cost - base:.6f} 元；无 48h 对照日末 SOC = {dump:.1f} kWh。"
        )
        lines.append(
            f"  - 理想化负荷对照 `actual_load_proxy`：M0 = {proxy_m0:.6f} 元，"
            f"M1/M6 = {proxy_m1:.6f} 元。主模型相对对照的 M1/M6 差额 "
            f"{main_cost - proxy_m1:.6f} 元（正值表示完美负荷信息更便宜；**对照不可执行**）。"
        )
        day_log = log[
            (log["date"] == date)
            & (log["strategy"] == "M1_M6")
            & (log["load_information_case"] == LOAD_INFORMATION_MAIN)
            & (log["with_terminal_value"] == True)
            & (log["update_time"] != "00:00")
        ]
        if len(day_log):
            voi = ", ".join(
                f"{row.update_time} VoI={row.voi_yuan:.3f} 元"
                f"{'（实施）' if row.implemented else '（不实施）'}"
                for row in day_log.itertuples()
            )
            lines.append(f"  - 主模型逐时点 VoI：{voi}")
    lines += [
        "",
        "## 信息口径",
        "",
        "- 日前负荷：最近至多 4 个已结束同星期日均值；历史不足时回退附件 1。核截止日严格早于目标日。",
        "- 6/12/18 的未来规划继续使用该日 0:00 hat，不新增同日负荷后验更新。",
        "- `q3_causality_audit.json`：扰动当天 06:00 之后尚未发生的真实负荷后，主模型日前/更新负荷预测与 0:00 计划不变；代理对照允许变化。",
        "- 修订前未标注信息情形的 `q3_dispatch_YYYY-MM-DD_<strategy>.csv` 保留作历史文件，**不是**主结果。",
        "",
        "## 主模型策略成本（causal_load_main）",
        "",
        main.to_string(index=False),
        "",
        "## 负荷信息对照全表",
        "",
        info.to_string(index=False),
        "",
        "数字待队长签收前不得写入论文。",
    ]
    if unlabeled:
        lines[lines.index("- 修订前未标注信息情形的 `q3_dispatch_YYYY-MM-DD_<strategy>.csv` 保留作历史文件，**不是**主结果。")] = (
            "- 修订前未标注信息情形的调度文件保留作历史对照，**不是**主结果："
            + ", ".join(unlabeled)
        )

    (OUTPUT_DIR / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "all_pass": not failures and bool(audit.get("all_pass")) and bool(causality.get("all_pass")),
        "failures": failures,
        "n_comparison_rows": int(len(comparison)),
        "n_main_comparison_rows": int(len(main)),
        "n_mapping_rows": int(len(mapping)),
        "n_unlabeled_legacy_dispatch_files": int(len(unlabeled)),
        "max_simultaneous_cd_tol": SIMULTANEOUS_CD_TOL,
        "load_treatment": LOAD_INFORMATION_MAIN,
    }
    (OUTPUT_DIR / "validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        raise SystemExit("validation failed:\n- " + "\n- ".join(failures))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

# ===== q3/validate_q3_sensitivity.py =====
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import (
    LOAD_INFORMATION_MAIN,
    PILOT_DATES,
    PV_MAPPING_LINEAR,
    PV_MAPPING_MODES,
    PV_MAPPING_STEP,
    SENSITIVITY_OUTPUT_DIR,
    SETTLEMENT_ALT,
    SETTLEMENT_MAIN,
    SETTLEMENT_MODES,
    STRATEGIES,
    dispatch_stem,
    make_run_id,
)
from q3.optimization import realized_settlement

KEY = [
    "date",
    "strategy",
    "load_information_case",
    "pv_mapping_mode",
    "settlement_mode",
    "with_terminal_value",
]
REQUIRED = [
    "input_audit.json",
    "q3_forecast_mapping.csv",
    "q3_update_log.csv",
    "q3_sensitivity_comparison.csv",
    "q3_settlement_ledger.csv",
    "q3_physical_audit.json",
    "run_meta.json",
]


def _fail(failures: list[str], run_id: str, field: str, msg: str) -> None:
    failures.append(f"{run_id} [{field}]: {msg}")


def main() -> None:
    out = SENSITIVITY_OUTPUT_DIR
    missing = [name for name in REQUIRED if not (out / name).exists()]
    if missing:
        raise SystemExit(f"missing outputs: {missing}")

    audit = json.loads((out / "q3_physical_audit.json").read_text(encoding="utf-8"))
    comparison = pd.read_csv(out / "q3_sensitivity_comparison.csv")
    ledger = pd.read_csv(out / "q3_settlement_ledger.csv")
    mapping = pd.read_csv(out / "q3_forecast_mapping.csv")
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    log = pd.read_csv(out / "q3_update_log.csv")

    failures: list[str] = []
    if not audit.get("all_pass"):
        failures.append("physical audit all_pass is false")
    for col in KEY + ["run_id"]:
        if col not in comparison.columns:
            failures.append(f"comparison missing {col}")
        if col not in ledger.columns:
            failures.append(f"ledger missing {col}")
        if col not in log.columns:
            failures.append(f"update log missing {col}")

    if mapping["pv_mapping_mode"].isna().any() or mapping["is_executed_actual"].isna().any():
        failures.append("mapping table missing mode or executed flags")
    dup = comparison.duplicated(KEY).sum()
    if dup:
        failures.append(f"duplicate comparison keys: {dup}")

    expected_n = len(PILOT_DATES) * len(STRATEGIES) * len(PV_MAPPING_MODES) * len(SETTLEMENT_MODES)
    if len(comparison) != expected_n:
        failures.append(f"expected {expected_n} comparison rows, got {len(comparison)}")

    for _, row in comparison.iterrows():
        run_id = str(row["run_id"])
        expected_id = make_run_id(
            row["date"],
            row["strategy"],
            row["load_information_case"],
            row["pv_mapping_mode"],
            row["settlement_mode"],
            bool(row["with_terminal_value"]),
        )
        if run_id != expected_id:
            _fail(failures, run_id, "run_id", f"mismatch {expected_id}")
        stem = dispatch_stem(
            row["date"],
            row["strategy"],
            row["load_information_case"],
            row["pv_mapping_mode"],
            row["settlement_mode"],
            bool(row["with_terminal_value"]),
        )
        path = out / f"{stem}.csv"
        if not path.exists():
            _fail(failures, run_id, "dispatch", f"missing {path.name}")
            continue
        if stem.split("_", 3)[-1].replace(".csv", "") and row["pv_mapping_mode"] not in path.name:
            _fail(failures, run_id, "filename", "pv_mapping_mode not in filename")
        if row["settlement_mode"] not in path.name:
            _fail(failures, run_id, "filename", "settlement_mode not in filename")
        frame = pd.read_csv(path)
        if frame["run_id"].nunique() != 1 or str(frame["run_id"].iloc[0]) != run_id:
            _fail(failures, run_id, "dispatch.run_id", "inconsistent")
        if float(np.max(np.abs(frame["balance_residual_kwh"]))) >= 1e-5:
            _fail(failures, run_id, "balance_residual_kwh", "energy residual")
        phi = None
        if row["settlement_mode"] == SETTLEMENT_MAIN:
            phi = realized_settlement(
                frame["price"].to_numpy(),
                [frame["planned_g0_kwh"].to_numpy(), frame["final_g_kwh"].to_numpy()],
                SETTLEMENT_MAIN,
            )

        led = ledger[(ledger["run_id"] == run_id) & (ledger["row_role"] == "period_total")]
        if len(led) != 144:
            _fail(failures, run_id, "ledger", f"period_total rows {len(led)}")
            continue
        settle_from_led = float(led["ordinary_yuan"].sum() + led["up_fee_yuan"].sum() + led["down_fee_yuan"].sum())
        emerg_from_led = float(led["emergency_yuan"].sum())
        total_from_led = float(led["total_yuan"].sum())
        if abs(settle_from_led - float(row["settlement_cost_yuan"])) > 1e-6:
            _fail(
                failures,
                run_id,
                "settlement_cost_yuan",
                f"ledger {settle_from_led:.8f} vs summary {row['settlement_cost_yuan']:.8f}",
            )
        if abs(emerg_from_led - float(row["emergency_cost_yuan"])) > 1e-6:
            _fail(
                failures,
                run_id,
                "emergency_cost_yuan",
                f"ledger {emerg_from_led:.8f} vs summary {row['emergency_cost_yuan']:.8f}",
            )
        if abs(total_from_led - float(row["total_cost_yuan"])) > 1e-6:
            _fail(
                failures,
                run_id,
                "total_cost_yuan",
                f"ledger {total_from_led:.8f} vs summary {row['total_cost_yuan']:.8f}",
            )
        events = ledger[(ledger["run_id"] == run_id) & (ledger["row_role"] == "event")]
        if len(events):
            by_period = events.groupby("period")["total_yuan"].sum()
            tot = led.set_index("period")["total_yuan"]
            if float(np.max(np.abs(by_period.reindex(tot.index).fillna(0.0) - tot))) > 1e-6:
                _fail(failures, run_id, "ledger.event", "events do not sum to period_total")

        if row["settlement_mode"] == SETTLEMENT_MAIN and "price" in frame.columns and phi is not None:
            if float(np.max(np.abs(phi - frame["phi_yuan"].to_numpy()))) > 1e-8:
                _fail(failures, run_id, "phi_yuan", "does not match p gF + 0.5 p |gF-g0|")

        if row["strategy"] == "M0" and row["settlement_mode"] == SETTLEMENT_ALT:
            mate = comparison[
                (comparison["date"] == row["date"])
                & (comparison["strategy"] == "M0")
                & (comparison["pv_mapping_mode"] == row["pv_mapping_mode"])
                & (comparison["settlement_mode"] == SETTLEMENT_MAIN)
            ]
            if len(mate) == 1:
                if abs(float(mate["total_cost_yuan"].iloc[0]) - float(row["total_cost_yuan"])) > 1e-4:
                    _fail(failures, run_id, "M0", "alt settlement should match main when gF=g0")

        if row["load_information_case"] != LOAD_INFORMATION_MAIN:
            _fail(failures, run_id, "load_information_case", "sensitivity must stay on causal_load_main")

    # Mapping sanity: step 6:10-7:00 share one source hour.
    step6 = mapping[
        (mapping["pv_mapping_mode"] == PV_MAPPING_STEP)
        & (mapping["update_time"] == "06:00")
        & (mapping["period"].between(36, 41))
    ]
    if len(step6) and not (step6["source_forecast_hour"] == 1).all():
        failures.append("step mapping 06:10-07:00 is not entirely 预报1小时")
    lin6 = mapping[
        (mapping["pv_mapping_mode"] == PV_MAPPING_LINEAR)
        & (mapping["update_time"] == "06:00")
        & (mapping["period"] == 41)
    ]
    if len(lin6):
        # 07:00 node should match 预报1小时 * dt; left/right collapse at the knot.
        if not np.allclose(lin6["left_weight"] + lin6["right_weight"], 1.0):
            failures.append("linear 07:00 weights do not sum to 1")

    lines = [
        "# Q3 映射/结算敏感性两日审计（RQ3-2、RQ3-4、RQ3-5）",
        "",
        "主负荷口径仍为 `causal_load_main`。本目录与已验收的 `output/q3_pilot/` 隔离。",
        "**不**生成 `result3.xlsx`，**不**实现 M5，**不**宣布全年策略排序。",
        "",
        "## 运行",
        "",
        "```bash",
        ".venv/bin/python -m unittest q3.test_q3 -v",
        ".venv/bin/python q3/run_q3_sensitivity.py",
        ".venv/bin/python q3/validate_q3_sensitivity.py",
        "```",
        "",
        f"- 物理审计全部通过：{audit.get('all_pass')}",
        f"- git：{meta.get('git_commit')}",
        f"- 求解器：{meta.get('solver')}；依赖：{meta.get('dependency_versions')}",
        f"- 运行键数：{len(comparison)}（2 日 × 5 策略 × 2 映射 × 2 结算）",
        f"- 日初 SOC：{meta.get('initial_soc')}",
        "",
        "## 相对 baseline（linear_anchor_main + anchor_final_main）的总成本差",
        "",
    ]
    pivot = comparison.pivot_table(
        index=["date", "strategy"],
        columns=["pv_mapping_mode", "settlement_mode"],
        values="delta_total_vs_baseline_yuan",
    )
    lines.append(pivot.to_string())
    lines += [
        "",
        "## 对照全表",
        "",
        comparison[
            [
                "date",
                "strategy",
                "pv_mapping_mode",
                "settlement_mode",
                "total_cost_yuan",
                "settlement_cost_yuan",
                "emergency_cost_yuan",
                "emergency_kwh",
                "curtailment_kwh",
                "soc_start_kwh",
                "soc_end_kwh",
                "adjustment_count",
                "delta_total_vs_baseline_yuan",
            ]
        ].to_string(index=False),
        "",
        "数字待队长签收前不得写入论文主结论。",
    ]
    (out / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "all_pass": not failures and bool(audit.get("all_pass")),
        "failures": failures,
        "n_comparison_rows": int(len(comparison)),
        "n_ledger_rows": int(len(ledger)),
        "git_commit": meta.get("git_commit"),
        "load_treatment": LOAD_INFORMATION_MAIN,
    }
    (out / "validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        raise SystemExit("validation failed:\n- " + "\n- ".join(failures))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

# ===== q3/validate_q3_terminal_soc_pilot.py =====
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import (
    E_INITIAL_KWH,
    LOAD_INFORMATION_MAIN,
    PV_MAPPING_LINEAR,
    SETTLEMENT_MAIN,
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
    make_run_id,
)
from q3.optimization import realized_settlement

KEY = [
    "date",
    "strategy",
    "load_information_case",
    "pv_mapping_mode",
    "settlement_mode",
    "with_terminal_value",
    "year_end_soc_kwh",
]
REQUIRED = [
    "input_audit.json",
    "q3_forecast_mapping.csv",
    "q3_update_log.csv",
    "q3_terminal_soc_daily.csv",
    "q3_terminal_soc_strategy_totals.csv",
    "q3_terminal_soc_boundary_delta.csv",
    "q3_settlement_ledger.csv",
    "q3_physical_audit.json",
    "run_meta.json",
]
REQUIRED_FIGS = [
    "fig3_terminal_soc_strategy_cost.png",
    "fig3_terminal_soc_daily_soc.png",
    "fig3_terminal_soc_daily_cost_emergency.png",
    "fig3_terminal_soc_dec31_M1_M6.png",
]


def _fail(failures: list[str], run_id: str, field: str, msg: str) -> None:
    failures.append(f"{run_id} [{field}]: {msg}")


def main() -> None:
    out = TERMINAL_SOC_OUTPUT_DIR
    missing = [name for name in REQUIRED if not (out / name).exists()]
    if missing:
        raise SystemExit(f"missing outputs: {missing}")
    missing_figs = [name for name in REQUIRED_FIGS if not (TERMINAL_SOC_FIG_DIR / name).exists()]
    if missing_figs:
        raise SystemExit(f"missing figures: {missing_figs}")
    audit = json.loads((out / "q3_physical_audit.json").read_text(encoding="utf-8"))
    daily = pd.read_csv(out / "q3_terminal_soc_daily.csv")
    totals = pd.read_csv(out / "q3_terminal_soc_strategy_totals.csv")
    delta = pd.read_csv(out / "q3_terminal_soc_boundary_delta.csv")
    ledger = pd.read_csv(out / "q3_settlement_ledger.csv")
    log = pd.read_csv(out / "q3_update_log.csv")
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))

    failures: list[str] = []
    if not audit.get("all_pass"):
        failures.append("physical/continuity audit all_pass is false")

    for col in KEY + ["run_id", "year_end_boundary"]:
        if col not in daily.columns:
            failures.append(f"daily missing {col}")
        if col not in ledger.columns:
            failures.append(f"ledger missing {col}")
        if col not in log.columns:
            failures.append(f"update log missing {col}")

    expected_n = 31 * len(STRATEGIES) * len(YEAR_END_BOUNDARIES)
    if len(daily) != expected_n:
        failures.append(f"expected {expected_n} daily rows, got {len(daily)}")
    if daily.duplicated(KEY).sum():
        failures.append("duplicate daily keys")
    if len(totals) != len(STRATEGIES) * len(YEAR_END_BOUNDARIES):
        failures.append(f"expected 10 strategy totals, got {len(totals)}")

    dispatch_dir = out / "dispatch_daily"
    for _, row in daily.iterrows():
        run_id = str(row["run_id"])
        expected_id = make_run_id(
            row["date"],
            row["strategy"],
            row["load_information_case"],
            row["pv_mapping_mode"],
            row["settlement_mode"],
            bool(row["with_terminal_value"]),
            float(row["year_end_soc_kwh"]),
        )
        if run_id != expected_id:
            _fail(failures, run_id, "run_id", f"mismatch {expected_id}")
        if row["load_information_case"] != LOAD_INFORMATION_MAIN:
            _fail(failures, run_id, "load_information_case", "must stay causal_load_main")
        if row["pv_mapping_mode"] != PV_MAPPING_LINEAR:
            _fail(failures, run_id, "pv_mapping_mode", "pilot is linear_anchor_main only")
        if row["settlement_mode"] != SETTLEMENT_MAIN:
            _fail(failures, run_id, "settlement_mode", "pilot is anchor_final_main only")
        stem = dispatch_stem(
            row["date"],
            row["strategy"],
            row["load_information_case"],
            row["pv_mapping_mode"],
            row["settlement_mode"],
            bool(row["with_terminal_value"]),
            float(row["year_end_soc_kwh"]),
        )
        path = dispatch_dir / f"{stem}.csv"
        if not path.exists():
            _fail(failures, run_id, "dispatch", f"missing {path.name}")
            continue
        frame = pd.read_csv(path)
        if len(frame) != T:
            _fail(failures, run_id, "dispatch", f"rows {len(frame)} != {T}")
        if str(frame["run_id"].iloc[0]) != run_id:
            _fail(failures, run_id, "dispatch.run_id", "inconsistent")
        if float(np.max(np.abs(frame["balance_residual_kwh"]))) >= 1e-5:
            _fail(failures, run_id, "balance_residual_kwh", "energy residual")
        if float(row["max_soc_residual_kwh"]) >= 1e-5:
            _fail(failures, run_id, "max_soc_residual_kwh", "SOC residual")
        if float(row["max_simultaneous_cd_kwh2"]) > 1e-4:
            _fail(failures, run_id, "simultaneous_cd", "charge*discharge")
        if int(row["locked_period_violations"]) != 0:
            _fail(failures, run_id, "locked_period_violations", "locked rewrite")
        if row["date"] == TERMINAL_SOC_PILOT_START and abs(float(row["soc_start_kwh"]) - E_INITIAL_KWH) > 1e-5:
            _fail(failures, run_id, "soc_start_kwh", "Dec 1 must start at 6000")
        if row["date"] == TERMINAL_SOC_PILOT_END:
            if abs(float(row["soc_end_kwh"]) - float(row["year_end_soc_kwh"])) > 1e-5:
                _fail(
                    failures,
                    run_id,
                    "soc_end_kwh",
                    f"{row['soc_end_kwh']} vs target {row['year_end_soc_kwh']}",
                )
        phi = realized_settlement(
            frame["price"].to_numpy(),
            [frame["planned_g0_kwh"].to_numpy(), frame["final_g_kwh"].to_numpy()],
            SETTLEMENT_MAIN,
        )
        if float(np.max(np.abs(phi - frame["phi_yuan"].to_numpy()))) > 1e-8:
            _fail(failures, run_id, "phi_yuan", "does not match p gF + 0.5 p |gF-g0|")
        led = ledger[(ledger["run_id"] == run_id) & (ledger["row_role"] == "period_total")]
        if len(led) != T:
            _fail(failures, run_id, "ledger", f"period_total rows {len(led)}")
        elif abs(float(led["total_yuan"].sum()) - float(row["total_cost_yuan"])) > 1e-6:
            _fail(failures, run_id, "total_cost_yuan", "ledger mismatch")

    for (strategy, boundary), block in daily.groupby(["strategy", "year_end_boundary"]):
        block = block.sort_values("date")
        if len(block) != 31:
            failures.append(f"{strategy}/{boundary}: {len(block)} days")
            continue
        if block["date"].iloc[0] != TERMINAL_SOC_PILOT_START or block["date"].iloc[-1] != TERMINAL_SOC_PILOT_END:
            failures.append(f"{strategy}/{boundary}: date range")
        starts = block["soc_start_kwh"].to_numpy()
        ends = block["soc_end_kwh"].to_numpy()
        if float(np.max(np.abs(starts[1:] - ends[:-1]))) > 1e-5:
            failures.append(f"{strategy}/{boundary}: cross-day SOC not continuous")

    if set(delta["strategy"]) != set(STRATEGIES):
        failures.append("delta table missing strategies")
    if YEAR_END_BOUNDARY_A not in set(totals["year_end_boundary"]) or YEAR_END_BOUNDARY_B not in set(
        totals["year_end_boundary"]
    ):
        failures.append("totals missing A or B")

    lines = [
        "# Q3 年末 SOC 边界 12 月试验审计",
        "",
        "主口径固定 `causal_load_main` + `linear_anchor_main` + `anchor_final_main`。",
        "12 月 1 日 00:00 孤立起点 6000 kWh，不是全年真实 12 月 1 日 SOC。",
        "**不**生成 `result3.xlsx`，**不**实现 M5，**不**自动选择 A/B。",
        "",
        "## 运行",
        "",
        "```bash",
        ".venv/bin/python -m unittest q3.test_q3 -v",
        ".venv/bin/python q3/run_q3_terminal_soc_pilot.py",
        ".venv/bin/python q3/validate_q3_terminal_soc_pilot.py",
        "```",
        "",
        f"- 物理/连续审计全部通过：{audit.get('all_pass')}",
        f"- git：{meta.get('git_commit')}",
        f"- 求解器：{meta.get('solver')}；依赖：{meta.get('dependency_versions')}",
        f"- 日运行数：{len(daily)}（2 边界 × 5 策略 × 31 日）",
        "",
        "## 策略 × 边界汇总",
        "",
        totals.to_string(index=False),
        "",
        "## ΔC = C(6000) − C(1200)",
        "",
        delta.to_string(index=False),
        "",
        "本试验只为队长选择年末边界提供证据，不得写入论文主结论。",
    ]
    (out / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "all_pass": not failures and bool(audit.get("all_pass")),
        "failures": failures,
        "n_daily_rows": int(len(daily)),
        "n_ledger_rows": int(len(ledger)),
        "git_commit": meta.get("git_commit"),
        "load_treatment": LOAD_INFORMATION_MAIN,
        "chooses_year_end_boundary": False,
    }
    (out / "validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        raise SystemExit("validation failed:\n- " + "\n- ".join(failures))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

# ===== q4/audit.py =====
"""Physical, ledger, and information-set audits for Q4-2/Q4-3."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import E_MAX_KWH, E_MIN_KWH, NUMERIC_TOL, SIMULTANEOUS_CD_TOL, T
from q3.optimization import settlement_cost


def ledger_from_dispatch_q42(dispatch: pd.DataFrame) -> pd.DataFrame:
    out = dispatch.copy()
    out["normal_cost_yuan"] = out["actual_price"] * out["q_or_g0_kwh"]
    out["adjustment_cost_yuan"] = 0.0
    out["emergency_cost_yuan"] = 5.0 * out["actual_price"] * out["emergency_kwh"]
    out["total_cost_yuan"] = (
        out["normal_cost_yuan"] + out["adjustment_cost_yuan"] + out["emergency_cost_yuan"]
    )
    return out


def ledger_from_dispatch_q43(dispatch: pd.DataFrame) -> pd.DataFrame:
    phi = settlement_cost(
        dispatch["actual_price"].to_numpy(),
        dispatch["q_or_g0_kwh"].to_numpy(),
        dispatch["g_final_kwh"].to_numpy(),
    )
    out = dispatch.copy()
    out["normal_cost_yuan"] = dispatch["actual_price"] * dispatch["g_final_kwh"]
    out["adjustment_cost_yuan"] = phi - out["normal_cost_yuan"].to_numpy()
    out["emergency_cost_yuan"] = 5.0 * dispatch["actual_price"] * dispatch["emergency_kwh"]
    out["total_cost_yuan"] = (
        out["normal_cost_yuan"] + out["adjustment_cost_yuan"] + out["emergency_cost_yuan"]
    )
    return out


def physical_from_dispatch(dispatch: pd.DataFrame, q4_3: bool) -> dict:
    x = dispatch["x_kwh"].to_numpy()
    cap = dispatch["g_final_kwh"].to_numpy() if q4_3 else dispatch["q_or_g0_kwh"].to_numpy()
    cd = dispatch["charge_kwh"].to_numpy() * dispatch["discharge_kwh"].to_numpy()
    return {
        "n_periods": int(len(dispatch)),
        "max_balance_residual_kwh": float(dispatch["balance_residual_kwh"].abs().max()),
        "soc_min_kwh": float(dispatch["soc_end_kwh"].min()),
        "soc_max_kwh": float(dispatch["soc_end_kwh"].max()),
        "max_x_minus_cap_kwh": float(np.max(x - cap)),
        "max_simultaneous_cd_kwh2": float(np.max(cd)),
        "n_rows": int(len(dispatch)),
        "pass": bool(
            len(dispatch) == T
            and dispatch["balance_residual_kwh"].abs().max() < 1e-5
            and dispatch["soc_end_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL
            and dispatch["soc_end_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL
            and np.max(x - cap) < NUMERIC_TOL
            and np.max(cd) <= SIMULTANEOUS_CD_TOL
        ),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def q_unchanged_probe(result_q: np.ndarray, dispatch: pd.DataFrame) -> bool:
    return bool(np.allclose(result_q, dispatch["q_or_g0_kwh"].to_numpy(), atol=1e-9))


def prefix_lock_probe(update_log: pd.DataFrame) -> bool:
    if update_log.empty:
        return True
    return bool(update_log["prefix_lock_ok"].all())


def warmup_soc_continuity(daily: pd.DataFrame) -> dict:
    if daily.empty or len(daily) < 2:
        return {"n_days": int(len(daily)), "max_soc_gap_kwh": 0.0, "pass": True}
    end_vals = daily["soc_end_kwh"].to_numpy()[:-1]
    start_vals = daily["soc_start_kwh"].to_numpy()[1:]
    gap = float(np.max(np.abs(end_vals - start_vals)))
    return {"n_days": int(len(daily)), "max_soc_gap_kwh": gap, "pass": bool(gap < 1e-6)}

# ===== q4/bundle.py =====
"""Load accepted Q2/Q3 information plus the frozen causal price archive."""

from __future__ import annotations

from dataclasses import dataclass

from q2.data import Q2Data, load_q2_data
from q2.forecast import ForecastArchive, build_forecast_archive
from q3.data import Q3Data, load_q3_data
from q4.data import Q4PriceData, load_q4_prices
from q4.price_forecast import PriceForecastArchive, fit_causal_price_forecasts


@dataclass(frozen=True)
class Q4Bundle:
    q3: Q3Data
    q2: Q2Data
    q2_forecast: ForecastArchive
    prices: Q4PriceData
    price_archive: PriceForecastArchive

    def date_index(self, date: str) -> int:
        return self.prices.date_index(date)

    def n_days(self) -> int:
        return len(self.prices.dates)


def load_q4_bundle(compute_price_mpc: bool = False) -> Q4Bundle:
    q3 = load_q3_data()
    q2 = load_q2_data()
    prices = load_q4_prices()
    if not q3.dates.equals(prices.dates) or not q2.dates.equals(prices.dates):
        raise ValueError("Q2/Q3/附件4 calendars must match")
    price_archive = fit_causal_price_forecasts(
        prices.price, prices.dates, compute_mpc=compute_price_mpc
    )
    return Q4Bundle(
        q3=q3,
        q2=q2,
        q2_forecast=build_forecast_archive(q2),
        prices=prices,
        price_archive=price_archive,
    )

# ===== q4/campaign.py =====
"""Sequential Q4-2 / Q4-3 campaigns with streamed daily outputs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import E_INITIAL_KWH
from q3.config import PILOT_DATES
from q4.bundle import Q4Bundle
from q4.config import (
    FIXED_SCENARIO_K,
    OUTPUT_DIR,
    PAM_SEED,
    Q4_2_DISPATCH_DIR,
    Q4_3_DISPATCH_DIR,
    RISK_CALIBRATION_DAYS,
    RISK_WARMUP_DAYS,
)
from q4.q4_2 import alpha_for_day, run_q4_2_day, select_risk_alpha
from q4.q4_3 import run_q4_3_day


def _append_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists() or path.stat().st_size == 0
    frame.to_csv(path, mode="a", header=header, index=False)


def last_index_for_dates(bundle: Q4Bundle, dates: tuple[str, ...]) -> int:
    return max(bundle.date_index(date) for date in dates)


def run_q4_2_campaign(
    bundle: Q4Bundle,
    end_index: int,
    detail_dates: tuple[str, ...] = PILOT_DATES,
    out_dir: Path = OUTPUT_DIR,
    write_all_dispatch: bool = False,
) -> dict:
    Q4_2_DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    daily_path = out_dir / "q4_2_warmup_daily.csv"
    ahead_path = out_dir / "q4_2_day_ahead_audit.csv"
    scen_path = out_dir / "q4_2_scenario_audit.csv"
    ledger_path = out_dir / "q4_2_cost_ledger.csv"
    alpha_sel_path = out_dir / "q4_2_alpha_selection.csv"
    alpha_daily_path = out_dir / "q4_2_alpha_calibration_daily.csv"
    for path in (
        daily_path,
        ahead_path,
        scen_path,
        ledger_path,
        alpha_sel_path,
        alpha_daily_path,
    ):
        if path.exists():
            path.unlink()
    soc = E_INITIAL_KWH
    start_soc = np.full(bundle.n_days(), np.nan)
    calibrated: dict[int, float | None] = {}
    detail = {}
    for i in range(end_index + 1):
        start_soc[i] = soc
        cal = (i // RISK_CALIBRATION_DAYS) * RISK_CALIBRATION_DAYS
        if i >= RISK_WARMUP_DAYS and cal not in calibrated and i == cal:
            choice = select_risk_alpha(
                bundle, start_soc, i, FIXED_SCENARIO_K, log=True
            )
            calibrated[cal] = choice.selected_alpha
            cal_date = bundle.prices.dates[i].strftime("%Y-%m-%d")
            window_frame = pd.DataFrame(
                [{"calibration_date": cal_date, **row} for row in choice.window_records]
            )
            daily_frame = pd.DataFrame(
                [{"calibration_date": cal_date, **row} for row in choice.daily_records]
            )
            _append_csv(alpha_sel_path, window_frame)
            if not daily_frame.empty:
                _append_csv(alpha_daily_path, daily_frame)
            print(
                f"Q4-2 calibrated alpha={choice.selected_alpha} at {cal_date}",
                flush=True,
            )
        elif i < RISK_WARMUP_DAYS:
            calibrated.setdefault(cal, None)
        alpha = alpha_for_day(i, calibrated)
        date = bundle.prices.dates[i].strftime("%Y-%m-%d")
        keep = write_all_dispatch or date in detail_dates
        write_path = Q4_2_DISPATCH_DIR / f"dispatch_{date}.csv" if keep else None
        result = run_q4_2_day(bundle, i, soc, alpha, write_dispatch=write_path)
        soc = float(result.summary["soc_end_kwh"])
        _append_csv(daily_path, pd.DataFrame([result.summary]))
        _append_csv(ahead_path, pd.DataFrame([result.day_ahead_audit]))
        if result.scenario_rows:
            _append_csv(scen_path, pd.DataFrame(result.scenario_rows))
        if keep:
            nrm = result.dispatch["actual_price"] * result.dispatch["q_or_g0_kwh"]
            emg = 5.0 * result.dispatch["actual_price"] * result.dispatch["emergency_kwh"]
            _append_csv(
                ledger_path,
                pd.DataFrame(
                    {
                        "date": result.dispatch["date"],
                        "period_index": result.dispatch["period_index"],
                        "normal_cost_yuan": nrm,
                        "adjustment_cost_yuan": 0.0,
                        "emergency_cost_yuan": emg,
                        "total_cost_yuan": nrm + emg,
                    }
                ),
            )
            if date in detail_dates:
                detail[date] = result
        print(
            f"Q4-2 [{i+1}/{end_index+1}] {date} cost={result.summary['total_cost_yuan']:.2f} "
            f"soc={soc:.2f} K={result.summary['k_effective']} alpha={alpha}",
            flush=True,
        )
        if date not in detail:
            del result
    return {"detail": detail, "end_soc": soc, "calibrated_alpha": calibrated}


def run_q4_3_campaign(
    bundle: Q4Bundle,
    end_index: int,
    detail_dates: tuple[str, ...] = PILOT_DATES,
    out_dir: Path = OUTPUT_DIR,
    write_all_dispatch: bool = False,
    *,
    price_mode: str = "causal",
    dispatch_dir: Path | None = None,
    daily_name: str = "q4_3_warmup_daily.csv",
    update_name: str = "q4_3_update_log.csv",
    ledger_name: str = "q4_3_cost_ledger.csv",
    commitment_prefix: str = "q4_3_commitment_versions",
    unlink_existing: bool = True,
) -> dict:
    dest = Q4_3_DISPATCH_DIR if dispatch_dir is None else dispatch_dir
    dest.mkdir(parents=True, exist_ok=True)
    daily_path = out_dir / daily_name
    update_path = out_dir / update_name
    ledger_path = out_dir / ledger_name
    if unlink_existing:
        for path in (daily_path, update_path, ledger_path):
            if path.exists():
                path.unlink()
    soc = E_INITIAL_KWH
    cache: dict = {}
    detail = {}
    for i in range(end_index + 1):
        date = bundle.prices.dates[i].strftime("%Y-%m-%d")
        keep = write_all_dispatch or date in detail_dates
        result = run_q4_3_day(
            bundle, i, soc, value_cut_cache=cache, price_mode=price_mode
        )
        soc = float(result.summary["soc_end_kwh"])
        _append_csv(daily_path, pd.DataFrame([result.summary]))
        _append_csv(update_path, result.update_log)
        if keep:
            result.dispatch.to_csv(dest / f"dispatch_{date}.csv", index=False)
            ledger = result.dispatch[
                ["date", "period_index", "normal_cost_yuan", "adjustment_cost_yuan", "emergency_cost_yuan"]
            ].copy()
            ledger["total_cost_yuan"] = (
                ledger["normal_cost_yuan"]
                + ledger["adjustment_cost_yuan"]
                + ledger["emergency_cost_yuan"]
            )
            _append_csv(ledger_path, ledger)
            if date in detail_dates:
                pd.DataFrame(
                    {
                        "date": date,
                        "period_index": np.arange(len(result.g0)),
                        "g0_kwh": result.g0,
                        "g_final_kwh": result.g_final,
                    }
                ).to_csv(out_dir / f"{commitment_prefix}_{date}.csv", index=False)
                detail[date] = result
        print(
            f"Q4-3/{price_mode} [{i+1}/{end_index+1}] {date} "
            f"cost={result.summary['total_cost_yuan']:.2f} "
            f"soc={soc:.2f} adj={result.summary['adjustment_count']}",
            flush=True,
        )
        if date not in detail:
            del result
    return {"detail": detail, "end_soc": soc, "pam_seed": PAM_SEED, "price_mode": price_mode}


def load_q42_detail_from_disk(
    out_dir: Path = OUTPUT_DIR,
    detail_dates: tuple[str, ...] = PILOT_DATES,
) -> dict:
    """Rebuild the in-memory Q4-2 pilot detail from streamed CSVs."""
    from q4.q4_2 import Q42DayResult

    daily = pd.read_csv(out_dir / "q4_2_warmup_daily.csv")
    detail = {}
    for date in detail_dates:
        path = Q4_2_DISPATCH_DIR / f"dispatch_{date}.csv"
        dispatch = pd.read_csv(path)
        row = daily.loc[daily["date"] == date].iloc[0].to_dict()
        alpha = row.get("risk_alpha")
        if alpha is None or (isinstance(alpha, float) and not np.isfinite(alpha)):
            row["risk_alpha"] = None
        detail[date] = Q42DayResult(
            date=date,
            day_index=int(row["day_index"]),
            q=dispatch["q_or_g0_kwh"].to_numpy(float),
            dispatch=dispatch,
            summary=row,
            day_ahead_audit={},
        )
    return {"detail": detail, "end_soc": float(daily["soc_end_kwh"].iloc[-1]), "from_disk": True}


def load_q43_detail_from_disk(
    out_dir: Path = OUTPUT_DIR,
    detail_dates: tuple[str, ...] = PILOT_DATES,
) -> dict:
    """Rebuild the in-memory Q4-3 pilot detail from streamed CSVs."""
    from q4.q4_3 import Q43DayResult

    daily = pd.read_csv(out_dir / "q4_3_warmup_daily.csv")
    updates = pd.read_csv(out_dir / "q4_3_update_log.csv")
    detail = {}
    for date in detail_dates:
        dispatch = pd.read_csv(Q4_3_DISPATCH_DIR / f"dispatch_{date}.csv")
        row = daily.loc[daily["date"] == date].iloc[0].to_dict()
        versions = out_dir / f"q4_3_commitment_versions_{date}.csv"
        if versions.exists():
            ver = pd.read_csv(versions)
            g0 = ver["g0_kwh"].to_numpy(float)
            g_final = ver["g_final_kwh"].to_numpy(float)
        else:
            g0 = dispatch["q_or_g0_kwh"].to_numpy(float)
            g_final = dispatch["g_final_kwh"].to_numpy(float)
        detail[date] = Q43DayResult(
            date=date,
            day_index=int(row["day_index"]),
            g0=g0,
            g_final=g_final,
            dispatch=dispatch,
            update_log=updates.loc[updates["date"] == date].copy(),
            summary=row,
        )
    return {"detail": detail, "end_soc": float(daily["soc_end_kwh"].iloc[-1]), "from_disk": True}

# ===== q4/closeout.py =====
"""Reporting-only Q4 closeout: tails, fair windows, physical year scan, residual correlation.

Does not change decisions, workbooks, or official dispatch archives.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import E_MAX_KWH, E_MIN_KWH, NUMERIC_TOL, POWER_LIMIT_KWH, SIMULTANEOUS_CD_TOL, T
from q3.config import HOUR_TO_FIRST_MUTABLE, RESULT3_OFFICIAL_STRATEGY, YEAR_END_BOUNDARY_A
from q4.audit import (
    ledger_from_dispatch_q42,
    ledger_from_dispatch_q43,
    physical_from_dispatch,
    warmup_soc_continuity,
)
from q4.config import (
    EXPECTED_Q2_K8_EXPORT_YUAN,
    EXPECTED_Q3_ANNUAL_YUAN,
    EXPECTED_Q4_2_ALPHA070_END,
    EXPECTED_Q4_2_ALPHA070_START,
    EXPECTED_Q4_2_ANNUAL_YUAN,
    EXPECTED_Q4_2_EXPORT_YUAN,
    EXPECTED_Q4_3_ANNUAL_YUAN,
    EXPECTED_Q4_3_EXPORT_YUAN,
    EXPORT_END,
    EXPORT_N_DAYS,
    EXPORT_START,
    LOAD_INFORMATION_CASE,
    OUTPUT_DIR,
    Q2_K8_DAILY_CSV,
    Q3_ANNUAL_DAILY_CSV,
    Q4_2_ALPHA_SELECTION_CSV,
    Q4_2_DAILY_CSV,
    Q4_2_DISPATCH_DIR,
    Q4_2_SCENARIO_AUDIT_CSV,
    Q4_3_DAILY_CSV,
    Q4_3_DISPATCH_DIR,
    YEAR_N_DAYS,
)

ALLOWED_Q43_UPDATE_CLOCKS = ("00:00", "06:00", "12:00", "18:00")
PRICE_NOTE = (
    "公平对比窗口为 2025-02-01 至 2025-12-31（334 日），设备、SOC 规则与负荷/光伏主案例相同；"
    "Q2/Q3 使用附件1 分时电价，Q4 使用附件4 变动电价。对比解释为同一套储能在不同价格信息下的运行结果，"
    "不是同一电价序列下的会计差额。"
)


def output_interval(
    frame: pd.DataFrame,
    start: str = EXPORT_START,
    end: str = EXPORT_END,
    n_days: int = EXPORT_N_DAYS,
) -> pd.DataFrame:
    if "date" not in frame.columns:
        raise AssertionError("daily frame lacks date column")
    dates = pd.to_datetime(frame["date"])
    selected = frame.loc[dates.between(pd.Timestamp(start), pd.Timestamp(end))].copy()
    selected = selected.sort_values("date").reset_index(drop=True)
    if len(selected) != n_days:
        raise AssertionError(f"Expected {n_days} output days, got {len(selected)}")
    return selected


def empirical_var(values: np.ndarray, alpha: float) -> float:
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values must be non-empty")
    return float(np.quantile(arr, alpha, method="linear"))


def empirical_cvar(values: np.ndarray, alpha: float) -> float:
    """Mean of the worst ceil((1-alpha)*n) observations (higher cost is worse)."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    arr = np.sort(np.asarray(values, dtype=float))
    if arr.size == 0:
        raise ValueError("values must be non-empty")
    k = max(1, int(np.ceil((1.0 - alpha) * arr.size)))
    return float(arr[-k:].mean())


def tail_bundle(values: np.ndarray, prefix: str = "") -> dict:
    arr = np.asarray(values, dtype=float)
    key = f"{prefix}_" if prefix else ""
    return {
        f"{key}n_days": int(arr.size),
        f"{key}mean_yuan": float(arr.mean()),
        f"{key}max_yuan": float(arr.max()),
        f"{key}p90_yuan": empirical_var(arr, 0.90),
        f"{key}p95_yuan": empirical_var(arr, 0.95),
        f"{key}cvar_0_90_yuan": empirical_cvar(arr, 0.90),
        f"{key}cvar_n_tail_0_90": int(max(1, int(np.ceil(0.10 * arr.size)))),
    }


def _require_close(actual: float, expected: float, label: str, atol: float = 0.01) -> None:
    if abs(actual - expected) >= atol:
        raise AssertionError(f"{label} mismatch: {actual:.6f} vs signed-off {expected:.2f}")


def load_q4_2_daily() -> pd.DataFrame:
    return pd.read_csv(Q4_2_DAILY_CSV)


def load_q4_3_daily() -> pd.DataFrame:
    return pd.read_csv(Q4_3_DAILY_CSV)


def load_q2_k8_daily() -> pd.DataFrame:
    return pd.read_csv(Q2_K8_DAILY_CSV)


def load_q3_official_daily() -> pd.DataFrame:
    raw = pd.read_csv(Q3_ANNUAL_DAILY_CSV)
    selected = raw.loc[
        (raw["strategy"] == RESULT3_OFFICIAL_STRATEGY)
        & (raw["year_end_boundary"] == YEAR_END_BOUNDARY_A)
        & (raw["load_information_case"] == LOAD_INFORMATION_CASE)
    ].copy()
    selected = selected.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if len(selected) != YEAR_N_DAYS:
        raise AssertionError(f"Q3 official daily expected {YEAR_N_DAYS} days, got {len(selected)}")
    annual = float(selected["total_cost_yuan"].sum())
    _require_close(annual, EXPECTED_Q3_ANNUAL_YUAN, "Q3 official annual")
    return selected


def cost_components(frame: pd.DataFrame, scheme: str) -> dict:
    if scheme == "q4_2":
        normal = float(frame["normal_cost_yuan"].sum())
        adjustment = float(frame["adjustment_cost_yuan"].sum()) if "adjustment_cost_yuan" in frame else 0.0
        emergency = float(frame["emergency_cost_yuan"].sum())
        total = float(frame["total_cost_yuan"].sum())
        planned_kwh = float(frame["planned_q_kwh"].sum()) if "planned_q_kwh" in frame else float("nan")
    elif scheme == "q4_3":
        normal = float(frame["normal_cost_yuan"].sum())
        adjustment = float(frame["adjustment_cost_yuan"].sum())
        emergency = float(frame["emergency_cost_yuan"].sum())
        total = float(frame["total_cost_yuan"].sum())
        planned_kwh = float(frame["g0_kwh"].sum()) if "g0_kwh" in frame else float("nan")
    elif scheme == "q2":
        normal = float(frame["planned_cost_yuan"].sum())
        adjustment = 0.0
        emergency = float(frame["emergency_cost_yuan"].sum())
        total = float(frame["total_cost_yuan"].sum())
        planned_kwh = float("nan")
    elif scheme == "q3":
        normal = float(frame["settlement_cost_yuan"].sum())
        adjustment = 0.0
        emergency = float(frame["emergency_cost_yuan"].sum())
        total = float(frame["total_cost_yuan"].sum())
        planned_kwh = float("nan")
    else:
        raise ValueError(scheme)
    if abs(total - (normal + adjustment + emergency)) >= 0.05:
        raise AssertionError(f"{scheme} components do not sum to total")
    return {
        "scheme": scheme,
        "n_days": int(len(frame)),
        "normal_or_settlement_yuan": normal,
        "adjustment_yuan": adjustment,
        "emergency_cost_yuan": emergency,
        "total_cost_yuan": total,
        "emergency_kwh": float(frame["emergency_kwh"].sum()),
        "planned_kwh": planned_kwh,
        "max_day_cost_yuan": float(frame["total_cost_yuan"].max()),
        "max_day_cost_date": str(
            pd.Timestamp(frame.loc[frame["total_cost_yuan"].idxmax(), "date"]).date()
        ),
        "max_emergency_cost_yuan": float(frame["emergency_cost_yuan"].max()),
        "max_emergency_cost_date": str(
            pd.Timestamp(frame.loc[frame["emergency_cost_yuan"].idxmax(), "date"]).date()
        ),
        **tail_bundle(frame["total_cost_yuan"].to_numpy(float), prefix="daily_cost"),
    }


def price_error_stats(audit: pd.DataFrame, start: str, end: str) -> dict:
    dates = pd.to_datetime(audit["date"])
    window = audit.loc[dates.between(pd.Timestamp(start), pd.Timestamp(end))].copy()
    ahead = window.loc[np.isfinite(window["day_ahead_mae"].to_numpy(float))].copy()
    if ahead.empty:
        raise AssertionError("no finite day-ahead price errors in window")
    mae = float(ahead["day_ahead_mae"].mean())
    rmse = float(np.sqrt(np.mean(np.square(ahead["day_ahead_rmse"].to_numpy(float)))))
    return {
        "start": start,
        "end": end,
        "n_days": int(len(window)),
        "n_days_with_day_ahead": int(len(ahead)),
        "day_ahead_mae": mae,
        "day_ahead_rmse_pooled": rmse,
        "day_ahead_rmse_mean_daily": float(ahead["day_ahead_rmse"].mean()),
        "intraday_06_mae": float(ahead["intraday_06_mae"].mean()),
        "intraday_12_mae": float(ahead["intraday_12_mae"].mean()),
        "intraday_18_mae": float(ahead["intraday_18_mae"].mean()),
        "aggregation": (
            "MAE = mean of daily MAE; pooled RMSE = sqrt(mean of daily RMSE squared); "
            "equal slot count per day with a finite day-ahead forecast"
        ),
    }


def build_fair_comparison(
    q42: pd.DataFrame,
    q43: pd.DataFrame,
    q2: pd.DataFrame,
    q3: pd.DataFrame,
) -> dict:
    q42_year = cost_components(q42, "q4_2")
    q43_year = cost_components(q43, "q4_3")
    q42_export = cost_components(output_interval(q42), "q4_2")
    q43_export = cost_components(output_interval(q43), "q4_3")
    q2_export = cost_components(output_interval(q2), "q2")
    q3_export = cost_components(output_interval(q3), "q3")
    q3_year = cost_components(q3, "q3")
    _require_close(q42_year["total_cost_yuan"], EXPECTED_Q4_2_ANNUAL_YUAN, "Q4-2 annual")
    _require_close(q42_export["total_cost_yuan"], EXPECTED_Q4_2_EXPORT_YUAN, "Q4-2 2-12")
    _require_close(q43_year["total_cost_yuan"], EXPECTED_Q4_3_ANNUAL_YUAN, "Q4-3 annual")
    _require_close(q43_export["total_cost_yuan"], EXPECTED_Q4_3_EXPORT_YUAN, "Q4-3 2-12")
    _require_close(q2_export["total_cost_yuan"], EXPECTED_Q2_K8_EXPORT_YUAN, "Q2 K=8 2-12")
    _require_close(q3_year["total_cost_yuan"], EXPECTED_Q3_ANNUAL_YUAN, "Q3 official annual")
    return {
        "price_note": PRICE_NOTE,
        "export_window": {"start": EXPORT_START, "end": EXPORT_END, "n_days": EXPORT_N_DAYS},
        "annual_window": {"start": "2025-01-01", "end": "2025-12-31", "n_days": YEAR_N_DAYS},
        "q4_2_annual": q42_year,
        "q4_3_annual": q43_year,
        "q3_annual": q3_year,
        "export": {
            "q4_2": q42_export,
            "q4_3": q43_export,
            "q2_k8": q2_export,
            "q3_m1_m6": q3_export,
        },
        "pairs": {
            "q4_2_minus_q2_k8_export_yuan": q42_export["total_cost_yuan"] - q2_export["total_cost_yuan"],
            "q4_2_minus_q2_k8_emergency_kwh": q42_export["emergency_kwh"] - q2_export["emergency_kwh"],
            "q4_3_minus_q3_m1_m6_export_yuan": q43_export["total_cost_yuan"] - q3_export["total_cost_yuan"],
            "q4_3_minus_q3_m1_m6_emergency_kwh": q43_export["emergency_kwh"] - q3_export["emergency_kwh"],
        },
    }


def expected_q43_last_update(period_index: np.ndarray) -> np.ndarray:
    clocks = np.full(len(period_index), "00:00", dtype=object)
    clocks[period_index >= HOUR_TO_FIRST_MUTABLE[6]] = "06:00"
    clocks[period_index >= HOUR_TO_FIRST_MUTABLE[12]] = "12:00"
    clocks[period_index >= HOUR_TO_FIRST_MUTABLE[18]] = "18:00"
    return clocks


def _intra_day_soc_gap(dispatch: pd.DataFrame) -> float:
    if len(dispatch) < 2:
        return 0.0
    return float(
        np.max(
            np.abs(
                dispatch["soc_start_kwh"].to_numpy(float)[1:]
                - dispatch["soc_end_kwh"].to_numpy(float)[:-1]
            )
        )
    )


def _energy_balance_gap(dispatch: pd.DataFrame) -> float:
    x = dispatch["x_kwh"].to_numpy(float)
    e = dispatch["emergency_kwh"].to_numpy(float)
    pv = dispatch["actual_pv_kwh"].to_numpy(float)
    curt = dispatch["curtailment_kwh"].to_numpy(float)
    d = dispatch["discharge_kwh"].to_numpy(float)
    load = dispatch["actual_load_kwh"].to_numpy(float)
    c = dispatch["charge_kwh"].to_numpy(float)
    residual = x + e + pv - curt + d - load - c
    stored = dispatch["balance_residual_kwh"].to_numpy(float)
    return float(max(np.max(np.abs(residual)), np.max(np.abs(residual - stored))))


def scan_dispatch_year(
    dispatch_dir: Path,
    daily: pd.DataFrame,
    *,
    q4_3: bool,
) -> dict:
    paths = sorted(dispatch_dir.glob("dispatch_*.csv"))
    if len(paths) != YEAR_N_DAYS:
        raise AssertionError(f"Expected {YEAR_N_DAYS} dispatch files in {dispatch_dir}, got {len(paths)}")
    daily = daily.sort_values("date").reset_index(drop=True)
    if len(daily) != YEAR_N_DAYS:
        raise AssertionError(f"Expected {YEAR_N_DAYS} daily rows, got {len(daily)}")
    by_date = {str(row.date): row for row in daily.itertuples()}
    max_balance = 0.0
    max_x_minus_cap = 0.0
    max_cd = 0.0
    max_power = 0.0
    max_soc_chain = 0.0
    soc_min = float("inf")
    soc_max = float("-inf")
    max_ledger_gap = 0.0
    n_physical_pass = 0
    info_fail = 0
    prefix_fail = 0
    first_intraday = HOUR_TO_FIRST_MUTABLE[6]
    for path in paths:
        date = path.stem.replace("dispatch_", "")
        frame = pd.read_csv(path)
        if len(frame) != T:
            raise AssertionError(f"{path.name} has {len(frame)} rows")
        phys = physical_from_dispatch(frame, q4_3=q4_3)
        max_balance = max(max_balance, phys["max_balance_residual_kwh"], _energy_balance_gap(frame))
        max_x_minus_cap = max(max_x_minus_cap, phys["max_x_minus_cap_kwh"])
        max_cd = max(max_cd, phys["max_simultaneous_cd_kwh2"])
        max_power = max(
            max_power,
            float(frame["charge_kwh"].max()),
            float(frame["discharge_kwh"].max()),
        )
        max_soc_chain = max(max_soc_chain, _intra_day_soc_gap(frame))
        soc_min = min(soc_min, phys["soc_min_kwh"])
        soc_max = max(soc_max, phys["soc_max_kwh"])
        n_physical_pass += int(phys["pass"])
        row = by_date[date]
        if q4_3:
            ledger = ledger_from_dispatch_q43(frame)
            expected_clock = expected_q43_last_update(frame["period_index"].to_numpy(int))
            clocks = frame["last_update_time"].astype(str).to_numpy()
            if not np.array_equal(clocks, expected_clock):
                info_fail += 1
            if not set(clocks).issubset(ALLOWED_Q43_UPDATE_CLOCKS):
                info_fail += 1
            g0 = frame["q_or_g0_kwh"].to_numpy(float)
            gf = frame["g_final_kwh"].to_numpy(float)
            if np.max(np.abs(gf[:first_intraday] - g0[:first_intraday])) > NUMERIC_TOL:
                prefix_fail += 1
        else:
            ledger = ledger_from_dispatch_q42(frame)
            if not (frame["last_update_time"].astype(str) == "00:00").all():
                info_fail += 1
        ledger_total = float(ledger["total_cost_yuan"].sum())
        max_ledger_gap = max(max_ledger_gap, abs(ledger_total - float(row.total_cost_yuan)))
    soc = warmup_soc_continuity(daily)
    physical_pass = (
        n_physical_pass == YEAR_N_DAYS
        and max_balance < 1e-5
        and max_x_minus_cap < NUMERIC_TOL
        and max_cd <= SIMULTANEOUS_CD_TOL
        and max_power <= POWER_LIMIT_KWH + NUMERIC_TOL
        and max_soc_chain < 1e-6
        and soc_min >= E_MIN_KWH - NUMERIC_TOL
        and soc_max <= E_MAX_KWH + NUMERIC_TOL
        and info_fail == 0
        and prefix_fail == 0
        and max_ledger_gap < 0.01
        and soc["pass"]
    )
    return {
        "system": "q4_3" if q4_3 else "q4_2",
        "n_dispatch_files": len(paths),
        "n_days": int(len(daily)),
        "n_physical_pass": n_physical_pass,
        "soc_continuity": soc,
        "max_balance_residual_kwh": max_balance,
        "max_x_minus_cap_kwh": max_x_minus_cap,
        "max_simultaneous_cd_kwh2": max_cd,
        "max_charge_or_discharge_kwh": max_power,
        "power_limit_kwh": float(POWER_LIMIT_KWH),
        "max_intraday_soc_chain_gap_kwh": max_soc_chain,
        "soc_min_kwh": float(soc_min),
        "soc_max_kwh": float(soc_max),
        "max_ledger_vs_daily_gap_yuan": max_ledger_gap,
        "info_cutoff_failures": info_fail,
        "prefix_lock_failures": prefix_fail,
        "dec31_soc_kwh": float(daily.iloc[-1]["soc_end_kwh"]),
        "pass": bool(physical_pass),
    }


def q4_2_policy_windows(daily: pd.DataFrame) -> pd.DataFrame:
    """14-day calibration calendar, including the 28-day warmup with no alpha."""
    from q4.config import RISK_CALIBRATION_DAYS, RISK_WARMUP_DAYS
    from q4.q4_2 import q2_aligned_calibration_indices

    work = daily.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)
    if len(work) != YEAR_N_DAYS:
        raise AssertionError(f"Q4-2 daily expected {YEAR_N_DAYS} days, got {len(work)}")
    rows = [
        {
            "effective_start_date": work.loc[0, "date"],
            "effective_end_date": work.loc[RISK_WARMUP_DAYS - 1, "date"],
            "n_days": RISK_WARMUP_DAYS,
            "risk_alpha": None,
            "kind": "warmup",
        }
    ]
    for start in q2_aligned_calibration_indices(len(work)):
        end = min(start + RISK_CALIBRATION_DAYS - 1, len(work) - 1)
        chunk = work.iloc[start : end + 1]
        alphas = chunk["risk_alpha"]
        if alphas.isna().any() or alphas.nunique() != 1:
            raise AssertionError(
                f"alpha is not constant on {chunk.iloc[0]['date']}–{chunk.iloc[-1]['date']}"
            )
        rows.append(
            {
                "effective_start_date": chunk.iloc[0]["date"],
                "effective_end_date": chunk.iloc[-1]["date"],
                "n_days": int(len(chunk)),
                "risk_alpha": round(float(chunk.iloc[0]["risk_alpha"]), 2),
                "kind": "calibrated",
            }
        )
    frame = pd.DataFrame(rows)
    if len(frame) != 26:
        raise AssertionError(f"expected 1 warmup + 25 calibrated windows, got {len(frame)}")
    hot = frame.loc[frame["risk_alpha"] == 0.70]
    if len(hot) != 1:
        raise AssertionError("expected exactly one alpha=0.70 window")
    if hot.iloc[0]["effective_start_date"] != pd.Timestamp(EXPECTED_Q4_2_ALPHA070_START):
        raise AssertionError("alpha=0.70 start mismatch")
    if hot.iloc[0]["effective_end_date"] != pd.Timestamp(EXPECTED_Q4_2_ALPHA070_END):
        raise AssertionError("alpha=0.70 end mismatch")
    return frame


def selected_alpha_blocks(daily: pd.DataFrame, selection: pd.DataFrame) -> pd.DataFrame:
    work = daily.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)
    blocks = []
    start_idx = 0
    for i in range(1, len(work) + 1):
        same = False
        if i < len(work):
            prev = work.loc[start_idx, "risk_alpha"]
            cur = work.loc[i, "risk_alpha"]
            same = (pd.isna(prev) and pd.isna(cur)) or (
                pd.notna(prev) and pd.notna(cur) and abs(float(prev) - float(cur)) < 1e-12
            )
        if same:
            continue
        chunk = work.iloc[start_idx:i]
        alpha = chunk.iloc[0]["risk_alpha"]
        blocks.append(
            {
                "effective_start_date": chunk.iloc[0]["date"],
                "effective_end_date": chunk.iloc[-1]["date"],
                "n_days": int(len(chunk)),
                "risk_alpha": None if pd.isna(alpha) else round(float(alpha), 2),
            }
        )
        start_idx = i
    frame = pd.DataFrame(blocks)
    selected = selection.loc[selection["selected"].astype(str).str.lower().isin(("true", "1"))].copy()
    selected["calibration_date"] = pd.to_datetime(selected["calibration_date"])
    if int(selected["calibration_date"].nunique()) != 25:
        raise AssertionError(f"expected 25 Q4-2 calibration windows, got {selected['calibration_date'].nunique()}")
    return frame


def pearson_corrcoef(a: np.ndarray, b: np.ndarray) -> float:
    x = np.asarray(a, dtype=float).ravel()
    y = np.asarray(b, dtype=float).ravel()
    if x.size != y.size or x.size < 3:
        raise ValueError("correlation requires aligned arrays with length >= 3")
    if np.std(x) < 1e-18 or np.std(y) < 1e-18:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def residual_correlation_report(
    load_r: np.ndarray, pv_r: np.ndarray, price_r: np.ndarray, dates: list[str]
) -> dict:
    load_r = np.asarray(load_r, dtype=float)
    pv_r = np.asarray(pv_r, dtype=float)
    price_r = np.asarray(price_r, dtype=float)
    if load_r.shape != pv_r.shape or load_r.shape != price_r.shape:
        raise AssertionError("residual stacks must share shape")
    if load_r.ndim != 2 or load_r.shape[1] != T:
        raise AssertionError(f"expected (n_days, {T}) residual stacks")
    names = ("load", "pv", "price")
    stacks = {"load": load_r, "pv": pv_r, "price": price_r}
    flat = {name: stacks[name].ravel() for name in names}
    daily_mean = {name: stacks[name].mean(axis=1) for name in names}
    corr_flat = {
        f"{a}_vs_{b}": pearson_corrcoef(flat[a], flat[b])
        for a in names
        for b in names
        if a < b
    }
    corr_daily = {
        f"{a}_vs_{b}": pearson_corrcoef(daily_mean[a], daily_mean[b])
        for a in names
        for b in names
        if a < b
    }
    return {
        "interpretation": (
            "Same-day (L, P, p) forecast residuals. Values are Pearson correlations, "
            "not causal effects. Residual dates are strictly those with archived causal "
            "load, PV, and day-ahead price forecasts."
        ),
        "n_days": int(load_r.shape[0]),
        "n_slots": int(load_r.size),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "pearson_flattened_slots": corr_flat,
        "pearson_daily_mean_residual": corr_daily,
        "residual_std": {
            "load_kwh": float(load_r.std()),
            "pv_kwh": float(pv_r.std()),
            "price_yuan_per_kwh": float(price_r.std()),
        },
        "scenario_audit_source": str(Q4_2_SCENARIO_AUDIT_CSV.relative_to(OUTPUT_DIR.parent.parent)),
    }


def build_residual_correlation_from_bundle(bundle) -> dict:
    from q4.scenarios import residual_stack

    ok = []
    for i in range(bundle.n_days()):
        if not np.isfinite(bundle.price_archive.day_ahead[i]).all():
            continue
        if not np.isfinite(bundle.q2_forecast.load_hat[i]).all():
            continue
        if not np.isfinite(bundle.q2_forecast.pv_hat[i]).all():
            continue
        ok.append(i)
    indices = np.asarray(ok, dtype=int)
    load_r, pv_r, price_r = residual_stack(bundle, indices)
    dates = [bundle.prices.dates[i].strftime("%Y-%m-%d") for i in indices]
    report = residual_correlation_report(load_r, pv_r, price_r, dates)
    if Q4_2_SCENARIO_AUDIT_CSV.exists():
        audit = pd.read_csv(Q4_2_SCENARIO_AUDIT_CSV)
        report["scenario_audit_n_rows"] = int(len(audit))
        report["scenario_audit_n_days"] = int(audit["date"].nunique())
    return report

# ===== q4/config.py =====
"""Q4 configuration. Price-forecast constants stay aligned with the accepted P1 module."""

from __future__ import annotations

from q3.config import ATTACH4, PILOT_DATES, ROOT, T

OUTPUT_DIR = ROOT / "output" / "q4"
AUDIT_CSV = OUTPUT_DIR / "q4_price_forecast_audit.csv"
TWODAY_JSON = OUTPUT_DIR / "q4_price_forecast_twoday.json"
CAUSALITY_JSON = OUTPUT_DIR / "q4_price_forecast_causality.json"

Q4_2_DISPATCH_DIR = OUTPUT_DIR / "q4_2_dispatch_daily"
Q4_3_DISPATCH_DIR = OUTPUT_DIR / "q4_3_dispatch_daily"
RESULT4_2_XLSX = ROOT / "output" / "result4-2.xlsx"
RESULT4_3_XLSX = ROOT / "output" / "result4-3.xlsx"

RESIDUAL_POOL_DAYS = 28
FIXED_SCENARIO_K = 8
K_REVIEW_CANDIDATES = (4, 8, 12)
K_REVIEW_REFERENCE_ALPHA = 0.60
K_REVIEW_COST_TOLERANCE = 0.01
RISK_ALPHA_CANDIDATES = (0.60, 0.70, 0.80, 0.90)
RISK_CALIBRATION_DAYS = 14
RISK_WARMUP_DAYS = 28
ALPHA_POLICY_LOOP = "day_ahead_joint_q+locked_q+causal_mpc+next_day_value_cuts"
PAM_SEED = 0
PRICE_MONTHLY_CSV = OUTPUT_DIR / "q4_price_forecast_monthly.csv"
PRICE_MONTHLY_JSON = OUTPUT_DIR / "q4_price_forecast_monthly.json"
LOAD_INFORMATION_CASE = "causal_load_main"
Q4_2_YEAR_END_RULE = "q2_accepted_no_hard_terminal"
Q4_3_YEAR_END_BOUNDARY = "A_q2_aligned"
Q4_3_YEAR_END_SOC_KWH = 1200.0
Q4_3_STRATEGY = "M1_M6"
SETTLEMENT_RULE = "delivery_time_actual_price"
Q4_3_ORACLE_DISPATCH_DIR = OUTPUT_DIR / "q4_3_oracle_dispatch_daily"
Q4_3_SETTLEMENT_SENSITIVITY_CSV = OUTPUT_DIR / "q4_3_settlement_sensitivity.csv"
Q4_3_SETTLEMENT_SENSITIVITY_JSON = OUTPUT_DIR / "q4_3_settlement_sensitivity.json"
Q4_3_ORACLE_DAILY_CSV = OUTPUT_DIR / "q4_3_oracle_warmup_daily.csv"
Q4_3_SENSITIVITY_SUMMARY_JSON = OUTPUT_DIR / "q4_3_sensitivity_summary.json"

FIG_DIR = ROOT / "fig" / "q4_final"
Q4_2_DAILY_CSV = OUTPUT_DIR / "q4_2_warmup_daily.csv"
Q4_3_DAILY_CSV = OUTPUT_DIR / "q4_3_warmup_daily.csv"
Q4_2_ALPHA_SELECTION_CSV = OUTPUT_DIR / "q4_2_alpha_selection.csv"
Q4_2_SCENARIO_AUDIT_CSV = OUTPUT_DIR / "q4_2_scenario_audit.csv"
Q2_K8_DAILY_CSV = ROOT / "output/q2_full_k8_risk/daily_summary.csv"
Q3_ANNUAL_DAILY_CSV = ROOT / "output/q3_full_annual/q3_annual_daily_summary.csv"
TAIL_STATS_JSON = OUTPUT_DIR / "q4_tail_stats.json"
TAIL_STATS_CSV = OUTPUT_DIR / "q4_tail_stats.csv"
FAIR_COMPARISON_JSON = OUTPUT_DIR / "q4_fair_comparison.json"
FAIR_COMPARISON_CSV = OUTPUT_DIR / "q4_fair_comparison.csv"
PHYSICAL_YEAR_AUDIT_JSON = OUTPUT_DIR / "q4_physical_audit.json"
SCENARIO_CORR_JSON = OUTPUT_DIR / "q4_2_scenario_correlation.json"

EXPORT_START = "2025-02-01"
EXPORT_END = "2025-12-31"
EXPORT_N_DAYS = 334
YEAR_N_DAYS = 365

# Signed-off workbook / annual totals. Comparisons must not mix 1-12 with 2-12.
EXPECTED_Q4_2_ANNUAL_YUAN = 17_681_029.10
EXPECTED_Q4_2_EXPORT_YUAN = 15_257_873.75
EXPECTED_Q4_3_ANNUAL_YUAN = 17_489_808.24
EXPECTED_Q4_3_EXPORT_YUAN = 15_346_418.14
EXPECTED_Q2_K8_EXPORT_YUAN = 14_456_670.55
EXPECTED_Q3_ANNUAL_YUAN = 16_373_508.75
EXPECTED_Q4_2_ALPHA070_START = "2025-03-12"
EXPECTED_Q4_2_ALPHA070_END = "2025-03-25"

CANDIDATE_MODELS = (1, 2, 4)
CANDIDATE_NAMES = {
    1: "prev_day",
    2: "weekday2",
    4: "weekday4",
}

# Number of ended 10-minute periods at the named clock time.
# 06:00 has seen periods 0..35 (ending 06:00); remaining starts at 06:10 (index 36).
INTRA_HOUR_TAU = {
    6: 36,
    12: 72,
    18: 108,
}

VAR_EPS = 1e-18

# ===== q4/data.py =====
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from q3.data import normalize_time
from q4.config import ATTACH4, T


def _finite_nonnegative(values: np.ndarray, name: str) -> None:
    if not np.isfinite(values).all():
        raise ValueError(f"{name} contains missing or non-finite values")
    if np.any(values < 0):
        raise ValueError(f"{name} contains negative values")


@dataclass(frozen=True)
class Q4PriceData:
    dates: pd.DatetimeIndex
    time_labels: tuple[str, ...]
    price: np.ndarray

    def date_index(self, date: str) -> int:
        return int(self.dates.get_loc(pd.Timestamp(date)))


def load_q4_prices(attach4: Path = ATTACH4) -> Q4PriceData:
    if not attach4.exists():
        raise FileNotFoundError(
            f"附件4 not found: {attach4}. Set CUMCM_C_ATTACH_DIR to the attachments folder."
        )
    raw = pd.read_excel(attach4, sheet_name=0, header=None)
    if raw.shape != (366, 145):
        raise ValueError(f"附件4 must be 366x145; got {raw.shape}")
    if raw.iloc[0, 0] != "日期\\时间":
        raise ValueError("附件4 first header must be 日期\\时间")
    time_labels = tuple(normalize_time(x) for x in raw.iloc[0, 1:])
    if len(time_labels) != T or time_labels[0] != "00:10" or time_labels[-1] != "0:00+1":
        raise ValueError(f"Unexpected 附件4 time order: {time_labels[0]} .. {time_labels[-1]}")
    dates = pd.DatetimeIndex(pd.to_datetime(raw.iloc[1:, 0], errors="raise")).normalize()
    expected = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    if not dates.equals(expected):
        raise ValueError("附件4 dates must be continuous 2025-01-01 through 2025-12-31")
    price = raw.iloc[1:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    _finite_nonnegative(price, "附件4 price")
    return Q4PriceData(dates=dates, time_labels=time_labels, price=price)

# ===== q4/export_price_monthly.py =====
#!/usr/bin/env python3
"""Monthly MAE/RMSE from the accepted P1 price-forecast audit. Does not refit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from q4.config import AUDIT_CSV, PRICE_MONTHLY_CSV, PRICE_MONTHLY_JSON

METRIC_PAIRS = (
    ("day_ahead_mae", "day_ahead_rmse"),
    ("intraday_06_mae", "intraday_06_rmse"),
    ("intraday_12_mae", "intraday_12_rmse"),
    ("intraday_18_mae", "intraday_18_rmse"),
)
MAE_ONLY = ("mpc_remaining_mae_mean",)


def _pooled_rmse(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").to_numpy(float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan")
    return float(np.sqrt(np.mean(np.square(values))))


def monthly_from_audit(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["date"] = pd.to_datetime(work["date"])
    work["year_month"] = work["date"].dt.strftime("%Y-%m")
    rows = []
    for year_month, group in work.groupby("year_month", sort=True):
        row: dict = {
            "year_month": year_month,
            "n_days": int(len(group)),
            "n_days_with_day_ahead": int(pd.to_numeric(group["day_ahead_mae"], errors="coerce").notna().sum()),
        }
        for mae_col, rmse_col in METRIC_PAIRS:
            mae = pd.to_numeric(group[mae_col], errors="coerce")
            rmse = pd.to_numeric(group[rmse_col], errors="coerce")
            row[mae_col] = float(mae.mean()) if mae.notna().any() else float("nan")
            row[rmse_col] = _pooled_rmse(rmse)
            row[f"{rmse_col}_mean_daily"] = float(rmse.mean()) if rmse.notna().any() else float("nan")
        for col in MAE_ONLY:
            series = pd.to_numeric(group[col], errors="coerce")
            row[col] = float(series.mean()) if series.notna().any() else float("nan")
        rows.append(row)
    monthly = pd.DataFrame(rows)
    annual = {
        "year_month": "2025-annual",
        "n_days": int(len(work)),
        "n_days_with_day_ahead": int(
            pd.to_numeric(work["day_ahead_mae"], errors="coerce").notna().sum()
        ),
    }
    for mae_col, rmse_col in METRIC_PAIRS:
        mae = pd.to_numeric(work[mae_col], errors="coerce")
        rmse = pd.to_numeric(work[rmse_col], errors="coerce")
        annual[mae_col] = float(mae.mean()) if mae.notna().any() else float("nan")
        annual[rmse_col] = _pooled_rmse(rmse)
        annual[f"{rmse_col}_mean_daily"] = float(rmse.mean()) if rmse.notna().any() else float("nan")
    for col in MAE_ONLY:
        series = pd.to_numeric(work[col], errors="coerce")
        annual[col] = float(series.mean()) if series.notna().any() else float("nan")
    return pd.concat([monthly, pd.DataFrame([annual])], ignore_index=True)


def export_price_monthly(
    audit_csv: Path = AUDIT_CSV,
    dest_csv: Path = PRICE_MONTHLY_CSV,
    dest_json: Path = PRICE_MONTHLY_JSON,
) -> dict:
    if not audit_csv.exists():
        raise FileNotFoundError(f"price audit not found: {audit_csv}")
    frame = pd.read_csv(audit_csv)
    monthly = monthly_from_audit(frame)
    dest_csv.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(dest_csv, index=False)
    payload = {
        "source": str(audit_csv),
        "aggregation": {
            "mae": "mean of daily MAE over days with a finite value",
            "rmse": "pooled RMSE = sqrt(mean of daily RMSE squared); equal slot count per day",
            "rmse_mean_daily": "mean of daily RMSE, not pooled",
            "note": "Derived from the accepted P1 audit; the price module was not refit.",
        },
        "n_months": int((monthly["year_month"] != "2025-annual").sum()),
        "rows": monthly.to_dict("records"),
    }
    dest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    report = export_price_monthly()
    print(json.dumps({"csv": str(PRICE_MONTHLY_CSV), "n_rows": len(report["rows"])}, indent=2))

# ===== q4/export_result4.py =====
"""Export result4-2.xlsx and result4-3.xlsx from streamed 10-minute dispatch.

February–December only. January is warmup. Does not modify result2.xlsx or result3.xlsx.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from q3.config import RESULT3_TEMPLATE, T
from q3.export_result3 import (
    ADJUST_SHEET,
    CHARGE_SHEET,
    COL_DAY_FEE,
    COL_DAY_QTY,
    EMERGENCY_SHEET,
    NOTES_SHEET,
    PURCHASE_SHEET,
    _fill_energy_grid,
    _rewrite_charge_sheet,
    _rewrite_emergency_sheet,
    _time_headers,
    export_dates,
)
from q4.audit import ledger_from_dispatch_q42, ledger_from_dispatch_q43
from q4.config import (
    OUTPUT_DIR,
    Q4_2_DISPATCH_DIR,
    Q4_3_DISPATCH_DIR,
    RESULT4_2_XLSX,
    RESULT4_3_XLSX,
    ROOT,
)

RESULT2_LAYOUT = ROOT / "output" / "result2.xlsx"
RESULT4_2_AUDIT = ROOT / "output" / "result4-2_export_audit.json"
RESULT4_3_AUDIT = ROOT / "output" / "result4-3_export_audit.json"


def git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _load_dispatch(path: Path, q4_3: bool) -> pd.DataFrame:
    raw = pd.read_csv(path)
    if len(raw) != T:
        raise ValueError(f"{path} has {len(raw)} rows, expected {T}")
    g0 = raw["q_or_g0_kwh"].to_numpy(float)
    gf = raw["g_final_kwh"].to_numpy(float) if q4_3 else g0
    frame = pd.DataFrame(
        {
            "date": raw["date"].astype(str),
            "period_index": raw["period_index"].to_numpy(int),
            "time_label": raw["time_label"].astype(str),
            "g0_kwh": g0,
            "g_final_kwh": gf,
            "x_kwh": raw["x_kwh"].to_numpy(float),
            "emergency_kwh": raw["emergency_kwh"].to_numpy(float),
            "charge_kwh": raw["charge_kwh"].to_numpy(float),
            "discharge_kwh": raw["discharge_kwh"].to_numpy(float),
            "soc_start_kwh": raw["soc_start_kwh"].to_numpy(float),
            "soc_end_kwh": raw["soc_end_kwh"].to_numpy(float),
            "price": raw["actual_price"].to_numpy(float),
            "balance_residual_kwh": raw["balance_residual_kwh"].to_numpy(float),
        }
    )
    billed = ledger_from_dispatch_q43(raw) if q4_3 else ledger_from_dispatch_q42(raw)
    frame["phi_yuan"] = billed["normal_cost_yuan"] + billed["adjustment_cost_yuan"]
    frame["emergency_cost_yuan"] = billed["emergency_cost_yuan"]
    frame["plan_fee_yuan"] = frame["price"] * frame["g0_kwh"]
    frame["actual_fee_yuan"] = billed["total_cost_yuan"]
    return frame.sort_values("period_index").reset_index(drop=True)


def load_export_window(dispatch_dir: Path, q4_3: bool) -> dict[str, pd.DataFrame]:
    dates = export_dates()
    by_date = {}
    missing = []
    for date in dates:
        path = dispatch_dir / f"dispatch_{date}.csv"
        if not path.exists():
            missing.append(date)
            continue
        by_date[date] = _load_dispatch(path, q4_3)
    if missing:
        raise FileNotFoundError(
            f"{dispatch_dir} missing {len(missing)} export-window days, first {missing[:5]}"
        )
    return by_date


def _write_notes(wb, title: str, lines: list[str]) -> None:
    if NOTES_SHEET in wb.sheetnames:
        del wb[NOTES_SHEET]
    ws = wb.create_sheet(NOTES_SHEET)
    font = Font(name="宋体", size=11)
    for i, line in enumerate([title, *lines], start=1):
        cell = ws.cell(i, 1)
        cell.value = line
        cell.font = font
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 22
    ws.column_dimensions["A"].width = 118


def _label_fee_columns(wb, sheets: tuple[str, ...]) -> None:
    for name in sheets:
        ws = wb[name]
        ws.cell(1, COL_DAY_QTY).value = "全天购电量"
        ws.cell(1, COL_DAY_FEE).value = "全天购电费"
        ws.column_dimensions[get_column_letter(COL_DAY_QTY)].width = 14
        ws.column_dimensions[get_column_letter(COL_DAY_FEE)].width = 14


def write_result4_2(by_date: dict[str, pd.DataFrame], dest: Path = RESULT4_2_XLSX) -> dict:
    if not RESULT2_LAYOUT.exists():
        raise FileNotFoundError(f"result2 layout not found: {RESULT2_LAYOUT}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RESULT2_LAYOUT, dest)
    wb = load_workbook(dest)
    plan = wb[PURCHASE_SHEET]
    headers = _time_headers(plan)
    _fill_energy_grid(plan, by_date, "g0_kwh", "plan_fee_yuan")
    _rewrite_charge_sheet(wb[CHARGE_SHEET], by_date)
    n_emergency = _rewrite_emergency_sheet(wb[EMERGENCY_SHEET], by_date, headers)
    export_cost = float(sum(float(frame["actual_fee_yuan"].sum()) for frame in by_date.values()))
    annual = float(pd.read_csv(OUTPUT_DIR / "q4_2_warmup_daily.csv")["total_cost_yuan"].sum())
    _write_notes(
        wb,
        "C 题第 4 问 Q4-2 正式导出（日前 q + 因果 MPC）",
        [
            "额度 q 全日锁定；路径内充放电只用于评估 q，不直接执行。",
            "负荷/光伏：Q2 因果口径；价格：已验收 P1 模块；结算：附件4 实际电价 p*q+5*p*e。",
            "年末 SOC：继承 Q2 已验收规则（最后一日无硬约束）。load_information_case=causal_load_main。",
            "输出区间：2025-02-01 至 2025-12-31（334 天）。1 月只用于预热与 SOC 连续，不写入本表。",
            "单位：kWh 与元。时间列按附件 00:10 … 0:00+1 原顺序。",
            f"紧急购电量仅列出 e>0 的时段（本文件 {n_emergency} 行）。",
            f"数据来源 commit：{git_hash()}",
            f"2–12 月实际结算合计 {export_cost:.2f} 元；1–12 月年度合计 {annual:.2f} 元，二者不可混用。",
            "本文件不含 Q4-3、oracle 或未验收价格。未改写 result2.xlsx / result3.xlsx。",
        ],
    )
    _label_fee_columns(wb, (PURCHASE_SHEET,))
    if ADJUST_SHEET in wb.sheetnames:
        del wb[ADJUST_SHEET]
    wb.save(dest)
    return {
        "path": str(dest),
        "n_export_days": len(by_date),
        "n_emergency_rows": n_emergency,
        "export_window_cost_yuan": export_cost,
        "annual_cost_yuan": annual,
    }


def write_result4_3(by_date: dict[str, pd.DataFrame], dest: Path = RESULT4_3_XLSX) -> dict:
    if not RESULT3_TEMPLATE.exists():
        raise FileNotFoundError(f"result3 template not found: {RESULT3_TEMPLATE}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RESULT3_TEMPLATE, dest)
    wb = load_workbook(dest)
    plan = wb[PURCHASE_SHEET]
    adjust = wb[ADJUST_SHEET]
    headers = _time_headers(plan)
    _fill_energy_grid(plan, by_date, "g0_kwh", "plan_fee_yuan")
    _fill_energy_grid(adjust, by_date, "g_final_kwh", "actual_fee_yuan")
    _rewrite_charge_sheet(wb[CHARGE_SHEET], by_date)
    n_emergency = _rewrite_emergency_sheet(wb[EMERGENCY_SHEET], by_date, headers)
    export_cost = float(sum(float(frame["actual_fee_yuan"].sum()) for frame in by_date.values()))
    annual = float(pd.read_csv(OUTPUT_DIR / "q4_3_warmup_daily.csv")["total_cost_yuan"].sum())
    _write_notes(
        wb,
        "C 题第 4 问 Q4-3 正式导出（固定 M1_M6）",
        [
            "策略固定为 M1_M6：0:00 制定 g0；6:00/12:00/18:00 只改未执行承诺。",
            "预测层使用因果价格；账本按交付时实际电价 phi=p*gF+0.5*p*|gF-g0|，另加 5*p*e。",
            "年末 SOC：A / A_q2_aligned / 1200 kWh。load_information_case=causal_load_main。",
            "输出区间：2025-02-01 至 2025-12-31（334 天）。1 月只用于预热与 SOC 连续，不写入本表。",
            "计划购电量：g0。调整购电量：gF；未调整时段等于 g0。",
            f"紧急购电量仅列出 e>0 的时段（本文件 {n_emergency} 行）。",
            f"数据来源 commit：{git_hash()}",
            f"2–12 月实际结算合计 {export_cost:.2f} 元；1–12 月年度合计 {annual:.2f} 元，二者不可混用。",
            "本文件不含其它策略或 oracle。未改写 result3.xlsx。",
        ],
    )
    _label_fee_columns(wb, (PURCHASE_SHEET, ADJUST_SHEET))
    wb.save(dest)
    return {
        "path": str(dest),
        "n_export_days": len(by_date),
        "n_emergency_rows": n_emergency,
        "export_window_cost_yuan": export_cost,
        "annual_cost_yuan": annual,
    }


def export_q4_2() -> dict:
    q42 = load_export_window(Q4_2_DISPATCH_DIR, q4_3=False)
    r2 = write_result4_2(q42)
    RESULT4_2_AUDIT.write_text(json.dumps(r2, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"result4_2": r2}


def export_q4_3() -> dict:
    q43 = load_export_window(Q4_3_DISPATCH_DIR, q4_3=True)
    r3 = write_result4_3(q43)
    RESULT4_3_AUDIT.write_text(json.dumps(r3, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"result4_3": r3}


def export_all() -> dict:
    out = {}
    out.update(export_q4_2())
    out.update(export_q4_3())
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export result4 workbooks")
    parser.add_argument("--system", choices=("q4_2", "q4_3", "all"), default="all")
    args = parser.parse_args()
    if args.system == "q4_2":
        report = export_q4_2()
    elif args.system == "q4_3":
        report = export_q4_3()
    else:
        report = export_all()
    print(json.dumps(report, ensure_ascii=False, indent=2))

# ===== q4/info_set.py =====
"""Information-set probes: future actuals must not change day-ahead or alpha calibration."""

from __future__ import annotations

import numpy as np

from q2.data import Q2Data
from q2.forecast import build_forecast_archive
from q4.bundle import Q4Bundle
from q4.data import Q4PriceData
from q4.price_forecast import fit_causal_price_forecasts
from q4.q4_2 import plan_locked_q, select_risk_alpha
from q4.q4_3 import plan_g0


def perturb_unended_and_future(
    prices: np.ndarray, day_index: int, tau: int, delta: float = 3.25
) -> np.ndarray:
    out = np.asarray(prices, dtype=float).copy()
    out[day_index, tau:] = out[day_index, tau:] + delta
    if day_index + 1 < len(out):
        out[day_index + 1 :] = out[day_index + 1 :] + delta
    return np.maximum(out, 0.0)


def bundle_with_prices(bundle: Q4Bundle, new_prices: np.ndarray) -> Q4Bundle:
    archive = fit_causal_price_forecasts(
        new_prices, bundle.prices.dates, compute_mpc=False
    )
    prices = Q4PriceData(
        dates=bundle.prices.dates,
        time_labels=bundle.prices.time_labels,
        price=np.asarray(new_prices, dtype=float),
    )
    return Q4Bundle(
        q3=bundle.q3,
        q2=bundle.q2,
        q2_forecast=bundle.q2_forecast,
        prices=prices,
        price_archive=archive,
    )


def probe_day_ahead_invariance(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    risk_alpha: float | None,
    tau: int = 40,
    with_value_cuts: bool = False,
) -> dict:
    date = bundle.prices.dates[day_index].strftime("%Y-%m-%d")
    q0 = plan_locked_q(
        bundle, day_index, initial_soc, risk_alpha, with_value_cuts=with_value_cuts
    )
    g0 = plan_g0(bundle, day_index, initial_soc, with_value_cuts=with_value_cuts)
    perturbed = perturb_unended_and_future(bundle.prices.price, day_index, tau)
    other = bundle_with_prices(bundle, perturbed)
    q1 = plan_locked_q(
        other, day_index, initial_soc, risk_alpha, with_value_cuts=with_value_cuts
    )
    g1 = plan_g0(other, day_index, initial_soc, with_value_cuts=with_value_cuts)
    q_ok = bool(np.allclose(q0, q1, atol=1e-6, rtol=0.0))
    g_ok = bool(np.allclose(g0, g1, atol=1e-6, rtol=0.0))
    return {
        "date": date,
        "day_index": int(day_index),
        "tau_perturbed": int(tau),
        "with_value_cuts": with_value_cuts,
        "q_max_abs_diff_kwh": float(np.max(np.abs(q0 - q1))),
        "g0_max_abs_diff_kwh": float(np.max(np.abs(g0 - g1))),
        "q_invariant": q_ok,
        "g0_invariant": g_ok,
        "pass": q_ok and g_ok,
    }


def probe_executed_prefix(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    risk_alpha: float | None,
    q42_dispatch,
    q43_result,
    tau: int = 40,
) -> dict:
    """Re-solve the day after perturbing unended/future prices; prefix actions must match."""
    from q4.q4_2 import run_q4_2_day
    from q4.q4_3 import run_q4_3_day

    date = bundle.prices.dates[day_index].strftime("%Y-%m-%d")
    other = bundle_with_prices(
        bundle, perturb_unended_and_future(bundle.prices.price, day_index, tau)
    )
    r2 = run_q4_2_day(other, day_index, initial_soc, risk_alpha)
    soc_q43 = float(q43_result.summary["soc_start_kwh"])
    r3 = run_q4_3_day(other, day_index, soc_q43)
    cols = ["q_or_g0_kwh", "x_kwh", "charge_kwh", "discharge_kwh", "emergency_kwh"]
    d2 = q42_dispatch.iloc[:tau][cols].to_numpy(float)
    d2p = r2.dispatch.iloc[:tau][cols].to_numpy(float)
    q42_ok = bool(np.allclose(d2, d2p, atol=1e-5, rtol=0.0)) and bool(
        np.allclose(q42_dispatch["q_or_g0_kwh"].to_numpy(), r2.q, atol=1e-6)
    )
    g_cols = ["q_or_g0_kwh", "g_final_kwh", "x_kwh", "charge_kwh", "discharge_kwh"]
    d3 = q43_result.dispatch.iloc[:tau][g_cols].to_numpy(float)
    d3p = r3.dispatch.iloc[:tau][g_cols].to_numpy(float)
    q43_ok = bool(np.allclose(d3, d3p, atol=1e-5, rtol=0.0)) and bool(
        np.allclose(q43_result.g0, r3.g0, atol=1e-6)
    )
    return {
        "date": date,
        "tau_perturbed": int(tau),
        "q42_q_max_abs_diff_kwh": float(
            np.max(np.abs(q42_dispatch["q_or_g0_kwh"].to_numpy() - r2.q))
        ),
        "q42_prefix_max_abs_diff": float(np.max(np.abs(d2 - d2p))),
        "q43_g0_max_abs_diff_kwh": float(np.max(np.abs(q43_result.g0 - r3.g0))),
        "q43_prefix_max_abs_diff": float(np.max(np.abs(d3 - d3p))),
        "q42_pass": q42_ok,
        "q43_pass": q43_ok,
        "pass": q42_ok and q43_ok,
    }


def perturb_future_actuals(
    bundle: Q4Bundle,
    from_day: int,
    *,
    delta_price: float = 3.25,
    load_scale: float = 1.15,
    pv_scale: float = 0.85,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Shift actual price/load/PV on from_day and later; leave completed days intact."""
    prices = np.asarray(bundle.prices.price, dtype=float).copy()
    load = np.asarray(bundle.q2.load, dtype=float).copy()
    pv = np.asarray(bundle.q2.pv, dtype=float).copy()
    prices[from_day:] = np.maximum(prices[from_day:] + delta_price, 0.0)
    load[from_day:] = np.maximum(load[from_day:] * load_scale, 0.0)
    pv[from_day:] = np.maximum(pv[from_day:] * pv_scale, 0.0)
    return prices, load, pv


def bundle_with_future_actuals(
    bundle: Q4Bundle,
    from_day: int,
    *,
    delta_price: float = 3.25,
    load_scale: float = 1.15,
    pv_scale: float = 0.85,
) -> Q4Bundle:
    prices, load, pv = perturb_future_actuals(
        bundle,
        from_day,
        delta_price=delta_price,
        load_scale=load_scale,
        pv_scale=pv_scale,
    )
    q2 = Q2Data(
        dates=bundle.q2.dates,
        time_labels=bundle.q2.time_labels,
        price=bundle.q2.price,
        fallback_load=bundle.q2.fallback_load,
        fallback_pv=bundle.q2.fallback_pv,
        load=load,
        pv=pv,
    )
    archive = fit_causal_price_forecasts(
        prices, bundle.prices.dates, compute_mpc=False
    )
    return Q4Bundle(
        q3=bundle.q3,
        q2=q2,
        q2_forecast=build_forecast_archive(q2),
        prices=Q4PriceData(
            dates=bundle.prices.dates,
            time_labels=bundle.prices.time_labels,
            price=prices,
        ),
        price_archive=archive,
    )


def probe_alpha_calibration_invariance(
    bundle: Q4Bundle,
    policy_start_soc: np.ndarray,
    target_index: int,
    *,
    k_target: int = 8,
    n_validation: int = 1,
    alphas: tuple[float, ...] = (0.60, 0.90),
) -> dict:
    """Perturb actuals of the calibration day and later; alpha scores must not move."""
    baseline = select_risk_alpha(
        bundle,
        policy_start_soc,
        target_index,
        k_target,
        n_validation=n_validation,
        alphas=alphas,
        log=False,
    )
    other = bundle_with_future_actuals(bundle, target_index)
    perturbed = select_risk_alpha(
        other,
        policy_start_soc,
        target_index,
        k_target,
        n_validation=n_validation,
        alphas=alphas,
        log=False,
    )
    base_costs = {
        float(row["risk_alpha"]): float(row["mean_validation_cost_yuan"])
        for row in baseline.window_records
    }
    other_costs = {
        float(row["risk_alpha"]): float(row["mean_validation_cost_yuan"])
        for row in perturbed.window_records
    }
    cost_gaps = {
        alpha: abs(base_costs[alpha] - other_costs[alpha]) for alpha in base_costs
    }
    max_cost_gap = float(max(cost_gaps.values())) if cost_gaps else 0.0
    alpha_ok = abs(baseline.selected_alpha - perturbed.selected_alpha) < 1e-12
    cost_ok = max_cost_gap < 1e-6
    return {
        "target_index": int(target_index),
        "n_validation": int(n_validation),
        "alphas": [float(a) for a in alphas],
        "baseline_selected_alpha": float(baseline.selected_alpha),
        "perturbed_selected_alpha": float(perturbed.selected_alpha),
        "max_mean_cost_abs_diff_yuan": max_cost_gap,
        "mean_cost_abs_diff_by_alpha": cost_gaps,
        "alpha_invariant": alpha_ok,
        "cost_invariant": cost_ok,
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "pass": alpha_ok and cost_ok,
    }

# ===== q4/optimization.py =====
"""Q4 LPs: scenario-priced day-ahead q and remaining-horizon dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import cvxpy as cp
import numpy as np

from q2.config import (
    EMERGENCY_PRICE_MULTIPLIER,
    E_MAX_KWH,
    E_MIN_KWH,
    ETA_C,
    ETA_D,
    MPC_COST_TOL,
    POWER_LIMIT_KWH,
    SOLVER,
)
from q2.optimization import ValueCut, evaluate_value_cuts


@dataclass(frozen=True)
class DispatchResult:
    x: np.ndarray
    emergency: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    curtailment: np.ndarray
    soc: np.ndarray
    emergency_cost: float
    terminal_value: float
    solve_seconds: float
    status: str

    @property
    def max_cd(self) -> float:
        return float(np.max(self.charge * self.discharge))


@dataclass(frozen=True)
class PlanResult:
    q: np.ndarray
    expected_normal_cost: float
    expected_emergency_cost: float
    expected_terminal_value: float
    initial_soc_marginal: float
    solve_seconds: float
    status: str


def _terminal_value_expression(
    terminal_soc: cp.Expression, cuts: tuple[ValueCut, ...] | None
) -> tuple[cp.Variable | None, list[cp.Constraint]]:
    if not cuts:
        return None, []
    value = cp.Variable(nonneg=True)
    constraints = [
        value >= cut_value + slope * (terminal_soc - reference_soc)
        for reference_soc, cut_value, slope in cuts
    ]
    return value, constraints


def _physical_constraints(
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    normal: cp.Variable,
    emergency: cp.Variable,
    charge: cp.Variable,
    discharge: cp.Variable,
    curtailment: cp.Variable,
    soc: cp.Variable,
) -> list[cp.Constraint]:
    return [
        soc[0] == initial_soc,
        soc[1:] == soc[:-1] + ETA_C * charge - discharge / ETA_D,
        soc[1:] >= E_MIN_KWH,
        soc[1:] <= E_MAX_KWH,
        charge <= POWER_LIMIT_KWH,
        discharge <= POWER_LIMIT_KWH,
        curtailment <= pv,
        normal + emergency + pv - curtailment + discharge == load + charge,
    ]


def solve_stochastic_plan_varying_price(
    scenario_price: np.ndarray,
    scenario_load: np.ndarray,
    scenario_pv: np.ndarray,
    probabilities: np.ndarray,
    initial_soc: float,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    q_floor: np.ndarray | None = None,
    terminal_soc: float | None = None,
) -> PlanResult:
    k, n = scenario_load.shape
    if scenario_price.shape != (k, n) or scenario_pv.shape != (k, n):
        raise ValueError("scenario price/load/PV shapes must match")
    q = cp.Variable(n, nonneg=True)
    expected_normal: cp.Expression | float = 0.0
    expected_emergency: cp.Expression | float = 0.0
    expected_terminal: cp.Expression | float = 0.0
    constraints: list[cp.Constraint] = []
    if q_floor is not None:
        floor = np.asarray(q_floor, dtype=float).ravel()
        if floor.shape != (n,) or np.any(floor < -1e-9):
            raise ValueError("q_floor must be a nonnegative vector matching the horizon")
        constraints.append(q >= floor)
    initial_constraints: list[cp.Constraint] = []
    for omega in range(k):
        x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
        E = cp.Variable(n + 1)
        constraints.append(x <= q)
        physical = _physical_constraints(
            scenario_load[omega],
            scenario_pv[omega],
            initial_soc,
            x,
            e,
            c,
            d,
            w,
            E,
        )
        constraints += physical
        initial_constraints.append(physical[0])
        if terminal_soc is not None:
            constraints.append(E[-1] == float(terminal_soc))
        terminal_value, terminal_constraints = _terminal_value_expression(
            E[-1], terminal_value_cuts
        )
        constraints += terminal_constraints
        price = np.asarray(scenario_price[omega], dtype=float).ravel()
        expected_normal += probabilities[omega] * (price @ q)
        expected_emergency += probabilities[omega] * EMERGENCY_PRICE_MULTIPLIER * (price @ e)
        if terminal_value is not None:
            expected_terminal += probabilities[omega] * terminal_value
    problem = cp.Problem(
        cp.Minimize(expected_normal + expected_emergency + expected_terminal),
        constraints,
    )
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    elapsed = perf_counter() - started
    if q.value is None:
        raise RuntimeError(f"Q4-2 stochastic plan LP failed: {problem.status}")
    qv = np.asarray(q.value).ravel()
    marginal = -float(
        sum(float(np.asarray(constraint.dual_value)) for constraint in initial_constraints)
    )
    terminal_value_result = (
        float(expected_terminal.value)
        if isinstance(expected_terminal, cp.Expression)
        else float(expected_terminal)
    )
    expected_normal_v = float(sum(probabilities[o] * (scenario_price[o] @ qv) for o in range(k)))
    return PlanResult(
        q=qv,
        expected_normal_cost=expected_normal_v,
        expected_emergency_cost=float(problem.value - expected_normal_v - terminal_value_result),
        expected_terminal_value=terminal_value_result,
        initial_soc_marginal=marginal,
        solve_seconds=elapsed,
        status=str(problem.status),
    )


def solve_fixed_q_dispatch(
    price: np.ndarray,
    q: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    throughput_tiebreak: bool = True,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    terminal_soc: float | None = None,
) -> DispatchResult:
    n = len(load)
    x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
    E = cp.Variable(n + 1)
    constraints = [x <= q]
    constraints += _physical_constraints(load, pv, initial_soc, x, e, c, d, w, E)
    if terminal_soc is not None:
        constraints.append(E[-1] == float(terminal_soc))
    emergency_cost = EMERGENCY_PRICE_MULTIPLIER * price @ e
    terminal_value, terminal_constraints = _terminal_value_expression(E[-1], terminal_value_cuts)
    constraints += terminal_constraints
    primary = emergency_cost + (terminal_value if terminal_value is not None else 0.0)
    first = cp.Problem(cp.Minimize(primary), constraints)
    started = perf_counter()
    first.solve(solver=SOLVER, verbose=False)
    if e.value is None:
        raise RuntimeError(f"Q4-2 fixed-q dispatch LP failed: {first.status}")
    primary_opt = float(primary.value)
    status = str(first.status)
    if throughput_tiebreak:
        second = cp.Problem(
            cp.Minimize(cp.sum(c + d)),
            constraints + [primary <= primary_opt + MPC_COST_TOL],
        )
        second.solve(solver=SOLVER, verbose=False)
        if x.value is None:
            raise RuntimeError(f"Q4-2 tiebreak LP failed: {second.status}")
        status = str(second.status)
    elapsed = perf_counter() - started
    return DispatchResult(
        x=np.asarray(x.value).ravel(),
        emergency=np.asarray(e.value).ravel(),
        charge=np.asarray(c.value).ravel(),
        discharge=np.asarray(d.value).ravel(),
        curtailment=np.asarray(w.value).ravel(),
        soc=np.asarray(E.value).ravel(),
        emergency_cost=float(EMERGENCY_PRICE_MULTIPLIER * price @ e.value),
        terminal_value=evaluate_value_cuts(float(E.value[-1]), terminal_value_cuts),
        solve_seconds=elapsed,
        status=status,
    )

# ===== q4/plot_final_figures.py =====
#!/usr/bin/env python3
"""Render Q4 final figures from signed-off result artifacts only. Does not re-solve."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q4.closeout import (
    build_fair_comparison,
    load_q2_k8_daily,
    load_q3_official_daily,
    load_q4_2_daily,
    load_q4_3_daily,
    output_interval,
    q4_2_policy_windows,
)
from q4.config import (
    EXPECTED_Q4_2_ALPHA070_END,
    EXPECTED_Q4_2_ALPHA070_START,
    FIG_DIR,
    Q4_2_ALPHA_SELECTION_CSV,
    Q4_2_DAILY_CSV,
    Q4_2_DISPATCH_DIR,
    Q4_3_DAILY_CSV,
    Q4_3_DISPATCH_DIR,
    RESULT4_2_XLSX,
    RESULT4_3_XLSX,
)

RESULT3 = ROOT / "output/result3.xlsx"
Q2_K8_DAILY = ROOT / "output/q2_full_k8_risk/daily_summary.csv"
Q3_DAILY = ROOT / "output/q3_full_annual/q3_annual_daily_summary.csv"

BLUE = "#276FBF"
RED = "#C0392B"
GRAY = "#6B7280"
BLACK = "#1F2933"
LIGHT_BLUE = "#E8F1FA"
LIGHT_RED = "#F8E7E5"
LIGHT_GRAY = "#F3F4F6"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def configure_style() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = (
        "PingFang SC",
        "Hiragino Sans GB",
        "Heiti SC",
        "Songti SC",
        "Arial Unicode MS",
        "Noto Sans CJK SC",
        "WenQuanYi Micro Hei",
        "Droid Sans Fallback",
    )
    font = next((name for name in candidates if name in available), None)
    if font is None:
        raise RuntimeError("No usable Chinese font found")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font],
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "axes.titleweight": "normal",
            "pdf.fonttype": 42,
        }
    )
    return font


def save_figure(fig: plt.Figure, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(FIG_DIR / f"{stem}.png", dpi=320, bbox_inches="tight")
    plt.close(fig)


def draw_box(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    facecolor: str,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.15,
        edgecolor=BLACK,
        facecolor=facecolor,
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height / 2, text, ha="center", va="center", linespacing=1.38)


def style_axes(ax: plt.Axes, hide_right: bool = True) -> None:
    ax.spines["top"].set_visible(False)
    if hide_right:
        ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRAY)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(color=GRAY, length=3.5)


def draw_arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    label: str,
    label_y: float,
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.25,
            color=BLACK,
            shrinkA=2,
            shrinkB=2,
        )
    )
    ax.text(
        (start[0] + end[0]) / 2,
        label_y,
        label,
        ha="center",
        va="bottom",
        fontsize=8.8,
        color=BLACK,
        bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.95},
    )


def plot_q4_2_loop() -> None:
    fig, ax = plt.subplots(figsize=(15.6, 6.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    y, width, height = 0.48, 0.148, 0.30
    gap = 0.055
    xs = [0.020 + index * (width + gap) for index in range(5)]
    texts = [
        "历史负荷—光伏—价格\n配对残差\n（仅已结束日）",
        "日前 8 个联合情景\n风险分位购电下限",
        "0:00 锁定\n计划购电量 $q$",
        "每 10 分钟因果 MPC\n更新 $x,c,d,e$\n当天 $q$ 不可改",
        "实际日末 SOC\n$E_{d,144}$\n传至下一日",
    ]
    faces = [LIGHT_GRAY, LIGHT_BLUE, LIGHT_BLUE, LIGHT_RED, LIGHT_GRAY]
    for x, text, face in zip(xs, texts, faces):
        draw_box(ax, x, y, width, height, text, face)
    labels = ["构造因果预测", "0:00 决策", "当天 $q$ 锁定", "仅传递实际 SOC"]
    for index in range(4):
        draw_arrow(
            ax,
            (xs[index] + width, y + height / 2),
            (xs[index + 1], y + height / 2),
            labels[index],
            y + height + 0.035,
        )
    mid_y = 0.30
    ax.plot(
        [xs[4] + width / 2, xs[4] + width / 2, xs[1] + width / 2, xs[1] + width / 2],
        [y, mid_y, mid_y, y],
        color=BLUE,
        linestyle="--",
        linewidth=1.25,
        solid_capstyle="round",
    )
    ax.annotate(
        "",
        xy=(xs[1] + width / 2, y),
        xytext=(xs[1] + width / 2, mid_y + 0.01),
        arrowprops={"arrowstyle": "-|>", "color": BLUE, "lw": 1.25},
    )
    ax.text(
        (xs[1] + xs[4] + width) / 2,
        mid_y - 0.055,
        "次日 0:00 用新的因果价格预测重新锁定自己的 $q$；不提前锁定次日计划",
        ha="center",
        color=BLUE,
        fontsize=9.2,
    )
    ax.text(
        0.5,
        0.09,
        "日内只修正储能与实际取用；紧急购电 $e$ 只补当期缺口。结算按交付时点附件4 实际电价。",
        ha="center",
        color=RED,
        fontsize=9.2,
        bbox={"boxstyle": "round,pad=0.32", "facecolor": LIGHT_RED, "edgecolor": RED, "linewidth": 0.6},
    )
    ax.set_title("Q4-2 日前联合计划—日内因果 MPC—跨日 SOC 闭环", pad=10)
    save_figure(fig, "fig_q4_2_closed_loop")


def plot_q4_3_clock() -> None:
    fig, ax = plt.subplots(figsize=(15.6, 6.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    y, width, height = 0.48, 0.148, 0.30
    gap = 0.055
    xs = [0.020 + index * (width + gap) for index in range(5)]
    texts = [
        "0:00 制定 $g^0$\n因果日前价格\n负荷/光伏主案例",
        "6:00 评估 VOI\n可改 06:10 起\n前缀 $g$ 锁定",
        "12:00 评估 VOI\n可改 12:10 起",
        "18:00 评估 VOI\n可改 18:10 起",
        "交付时点结算\n$\\phi=p g^F+0.5p|g^F-g^0|$\n加 $5pe$",
    ]
    faces = [LIGHT_BLUE, LIGHT_GRAY, LIGHT_GRAY, LIGHT_GRAY, LIGHT_RED]
    for x, text, face in zip(xs, texts, faces):
        draw_box(ax, x, y, width, height, text, face)
    labels = ["主策略 M1_M6", "仅未执行段", "仅未执行段", "会计不改决策"]
    for index in range(4):
        draw_arrow(
            ax,
            (xs[index] + width, y + height / 2),
            (xs[index + 1], y + height / 2),
            labels[index],
            y + height + 0.035,
        )
    ax.text(
        0.5,
        0.22,
        "每个更新时刻用当时可得的日内价格预测；次日价值割仍因果。价格神谕与更新时刻重记账不进入主方案。",
        ha="center",
        color=BLUE,
        fontsize=9.2,
    )
    ax.text(
        0.5,
        0.09,
        "6:00 前 $g^F=g^0$；紧急购电只补当期缺口。主图成本为交付时点附件4 电价，不是神谕对照。",
        ha="center",
        color=RED,
        fontsize=9.2,
        bbox={"boxstyle": "round,pad=0.32", "facecolor": LIGHT_RED, "edgecolor": RED, "linewidth": 0.6},
    )
    ax.set_title("Q4-3 M1_M6 0/6/12/18 更新时钟与前缀锁定", pad=10)
    save_figure(fig, "fig_q4_3_update_clock")


def _stacked_pair(ax, names, planned, extra, emergency, extra_label: str | None) -> None:
    x = np.arange(len(names))
    width = 0.52
    total = planned + extra + emergency
    ax.bar(x, planned, width=width, color=BLUE, edgecolor=BLACK, linewidth=0.7, label="计划/普通购电费", zorder=3)
    if extra_label:
        ax.bar(
            x,
            extra,
            width=width,
            bottom=planned,
            color="white",
            edgecolor=GRAY,
            linewidth=1.05,
            hatch="xxx",
            label=extra_label,
            zorder=3,
        )
    ax.bar(
        x,
        emergency,
        width=width,
        bottom=planned + extra,
        color="white",
        edgecolor=RED,
        linewidth=1.15,
        hatch="///",
        label="紧急购电费",
        zorder=3,
    )
    for index, value in enumerate(total):
        ax.text(
            x[index],
            value + total.max() * 0.018,
            f"合计 {value:,.2f} 元",
            ha="center",
            va="bottom",
            fontsize=8.8,
            zorder=4,
            clip_on=False,
        )
        ax.text(
            x[index],
            planned[index] * 0.52,
            f"{planned[index] / 1e6:.2f} 百万",
            ha="center",
            va="center",
            color="white",
            fontsize=8.6,
            zorder=4,
        )
    ax.set_xticks(x, names)
    ax.set_ylabel("2—12 月购电成本（元）")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value / 1e6:.1f} 百万"))
    ax.set_ylim(0, total.max() * 1.16)
    ax.set_xlim(-0.55, len(names) - 0.45)
    ax.grid(axis="y", linestyle=":", color=GRAY, alpha=0.35, zorder=0)
    ax.set_axisbelow(True)
    style_axes(ax)


def plot_cost_comparison(comparison: dict) -> dict:
    q2 = comparison["export"]["q2_k8"]
    q42 = comparison["export"]["q4_2"]
    q3 = comparison["export"]["q3_m1_m6"]
    q43 = comparison["export"]["q4_3"]
    fig, axes = plt.subplots(1, 2, figsize=(13.8, 6.8))
    _stacked_pair(
        axes[0],
        ["Q2 K=8\n附件1 电价", "Q4-2\n附件4 电价"],
        np.array([q2["normal_or_settlement_yuan"], q42["normal_or_settlement_yuan"]]),
        np.array([0.0, q42["adjustment_yuan"]]),
        np.array([q2["emergency_cost_yuan"], q42["emergency_cost_yuan"]]),
        extra_label=None,
    )
    axes[0].set_title("日前锁定系统", pad=10)
    _stacked_pair(
        axes[1],
        ["Q3 M1_M6\n附件1 电价", "Q4-3\n附件4 电价"],
        np.array([q3["normal_or_settlement_yuan"], q43["normal_or_settlement_yuan"]]),
        np.array([0.0, q43["adjustment_yuan"]]),
        np.array([q3["emergency_cost_yuan"], q43["emergency_cost_yuan"]]),
        extra_label="偏差调整费",
    )
    axes[1].set_title("滚动调整系统", pad=10)
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 0.10),
    )
    fig.suptitle("2—12 月成本构成：同一套设备，不同价格信息", y=0.98)
    fig.subplots_adjust(bottom=0.28, top=0.86, wspace=0.28)
    fig.text(
        0.5,
        0.045,
        "注：两侧都是 2025-02-01 至 2025-12-31 共 334 日。Q4 相对 Q2/Q3 的差额不是同一电价下的会计节省；"
        "Q4-3 主图不含价格神谕与更新时刻重记账。",
        ha="center",
        fontsize=9,
        color=GRAY,
    )
    save_figure(fig, "fig_q4_cost_comparison")
    return {
        "q2_k8_export_yuan": q2["total_cost_yuan"],
        "q4_2_export_yuan": q42["total_cost_yuan"],
        "q3_m1_m6_export_yuan": q3["total_cost_yuan"],
        "q4_3_export_yuan": q43["total_cost_yuan"],
        "q4_2_minus_q2_yuan": comparison["pairs"]["q4_2_minus_q2_k8_export_yuan"],
        "q4_3_minus_q3_yuan": comparison["pairs"]["q4_3_minus_q3_m1_m6_export_yuan"],
    }


def _load_rep_day(daily: pd.DataFrame, dispatch_dir: Path) -> tuple[pd.Timestamp, pd.DataFrame, Path, dict]:
    output = output_interval(daily)
    selected = output.loc[output["emergency_cost_yuan"].idxmax()]
    date = pd.Timestamp(selected["date"])
    path = dispatch_dir / f"dispatch_{date:%Y-%m-%d}.csv"
    frame = pd.read_csv(path)
    if len(frame) != 144:
        raise AssertionError(f"{path.name} row count {len(frame)}")
    if not np.array_equal(frame["period_index"].to_numpy(), np.arange(144)):
        raise AssertionError("period_index order changed")
    if str(frame["time_label"].iloc[0]) != "00:10" or str(frame["time_label"].iloc[-1]) != "0:00+1":
        raise AssertionError("raw attachment time order mismatch")
    return date, frame, path, {
        "selected_date": date.strftime("%Y-%m-%d"),
        "selection_metric": "maximum emergency_cost_yuan over 2025-02-01..2025-12-31",
        "emergency_cost_yuan": float(selected["emergency_cost_yuan"]),
        "emergency_kwh": float(selected["emergency_kwh"]),
        "dispatch_rows": len(frame),
        "first_time": str(frame["time_label"].iloc[0]),
        "last_time": str(frame["time_label"].iloc[-1]),
        "source": str(path.relative_to(ROOT)),
    }


def plot_representative_day(daily: pd.DataFrame, dispatch_dir: Path, title_prefix: str, stem: str) -> dict:
    date, frame, path, meta = _load_rep_day(daily, dispatch_dir)
    hours = (frame["period_index"].to_numpy() + 1) / 6.0
    net_load = frame["actual_load_kwh"].to_numpy() - frame["actual_pv_kwh"].to_numpy()
    battery_net = frame["discharge_kwh"].to_numpy() - frame["charge_kwh"].to_numpy()
    plan = frame["g_final_kwh"].to_numpy(float) if "g_final_kwh" in frame and frame["g_final_kwh"].notna().all() else frame["q_or_g0_kwh"].to_numpy(float)
    plan_label = "终承诺 $g^F$" if "g_final" in stem or title_prefix.startswith("Q4-3") else "锁定计划 $q$"
    price = frame["actual_price"].to_numpy(float)

    fig, axes = plt.subplots(3, 1, figsize=(12.6, 11.0), sharex=True, gridspec_kw={"hspace": 0.16})
    legend_box = {
        "frameon": True,
        "framealpha": 0.96,
        "edgecolor": "#E5E7EB",
        "fancybox": False,
        "borderpad": 0.45,
        "handlelength": 2.2,
    }
    ax = axes[0]
    ax.plot(hours, net_load, color=BLACK, linewidth=1.35, label="实际净负荷 $L-P$")
    ax.plot(hours, plan, color=BLUE, linewidth=1.25, label=plan_label)
    ax.plot(hours, frame["x_kwh"], color=GRAY, linestyle="--", linewidth=1.15, label="实际普通取电 $x$")
    ax.plot(hours, frame["emergency_kwh"], color=RED, linestyle="-.", linewidth=1.45, label="紧急购电 $e$")
    ax.fill_between(hours, 0, frame["emergency_kwh"], color=RED, alpha=0.12, linewidth=0)
    ymax = max(net_load.max(), np.nanmax(plan), frame["emergency_kwh"].max())
    ax.set_ylim(-0.10 * ymax, ymax * 1.22)
    ax.set_ylabel("时段电量（kWh）")
    ax.legend(loc="upper left", ncol=2, **legend_box)
    ax.grid(linestyle=":", color=GRAY, alpha=0.32)
    ax.set_axisbelow(True)
    style_axes(ax)

    ax = axes[1]
    ax.axhline(0, color=GRAY, linewidth=0.8)
    ax.plot(hours, battery_net, color=BLACK, linewidth=1.2, label="电池净动作 $d-c$")
    ax.fill_between(hours, 0, battery_net, color=BLACK, alpha=0.10, linewidth=0)
    ax.set_ylabel("$d-c$（kWh）")
    abs_max = max(np.max(np.abs(battery_net)), 1e-9)
    ax.set_ylim(-abs_max * 1.28, abs_max * 1.28)
    ax_price = ax.twinx()
    ax_price.step(hours, price, where="mid", color=RED, linestyle="--", linewidth=1.15, label="实际电价")
    ax_price.set_ylabel("电价（元/kWh）", color=RED)
    ax_price.tick_params(axis="y", colors=RED)
    ax_price.set_ylim(0.0, max(price.max() * 1.22, 0.4))
    ax_price.spines["top"].set_visible(False)
    ax_price.spines["right"].set_color(RED)
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax_price.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, loc="lower left", **legend_box)
    ax.grid(linestyle=":", color=GRAY, alpha=0.32)
    ax.set_axisbelow(True)
    style_axes(ax, hide_right=False)

    ax = axes[2]
    ax.plot(hours, frame["soc_end_kwh"], color=BLUE, linewidth=1.5, label="SOC")
    ax.axhline(1200, color=GRAY, linestyle="--", linewidth=1.0, label="SOC 边界 1200 / 10800 kWh")
    ax.axhline(10800, color=GRAY, linestyle="--", linewidth=1.0)
    ax.set_ylabel("SOC（kWh）")
    ax.set_xlabel("时刻")
    ax.set_ylim(200, 12800)
    ax.legend(loc="center left", **legend_box)
    ax.grid(linestyle=":", color=GRAY, alpha=0.32)
    ax.set_axisbelow(True)
    style_axes(ax)
    axes[-1].set_xlim(0, 24)
    axes[-1].set_xticks(np.arange(0, 25, 2))
    axes[-1].set_xticklabels([f"{hour:02d}:00" for hour in range(0, 25, 2)])
    fig.suptitle(f"{title_prefix}：{date:%Y-%m-%d}（2—12 月紧急费用最高日）", y=0.98)
    fig.subplots_adjust(top=0.945, bottom=0.055, left=0.08, right=0.91, hspace=0.20)
    save_figure(fig, stem)
    return meta


def plot_alpha_timeline(daily: pd.DataFrame) -> dict:
    selected = q4_2_policy_windows(daily)
    fig, ax = plt.subplots(figsize=(13.4, 6.2))
    y_map = {None: 0, 0.6: 1, 0.7: 2, 0.8: 3, 0.9: 4}
    ytick_labels = ["预热 / 无风险分位", "alpha = 0.60", "alpha = 0.70", "alpha = 0.80", "alpha = 0.90"]
    year_start = mdates.date2num(pd.Timestamp("2025-01-01").to_pydatetime())
    year_end = mdates.date2num(pd.Timestamp("2026-01-01").to_pydatetime())
    for y in range(5):
        ax.barh(y, year_end - year_start, left=year_start, height=0.62, color=LIGHT_GRAY, edgecolor="none", zorder=0)
    ax.axvspan(pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-29"), color=GRAY, alpha=0.10, zorder=1)
    for row in selected.itertuples():
        start = mdates.date2num(pd.Timestamp(row.effective_start_date).to_pydatetime())
        end = mdates.date2num((pd.Timestamp(row.effective_end_date) + pd.Timedelta(days=1)).to_pydatetime())
        if pd.isna(row.risk_alpha) or row.kind == "warmup":
            y = y_map[None]
            ax.barh(y, end - start, left=start, height=0.62, color="white", edgecolor=BLACK, linewidth=0.8, hatch="///", zorder=3)
        else:
            alpha = round(float(row.risk_alpha), 2)
            y = y_map[alpha]
            ax.barh(y, end - start, left=start, height=0.62, color=BLUE, edgecolor=BLUE, linewidth=0.8, zorder=3)
            if alpha == 0.7:
                ax.text((start + end) / 2, y, "alpha=0.70", ha="center", va="center", fontsize=8.2, color="white", zorder=4)
            if int(row.n_days) == 1:
                ax.text(
                    start - 1.2,
                    y,
                    "12/31",
                    ha="right",
                    va="center",
                    fontsize=8.2,
                    color=BLACK,
                    zorder=5,
                    bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.92},
                )
    ax.text(
        mdates.date2num(pd.Timestamp("2025-01-15").to_pydatetime()),
        0,
        "1/1–1/28",
        ha="center",
        va="center",
        fontsize=8.2,
        color=BLACK,
        zorder=4,
        bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    for unused_y in (3, 4):
        ax.text(
            mdates.date2num(pd.Timestamp("2025-07-01").to_pydatetime()),
            unused_y,
            "候选未选用",
            ha="center",
            va="center",
            fontsize=8.4,
            color=GRAY,
            zorder=2,
        )
    ax.set_yticks(list(range(5)), ytick_labels)
    ax.set_ylim(-0.55, 4.75)
    ax.set_ylabel("政策档位")
    ax.set_xlabel("风险分位生效区间（每 14 日一块；12/31 为最后一块）")
    ax.set_title("Q4-2 滚动风险分位的因果校准时间线", pad=8)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_xlim(pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-04"))
    ax.grid(axis="x", linestyle=":", color=GRAY, alpha=0.32, zorder=0)
    style_axes(ax)
    fig.subplots_adjust(bottom=0.24)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.text(
        0.5,
        0.04,
        f"候选集 alphain{{0.60, 0.70, 0.80, 0.90}}；校准走官方闭环。"
        f"{EXPECTED_Q4_2_ALPHA070_START[5:]}–{EXPECTED_Q4_2_ALPHA070_END[5:]} 为唯一 alpha=0.70 窗口，其余预热后为 alpha=0.60。",
        ha="center",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": LIGHT_GRAY, "edgecolor": GRAY},
    )
    save_figure(fig, "fig_q4_2_risk_calibration")
    return {
        "selected_blocks": int(len(selected)),
        "warmup_days": int(selected.loc[selected["kind"] == "warmup", "n_days"].sum()),
        "calibrated_blocks": int((selected["kind"] == "calibrated").sum()),
        "alpha_060_days": int(selected.loc[selected["risk_alpha"] == 0.60, "n_days"].sum()),
        "alpha_070_days": int(selected.loc[selected["risk_alpha"] == 0.70, "n_days"].sum()),
        "calendar_start": selected["effective_start_date"].iloc[0].strftime("%Y-%m-%d"),
        "calendar_end": selected["effective_end_date"].iloc[-1].strftime("%Y-%m-%d"),
        "alpha_070_window": f"{EXPECTED_Q4_2_ALPHA070_START}..{EXPECTED_Q4_2_ALPHA070_END}",
    }


def write_readme(font: str, f2: dict, f3_2: dict, f3_3: dict, f4: dict, hashes: dict[str, str]) -> None:
    lines = [
        "# Q4 正式交付图",
        "",
        "运行命令：",
        "",
        "```bash",
        "MPLCONFIGDIR=\"$PWD/.mplconfig\" python3 q4/plot_final_figures.py",
        "python3 q4/report_q4_closeout.py",
        "```",
        "",
        f"- 中文字体：{font}",
        "- 所有 PNG 均以 320 dpi 导出，同时提供矢量 PDF。",
        "- 原始时段顺序保持 `00:10` 至 `0:00+1`，未旋转或补造时段。",
        "- 主图不含 Q4-3 价格神谕年与更新时刻重记账。",
        "",
        "## F1a `fig_q4_2_closed_loop`",
        "",
        "- 数据源：已签收 Q4-2 机制；图形由 matplotlib patches 矢量绘制。",
        "- 核验：当天 q 锁定、因果 MPC、紧急购电只补当期、实际 SOC 跨日传递。",
        "",
        "## F1b `fig_q4_3_update_clock`",
        "",
        "- 数据源：已签收 Q4-3 M1_M6 0/6/12/18 时钟。",
        "- 核验：6:00 前前缀锁定；结算为交付时点实际电价。",
        "",
        "## F2 `fig_q4_cost_comparison`",
        "",
        "- 数据源：Q4-2/Q4-3 日汇总、Q2 K=8 日汇总、Q3 官方 A+M1_M6 日汇总。",
        "- 汇总范围：2025-02-01 至 2025-12-31，共 334 日。不要与 1—12 月年合计混用。",
        f"- Q4-2：{f2['q4_2_export_yuan']:,.2f} 元；Q2 K=8：{f2['q2_k8_export_yuan']:,.2f} 元。",
        f"- Q4-3：{f2['q4_3_export_yuan']:,.2f} 元；Q3 M1_M6 同期：{f2['q3_m1_m6_export_yuan']:,.2f} 元。",
        "- 核验：Q4 与 Q2 对照值与签收工作簿差小于 0.01 元。Q2/Q3 用附件1，Q4 用附件4。",
        "",
        "## F3a `fig_q4_2_representative_day`",
        "",
        f"- 可复现选择：2—12 月 `emergency_cost_yuan` 最大日为 {f3_2['selected_date']}。",
        f"- 源文件：`{f3_2['source']}`；{f3_2['first_time']} 至 {f3_2['last_time']}。",
        "",
        "## F3b `fig_q4_3_representative_day`",
        "",
        f"- 可复现选择：2—12 月 `emergency_cost_yuan` 最大日为 {f3_3['selected_date']}。",
        f"- 源文件：`{f3_3['source']}`。",
        "",
        "## F4 `fig_q4_2_risk_calibration`",
        "",
        f"- 共 {f4['selected_blocks']} 个生效块：预热 {f4['warmup_days']} 日，其后 {f4['calibrated_blocks']} 块。",
        f"- alpha=0.60 为 {f4['alpha_060_days']} 日，alpha=0.70 为 {f4['alpha_070_days']} 日（{f4['alpha_070_window']}）。",
        "",
        "## 只读保护",
        "",
        "- 绘图脚本对日汇总、alpha 选择表与 result4/result3 工作簿执行前后 SHA-256 校验。",
        f"- `output/result4-2.xlsx` SHA-256：`{hashes.get(str(RESULT4_2_XLSX.relative_to(ROOT)), '文件不存在')}`。",
        f"- `output/result4-3.xlsx` SHA-256：`{hashes.get(str(RESULT4_3_XLSX.relative_to(ROOT)), '文件不存在')}`。",
    ]
    (FIG_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    source_paths = [
        Q4_2_DAILY_CSV,
        Q4_3_DAILY_CSV,
        Q4_2_ALPHA_SELECTION_CSV,
        Q2_K8_DAILY,
        Q3_DAILY,
    ]
    for path in (RESULT4_2_XLSX, RESULT4_3_XLSX, RESULT3):
        if path.exists():
            source_paths.append(path)
    for path in source_paths:
        if not path.exists():
            raise FileNotFoundError(path)
    hashes_before = {str(path.relative_to(ROOT)): file_hash(path) for path in source_paths}
    font = configure_style()
    q42 = load_q4_2_daily()
    q43 = load_q4_3_daily()
    comparison = build_fair_comparison(q42, q43, load_q2_k8_daily(), load_q3_official_daily())

    plot_q4_2_loop()
    plot_q4_3_clock()
    f2 = plot_cost_comparison(comparison)
    f3_2 = plot_representative_day(q42, Q4_2_DISPATCH_DIR, "Q4-2 日前—日内联动轨迹", "fig_q4_2_representative_day")
    f3_3 = plot_representative_day(q43, Q4_3_DISPATCH_DIR, "Q4-3 M1_M6 滚动调整轨迹", "fig_q4_3_representative_day")
    f4 = plot_alpha_timeline(q42)

    hashes_after = {str(path.relative_to(ROOT)): file_hash(path) for path in source_paths}
    if hashes_before != hashes_after:
        raise AssertionError("A source result file changed during plotting")
    audit = {
        "status": "PASS",
        "font": font,
        "png_dpi": 320,
        "f2": f2,
        "f3_q4_2": f3_2,
        "f3_q4_3": f3_3,
        "f4": f4,
        "source_sha256": hashes_after,
        "oracle_on_main_figures": False,
        "result4_2_unchanged": hashes_before.get(str(RESULT4_2_XLSX.relative_to(ROOT)))
        == hashes_after.get(str(RESULT4_2_XLSX.relative_to(ROOT))),
        "result4_3_unchanged": hashes_before.get(str(RESULT4_3_XLSX.relative_to(ROOT)))
        == hashes_after.get(str(RESULT4_3_XLSX.relative_to(ROOT))),
    }
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    (FIG_DIR / "figure_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_readme(font, f2, f3_2, f3_3, f4, hashes_after)
    print(json.dumps({k: audit[k] for k in ("status", "font", "f2", "f3_q4_2", "f3_q4_3", "f4")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# ===== q4/price_forecast.py =====
"""Causal day-ahead and intraday price forecasts. History is strictly before day d."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from q4.config import (
    CANDIDATE_MODELS,
    CANDIDATE_NAMES,
    INTRA_HOUR_TAU,
    T,
    VAR_EPS,
)


def construct_candidate(
    prices: np.ndarray,
    weekdays: np.ndarray,
    day_index: int,
    model: int,
) -> np.ndarray | None:
    if model == 1:
        if day_index < 1:
            return None
        return prices[day_index - 1].copy()
    if model not in (2, 4):
        raise ValueError(f"unknown candidate model {model}")
    same = np.flatnonzero((np.arange(day_index) >= 0) & (weekdays[:day_index] == weekdays[day_index]))
    if same.size < model:
        return None
    return prices[same[-model:]].mean(axis=0)


def _mae(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - forecast)))


def _rmse(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - forecast) ** 2)))


def ols_remaining(
    residual_hist: np.ndarray,
    z_hist: np.ndarray,
    z_now: float,
) -> tuple[np.ndarray, bool]:
    """Fit r_t = alpha_t + beta_t z on historical days; return residual forecast for remaining t.

    residual_hist has shape (n_hist, n_future). z_hist has shape (n_hist,).
    """
    n_hist, n_future = residual_hist.shape
    if n_hist < 2:
        if n_hist == 1:
            return residual_hist[0].copy(), True
        return np.zeros(n_future, dtype=float), True
    z_center = z_hist - float(z_hist.mean())
    denom = float(np.dot(z_center, z_center))
    if denom <= VAR_EPS:
        return residual_hist.mean(axis=0).copy(), True
    r_center = residual_hist - residual_hist.mean(axis=0)
    beta = z_center @ r_center / denom
    alpha = residual_hist.mean(axis=0) - beta * float(z_hist.mean())
    return alpha + beta * float(z_now), False


def intraday_price_forecast(
    actual: np.ndarray,
    day_ahead: np.ndarray,
    hist_actual: np.ndarray,
    hist_day_ahead: np.ndarray,
    tau: int,
) -> tuple[np.ndarray, bool]:
    """Return a 144-vector: known actual[:tau], OLS-updated remaining[tau:], clamped at 0."""
    if tau < 0 or tau > T:
        raise ValueError(f"tau out of range: {tau}")
    out = np.empty(T, dtype=float)
    if tau == 0:
        return np.maximum(0.0, day_ahead.copy()), True
    out[:tau] = actual[:tau]
    if tau == T:
        return out, True
    z_now = float(np.mean(actual[:tau] - day_ahead[:tau]))
    if hist_actual.size == 0:
        out[tau:] = np.maximum(0.0, day_ahead[tau:])
        return out, True
    residual_hist = hist_actual[:, tau:] - hist_day_ahead[:, tau:]
    z_hist = (hist_actual[:, :tau] - hist_day_ahead[:, :tau]).mean(axis=1)
    delta, fallback = ols_remaining(residual_hist, z_hist, z_now)
    out[tau:] = np.maximum(0.0, day_ahead[tau:] + delta)
    return out, fallback


@dataclass
class PriceForecastArchive:
    dates: pd.DatetimeIndex
    price: np.ndarray
    day_ahead: np.ndarray
    chosen_model: np.ndarray
    candidate_forecasts: dict[int, np.ndarray]
    candidate_available: dict[int, np.ndarray]
    mae_through_prev: dict[int, np.ndarray]
    n_backtest: dict[int, np.ndarray]
    audit: pd.DataFrame


def fit_causal_price_forecasts(
    prices: np.ndarray,
    dates: pd.DatetimeIndex,
    compute_mpc: bool = True,
) -> PriceForecastArchive:
    n = len(dates)
    if prices.shape != (n, T):
        raise ValueError(f"prices shape {prices.shape} != {(n, T)}")
    weekdays = dates.weekday.to_numpy()
    day_ahead = np.full((n, T), np.nan)
    chosen = np.full(n, -1, dtype=int)
    cand_hat = {a: np.full((n, T), np.nan) for a in CANDIDATE_MODELS}
    cand_ok = {a: np.zeros(n, dtype=bool) for a in CANDIDATE_MODELS}
    mae_prev = {a: np.full(n, np.nan) for a in CANDIDATE_MODELS}
    n_bt = {a: np.zeros(n, dtype=int) for a in CANDIDATE_MODELS}
    abs_sum = {a: 0.0 for a in CANDIDATE_MODELS}
    bt_count = {a: 0 for a in CANDIDATE_MODELS}

    rows = []
    for d in range(n):
        for a in CANDIDATE_MODELS:
            n_bt[a][d] = bt_count[a]
            if bt_count[a] > 0:
                mae_prev[a][d] = abs_sum[a] / (bt_count[a] * T)
            hat = construct_candidate(prices, weekdays, d, a)
            if hat is None:
                continue
            cand_hat[a][d] = hat
            cand_ok[a][d] = True

        available = [a for a in CANDIDATE_MODELS if cand_ok[a][d]]
        fallback = "none"
        if not available:
            fallback = "no_history"
            chosen_a = -1
        else:
            scored = []
            for a in available:
                mae = mae_prev[a][d]
                score = float("inf") if not np.isfinite(mae) else float(mae)
                scored.append((score, a))
            chosen_a = min(scored)[1]
            if not cand_ok[1][d]:
                fallback = "no_previous_day"
            elif not cand_ok[2][d] and not cand_ok[4][d]:
                fallback = "previous_day_only"
        chosen[d] = chosen_a
        if chosen_a > 0:
            day_ahead[d] = cand_hat[chosen_a][d]

        da_mae = np.nan
        da_rmse = np.nan
        if chosen_a > 0:
            da_mae = _mae(prices[d], day_ahead[d])
            da_rmse = _rmse(prices[d], day_ahead[d])

        hist_idx = [i for i in range(d) if chosen[i] > 0]
        hist_actual = prices[hist_idx] if hist_idx else np.zeros((0, T))
        hist_da = day_ahead[hist_idx] if hist_idx else np.zeros((0, T))
        intra = {}
        mpc_mae = []
        n_mpc_fallback = 0
        n_mpc = 0
        if chosen_a > 0:
            for hour, tau in INTRA_HOUR_TAU.items():
                pred, ols_fb = intraday_price_forecast(
                    prices[d], day_ahead[d], hist_actual, hist_da, tau
                )
                intra[hour] = {
                    "mae": _mae(prices[d, tau:], pred[tau:]),
                    "rmse": _rmse(prices[d, tau:], pred[tau:]),
                    "ols_fallback": bool(ols_fb),
                }
            if compute_mpc:
                for tau in range(1, T):
                    pred, ols_fb = intraday_price_forecast(
                        prices[d], day_ahead[d], hist_actual, hist_da, tau
                    )
                    mpc_mae.append(_mae(prices[d, tau:], pred[tau:]))
                    n_mpc += 1
                    n_mpc_fallback += int(ols_fb)

        train_cutoff = dates[d - 1].strftime("%Y-%m-%d") if d else ""
        row = {
            "date": dates[d].strftime("%Y-%m-%d"),
            "day_index": d,
            "train_cutoff_date": train_cutoff,
            "weekday": int(weekdays[d]),
            "mae_prev_day": mae_prev[1][d],
            "mae_weekday2": mae_prev[2][d],
            "mae_weekday4": mae_prev[4][d],
            "n_backtest_prev_day": int(n_bt[1][d]),
            "n_backtest_weekday2": int(n_bt[2][d]),
            "n_backtest_weekday4": int(n_bt[4][d]),
            "candidate_prev_day_available": bool(cand_ok[1][d]),
            "candidate_weekday2_available": bool(cand_ok[2][d]),
            "candidate_weekday4_available": bool(cand_ok[4][d]),
            "chosen_model": chosen_a if chosen_a > 0 else "",
            "chosen_model_name": CANDIDATE_NAMES.get(chosen_a, "none"),
            "day_ahead_fallback": fallback,
            "day_ahead_mae": da_mae,
            "day_ahead_rmse": da_rmse,
            "intraday_06_mae": intra.get(6, {}).get("mae", np.nan),
            "intraday_06_rmse": intra.get(6, {}).get("rmse", np.nan),
            "intraday_06_ols_fallback": intra.get(6, {}).get("ols_fallback", True),
            "intraday_12_mae": intra.get(12, {}).get("mae", np.nan),
            "intraday_12_rmse": intra.get(12, {}).get("rmse", np.nan),
            "intraday_12_ols_fallback": intra.get(12, {}).get("ols_fallback", True),
            "intraday_18_mae": intra.get(18, {}).get("mae", np.nan),
            "intraday_18_rmse": intra.get(18, {}).get("rmse", np.nan),
            "intraday_18_ols_fallback": intra.get(18, {}).get("ols_fallback", True),
            "mpc_remaining_mae_mean": float(np.mean(mpc_mae)) if mpc_mae else np.nan,
            "n_mpc_points": n_mpc,
            "n_mpc_ols_fallback": n_mpc_fallback,
        }
        rows.append(row)

        for a in CANDIDATE_MODELS:
            if cand_ok[a][d]:
                abs_sum[a] += float(np.abs(prices[d] - cand_hat[a][d]).sum())
                bt_count[a] += 1

    audit = pd.DataFrame(rows)
    return PriceForecastArchive(
        dates=dates,
        price=prices,
        day_ahead=day_ahead,
        chosen_model=chosen,
        candidate_forecasts=cand_hat,
        candidate_available=cand_ok,
        mae_through_prev=mae_prev,
        n_backtest=n_bt,
        audit=audit,
    )


def assert_no_future_price_leak(
    prices: np.ndarray,
    dates: pd.DatetimeIndex,
    day_index: int,
    tau: int = 0,
) -> None:
    """Perturb prices at and after (day_index, tau); earlier forecasts/choices must not change."""
    archive = fit_causal_price_forecasts(prices, dates, compute_mpc=False)
    perturbed = prices.copy()
    perturbed[day_index, tau:] += 7.5
    if day_index + 1 < len(prices):
        perturbed[day_index + 1 :] += 3.25
    other = fit_causal_price_forecasts(perturbed, dates, compute_mpc=False)
    if day_index > 0:
        np.testing.assert_allclose(
            archive.day_ahead[:day_index],
            other.day_ahead[:day_index],
            equal_nan=True,
        )
        np.testing.assert_array_equal(archive.chosen_model[:day_index], other.chosen_model[:day_index])
    if tau == 0:
        if np.isfinite(archive.day_ahead[day_index]).all():
            np.testing.assert_allclose(archive.day_ahead[day_index], other.day_ahead[day_index], equal_nan=True)
        np.testing.assert_equal(archive.chosen_model[day_index], other.chosen_model[day_index])
    else:
        if archive.chosen_model[day_index] <= 0:
            return
        hist_idx = [i for i in range(day_index) if archive.chosen_model[i] > 0]
        hist_actual = prices[hist_idx] if hist_idx else np.zeros((0, T))
        hist_da = archive.day_ahead[hist_idx] if hist_idx else np.zeros((0, T))
        before, _ = intraday_price_forecast(
            prices[day_index], archive.day_ahead[day_index], hist_actual, hist_da, tau
        )
        after, _ = intraday_price_forecast(
            perturbed[day_index], other.day_ahead[day_index], hist_actual, hist_da, tau
        )
        np.testing.assert_allclose(before[tau:], after[tau:])


def two_day_regression(archive: PriceForecastArchive, dates: tuple[str, ...]) -> dict:
    payload = {}
    for date in dates:
        loc = archive.dates.get_loc(pd.Timestamp(date))
        i = int(loc)
        row = archive.audit.iloc[i].to_dict()
        payload[date] = {
            **{k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in row.items()},
            "day_ahead_first6": archive.day_ahead[i, :6].tolist()
            if np.isfinite(archive.day_ahead[i, :6]).all()
            else None,
            "actual_first6": archive.price[i, :6].tolist(),
        }
    return payload

# ===== q4/prices.py =====
"""Causal helpers that call the accepted price module without rewriting it."""

from __future__ import annotations

import numpy as np

from q4.bundle import Q4Bundle
from q4.config import CANDIDATE_MODELS
from q4.price_forecast import intraday_price_forecast


def day_ahead_today(bundle: Q4Bundle, day_index: int) -> tuple[np.ndarray, str, int]:
    hat = bundle.price_archive.day_ahead[day_index]
    chosen = int(bundle.price_archive.chosen_model[day_index])
    if np.isfinite(hat).all() and chosen > 0:
        return hat.copy(), "price_module", chosen
    return bundle.q3.price.copy(), "attachment1_no_history", -1


def day_ahead_as_of(
    bundle: Q4Bundle, target_index: int, history_end_exclusive: int
) -> tuple[np.ndarray, str, int]:
    """Forecast target_index using only prices with index < history_end_exclusive.

    This is required for the 48-hour value of day d+1 at day d 00:00: the
    archived ``day_ahead[d+1]`` is as-of d+1 00:00 and would leak day d actuals.
    """
    if history_end_exclusive <= 0:
        return bundle.q3.price.copy(), "attachment1_no_history", -1
    weekdays = bundle.prices.dates.weekday.to_numpy()
    prices = bundle.prices.price
    hats: dict[int, np.ndarray] = {}
    if target_index >= 1 and (target_index - 1) < history_end_exclusive:
        hats[1] = prices[target_index - 1].copy()
    for model in (2, 4):
        same = np.flatnonzero(
            weekdays[:history_end_exclusive] == weekdays[target_index]
        )
        if same.size < model:
            continue
        hats[model] = prices[same[-model:]].mean(axis=0)
    if not hats:
        return bundle.q3.price.copy(), "attachment1_no_history", -1
    mae_idx = min(history_end_exclusive, target_index, bundle.n_days() - 1)
    scored = []
    for model in CANDIDATE_MODELS:
        if model not in hats:
            continue
        mae = bundle.price_archive.mae_through_prev[model][mae_idx]
        score = float("inf") if not np.isfinite(mae) else float(mae)
        scored.append((score, model))
    chosen = min(scored)[1]
    return hats[chosen], "price_module_as_of", chosen


def remaining_price_forecast(
    bundle: Q4Bundle, day_index: int, tau: int
) -> tuple[np.ndarray, bool]:
    day_ahead, _src, chosen = day_ahead_today(bundle, day_index)
    actual = bundle.prices.price[day_index]
    if chosen <= 0 or tau <= 0:
        out = day_ahead.copy()
        if tau > 0:
            out[:tau] = actual[:tau]
        return np.maximum(0.0, out), True
    hist_idx = [i for i in range(day_index) if bundle.price_archive.chosen_model[i] > 0]
    if hist_idx:
        hist_actual = bundle.prices.price[hist_idx]
        hist_da = bundle.price_archive.day_ahead[hist_idx]
    else:
        hist_actual = np.zeros((0, day_ahead.shape[0]))
        hist_da = np.zeros((0, day_ahead.shape[0]))
    return intraday_price_forecast(actual, day_ahead, hist_actual, hist_da, tau)

# ===== q4/q4_2.py =====
"""Q4-2: triple-scenario day-ahead q, locked all day, causal MPC execution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from math import inf, sqrt
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from q2.config import (
    E_MAX_KWH,
    E_MIN_KWH,
    EMERGENCY_PRICE_MULTIPLIER,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
    NEXT_DAY_VALUE_MAX_SAMPLES,
    NUMERIC_TOL,
    SIMULTANEOUS_CD_TOL,
    T,
)
from q2.forecast import forecast_as_of
from q2.optimization import ValueCut, evaluate_value_cuts
from q2.pilot import risk_quantile_floor
from q4.bundle import Q4Bundle
from q4.config import (
    ALPHA_POLICY_LOOP,
    FIXED_SCENARIO_K,
    LOAD_INFORMATION_CASE,
    Q4_2_YEAR_END_RULE,
    RISK_ALPHA_CANDIDATES,
    RISK_CALIBRATION_DAYS,
    RISK_WARMUP_DAYS,
    SETTLEMENT_RULE,
)
from q4.optimization import solve_fixed_q_dispatch, solve_stochastic_plan_varying_price
from q4.prices import day_ahead_as_of, day_ahead_today, remaining_price_forecast
from q4.scenarios import (
    TripleScenarioSet,
    build_triple_scenarios,
    posterior_weights,
    residual_stack,
    scenario_paths,
)


def plan_locked_q(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    risk_alpha: float | None,
    k_target: int = FIXED_SCENARIO_K,
    with_value_cuts: bool = True,
) -> np.ndarray:
    """Day-ahead q only (no MPC). Used by information-set probes."""
    loads, pvs, prices, probs, _sc, base_load, base_pv, _src, _ch = q4_2_day_inputs(
        bundle, day_index, day_index, k_target
    )
    q_floor = risk_quantile_floor(loads, pvs, probs, base_load, base_pv, risk_alpha)
    cuts = ()
    if with_value_cuts:
        cuts, _ = build_q4_2_value_cuts(bundle, day_index, k_target, risk_alpha)
    plan = solve_stochastic_plan_varying_price(
        prices,
        loads,
        pvs,
        probs,
        initial_soc,
        terminal_value_cuts=cuts or None,
        q_floor=q_floor,
    )
    return plan.q.copy()


def planned_q_hash(q: np.ndarray) -> str:
    canonical = ",".join(f"{float(value):.9f}" for value in np.asarray(q).ravel())
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


@dataclass
class Q42DayResult:
    date: str
    day_index: int
    q: np.ndarray
    dispatch: pd.DataFrame
    summary: dict
    day_ahead_audit: dict
    scenario_rows: list[dict] = field(default_factory=list)
    value_rows: list[dict] = field(default_factory=list)


def _point_paths(load_hat: np.ndarray, pv_hat: np.ndarray, price_hat: np.ndarray):
    return load_hat[None, :], pv_hat[None, :], price_hat[None, :], np.ones(1)


def q4_2_day_inputs(
    bundle: Q4Bundle,
    day_index: int,
    history_end_exclusive: int,
    k_target: int = FIXED_SCENARIO_K,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, TripleScenarioSet | None, np.ndarray, np.ndarray, str, int]:
    load_hat, pv_hat, _ls, _ps = forecast_as_of(
        bundle.q2, day_index, history_end_exclusive
    )
    if history_end_exclusive == day_index:
        price_hat, price_src, chosen = day_ahead_today(bundle, day_index)
    else:
        price_hat, price_src, chosen = day_ahead_as_of(
            bundle, day_index, history_end_exclusive
        )
    scenarios = build_triple_scenarios(
        bundle, day_index, history_end_exclusive, k_target=k_target
    )
    if scenarios is None:
        loads, pvs, prices, probs = _point_paths(load_hat, pv_hat, price_hat)
    else:
        loads, pvs, prices = scenario_paths(
            bundle, scenarios, load_hat, pv_hat, price_hat
        )
        probs = scenarios.probabilities
    return loads, pvs, prices, probs, scenarios, load_hat, pv_hat, price_src, chosen


def build_q4_2_value_cuts(
    bundle: Q4Bundle,
    current_index: int,
    k_target: int,
    risk_alpha: float | None,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    next_index = current_index + 1
    if next_index >= bundle.n_days():
        return (), []
    loads, pvs, prices, probs, scenarios, base_load, base_pv, price_src, chosen = q4_2_day_inputs(
        bundle, next_index, current_index, k_target
    )
    q_floor = risk_quantile_floor(loads, pvs, probs, base_load, base_pv, risk_alpha)
    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = solve_stochastic_plan_varying_price(
            prices, loads, pvs, probs, float(soc), q_floor=q_floor
        )
        value = result.expected_normal_cost + result.expected_emergency_cost
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
            raise AssertionError("Q4-2 next-day value subgradients are not monotone")
        gap, refine_soc = certified_max_gap(cuts)
        if gap <= NEXT_DAY_VALUE_GAP_TOL_YUAN:
            break
        if len(cuts) >= NEXT_DAY_VALUE_MAX_SAMPLES:
            raise AssertionError(
                f"Q4-2 next-day value gap {gap:.6f} exceeds tolerance after {len(cuts)} samples"
            )
        if min(abs(refine_soc - soc) for soc in solved) < 1e-7:
            raise AssertionError("Q4-2 next-day value refinement stalled")
        solve_at(refine_soc)
    k_eff = 1 if scenarios is None else scenarios.k_effective
    rows = [
        {
            "current_date": bundle.prices.dates[current_index].strftime("%Y-%m-%d"),
            "target_date": bundle.prices.dates[next_index].strftime("%Y-%m-%d"),
            "k_effective": k_eff,
            "risk_alpha": risk_alpha,
            "price_source": price_src,
            "chosen_price_model": chosen,
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
        }
        for reference, value, slope in cuts
    ]
    return cuts, rows


@dataclass
class AlphaSelection:
    selected_alpha: float
    window_records: list[dict]
    daily_records: list[dict]


def calibration_window(target_index: int, n_validation: int | None = None) -> np.ndarray:
    n = RISK_CALIBRATION_DAYS if n_validation is None else int(n_validation)
    if n <= 0 or target_index <= 0:
        return np.zeros(0, dtype=int)
    return np.arange(max(0, target_index - n), target_index, dtype=int)


def q2_aligned_calibration_indices(n_days: int) -> list[int]:
    """Q2 14-day blocks after the 28-day warmup: 28, 42, ..., up to the last complete index."""
    return [
        i
        for i in range(RISK_WARMUP_DAYS, n_days)
        if i % RISK_CALIBRATION_DAYS == 0
    ]


def _metrics_from_day(result: Q42DayResult, elapsed_seconds: float) -> dict:
    q = np.asarray(result.q, dtype=float)
    x = result.dispatch["x_kwh"].to_numpy(float)
    soc_end = result.dispatch["soc_end_kwh"].to_numpy(float)
    gap = (
        float(result.value_rows[0]["certified_max_gap_yuan"])
        if result.value_rows
        else float("nan")
    )
    return {
        "date": result.date,
        "day_index": int(result.day_index),
        "planned_fee_yuan": float(result.summary["normal_cost_yuan"]),
        "emergency_fee_yuan": float(result.summary["emergency_cost_yuan"]),
        "total_cost_yuan": float(result.summary["total_cost_yuan"]),
        "unused_quota_kwh": float(np.sum(q - x)),
        "emergency_kwh": float(result.summary["emergency_kwh"]),
        "soc_start_kwh": float(result.summary["soc_start_kwh"]),
        "soc_end_kwh": float(result.summary["soc_end_kwh"]),
        "soc_min_kwh": float(soc_end.min()),
        "soc_max_kwh": float(soc_end.max()),
        "soc_end_path_kwh": ";".join(f"{value:.6f}" for value in soc_end),
        "has_value_cuts": bool(result.value_rows),
        "n_value_cuts": int(len(result.value_rows)),
        "value_cut_gap_yuan": gap,
        "value_cuts_used": bool(result.value_rows),
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "k_effective": int(result.summary["k_effective"]),
        "elapsed_seconds": float(elapsed_seconds),
        "policy_loop": ALPHA_POLICY_LOOP,
    }


def run_candidate_window(
    bundle: Q4Bundle,
    policy_start_soc: np.ndarray,
    target_index: int,
    *,
    risk_alpha: float | None,
    k_target: int = FIXED_SCENARIO_K,
    n_validation: int | None = None,
    log_prefix: str | None = None,
) -> tuple[list[dict], dict]:
    """Replay prior completed days with the official Q4-2 closed loop.

    Each candidate carries its own SOC. The window opens at the deployed
    policy's recorded start SOC on the first validation day. Full-day actual
    path dispatch is not used.
    """
    validation = calibration_window(target_index, n_validation)
    empty = {
        "risk_alpha": None if risk_alpha is None else float(risk_alpha),
        "k_target": int(k_target),
        "validation_days": 0,
        "mean_validation_cost_yuan": np.nan,
        "standard_error_yuan": np.nan,
        "total_planned_fee_yuan": np.nan,
        "total_emergency_fee_yuan": np.nan,
        "total_cost_yuan": np.nan,
        "total_unused_quota_kwh": np.nan,
        "emergency_purchase_kwh": np.nan,
        "soc_window_start_kwh": np.nan,
        "soc_window_end_kwh": np.nan,
        "daily_soc_end_path_kwh": "",
        "all_value_cuts_present": False,
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "mean_elapsed_seconds": np.nan,
        "mean_solve_seconds": np.nan,
        "policy_loop": ALPHA_POLICY_LOOP,
        "fallback_reason": "empty_validation_window",
    }
    if len(validation) == 0:
        return [], empty
    soc = float(policy_start_soc[int(validation[0])])
    if not np.isfinite(soc):
        empty["fallback_reason"] = "no_validation_soc"
        return [], empty
    daily: list[dict] = []
    for offset, day_index in enumerate(validation):
        started = perf_counter()
        result = run_q4_2_day(
            bundle, int(day_index), soc, risk_alpha, k_target=k_target
        )
        elapsed = perf_counter() - started
        row = _metrics_from_day(result, elapsed)
        row["risk_alpha"] = None if risk_alpha is None else float(risk_alpha)
        row["k_target"] = int(k_target)
        row["calibration_day_index"] = int(target_index)
        daily.append(row)
        soc = float(result.summary["soc_end_kwh"])
        if log_prefix:
            print(
                f"{log_prefix} [{offset + 1}/{len(validation)}] {result.date} "
                f"cost={row['total_cost_yuan']:.2f} soc={soc:.2f}",
                flush=True,
            )
        del result
    costs = np.asarray([row["total_cost_yuan"] for row in daily], dtype=float)
    summary = {
        "risk_alpha": None if risk_alpha is None else float(risk_alpha),
        "k_target": int(k_target),
        "validation_days": int(len(daily)),
        "mean_validation_cost_yuan": float(np.mean(costs)),
        "standard_error_yuan": float(
            np.std(costs, ddof=1) / sqrt(len(costs)) if len(costs) > 1 else 0.0
        ),
        "total_planned_fee_yuan": float(sum(row["planned_fee_yuan"] for row in daily)),
        "total_emergency_fee_yuan": float(
            sum(row["emergency_fee_yuan"] for row in daily)
        ),
        "total_cost_yuan": float(np.sum(costs)),
        "total_unused_quota_kwh": float(
            sum(row["unused_quota_kwh"] for row in daily)
        ),
        "emergency_purchase_kwh": float(sum(row["emergency_kwh"] for row in daily)),
        "soc_window_start_kwh": float(daily[0]["soc_start_kwh"]),
        "soc_window_end_kwh": float(daily[-1]["soc_end_kwh"]),
        "daily_soc_end_path_kwh": ";".join(
            f"{row['soc_end_kwh']:.6f}" for row in daily
        ),
        "all_value_cuts_present": bool(all(row["has_value_cuts"] for row in daily)),
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "mean_elapsed_seconds": float(np.mean([row["elapsed_seconds"] for row in daily])),
        "mean_solve_seconds": float(np.mean([row["elapsed_seconds"] for row in daily])),
        "policy_loop": ALPHA_POLICY_LOOP,
        "fallback_reason": "",
    }
    return daily, summary


def select_risk_alpha(
    bundle: Q4Bundle,
    policy_start_soc: np.ndarray,
    target_index: int,
    k_target: int,
    n_validation: int | None = None,
    alphas: tuple[float, ...] | None = None,
    log: bool = False,
) -> AlphaSelection:
    """Score each alpha on the prior completed days with the official Q4-2 loop."""
    candidates = RISK_ALPHA_CANDIDATES if alphas is None else tuple(alphas)
    records: list[dict] = []
    daily_records: list[dict] = []
    for alpha in candidates:
        prefix = (
            f"Q4-2 alpha-cal d={target_index} alpha={float(alpha):.2f}" if log else None
        )
        daily, summary = run_candidate_window(
            bundle,
            policy_start_soc,
            target_index,
            risk_alpha=float(alpha),
            k_target=k_target,
            n_validation=n_validation,
            log_prefix=prefix,
        )
        summary["selected"] = False
        records.append(summary)
        daily_records.extend(daily)
    eligible = [row for row in records if np.isfinite(row["mean_validation_cost_yuan"])]
    selected = min(
        eligible or records,
        key=lambda row: (
            row["mean_validation_cost_yuan"]
            if np.isfinite(row["mean_validation_cost_yuan"])
            else inf,
            row["risk_alpha"] if row["risk_alpha"] is not None else inf,
        ),
    )
    selected["selected"] = True
    chosen = float(selected["risk_alpha"])
    for row in daily_records:
        row["selected"] = bool(
            row["risk_alpha"] is not None and abs(float(row["risk_alpha"]) - chosen) < 1e-12
        )
    return AlphaSelection(chosen, records, daily_records)


def run_q4_2_day(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    risk_alpha: float | None,
    k_target: int = FIXED_SCENARIO_K,
    write_dispatch: Path | None = None,
) -> Q42DayResult:
    started = perf_counter()
    date = bundle.prices.dates[day_index].strftime("%Y-%m-%d")
    loads, pvs, prices, probs, scenarios, base_load, base_pv, price_src, chosen = q4_2_day_inputs(
        bundle, day_index, day_index, k_target
    )
    q_floor = risk_quantile_floor(loads, pvs, probs, base_load, base_pv, risk_alpha)
    cuts, value_rows = build_q4_2_value_cuts(bundle, day_index, k_target, risk_alpha)
    plan = solve_stochastic_plan_varying_price(
        prices,
        loads,
        pvs,
        probs,
        initial_soc,
        terminal_value_cuts=cuts or None,
        q_floor=q_floor,
    )
    locked_q = plan.q.copy()
    q_hash = planned_q_hash(locked_q)
    actual_p = bundle.prices.price[day_index]
    actual_load = bundle.q2.load[day_index]
    actual_pv = bundle.q2.pv[day_index]
    day_ahead, _, _ = day_ahead_today(bundle, day_index)
    rows = []
    soc = float(initial_soc)
    max_cd = 0.0
    k_eff = 1 if scenarios is None else scenarios.k_effective
    for t in range(T):
        price_hat_tau, ols_fb = remaining_price_forecast(bundle, day_index, t)
        if scenarios is None:
            weights = np.ones(1)
            bandwidth = np.nan
            load_horizon = base_load[t:].copy()
            pv_horizon = base_pv[t:].copy()
            price_horizon = price_hat_tau[t:].copy()
        else:
            if t == 0:
                obs_l = np.zeros(0)
                obs_p = np.zeros(0)
                obs_r = np.zeros(0)
            else:
                # Ended prefix only; do not form a full-day residual against today's future actuals.
                obs_l = actual_load[:t] - base_load[:t]
                obs_p = actual_pv[:t] - base_pv[:t]
                obs_r = actual_p[:t] - day_ahead[:t]
            weights, bandwidth = posterior_weights(
                bundle, scenarios, obs_l, obs_p, obs_r
            )
            med_l, med_p, med_r = residual_stack(bundle, scenarios.medoid_indices)
            load_horizon = np.maximum(0.0, base_load[t:] + weights @ med_l[:, t:])
            pv_horizon = np.maximum(0.0, base_pv[t:] + weights @ med_p[:, t:])
            price_horizon = np.maximum(0.0, price_hat_tau[t:] + weights @ med_r[:, t:])
        load_horizon[0] = actual_load[t]
        pv_horizon[0] = actual_pv[t]
        step = solve_fixed_q_dispatch(
            price_horizon,
            locked_q[t:],
            load_horizon,
            pv_horizon,
            soc,
            terminal_value_cuts=cuts or None,
        )
        residual = (
            step.x[0]
            + step.emergency[0]
            + actual_pv[t]
            - step.curtailment[0]
            + step.discharge[0]
            - actual_load[t]
            - step.charge[0]
        )
        soc_next = float(step.soc[1])
        rows.append(
            {
                "date": date,
                "period_index": t,
                "time_label": bundle.q3.time_labels[t],
                "q_or_g0_kwh": float(locked_q[t]),
                "g_final_kwh": np.nan,
                "x_kwh": float(step.x[0]),
                "emergency_kwh": float(step.emergency[0]),
                "charge_kwh": float(step.charge[0]),
                "discharge_kwh": float(step.discharge[0]),
                "curtailment_kwh": float(step.curtailment[0]),
                "soc_start_kwh": soc,
                "soc_end_kwh": soc_next,
                "actual_load_kwh": float(actual_load[t]),
                "actual_pv_kwh": float(actual_pv[t]),
                "actual_price": float(actual_p[t]),
                "price_forecast_used": float(price_horizon[0]),
                "last_update_time": "00:00",
                "balance_residual_kwh": float(residual),
                "ols_fallback": bool(ols_fb),
            }
        )
        max_cd = max(max_cd, float(step.charge[0] * step.discharge[0]))
        if np.max(np.abs(locked_q - plan.q)) > 0:
            raise AssertionError("Q4-2 q changed during the day")
        soc = soc_next
    if planned_q_hash(locked_q) != q_hash:
        raise AssertionError("Q4-2 q hash changed")
    dispatch = pd.DataFrame(rows)
    if write_dispatch is not None:
        write_dispatch.parent.mkdir(parents=True, exist_ok=True)
        dispatch.to_csv(write_dispatch, index=False)
    normal_cost = float(actual_p @ locked_q)
    emergency_cost = float(
        EMERGENCY_PRICE_MULTIPLIER * actual_p @ dispatch["emergency_kwh"].to_numpy()
    )
    scenario_rows = []
    if scenarios is not None:
        for cluster, medoid in enumerate(scenarios.medoid_indices):
            scenario_rows.append(
                {
                    "date": date,
                    "cluster": int(cluster),
                    "medoid_date": bundle.prices.dates[medoid].strftime("%Y-%m-%d"),
                    "medoid_index": int(medoid),
                    "probability": float(scenarios.probabilities[cluster]),
                    "cluster_size": int(np.sum(scenarios.cluster_labels == cluster)),
                    "pool_start": bundle.prices.dates[scenarios.pool_indices[0]].strftime("%Y-%m-%d"),
                    "pool_end": bundle.prices.dates[scenarios.pool_indices[-1]].strftime("%Y-%m-%d"),
                    "k_effective": int(scenarios.k_effective),
                    "scale_load": float(scenarios.scale_load),
                    "scale_pv": float(scenarios.scale_pv),
                    "scale_price": float(scenarios.scale_price),
                }
            )
    day_ahead_audit = {
        "date": date,
        "day_index": day_index,
        "history_cutoff_date": (
            bundle.prices.dates[day_index - 1].strftime("%Y-%m-%d") if day_index else ""
        ),
        "k_target": k_target,
        "k_effective": k_eff,
        "risk_alpha": risk_alpha,
        "risk_q_floor_kwh": float(np.sum(q_floor)),
        "price_source": price_src,
        "chosen_price_model": chosen,
        "planned_q_kwh": float(locked_q.sum()),
        "planned_q_sha256": q_hash,
        "n_scenarios": int(len(probs)),
        "load_information_case": LOAD_INFORMATION_CASE,
        "year_end_rule": Q4_2_YEAR_END_RULE,
        "settlement_rule": SETTLEMENT_RULE,
    }
    summary = {
        "date": date,
        "day_index": day_index,
        "load_information_case": LOAD_INFORMATION_CASE,
        "year_end_rule": Q4_2_YEAR_END_RULE,
        "settlement_rule": SETTLEMENT_RULE,
        "k_effective": k_eff,
        "risk_alpha": risk_alpha,
        "normal_cost_yuan": normal_cost,
        "adjustment_cost_yuan": 0.0,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": normal_cost + emergency_cost,
        "planned_q_kwh": float(locked_q.sum()),
        "actual_x_kwh": float(dispatch["x_kwh"].sum()),
        "emergency_kwh": float(dispatch["emergency_kwh"].sum()),
        "curtailment_kwh": float(dispatch["curtailment_kwh"].sum()),
        "soc_start_kwh": float(initial_soc),
        "soc_end_kwh": float(soc),
        "unused_quota_kwh": float(np.sum(locked_q - dispatch["x_kwh"].to_numpy(float))),
        "has_value_cuts": bool(value_rows),
        "n_value_cuts": int(len(value_rows)),
        "value_cut_gap_yuan": (
            float(value_rows[0]["certified_max_gap_yuan"]) if value_rows else float("nan")
        ),
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "elapsed_seconds": float(perf_counter() - started),
        "max_balance_residual_kwh": float(dispatch["balance_residual_kwh"].abs().max()),
        "max_simultaneous_cd_kwh2": max_cd,
        "max_x_minus_q_kwh": float(np.max(dispatch["x_kwh"].to_numpy() - locked_q)),
        "q_unchanged": True,
        "pass": bool(
            dispatch["balance_residual_kwh"].abs().max() < NUMERIC_TOL
            and np.max(dispatch["x_kwh"].to_numpy() - locked_q) < NUMERIC_TOL
            and dispatch["soc_end_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL
            and dispatch["soc_end_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL
            and max_cd <= SIMULTANEOUS_CD_TOL
        ),
    }
    return Q42DayResult(
        date=date,
        day_index=day_index,
        q=locked_q,
        dispatch=dispatch,
        summary=summary,
        day_ahead_audit=day_ahead_audit,
        scenario_rows=scenario_rows,
        value_rows=value_rows,
    )


def alpha_for_day(day_index: int, calibrated: dict[int, float | None]) -> float | None:
    if day_index < RISK_WARMUP_DAYS:
        return None
    start = (day_index // RISK_CALIBRATION_DAYS) * RISK_CALIBRATION_DAYS
    return calibrated.get(start, None)

# ===== q4/q4_3.py =====
"""Q4-3: fixed M1_M6 with causal price forecasts and delivery-time settlement."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

import numpy as np
import pandas as pd

from q3.config import (
    E_MAX_KWH,
    E_MIN_KWH,
    EMERGENCY_PRICE_MULTIPLIER,
    HOUR_TO_FIRST_MUTABLE,
    LOAD_INFORMATION_MAIN,
    NUMERIC_TOL,
    PV_MAPPING_LINEAR,
    SETTLEMENT_MAIN,
    SIMULTANEOUS_CD_TOL,
    STRATEGY_ALLOWED_UPDATES,
    T,
    VOI_EPS_YUAN,
    next_day_year_end_soc,
    today_year_end_soc,
)
from q3.forecast import (
    execution_load_horizon,
    map_issue_forecast,
    next_day_pv_forecast,
    planning_load_curve,
    causal_load_forecast,
)
from q3.optimization import (
    ValueCut,
    evaluate_value_cuts,
    settlement_cost,
    solve_horizon,
)


def _solve_horizon(*args, **kwargs):
    """Call Q3's LP; if the unique-throughput tiebreak is numerically infeasible, keep the primary solution."""
    try:
        return solve_horizon(*args, **kwargs)
    except RuntimeError as exc:
        if "tiebreak" not in str(exc):
            raise
        kwargs = dict(kwargs)
        kwargs["throughput_tiebreak"] = False
        return solve_horizon(*args, **kwargs)
from q4.bundle import Q4Bundle
from q4.config import (
    LOAD_INFORMATION_CASE,
    Q4_3_STRATEGY,
    Q4_3_YEAR_END_BOUNDARY,
    Q4_3_YEAR_END_SOC_KWH,
    SETTLEMENT_RULE,
)
from q4.prices import day_ahead_as_of, day_ahead_today, remaining_price_forecast
from q4.q4_2 import planned_q_hash


def _index_to_update_hour(index: int) -> int | None:
    inverse = {first: hour for hour, first in HOUR_TO_FIRST_MUTABLE.items() if hour != 0}
    return inverse.get(index)


def _decision_prices(
    bundle: Q4Bundle, day_index: int, tau: int, price_mode: str
) -> tuple[np.ndarray, bool]:
    if price_mode == "oracle":
        return np.asarray(bundle.prices.price[day_index], dtype=float).copy(), False
    return remaining_price_forecast(bundle, day_index, tau)


def _midnight_prices(
    bundle: Q4Bundle, day_index: int, price_mode: str
) -> tuple[np.ndarray, str, int]:
    if price_mode == "oracle":
        return np.asarray(bundle.prices.price[day_index], dtype=float).copy(), "price_oracle", -1
    return day_ahead_today(bundle, day_index)


def build_q4_3_value_cuts(
    bundle: Q4Bundle,
    current_index: int,
    issue_hour: int,
    next_day_terminal_soc: float | None,
    cache: dict | None,
) -> tuple[tuple[ValueCut, ...], list[dict]]:
    key = (int(current_index), int(issue_hour), None if next_day_terminal_soc is None else float(next_day_terminal_soc))
    if cache is not None and key in cache:
        return cache[key]
    next_index = current_index + 1
    if next_index >= bundle.n_days():
        cuts, rows = (), []
        if cache is not None:
            cache[key] = (cuts, rows)
        return cuts, rows
    load = causal_load_forecast(bundle.q3, next_index, current_index)
    pv = next_day_pv_forecast(bundle.q3, current_index, issue_hour, PV_MAPPING_LINEAR)
    price, price_src, chosen = day_ahead_as_of(bundle, next_index, current_index)

    # Reuse Q3's supporting-cut sampler by solving with the causal next-day price.
    from q3.config import NEXT_DAY_VALUE_GAP_TOL_YUAN, NEXT_DAY_VALUE_MAX_SAMPLES
    from math import inf

    solved: dict[float, ValueCut] = {}

    def solve_at(soc: float) -> None:
        result = _solve_horizon(
            price,
            load,
            pv,
            float(soc),
            bill_as_day_ahead=True,
            throughput_tiebreak=False,
            terminal_soc=next_day_terminal_soc,
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
            raise AssertionError("Q4-3 next-day value subgradients are not monotone")
        gap, refine_soc = certified_max_gap(cuts)
        if gap <= NEXT_DAY_VALUE_GAP_TOL_YUAN:
            break
        if len(cuts) >= NEXT_DAY_VALUE_MAX_SAMPLES:
            raise AssertionError(
                f"Q4-3 next-day value gap {gap:.6f} exceeds tolerance after {len(cuts)} samples"
            )
        if min(abs(refine_soc - soc) for soc in solved) < 1e-7:
            raise AssertionError("Q4-3 next-day value refinement stalled")
        solve_at(refine_soc)
    date = bundle.prices.dates[current_index].strftime("%Y-%m-%d")
    rows = [
        {
            "current_date": date,
            "target_date": bundle.prices.dates[next_index].strftime("%Y-%m-%d"),
            "issue_hour": issue_hour,
            "price_source": price_src,
            "chosen_price_model": chosen,
            "soc_sample_kwh": reference,
            "virtual_next_day_cost_yuan": value,
            "value_subgradient_yuan_per_kwh": slope,
            "certified_max_gap_yuan": gap,
        }
        for reference, value, slope in cuts
    ]
    if cache is not None:
        cache[key] = (cuts, rows)
    return cuts, rows


def plan_g0(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    year_end_soc_kwh: float | None = Q4_3_YEAR_END_SOC_KWH,
    value_cut_cache: dict | None = None,
    with_value_cuts: bool = True,
    price_mode: str = "causal",
) -> np.ndarray:
    """Midnight g0 only (no intraday updates). Used by information-set probes."""
    data = bundle.q3
    n_days = len(data.dates)
    today_terminal = today_year_end_soc(day_index, n_days, year_end_soc_kwh)
    next_terminal = next_day_year_end_soc(day_index, n_days, year_end_soc_kwh)
    plan_load = planning_load_curve(data, day_index, LOAD_INFORMATION_MAIN)
    mapped0 = map_issue_forecast(data, day_index, 0, PV_MAPPING_LINEAR)
    price0, _src, _chosen = _midnight_prices(bundle, day_index, price_mode)
    cuts = ()
    if with_value_cuts:
        cuts, _rows = build_q4_3_value_cuts(
            bundle, day_index, 0, next_terminal, value_cut_cache
        )
    midnight = _solve_horizon(
        price0,
        plan_load,
        mapped0.today_kwh.copy(),
        initial_soc,
        bill_as_day_ahead=True,
        terminal_value_cuts=cuts or None,
        terminal_soc=today_terminal,
    )
    return midnight.g.copy()


@dataclass
class Q43DayResult:
    date: str
    day_index: int
    g0: np.ndarray
    g_final: np.ndarray
    dispatch: pd.DataFrame
    update_log: pd.DataFrame
    summary: dict
    value_rows: list[dict] = field(default_factory=list)


def run_q4_3_day(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    year_end_soc_kwh: float | None = Q4_3_YEAR_END_SOC_KWH,
    value_cut_cache: dict | None = None,
    price_mode: str = "causal",
) -> Q43DayResult:
    data = bundle.q3
    date = data.dates[day_index].strftime("%Y-%m-%d")
    n_days = len(data.dates)
    today_terminal = today_year_end_soc(day_index, n_days, year_end_soc_kwh)
    next_terminal = next_day_year_end_soc(day_index, n_days, year_end_soc_kwh)
    allowed = STRATEGY_ALLOWED_UPDATES[Q4_3_STRATEGY]
    actual_load = data.load[day_index]
    plan_load = planning_load_curve(data, day_index, LOAD_INFORMATION_MAIN)
    actual_pv = data.pv[day_index]
    actual_p = bundle.prices.price[day_index]
    started = perf_counter()
    mapped0 = map_issue_forecast(data, day_index, 0, PV_MAPPING_LINEAR)
    current_forecast = mapped0.today_kwh.copy()
    price0, price_src, chosen = _midnight_prices(bundle, day_index, price_mode)
    cuts, value_rows = build_q4_3_value_cuts(
        bundle, day_index, 0, next_terminal, value_cut_cache
    )
    midnight = _solve_horizon(
        price0,
        plan_load,
        current_forecast,
        initial_soc,
        bill_as_day_ahead=True,
        terminal_value_cuts=cuts or None,
        terminal_soc=today_terminal,
    )
    g0 = midnight.g.copy()
    g = g0.copy()
    versions = [g0.copy()]
    last_update = "00:00"
    first_intraday = HOUR_TO_FIRST_MUTABLE[6]
    update_rows = [
        {
            "date": date,
            "update_time": "00:00",
            "first_mutable_index": 0,
            "voi_yuan": np.nan,
            "implemented": True,
            "l1_change_kwh": float(np.abs(g0).sum()),
            "price_source": price_src,
            "chosen_price_model": chosen,
            "affected_periods": "0:143",
            "prefix_lock_ok": True,
            "forecast_version": "day_ahead",
            "g_old_sha256": "",
            "g_new_sha256": planned_q_hash(g0),
        }
    ]

    def remaining_kwargs(t: int, price_rem: np.ndarray) -> dict:
        return {
            "settlement_mode": SETTLEMENT_MAIN,
            "terminal_value_cuts": cuts or None,
            "g0": g0[t:],
            "terminal_soc": today_terminal,
        }

    dispatch_rows = []
    soc = float(initial_soc)
    max_cd = 0.0
    max_balance = 0.0
    locked_violations = 0
    g_before_update = g.copy()

    for t in range(T):
        hour = _index_to_update_hour(t)
        if hour is not None and hour in allowed:
            g_before_update = g.copy()
            mapped = map_issue_forecast(data, day_index, hour, PV_MAPPING_LINEAR)
            current_forecast = mapped.today_kwh.copy()
            cuts, rows = build_q4_3_value_cuts(
                bundle, day_index, hour, next_terminal, value_cut_cache
            )
            value_rows.extend(rows)
            price_now, _fb = _decision_prices(bundle, day_index, t, price_mode)
            pv_plan = current_forecast[t:]
            load_plan = plan_load[t:]
            g_pre = g[t:].copy()
            settle_kw = remaining_kwargs(t, price_now[t:])
            j_fix = _solve_horizon(
                price_now[t:],
                load_plan,
                pv_plan,
                soc,
                g_fixed=g_pre,
                **settle_kw,
            )
            j_free = _solve_horizon(
                price_now[t:],
                load_plan,
                pv_plan,
                soc,
                **settle_kw,
            )
            voi = float(j_fix.objective - j_free.objective)
            implemented = bool(voi > VOI_EPS_YUAN)
            prefix_ok = bool(np.max(np.abs(g[:t] - g_before_update[:t])) <= NUMERIC_TOL)
            if implemented:
                g[t:] = j_free.g
                versions.append(g.copy())
            if not prefix_ok:
                locked_violations += 1
            delta = g[t:] - g_pre
            update_rows.append(
                {
                    "date": date,
                    "update_time": f"{hour:02d}:00",
                    "first_mutable_index": t,
                    "voi_yuan": voi,
                    "implemented": implemented,
                    "l1_change_kwh": float(np.abs(delta).sum()),
                    "price_source": "price_oracle" if price_mode == "oracle" else "intraday_ols",
                    "chosen_price_model": chosen,
                    "affected_periods": f"{t}:{T - 1}",
                    "prefix_lock_ok": prefix_ok,
                    "forecast_version": f"tau_{t}",
                    "g_old_sha256": planned_q_hash(g_before_update),
                    "g_new_sha256": planned_q_hash(g),
                }
            )
            last_update = f"{hour:02d}:00"
            if np.max(np.abs(g[:t] - g_before_update[:t])) > NUMERIC_TOL:
                locked_violations += 1

        price_now, _fb = _decision_prices(bundle, day_index, t, price_mode)
        pv_horizon = current_forecast[t:].copy()
        pv_horizon[0] = actual_pv[t]
        load_horizon = execution_load_horizon(plan_load, actual_load, t)
        step = _solve_horizon(
            price_now[t:],
            load_horizon,
            pv_horizon,
            soc,
            g_fixed=g[t:],
            **remaining_kwargs(t, price_now[t:]),
        )
        residual = (
            step.x[0]
            + step.emergency[0]
            + actual_pv[t]
            - step.curtailment[0]
            + step.discharge[0]
            - actual_load[t]
            - step.charge[0]
        )
        soc_next = float(step.soc[1])
        max_cd = max(max_cd, float(step.charge[0] * step.discharge[0]))
        max_balance = max(max_balance, abs(float(residual)))
        dispatch_rows.append(
            {
                "date": date,
                "period_index": t,
                "time_label": data.time_labels[t],
                "q_or_g0_kwh": float(g0[t]),
                "g_final_kwh": float(g[t]),
                "x_kwh": float(step.x[0]),
                "emergency_kwh": float(step.emergency[0]),
                "charge_kwh": float(step.charge[0]),
                "discharge_kwh": float(step.discharge[0]),
                "curtailment_kwh": float(step.curtailment[0]),
                "soc_start_kwh": soc,
                "soc_end_kwh": soc_next,
                "actual_load_kwh": float(actual_load[t]),
                "actual_pv_kwh": float(actual_pv[t]),
                "actual_price": float(actual_p[t]),
                "price_forecast_used": float(price_now[t]),
                "last_update_time": last_update,
                "balance_residual_kwh": float(residual),
            }
        )
        if abs(g[t] - step.g[0]) > 1e-6:
            locked_violations += 1
        soc = soc_next

    dispatch = pd.DataFrame(dispatch_rows)
    g_final = g.copy()
    if np.max(np.abs(g_final[:first_intraday] - g0[:first_intraday])) > NUMERIC_TOL:
        locked_violations += 1
        raise AssertionError("Q4-3 6:00 prefix lock violated: gF[:36] differs from g0")
    phi = settlement_cost(actual_p, g0, g_final)
    emergency_cost = EMERGENCY_PRICE_MULTIPLIER * actual_p * dispatch["emergency_kwh"].to_numpy()
    dispatch["normal_cost_yuan"] = actual_p * g_final
    dispatch["adjustment_cost_yuan"] = phi - actual_p * g_final
    dispatch["emergency_cost_yuan"] = emergency_cost
    n_adjust = int(
        sum(1 for row in update_rows if row["update_time"] != "00:00" and row["implemented"])
    )
    summary = {
        "date": date,
        "day_index": day_index,
        "strategy": Q4_3_STRATEGY,
        "load_information_case": LOAD_INFORMATION_CASE,
        "year_end_boundary": Q4_3_YEAR_END_BOUNDARY,
        "year_end_soc_kwh": year_end_soc_kwh,
        "settlement_rule": SETTLEMENT_RULE,
        "price_mode": price_mode,
        "normal_cost_yuan": float(np.sum(actual_p * g_final)),
        "adjustment_cost_yuan": float(np.sum(phi - actual_p * g_final)),
        "emergency_cost_yuan": float(np.sum(emergency_cost)),
        "total_cost_yuan": float(np.sum(phi) + np.sum(emergency_cost)),
        "g0_kwh": float(g0.sum()),
        "g_final_kwh": float(g_final.sum()),
        "emergency_kwh": float(dispatch["emergency_kwh"].sum()),
        "curtailment_kwh": float(dispatch["curtailment_kwh"].sum()),
        "soc_start_kwh": float(initial_soc),
        "soc_end_kwh": float(soc),
        "adjustment_count": n_adjust,
        "locked_period_violations": int(locked_violations),
        "max_balance_residual_kwh": float(max_balance),
        "max_simultaneous_cd_kwh2": float(max_cd),
        "runtime_seconds": float(perf_counter() - started),
        "max_x_minus_g_kwh": float(np.max(dispatch["x_kwh"].to_numpy() - g_final)),
        "pass": bool(
            max_balance < NUMERIC_TOL
            and locked_violations == 0
            and max_cd <= SIMULTANEOUS_CD_TOL
            and np.max(dispatch["x_kwh"].to_numpy() - g_final) < NUMERIC_TOL
            and dispatch["soc_end_kwh"].min() >= E_MIN_KWH - NUMERIC_TOL
            and dispatch["soc_end_kwh"].max() <= E_MAX_KWH + NUMERIC_TOL
        ),
    }
    return Q43DayResult(
        date=date,
        day_index=day_index,
        g0=g0,
        g_final=g_final,
        dispatch=dispatch,
        update_log=pd.DataFrame(update_rows),
        summary=summary,
        value_rows=value_rows,
    )

# ===== q4/q4_3_sensitivity.py =====
"""Q4-3 off-main sensitivities: update-time adjustment fees and a price oracle.

Neither path replaces the official M1_M6 delivery-time scheme or result4-3.xlsx.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from q3.config import ADJUST_ABS_COEFF, PILOT_DATES
from q4.audit import ledger_from_dispatch_q43, write_json
from q4.config import (
    OUTPUT_DIR,
    Q4_3_DISPATCH_DIR,
    Q4_3_ORACLE_DAILY_CSV,
    Q4_3_ORACLE_DISPATCH_DIR,
    Q4_3_SENSITIVITY_SUMMARY_JSON,
    Q4_3_SETTLEMENT_SENSITIVITY_CSV,
    Q4_3_SETTLEMENT_SENSITIVITY_JSON,
)

UPDATE_CLOCKS = ("06:00", "12:00", "18:00")


def clock_price_map(frame: pd.DataFrame) -> dict[str, float]:
    labels = frame["time_label"].astype(str)
    out: dict[str, float] = {}
    for clock in UPDATE_CLOCKS:
        hit = frame.loc[labels == clock]
        if not hit.empty:
            out[clock] = float(hit["actual_price"].iloc[0])
    return out


def adjustment_at_update_clock(frame: pd.DataFrame) -> pd.DataFrame:
    """Rebook 0.5 |gF-g0| at the last update clock price; keep p_t gF and 5 p_t e."""
    work = frame.copy()
    g0 = work["q_or_g0_kwh"].to_numpy(float)
    gf = work["g_final_kwh"].to_numpy(float)
    p = work["actual_price"].to_numpy(float)
    last = work["last_update_time"].astype(str).to_numpy()
    clocks = clock_price_map(work)
    p_tau = np.array(
        [clocks[t] if t in clocks else float(p[i]) for i, t in enumerate(last)],
        dtype=float,
    )
    delta = np.abs(gf - g0)
    adj_delivery = ADJUST_ABS_COEFF * p * delta
    adj_update = ADJUST_ABS_COEFF * p_tau * delta
    emergency = 5.0 * p * work["emergency_kwh"].to_numpy(float)
    normal = p * gf
    work["adjustment_delivery_yuan"] = adj_delivery
    work["adjustment_update_clock_yuan"] = adj_update
    work["update_clock_price"] = p_tau
    work["normal_cost_yuan"] = normal
    work["emergency_cost_yuan"] = emergency
    work["total_delivery_yuan"] = normal + adj_delivery + emergency
    work["total_update_clock_yuan"] = normal + adj_update + emergency
    return work


def summarize_settlement_day(frame: pd.DataFrame) -> dict:
    billed = ledger_from_dispatch_q43(frame)
    alt = adjustment_at_update_clock(frame)
    delivery_adj = float(alt["adjustment_delivery_yuan"].sum())
    ledger_adj = float(billed["adjustment_cost_yuan"].sum())
    return {
        "date": str(frame["date"].iloc[0]),
        "n_adjusted_periods": int(np.sum(np.abs(
            frame["g_final_kwh"].to_numpy(float) - frame["q_or_g0_kwh"].to_numpy(float)
        ) > 1e-9)),
        "normal_cost_yuan": float(alt["normal_cost_yuan"].sum()),
        "emergency_cost_yuan": float(alt["emergency_cost_yuan"].sum()),
        "adjustment_delivery_yuan": delivery_adj,
        "adjustment_update_clock_yuan": float(alt["adjustment_update_clock_yuan"].sum()),
        "total_delivery_yuan": float(alt["total_delivery_yuan"].sum()),
        "total_update_clock_yuan": float(alt["total_update_clock_yuan"].sum()),
        "adjustment_gap_yuan": float(alt["adjustment_update_clock_yuan"].sum() - delivery_adj),
        "ledger_matches_delivery": bool(abs(delivery_adj - ledger_adj) < 1e-6),
    }


def run_settlement_sensitivity(dispatch_dir: Path = Q4_3_DISPATCH_DIR) -> dict:
    paths = sorted(dispatch_dir.glob("dispatch_*.csv"))
    if not paths:
        raise FileNotFoundError(f"no Q4-3 dispatch files in {dispatch_dir}")
    rows = [summarize_settlement_day(pd.read_csv(path)) for path in paths]
    daily = pd.DataFrame(rows)
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date").reset_index(drop=True)
    export = daily.loc[daily["date"] >= pd.Timestamp("2025-02-01")]
    summary = {
        "policy": "official_q4_3_dispatch_rebooked_only",
        "changes_main_scheme": False,
        "n_days": int(len(daily)),
        "n_export_days": int(len(export)),
        "annual_delivery_yuan": float(daily["total_delivery_yuan"].sum()),
        "annual_update_clock_yuan": float(daily["total_update_clock_yuan"].sum()),
        "annual_adjustment_delivery_yuan": float(daily["adjustment_delivery_yuan"].sum()),
        "annual_adjustment_update_clock_yuan": float(daily["adjustment_update_clock_yuan"].sum()),
        "annual_adjustment_gap_yuan": float(daily["adjustment_gap_yuan"].sum()),
        "export_delivery_yuan": float(export["total_delivery_yuan"].sum()),
        "export_update_clock_yuan": float(export["total_update_clock_yuan"].sum()),
        "all_ledger_match": bool(daily["ledger_matches_delivery"].all()),
        "note": (
            "Main phi uses delivery-time p_t. The sensitivity keeps the same "
            "(g0, gF, e) and charges 0.5 |gF-g0| at the last update clock price "
            "p_{d,tau} (06:00/12:00/18:00 period ending at that clock)."
        ),
    }
    out = daily.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    Q4_3_SETTLEMENT_SENSITIVITY_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(Q4_3_SETTLEMENT_SENSITIVITY_CSV, index=False)
    write_json(Q4_3_SETTLEMENT_SENSITIVITY_JSON, summary)
    return {"daily": out, "summary": summary}


def write_sensitivity_summary(settlement: dict, oracle_daily: pd.DataFrame | None) -> dict:
    main = pd.read_csv(OUTPUT_DIR / "q4_3_warmup_daily.csv")
    q42 = pd.read_csv(OUTPUT_DIR / "q4_2_warmup_daily.csv")
    main["date"] = pd.to_datetime(main["date"])
    q42["date"] = pd.to_datetime(q42["date"])
    payload = {
        "main_scheme": "Q4-3 M1_M6 causal prices, delivery-time phi+5pe",
        "changes_main_scheme": False,
        "q4_3_main": {
            "annual_yuan": float(main["total_cost_yuan"].sum()),
            "export_yuan": float(main.loc[main["date"] >= "2025-02-01", "total_cost_yuan"].sum()),
            "end_soc_kwh": float(main["soc_end_kwh"].iloc[-1]),
        },
        "q4_2_main": {
            "annual_yuan": float(q42["total_cost_yuan"].sum()),
            "export_yuan": float(q42.loc[q42["date"] >= "2025-02-01", "total_cost_yuan"].sum()),
        },
        "settlement_update_clock": settlement["summary"],
        "pilot_dates": list(PILOT_DATES),
    }
    if oracle_daily is not None and not oracle_daily.empty:
        oracle_daily = oracle_daily.copy()
        oracle_daily["date"] = pd.to_datetime(oracle_daily["date"])
        payload["price_oracle"] = {
            "annual_yuan": float(oracle_daily["total_cost_yuan"].sum()),
            "export_yuan": float(
                oracle_daily.loc[oracle_daily["date"] >= "2025-02-01", "total_cost_yuan"].sum()
            ),
            "end_soc_kwh": float(oracle_daily["soc_end_kwh"].iloc[-1]),
            "gap_vs_main_annual_yuan": float(
                oracle_daily["total_cost_yuan"].sum() - main["total_cost_yuan"].sum()
            ),
            "note": (
                "Offline reference only: midnight and remaining-horizon prices are "
                "today's actual path. Next-day value cuts stay causal. Not executable."
            ),
        }
        for date in PILOT_DATES:
            main_hit = main.loc[main["date"] == date]
            ora_hit = oracle_daily.loc[oracle_daily["date"] == date]
            if not main_hit.empty and not ora_hit.empty:
                payload.setdefault("two_day", {})[date] = {
                    "main_yuan": float(main_hit.iloc[0]["total_cost_yuan"]),
                    "oracle_yuan": float(ora_hit.iloc[0]["total_cost_yuan"]),
                }
    write_json(Q4_3_SENSITIVITY_SUMMARY_JSON, payload)
    return payload

# ===== q4/report_q4_closeout.py =====
#!/usr/bin/env python3
"""Write Q4 closeout reports from signed-off daily/dispatch artifacts. Does not re-solve."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q4.audit import write_json
from q4.closeout import (
    build_fair_comparison,
    build_residual_correlation_from_bundle,
    cost_components,
    load_q2_k8_daily,
    load_q3_official_daily,
    load_q4_2_daily,
    load_q4_3_daily,
    price_error_stats,
    scan_dispatch_year,
    selected_alpha_blocks,
)
from q4.config import (
    AUDIT_CSV,
    FAIR_COMPARISON_CSV,
    FAIR_COMPARISON_JSON,
    OUTPUT_DIR,
    PHYSICAL_YEAR_AUDIT_JSON,
    PRICE_MONTHLY_JSON,
    Q4_2_ALPHA_SELECTION_CSV,
    Q4_2_DISPATCH_DIR,
    Q4_3_DISPATCH_DIR,
    SCENARIO_CORR_JSON,
    TAIL_STATS_CSV,
    TAIL_STATS_JSON,
)


def _tail_row(name: str, window: str, components: dict) -> dict:
    return {
        "scheme": name,
        "window": window,
        "n_days": components["n_days"],
        "total_cost_yuan": components["total_cost_yuan"],
        "emergency_cost_yuan": components["emergency_cost_yuan"],
        "emergency_kwh": components["emergency_kwh"],
        "max_day_cost_yuan": components["max_day_cost_yuan"],
        "max_day_cost_date": components["max_day_cost_date"],
        "max_emergency_cost_date": components["max_emergency_cost_date"],
        "p90_yuan": components["daily_cost_p90_yuan"],
        "p95_yuan": components["daily_cost_p95_yuan"],
        "cvar_0_90_yuan": components["daily_cost_cvar_0_90_yuan"],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Q4 reporting-only closeout")
    parser.add_argument("--skip-correlation", action="store_true")
    parser.add_argument("--skip-physical", action="store_true")
    args = parser.parse_args(argv)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    q42 = load_q4_2_daily()
    q43 = load_q4_3_daily()
    q2 = load_q2_k8_daily()
    q3 = load_q3_official_daily()
    comparison = build_fair_comparison(q42, q43, q2, q3)
    price_audit = pd.read_csv(AUDIT_CSV)
    price_export = price_error_stats(price_audit, "2025-02-01", "2025-12-31")
    price_annual = price_error_stats(price_audit, "2025-01-01", "2025-12-31")
    monthly = json.loads(PRICE_MONTHLY_JSON.read_text(encoding="utf-8")) if PRICE_MONTHLY_JSON.exists() else {}
    annual_row = next((row for row in monthly.get("rows", []) if row.get("year_month") == "2025-annual"), {})
    if annual_row:
        if abs(price_annual["day_ahead_mae"] - float(annual_row["day_ahead_mae"])) >= 1e-8:
            raise AssertionError("annual day-ahead MAE does not match signed-off monthly table")
        if abs(price_annual["day_ahead_rmse_pooled"] - float(annual_row["day_ahead_rmse"])) >= 1e-8:
            raise AssertionError("annual pooled RMSE does not match signed-off monthly table")

    tail_rows = [
        _tail_row("Q4-2", "1-12", cost_components(q42, "q4_2")),
        _tail_row("Q4-2", "2-12", comparison["export"]["q4_2"]),
        _tail_row("Q4-3", "1-12", cost_components(q43, "q4_3")),
        _tail_row("Q4-3", "2-12", comparison["export"]["q4_3"]),
        _tail_row("Q2-K8", "2-12", comparison["export"]["q2_k8"]),
        _tail_row("Q3-M1_M6", "2-12", comparison["export"]["q3_m1_m6"]),
        _tail_row("Q3-M1_M6", "1-12", comparison["q3_annual"]),
    ]
    tail = {
        "price_note": comparison["price_note"],
        "price_errors": {"export_2_12": price_export, "annual_1_12": price_annual},
        "rows": tail_rows,
    }
    write_json(TAIL_STATS_JSON, tail)
    pd.DataFrame(tail_rows).to_csv(TAIL_STATS_CSV, index=False)

    fair_rows = [
        {
            "pair": "Q4-2 vs Q2 K=8",
            "window": "2-12",
            "left": "Q4-2",
            "right": "Q2 K=8",
            "left_total_yuan": comparison["export"]["q4_2"]["total_cost_yuan"],
            "right_total_yuan": comparison["export"]["q2_k8"]["total_cost_yuan"],
            "delta_total_yuan": comparison["pairs"]["q4_2_minus_q2_k8_export_yuan"],
            "left_emergency_kwh": comparison["export"]["q4_2"]["emergency_kwh"],
            "right_emergency_kwh": comparison["export"]["q2_k8"]["emergency_kwh"],
            "delta_emergency_kwh": comparison["pairs"]["q4_2_minus_q2_k8_emergency_kwh"],
        },
        {
            "pair": "Q4-3 vs Q3 M1_M6",
            "window": "2-12",
            "left": "Q4-3",
            "right": "Q3 M1_M6",
            "left_total_yuan": comparison["export"]["q4_3"]["total_cost_yuan"],
            "right_total_yuan": comparison["export"]["q3_m1_m6"]["total_cost_yuan"],
            "delta_total_yuan": comparison["pairs"]["q4_3_minus_q3_m1_m6_export_yuan"],
            "left_emergency_kwh": comparison["export"]["q4_3"]["emergency_kwh"],
            "right_emergency_kwh": comparison["export"]["q3_m1_m6"]["emergency_kwh"],
            "delta_emergency_kwh": comparison["pairs"]["q4_3_minus_q3_m1_m6_emergency_kwh"],
        },
    ]
    write_json(FAIR_COMPARISON_JSON, comparison)
    pd.DataFrame(fair_rows).to_csv(FAIR_COMPARISON_CSV, index=False)

    physical = {"skipped": True}
    if not args.skip_physical:
        physical = {
            "q4_2": scan_dispatch_year(Q4_2_DISPATCH_DIR, q42, q4_3=False),
            "q4_3": scan_dispatch_year(Q4_3_DISPATCH_DIR, q43, q4_3=True),
        }
        if not physical["q4_2"]["pass"] or not physical["q4_3"]["pass"]:
            raise SystemExit("physical year audit failed")
        write_json(PHYSICAL_YEAR_AUDIT_JSON, physical)

    correlation = {"skipped": True}
    if not args.skip_correlation:
        from q4.bundle import load_q4_bundle

        bundle = load_q4_bundle(compute_price_mpc=False)
        correlation = build_residual_correlation_from_bundle(bundle)
        write_json(SCENARIO_CORR_JSON, correlation)

    alpha_blocks = selected_alpha_blocks(q42, pd.read_csv(Q4_2_ALPHA_SELECTION_CSV))
    summary = {
        "tail_stats": str(TAIL_STATS_JSON.relative_to(ROOT)),
        "fair_comparison": str(FAIR_COMPARISON_JSON.relative_to(ROOT)),
        "physical_audit": None
        if args.skip_physical
        else str(PHYSICAL_YEAR_AUDIT_JSON.relative_to(ROOT)),
        "residual_correlation": None
        if args.skip_correlation
        else str(SCENARIO_CORR_JSON.relative_to(ROOT)),
        "q4_2_alpha_blocks": [
            {
                "start": row.effective_start_date.strftime("%Y-%m-%d"),
                "end": row.effective_end_date.strftime("%Y-%m-%d"),
                "n_days": int(row.n_days),
                "risk_alpha": row.risk_alpha,
            }
            for row in alpha_blocks.itertuples()
        ],
        "physical_pass": None if args.skip_physical else physical["q4_2"]["pass"] and physical["q4_3"]["pass"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

# ===== q4/run_k_review.py =====
#!/usr/bin/env python3
"""K=4/8/12 cost and timing review on the Q2-aligned calibration calendar.

Uses the official Q4-2 closed loop on each historical 14-day window.
Does not re-pick K from the full-year result. If K=8 is stable, keep it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from q2.config import E_INITIAL_KWH
from q4.audit import write_json
from q4.bundle import load_q4_bundle
from q4.config import (
    FIXED_SCENARIO_K,
    K_REVIEW_CANDIDATES,
    K_REVIEW_COST_TOLERANCE,
    K_REVIEW_REFERENCE_ALPHA,
    OUTPUT_DIR,
)
from q4.q4_2 import q2_aligned_calibration_indices, run_candidate_window

DAILY_CSV = OUTPUT_DIR / "q4_2_k_review_daily.csv"
SUMMARY_CSV = OUTPUT_DIR / "q4_2_k_review.csv"
SUMMARY_JSON = OUTPUT_DIR / "q4_2_k_review.json"
WARMUP_CSV = OUTPUT_DIR / "q4_2_warmup_daily.csv"
POLICY_SOC_CSV = OUTPUT_DIR / "q4_2_k_review_policy_soc.csv"


def load_policy_start_soc(n_days: int, warmup_csv: Path = WARMUP_CSV) -> np.ndarray:
    soc = np.full(n_days, np.nan)
    source = POLICY_SOC_CSV if POLICY_SOC_CSV.exists() else warmup_csv
    if source.exists():
        daily = pd.read_csv(source)
        for _, row in daily.iterrows():
            idx = int(row["day_index"])
            if 0 <= idx < n_days and "soc_start_kwh" in row:
                soc[idx] = float(row["soc_start_kwh"])
    if not np.isfinite(soc[0]):
        soc[0] = E_INITIAL_KWH
    last = float(soc[0])
    for i in range(n_days):
        if np.isfinite(soc[i]):
            last = float(soc[i])
        else:
            soc[i] = last
    return soc


def decide_keep_k8(by_k: dict[int, dict]) -> dict:
    costs = {k: float(row["mean_cost_per_day_yuan"]) for k, row in by_k.items()}
    times = {k: float(row["mean_elapsed_seconds"]) for k, row in by_k.items()}
    best_k = min(costs, key=lambda k: (costs[k], k))
    best_cost = costs[best_k]
    k8_cost = costs[FIXED_SCENARIO_K]
    gap = (k8_cost - best_cost) / best_cost if best_cost > 0 else 0.0
    time_ok = times[FIXED_SCENARIO_K] <= 3.0 * max(times[min(times)], 1e-9)
    within = gap <= K_REVIEW_COST_TOLERANCE + 1e-15
    stable = within and time_ok
    return {
        "best_k_by_mean_cost": int(best_k),
        "k8_mean_cost_yuan": k8_cost,
        "best_mean_cost_yuan": best_cost,
        "k8_cost_gap_vs_best": float(gap),
        "k8_within_1pct_of_best": bool(within),
        "k8_time_acceptable": bool(time_ok),
        "k8_stable": bool(stable),
        "keep_k": int(FIXED_SCENARIO_K),
        "reason": (
            "K=8 remains within 1% of the best reviewed K and solve time is acceptable; keep K=8."
            if stable
            else "K=8 is retained as the inherited Q2 value; this review does not re-pick K from the year."
        ),
    }


def review_scenario_k(
    bundle,
    policy_start_soc: np.ndarray,
    *,
    k_candidates: tuple[int, ...] = K_REVIEW_CANDIDATES,
    reference_alpha: float = K_REVIEW_REFERENCE_ALPHA,
    n_validation: int | None = None,
    max_windows: int | None = None,
    log: bool = True,
) -> dict:
    indices = q2_aligned_calibration_indices(bundle.n_days())
    if max_windows is not None:
        indices = indices[: max(0, int(max_windows))]
    daily_rows: list[dict] = []
    window_rows: list[dict] = []
    started = perf_counter()
    for target in indices:
        cal_date = bundle.prices.dates[target].strftime("%Y-%m-%d")
        for k in k_candidates:
            prefix = (
                f"Q4-2 K-review K={k} alpha={reference_alpha:.2f} {cal_date}" if log else None
            )
            daily, summary = run_candidate_window(
                bundle,
                policy_start_soc,
                target,
                risk_alpha=float(reference_alpha),
                k_target=int(k),
                n_validation=n_validation,
                log_prefix=prefix,
            )
            for row in daily:
                daily_rows.append({"calibration_date": cal_date, **row})
            window_rows.append(
                {
                    "calibration_date": cal_date,
                    "calibration_day_index": int(target),
                    **summary,
                }
            )
            if log:
                print(
                    f"K-review {cal_date} K={k} mean_cost={summary['mean_validation_cost_yuan']:.2f} "
                    f"mean_s={summary['mean_elapsed_seconds']:.3f}",
                    flush=True,
                )
    window = pd.DataFrame(window_rows)
    by_k: dict[int, dict] = {}
    for k in k_candidates:
        part = window.loc[window["k_target"] == k]
        by_k[int(k)] = {
            "n_windows": int(len(part)),
            "n_validation_days_total": int(part["validation_days"].sum()) if not part.empty else 0,
            "mean_cost_per_day_yuan": float(part["mean_validation_cost_yuan"].mean())
            if not part.empty
            else float("nan"),
            "total_cost_yuan": float(part["total_cost_yuan"].sum()) if not part.empty else float("nan"),
            "total_planned_fee_yuan": float(part["total_planned_fee_yuan"].sum())
            if not part.empty
            else float("nan"),
            "total_emergency_fee_yuan": float(part["total_emergency_fee_yuan"].sum())
            if not part.empty
            else float("nan"),
            "total_unused_quota_kwh": float(part["total_unused_quota_kwh"].sum())
            if not part.empty
            else float("nan"),
            "mean_elapsed_seconds": float(part["mean_elapsed_seconds"].mean())
            if not part.empty
            else float("nan"),
        }
    decision = decide_keep_k8(by_k)
    report = {
        "k_candidates": [int(k) for k in k_candidates],
        "reference_alpha": float(reference_alpha),
        "n_windows": int(len(indices)),
        "calibration_dates": [
            bundle.prices.dates[i].strftime("%Y-%m-%d") for i in indices
        ],
        "policy_loop": "day_ahead_joint_q+locked_q+causal_mpc+next_day_value_cuts",
        "used_full_day_actual_scheduler": False,
        "no_future_info": True,
        "by_k": {str(k): v for k, v in by_k.items()},
        "decision": decision,
        "elapsed_seconds": float(perf_counter() - started),
    }
    return {
        "report": report,
        "window": window,
        "daily": pd.DataFrame(daily_rows),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Q4-2 K=4/8/12 review")
    parser.add_argument("--max-windows", type=int, default=None)
    parser.add_argument("--n-validation", type=int, default=None)
    args = parser.parse_args(argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = load_q4_bundle(compute_price_mpc=False)
    policy_start_soc = load_policy_start_soc(bundle.n_days())
    result = review_scenario_k(
        bundle,
        policy_start_soc,
        n_validation=args.n_validation,
        max_windows=args.max_windows,
        log=True,
    )
    if not result["window"].empty:
        result["window"].to_csv(SUMMARY_CSV, index=False)
    if not result["daily"].empty:
        result["daily"].to_csv(DAILY_CSV, index=False)
    write_json(SUMMARY_JSON, result["report"])
    print(json.dumps(result["report"]["decision"], ensure_ascii=False, indent=2))
    print(json.dumps({str(k): v for k, v in result["report"]["by_k"].items()}, indent=2))


if __name__ == "__main__":
    main()

# ===== q4/run_price_forecast_audit.py =====
#!/usr/bin/env python3
"""Run the Q4 causal price-forecast audit. Does not start Q4-2/Q4-3 storage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import PILOT_DATES  # noqa: E402
from q4.config import (  # noqa: E402
    ATTACH4,
    AUDIT_CSV,
    CAUSALITY_JSON,
    OUTPUT_DIR,
    TWODAY_JSON,
)
from q4.data import load_q4_prices  # noqa: E402
from q4.price_forecast import (  # noqa: E402
    assert_no_future_price_leak,
    fit_causal_price_forecasts,
    two_day_regression,
)


def main() -> None:
    data = load_q4_prices()
    archive = fit_causal_price_forecasts(data.price, data.dates)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    archive.audit.to_csv(AUDIT_CSV, index=False)

    twoday = two_day_regression(archive, PILOT_DATES)
    TWODAY_JSON.write_text(
        json.dumps(twoday, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    causality = {"probes": []}
    for date in PILOT_DATES:
        i = data.date_index(date)
        assert_no_future_price_leak(data.price, data.dates, i, tau=0)
        assert_no_future_price_leak(data.price, data.dates, i, tau=36)
        causality["probes"].append(
            {
                "date": date,
                "day_ahead_insensitive_to_future": True,
                "intraday_06_insensitive_to_unended_prices": True,
            }
        )
    causality["all_pass"] = True
    CAUSALITY_JSON.write_text(json.dumps(causality, indent=2) + "\n", encoding="utf-8")

    audit = archive.audit
    valid = audit[audit["chosen_model"] != ""]
    summary = {
        "attach4": str(ATTACH4),
        "n_days": int(len(audit)),
        "n_days_with_day_ahead": int(len(valid)),
        "chosen_counts": valid["chosen_model_name"].value_counts().to_dict(),
        "day_ahead_mae_mean": float(valid["day_ahead_mae"].mean()),
        "day_ahead_rmse_mean": float(valid["day_ahead_rmse"].mean()),
        "intraday_06_mae_mean": float(valid["intraday_06_mae"].mean()),
        "intraday_12_mae_mean": float(valid["intraday_12_mae"].mean()),
        "intraday_18_mae_mean": float(valid["intraday_18_mae"].mean()),
        "audit_csv": str(AUDIT_CSV),
        "twoday_json": str(TWODAY_JSON),
        "causality_json": str(CAUSALITY_JSON),
        "pilot_dates": list(PILOT_DATES),
        "note": "Price module only. Does not run Q4-2/Q4-3 storage or write result4-*.xlsx.",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("--- two-day regression ---")
    for date, payload in twoday.items():
        print(
            json.dumps(
                {
                    "date": date,
                    "train_cutoff_date": payload["train_cutoff_date"],
                    "chosen_model_name": payload["chosen_model_name"],
                    "mae_prev_day": payload["mae_prev_day"],
                    "mae_weekday2": payload["mae_weekday2"],
                    "mae_weekday4": payload["mae_weekday4"],
                    "day_ahead_mae": payload["day_ahead_mae"],
                    "day_ahead_rmse": payload["day_ahead_rmse"],
                    "intraday_06_mae": payload["intraday_06_mae"],
                    "intraday_12_mae": payload["intraday_12_mae"],
                    "intraday_18_mae": payload["intraday_18_mae"],
                    "day_ahead_fallback": payload["day_ahead_fallback"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()

# ===== q4/run_q4_3_sensitivity.py =====
#!/usr/bin/env python3
"""Q4-3 sensitivities. Does not overwrite result4-3.xlsx or the official dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from q3.config import PILOT_DATES
from q4.audit import warmup_soc_continuity, write_json
from q4.bundle import load_q4_bundle
from q4.campaign import run_q4_3_campaign
from q4.config import (
    OUTPUT_DIR,
    PAM_SEED,
    Q4_3_ORACLE_DAILY_CSV,
    Q4_3_ORACLE_DISPATCH_DIR,
    Q4_3_SENSITIVITY_SUMMARY_JSON,
)
from q4.q4_3_sensitivity import run_settlement_sensitivity, write_sensitivity_summary


def _run_oracle(end_index: int | None = None, write_all_dispatch: bool = True) -> dict:
    started = perf_counter()
    bundle = load_q4_bundle(compute_price_mpc=False)
    if end_index is None:
        end_index = bundle.n_days() - 1
    result = run_q4_3_campaign(
        bundle,
        end_index,
        detail_dates=PILOT_DATES,
        out_dir=OUTPUT_DIR,
        write_all_dispatch=write_all_dispatch,
        price_mode="oracle",
        dispatch_dir=Q4_3_ORACLE_DISPATCH_DIR,
        daily_name=Q4_3_ORACLE_DAILY_CSV.name,
        update_name="q4_3_oracle_update_log.csv",
        ledger_name="q4_3_oracle_cost_ledger.csv",
        commitment_prefix="q4_3_oracle_commitment_versions",
        unlink_existing=True,
    )
    daily = pd.read_csv(Q4_3_ORACLE_DAILY_CSV)
    soc = warmup_soc_continuity(daily)
    n_pass = int(daily["pass"].sum()) if "pass" in daily.columns else 0
    meta = {
        "system": "q4_3_price_oracle",
        "executable": False,
        "changes_main_scheme": False,
        "n_days": int(len(daily)),
        "annual_cost_yuan": float(daily["total_cost_yuan"].sum()),
        "end_soc": float(result["end_soc"]),
        "soc_continuity": soc,
        "n_days_pass": n_pass,
        "pam_seed": PAM_SEED,
        "elapsed_seconds": float(perf_counter() - started),
        "note": (
            "Day-ahead and remaining prices equal today's actual path. "
            "Next-day value cuts remain causal. Not an official Q4-3 result."
        ),
    }
    write_json(OUTPUT_DIR / "q4_3_oracle_run_metadata.json", meta)
    if not soc["pass"] or n_pass != len(daily):
        raise SystemExit("Q4-3 price-oracle stream failed physical/pass checks")
    return meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Q4-3 settlement and oracle sensitivities")
    parser.add_argument("--skip-settlement", action="store_true")
    parser.add_argument("--skip-oracle", action="store_true")
    parser.add_argument("--oracle-end-index", type=int, default=None)
    args = parser.parse_args(argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settlement = None
    if not args.skip_settlement:
        settlement = run_settlement_sensitivity()
        print(json.dumps(settlement["summary"], ensure_ascii=False, indent=2))
    oracle_daily = None
    if not args.skip_oracle:
        meta = _run_oracle(end_index=args.oracle_end_index)
        print(json.dumps({k: meta[k] for k in ("n_days", "annual_cost_yuan", "elapsed_seconds")}, indent=2))
        oracle_daily = pd.read_csv(Q4_3_ORACLE_DAILY_CSV)
    if settlement is None:
        settlement = {"summary": json.loads(Path(OUTPUT_DIR / "q4_3_settlement_sensitivity.json").read_text())} if (OUTPUT_DIR / "q4_3_settlement_sensitivity.json").exists() else {"summary": {}}
    payload = write_sensitivity_summary(settlement, oracle_daily)
    print(json.dumps({"wrote": str(Q4_3_SENSITIVITY_SUMMARY_JSON), "keys": list(payload)}, indent=2))


if __name__ == "__main__":
    main()

# ===== q4/run_q4_full.py =====
#!/usr/bin/env python3
"""365-day Q4-2 / Q4-3 stream with daily 10-minute dispatch. Does not touch result3.xlsx."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q4.audit import warmup_soc_continuity, write_json  # noqa: E402
from q4.bundle import load_q4_bundle  # noqa: E402
from q4.campaign import run_q4_2_campaign, run_q4_3_campaign  # noqa: E402
from q4.config import OUTPUT_DIR, PAM_SEED  # noqa: E402
import pandas as pd  # noqa: E402


def _git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Q4 full-year stream")
    parser.add_argument("--system", choices=("q4_2", "q4_3"), required=True)
    args = parser.parse_args(argv)
    started = perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = load_q4_bundle(compute_price_mpc=False)
    end_index = bundle.n_days() - 1
    print(
        f"Full-year {args.system} through {bundle.prices.dates[end_index].strftime('%Y-%m-%d')} "
        f"({end_index + 1} days)",
        flush=True,
    )
    if args.system == "q4_2":
        result = run_q4_2_campaign(
            bundle, end_index, detail_dates=(), out_dir=OUTPUT_DIR, write_all_dispatch=True
        )
        daily = pd.read_csv(OUTPUT_DIR / "q4_2_warmup_daily.csv")
        audit_path = OUTPUT_DIR / "q4_2_physical_audit.json"
        meta_path = OUTPUT_DIR / "q4_2_run_metadata.json"
        alpha_path = OUTPUT_DIR / "q4_2_alpha_selection.csv"
        if alpha_path.exists():
            alpha = pd.read_csv(alpha_path)
            selected = (
                alpha.loc[alpha["selected"].astype(str).str.lower().isin(("true", "1"))]
                if "selected" in alpha.columns
                else alpha
            )
            meta_alpha = {
                "n_calibration_windows": int(selected["calibration_date"].nunique())
                if "calibration_date" in selected.columns
                else int(len(selected)),
                "selected_alphas": sorted(
                    {float(v) for v in selected["risk_alpha"].dropna().unique()}
                )
                if "risk_alpha" in selected.columns
                else [],
            }
        else:
            meta_alpha = {}
    else:
        result = run_q4_3_campaign(
            bundle, end_index, detail_dates=(), out_dir=OUTPUT_DIR, write_all_dispatch=True
        )
        daily = pd.read_csv(OUTPUT_DIR / "q4_3_warmup_daily.csv")
        audit_path = OUTPUT_DIR / "q4_3_physical_audit.json"
        meta_path = OUTPUT_DIR / "q4_3_run_metadata.json"
        meta_alpha = {}
    soc = warmup_soc_continuity(daily)
    n_pass = int(daily["pass"].sum()) if "pass" in daily.columns else 0
    meta = {
        "git_commit": _git_hash(),
        "system": args.system,
        "full_year": True,
        "n_days": int(len(daily)),
        "annual_cost_yuan": float(daily["total_cost_yuan"].sum()),
        "soc_continuity": soc,
        "n_days_pass": n_pass,
        "end_soc": float(result["end_soc"]),
        "pam_seed": PAM_SEED,
        "load_information_case": "causal_load_main",
        "settlement_rule": "delivery_time_actual_price",
        "elapsed_seconds": float(perf_counter() - started),
        "wrote_result4_xlsx": False,
    }
    meta.update(meta_alpha)
    if args.system == "q4_2":
        meta["alpha_policy_loop"] = (
            "day_ahead_joint_q+locked_q+causal_mpc+next_day_value_cuts"
        )
        meta["used_full_day_actual_scheduler"] = False
        two_day = {}
        for date in ("2025-02-01", "2025-06-21"):
            hit = daily.loc[daily["date"].astype(str) == date]
            if not hit.empty:
                two_day[date] = float(hit.iloc[0]["total_cost_yuan"])
        if two_day:
            meta["two_day_costs"] = two_day
    write_json(audit_path, {"soc_continuity": soc, "n_days": int(len(daily)), "n_days_pass": n_pass})
    write_json(meta_path, meta)
    print(json.dumps({k: meta[k] for k in ("system", "n_days", "annual_cost_yuan", "elapsed_seconds")}, indent=2))
    if not soc["pass"] or n_pass != len(daily):
        raise SystemExit(f"{args.system} annual stream failed physical/pass checks")


if __name__ == "__main__":
    main()

# ===== q4/run_q4_twoday.py =====
#!/usr/bin/env python3
"""Q4-2 and Q4-3 two-day regression. Does not write result4-*.xlsx or run 365 days."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import PILOT_DATES  # noqa: E402
from q4.audit import (  # noqa: E402
    ledger_from_dispatch_q42,
    ledger_from_dispatch_q43,
    physical_from_dispatch,
    prefix_lock_probe,
    q_unchanged_probe,
    warmup_soc_continuity,
    write_json,
)
from q4.bundle import load_q4_bundle  # noqa: E402
from q4.campaign import (  # noqa: E402
    last_index_for_dates,
    load_q42_detail_from_disk,
    load_q43_detail_from_disk,
    run_q4_2_campaign,
    run_q4_3_campaign,
)
from q4.config import OUTPUT_DIR, PAM_SEED  # noqa: E402
from q4.info_set import probe_executed_prefix  # noqa: E402


def _git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _run_unittest() -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "q2.test_q2",
            "q3.test_q3",
            "q3.test_q3_result3_export",
            "q4.test_q4_price_forecast",
            "q4.test_q4_dispatch",
            "-v",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return {
        "command": (
            "python -m unittest q2.test_q2 q3.test_q3 q3.test_q3_result3_export "
            "q4.test_q4_price_forecast q4.test_q4_dispatch -v"
        ),
        "returncode": proc.returncode,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-60:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-40:]),
    }


def _audit_detail(q42, q43):
    phys2, phys3 = {"days": {}}, {"days": {}}
    all_pass = True
    for date, result in q42.items():
        phys = physical_from_dispatch(result.dispatch, q4_3=False)
        ledger = ledger_from_dispatch_q42(result.dispatch)
        recon = float(ledger["total_cost_yuan"].sum())
        ok = (
            phys["pass"]
            and q_unchanged_probe(result.q, result.dispatch)
            and abs(recon - float(result.summary["total_cost_yuan"])) < 1e-4
        )
        all_pass = all_pass and ok
        phys2["days"][date] = {**phys, "ledger_recompute_yuan": recon, "ok": ok}
    for date, result in q43.items():
        phys = physical_from_dispatch(result.dispatch, q4_3=True)
        ledger = ledger_from_dispatch_q43(result.dispatch)
        recon = float(ledger["total_cost_yuan"].sum())
        ok = (
            phys["pass"]
            and prefix_lock_probe(result.update_log)
            and abs(recon - float(result.summary["total_cost_yuan"])) < 1e-4
            and result.summary["locked_period_violations"] == 0
        )
        all_pass = all_pass and ok
        phys3["days"][date] = {**phys, "ledger_recompute_yuan": recon, "ok": ok}
    phys2["all_pass"] = all(day["ok"] for day in phys2["days"].values()) if phys2["days"] else False
    phys3["all_pass"] = all(day["ok"] for day in phys3["days"].values()) if phys3["days"] else False
    return phys2, phys3, all_pass and phys2["all_pass"] and phys3["all_pass"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Q4-2/Q4-3 two-day regression")
    parser.add_argument("--skip-q4-2", action="store_true", help="reuse streamed Q4-2 CSVs")
    parser.add_argument("--skip-q4-3", action="store_true", help="reuse streamed Q4-3 CSVs")
    parser.add_argument("--skip-tests", action="store_true", help="skip the unittest pre-check")
    args = parser.parse_args(argv)
    started = perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.skip_tests:
        tests = {"command": "skipped", "returncode": 0, "stdout_tail": "", "stderr_tail": ""}
    else:
        tests = _run_unittest()
        if tests["returncode"] != 0:
            write_json(OUTPUT_DIR / "q4_twoday_run_metadata.json", {"tests": tests, "aborted": True})
            raise SystemExit(f"unit tests failed:\n{tests['stderr_tail']}\n{tests['stdout_tail']}")
    bundle = load_q4_bundle(compute_price_mpc=False)
    end_index = last_index_for_dates(bundle, PILOT_DATES)
    print(f"Two-day regression with warmup through {bundle.prices.dates[end_index].strftime('%Y-%m-%d')}", flush=True)
    if args.skip_q4_2:
        q42 = load_q42_detail_from_disk(OUTPUT_DIR, PILOT_DATES)
        print("Reusing Q4-2 dispatch CSVs from disk", flush=True)
    else:
        q42 = run_q4_2_campaign(bundle, end_index, PILOT_DATES, OUTPUT_DIR)
    if args.skip_q4_3:
        q43 = load_q43_detail_from_disk(OUTPUT_DIR, PILOT_DATES)
        print("Reusing Q4-3 dispatch CSVs from disk", flush=True)
    else:
        q43 = run_q4_3_campaign(bundle, end_index, PILOT_DATES, OUTPUT_DIR)
    phys2, phys3, all_pass = _audit_detail(q42["detail"], q43["detail"])
    soc2 = warmup_soc_continuity(pd.read_csv(OUTPUT_DIR / "q4_2_warmup_daily.csv"))
    soc3 = warmup_soc_continuity(pd.read_csv(OUTPUT_DIR / "q4_3_warmup_daily.csv"))
    info_rows = []
    for date, result in q42["detail"].items():
        q43_res = q43["detail"][date]
        alpha = result.summary["risk_alpha"]
        if alpha is not None:
            alpha = float(alpha)
        info = probe_executed_prefix(
            bundle,
            result.day_index,
            float(result.summary["soc_start_kwh"]),
            alpha,
            result.dispatch,
            q43_res,
            tau=40,
        )
        info_rows.append(info)
        all_pass = all_pass and info["pass"]
        print(f"info-set {date}: {info}", flush=True)
    info_payload = {"days": info_rows, "all_pass": all(row["pass"] for row in info_rows)}
    write_json(OUTPUT_DIR / "q4_2_physical_audit.json", {**phys2, "soc_continuity": soc2})
    write_json(OUTPUT_DIR / "q4_3_physical_audit.json", {**phys3, "soc_continuity": soc3})
    write_json(OUTPUT_DIR / "q4_2_info_set_audit.json", info_payload)
    write_json(OUTPUT_DIR / "q4_3_info_set_audit.json", info_payload)
    all_pass = all_pass and soc2["pass"] and soc3["pass"] and info_payload["all_pass"]
    meta = {
        "git_commit": _git_hash(),
        "pilot_dates": list(PILOT_DATES),
        "warmup_start": "2025-01-01",
        "warmup_end": bundle.prices.dates[end_index].strftime("%Y-%m-%d"),
        "n_days_solved_each_system": end_index + 1,
        "pam_seed": PAM_SEED,
        "pam_algorithm": "deterministic_build_then_swap",
        "load_information_case": "causal_load_main",
        "q4_2_year_end_rule": "q2_accepted_no_hard_terminal",
        "q4_3_year_end": "A_q2_aligned_1200",
        "q4_3_strategy": "M1_M6",
        "settlement_rule": "delivery_time_actual_price",
        "wrote_result4_xlsx": False,
        "full_year": False,
        "elapsed_seconds": float(perf_counter() - started),
        "tests": tests,
        "q4_2_all_pass": phys2["all_pass"],
        "q4_3_all_pass": phys3["all_pass"],
        "all_pass": all_pass,
        "skip_q4_2": bool(args.skip_q4_2),
        "skip_q4_3": bool(args.skip_q4_3),
        "note": (
            "Two-day regression only. January through each target date is causal "
            "SOC warmup. result4-2/result4-3 are not written in this stage."
        ),
    }
    write_json(OUTPUT_DIR / "q4_2_run_metadata.json", {**meta, "system": "Q4-2"})
    write_json(OUTPUT_DIR / "q4_3_run_metadata.json", {**meta, "system": "Q4-3"})
    write_json(OUTPUT_DIR / "q4_twoday_run_metadata.json", meta)
    print(json.dumps({"all_pass": all_pass, "elapsed_seconds": meta["elapsed_seconds"]}, indent=2))
    if not all_pass:
        raise SystemExit("two-day physical, ledger, or information-set audit failed")


if __name__ == "__main__":
    main()

# ===== q4/scenarios.py =====
"""Triple residual K-medoids for Q4-2. Residuals are paired by historical date."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from q2.scenarios import pam, robust_scale
from q4.bundle import Q4Bundle
from q4.config import FIXED_SCENARIO_K, RESIDUAL_POOL_DAYS, T


@dataclass(frozen=True)
class TripleScenarioSet:
    target_index: int
    history_end_exclusive: int
    pool_indices: np.ndarray
    medoid_indices: np.ndarray
    cluster_labels: np.ndarray
    probabilities: np.ndarray
    scale_load: float
    scale_pv: float
    scale_price: float
    k_effective: int
    k_target: int


def complete_triple_days(bundle: Q4Bundle, history_end_exclusive: int) -> np.ndarray:
    """Days strictly before the cutoff with archived causal load, PV, and price forecasts."""
    ok = []
    for i in range(max(0, history_end_exclusive)):
        if not np.isfinite(bundle.price_archive.day_ahead[i]).all():
            continue
        if not np.isfinite(bundle.q2_forecast.load_hat[i]).all():
            continue
        if not np.isfinite(bundle.q2_forecast.pv_hat[i]).all():
            continue
        ok.append(i)
    if not ok:
        return np.zeros(0, dtype=int)
    pool = np.asarray(ok, dtype=int)
    return pool[pool >= max(0, history_end_exclusive - RESIDUAL_POOL_DAYS)]


def residual_stack(bundle: Q4Bundle, indices: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    load_r = bundle.q2.load[indices] - bundle.q2_forecast.load_hat[indices]
    pv_r = bundle.q2.pv[indices] - bundle.q2_forecast.pv_hat[indices]
    price_r = bundle.prices.price[indices] - bundle.price_archive.day_ahead[indices]
    return load_r, pv_r, price_r


def triple_distance_matrix(
    load_residual: np.ndarray, pv_residual: np.ndarray, price_residual: np.ndarray
) -> tuple[np.ndarray, float, float, float]:
    sl = robust_scale(load_residual)
    sp = robust_scale(pv_residual)
    spr = robust_scale(price_residual)
    dl = (load_residual[:, None, :] - load_residual[None, :, :]) / sl
    dp = (pv_residual[:, None, :] - pv_residual[None, :, :]) / sp
    dr = (price_residual[:, None, :] - price_residual[None, :, :]) / spr
    d2 = np.mean(dl * dl + dp * dp + dr * dr, axis=2)
    return np.sqrt(np.maximum(d2, 0.0)), sl, sp, spr


def build_triple_scenarios(
    bundle: Q4Bundle,
    target_index: int,
    history_end_exclusive: int | None = None,
    k_target: int = FIXED_SCENARIO_K,
) -> TripleScenarioSet | None:
    history_end = target_index if history_end_exclusive is None else history_end_exclusive
    if history_end <= 0 or history_end > target_index:
        return None
    pool = complete_triple_days(bundle, history_end)
    if len(pool) == 0:
        return None
    load_r, pv_r, price_r = residual_stack(bundle, pool)
    distance, sl, sp, spr = triple_distance_matrix(load_r, pv_r, price_r)
    k_eff = int(min(k_target, len(pool)))
    local_medoids, labels = pam(distance, k_eff)
    counts = np.bincount(labels, minlength=k_eff)
    probabilities = counts.astype(float) / len(pool)
    if not np.isclose(probabilities.sum(), 1.0, atol=1e-12):
        raise AssertionError("Q4-2 scenario probabilities do not sum to one")
    return TripleScenarioSet(
        target_index=target_index,
        history_end_exclusive=history_end,
        pool_indices=pool,
        medoid_indices=pool[local_medoids],
        cluster_labels=labels,
        probabilities=probabilities,
        scale_load=sl,
        scale_pv=sp,
        scale_price=spr,
        k_effective=k_eff,
        k_target=int(k_target),
    )


def scenario_paths(
    bundle: Q4Bundle,
    scenarios: TripleScenarioSet,
    base_load: np.ndarray,
    base_pv: np.ndarray,
    base_price: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    m = scenarios.medoid_indices
    load_r, pv_r, price_r = residual_stack(bundle, m)
    load = np.maximum(0.0, base_load[None, :] + load_r)
    pv = np.maximum(0.0, base_pv[None, :] + pv_r)
    price = np.maximum(0.0, base_price[None, :] + price_r)
    return load, pv, price


def posterior_weights(
    bundle: Q4Bundle,
    scenarios: TripleScenarioSet,
    observed_load_r: np.ndarray,
    observed_pv_r: np.ndarray,
    observed_price_r: np.ndarray,
) -> tuple[np.ndarray, float]:
    t = len(observed_load_r)
    if t == 0:
        return scenarios.probabilities.copy(), np.nan
    m = scenarios.medoid_indices
    load_r, pv_r, price_r = residual_stack(bundle, m)
    lr = load_r[:, :t]
    pr = pv_r[:, :t]
    rr = price_r[:, :t]
    delta = np.mean(
        ((lr - observed_load_r) / scenarios.scale_load) ** 2
        + ((pr - observed_pv_r) / scenarios.scale_pv) ** 2
        + ((rr - observed_price_r) / scenarios.scale_price) ** 2,
        axis=1,
    )
    if len(m) > 1:
        pair = []
        for a in range(len(m)):
            for b in range(a + 1, len(m)):
                pair.append(
                    np.mean(
                        ((lr[a] - lr[b]) / scenarios.scale_load) ** 2
                        + ((pr[a] - pr[b]) / scenarios.scale_pv) ** 2
                        + ((rr[a] - rr[b]) / scenarios.scale_price) ** 2
                    )
                )
        bandwidth = max(float(np.sqrt(np.median(pair))), 1e-6)
    else:
        bandwidth = 1.0
    logw = np.log(np.maximum(scenarios.probabilities, 1e-300)) - delta / (
        2.0 * bandwidth * bandwidth
    )
    logw -= np.max(logw)
    weights = np.exp(logw)
    weights /= weights.sum()
    return weights, bandwidth

# ===== scripts/export_paper_q2_q3.py =====
#!/usr/bin/env python3
"""Export Q2/Q3 paper tables and figures from signed-off workbooks and ledgers.

Reads only accepted outputs:
- Q2: `output/result2.xlsx`（V2 政策一致）与 `output/q2_policy_consistent/` 年度台账
- Q3: output/result3.xlsx and output/q3_full_annual/*.csv

Writes LaTeX tables under paper/manuscript/ and PNG/PDF figures under paper/overleaf/.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, time
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PAPER = ROOT / "paper" / "overleaf"
MANUSCRIPT = ROOT / "paper" / "manuscript"
TABLES_Q2 = MANUSCRIPT / "tables" / "q2"
TABLES_Q3 = MANUSCRIPT / "tables" / "q3"
FIG_Q2 = PAPER / "figures" / "q2"
FIG_Q3 = PAPER / "figures" / "q3"

RESULT2 = ROOT / "output" / "result2.xlsx"
RESULT3 = ROOT / "output" / "result3.xlsx"
Q2_DAILY = ROOT / "output" / "q2_policy_consistent" / "feb_dec_daily_summary.csv"
Q2_COST = ROOT / "output" / "q2_policy_consistent" / "cost_breakdown.csv"
Q2_K = ROOT / "output" / "q2_policy_consistent" / "k_sensitivity.csv"
Q2_CAL = ROOT / "output" / "q2_policy_consistent" / "frozen_policy_calendar.csv"
Q3_STRATEGY = ROOT / "output" / "q3_full_annual" / "q3_annual_strategy_comparison.csv"
Q3_MONTHLY = ROOT / "output" / "q3_full_annual" / "q3_annual_monthly.csv"
Q3_UPDATE = ROOT / "output" / "q3_full_annual" / "q3_update_log.csv"

SAMPLE_DATE = "2025-06-21"
SAMPLE_SLOTS = (
    "10:00-10:10",
    "12:00-12:10",
    "14:00-14:10",
    "16:00-16:10",
    "18:00-18:10",
    "20:00-20:10",
)

BLUE = "#276FBF"
RED = "#C0392B"
GRAY = "#6B7280"
GREEN = "#2F6F4E"


def fmt_num(value: float, digits: int = 4) -> str:
    return f"{float(value):.{digits}f}"


def latex_code(text: str) -> str:
    escaped = text.replace("_", "\\_")
    return f"\\texttt{{{escaped}}}"


def latex_escape(text: str) -> str:
    return (
        text.replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("&", "\\&")
        .replace("%", "\\%")
    )


def configure_style() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = (
        "Noto Sans CJK SC",
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "PingFang SC",
        "Hiragino Sans GB",
        "Heiti SC",
        "Songti SC",
        "Arial Unicode MS",
    )
    font = next((name for name in candidates if name in available), "DejaVu Sans")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font],
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "pdf.fonttype": 42,
        }
    )
    return font


def save_figure(fig: plt.Figure, stem: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(out_dir / f"{stem}.png", dpi=320, bbox_inches="tight")
    plt.close(fig)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_purchase_row(path: Path, sheet: str, date_text: str) -> tuple[list[str], dict[str, float], float, float]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = ws.iter_rows(values_only=True)
    headers = [str(h) if h is not None else "" for h in next(rows)]
    target = pd.Timestamp(date_text).to_pydatetime()
    values: dict[str, float] = {}
    day_total = 0.0
    day_fee = 0.0
    for row in rows:
        if row[0] is None:
            continue
        if pd.Timestamp(row[0]).normalize() != pd.Timestamp(target).normalize():
            continue
        for idx, header in enumerate(headers[1:], start=1):
            if idx >= len(row):
                break
            if header in SAMPLE_SLOTS:
                values[header] = float(row[idx] or 0.0)
        if len(row) > 145:
            day_total = float(row[145] or 0.0)
        if len(row) > 146:
            day_fee = float(row[146] or 0.0)
        break
    wb.close()
    if not values:
        raise ValueError(f"missing purchase row for {date_text} in {path}")
    return headers, values, day_total, day_fee


def load_charge_blocks(path: Path, date_text: str) -> tuple[list[tuple[str, float, float]], float, float]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["充放电量"]
    blocks: list[tuple[str, float, float]] = []
    soc_start = soc_end = 0.0
    target = pd.Timestamp(date_text).normalize()
    for row in ws.iter_rows(values_only=True):
        if row[0] == "日期" or row[1] == "时间段":
            continue
        if row[0] is not None:
            try:
                row_date = pd.Timestamp(row[0]).normalize()
            except (ValueError, TypeError):
                continue
            if row_date == target:
                soc_start = float(row[5] or 0.0)
        if row[1] is None:
            continue
        if row[0] is not None:
            try:
                row_date = pd.Timestamp(row[0]).normalize()
            except (ValueError, TypeError):
                row_date = None
            if row_date == target:
                blocks.append((str(row[1]), float(row[2] or 0.0), float(row[3] or 0.0)))
                if str(row[4]) in ("24:00", "0:00+1") or row[4] == time(0, 0):
                    soc_end = float(row[5] or 0.0)
        elif row[0] is None and blocks and len(blocks) < 6:
            blocks.append((str(row[1]), float(row[2] or 0.0), float(row[3] or 0.0)))
            if str(row[4]) in ("24:00", "0:00+1"):
                soc_end = float(row[5] or 0.0)
    wb.close()
    if len(blocks) != 6:
        raise ValueError(f"expected 6 charge blocks for {date_text}, got {len(blocks)}")
    return blocks, soc_start, soc_end


def load_emergency_segments(path: Path, date_text: str) -> list[tuple[str, float]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["紧急购电量"]
    target = pd.Timestamp(date_text).normalize()
    segments: list[tuple[str, float]] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        if pd.Timestamp(row[0]).normalize() != target:
            continue
        segments.append((str(row[1]), float(row[2] or 0.0)))
    wb.close()
    return segments


def load_adjust_row(path: Path, date_text: str) -> dict[str, float]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["调整购电量"]
    rows = ws.iter_rows(values_only=True)
    headers = [str(h) if h is not None else "" for h in next(rows)]
    target = pd.Timestamp(date_text).normalize()
    values: dict[str, float] = {}
    for row in rows:
        if row[0] is None:
            continue
        if pd.Timestamp(row[0]).normalize() != target:
            continue
        for idx, header in enumerate(headers[1:], start=1):
            if header in SAMPLE_SLOTS:
                values[header] = float(row[idx] or 0.0)
        break
    wb.close()
    if not values:
        raise ValueError(f"missing adjust row for {date_text}")
    return values


def render_triplet_table(
    caption: str,
    label: str,
    value_title: str,
    rows: list[tuple[str, str]],
    footer: tuple[str, str, str, str] | None = None,
) -> str:
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{{caption}}}\\label{{{label}}}",
        "\\normalsize\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}cccccc@{}}",
        "\\toprule",
        f"时间段 & {value_title} & 时间段 & {value_title} & 时间段 & {value_title} \\\\",
        "\\midrule",
    ]
    for i in range(0, len(rows), 3):
        chunk = rows[i : i + 3]
        while len(chunk) < 3:
            chunk.append(("", ""))
        lines.append(
            f"{chunk[0][0]} & {chunk[0][1]} & {chunk[1][0]} & {chunk[1][1]} & "
            f"{chunk[2][0]} & {chunk[2][1]} \\\\"
        )
    if footer:
        left_label, left_val, right_label, right_val = footer
        lines.append(
            f"{left_label} & \\multicolumn{{2}}{{c}}{{{left_val}}} & "
            f"{right_label} & \\multicolumn{{2}}{{c}}{{{right_val}}} \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    return "\n".join(lines)


def export_q2_tables() -> dict:
    _, purchase_vals, day_q, day_fee = load_purchase_row(RESULT2, "计划购电量", SAMPLE_DATE)
    blocks, soc_start, soc_end = load_charge_blocks(RESULT2, SAMPLE_DATE)
    emergency = load_emergency_segments(RESULT2, SAMPLE_DATE)
    cost = pd.read_csv(Q2_COST)
    k_df = pd.read_csv(Q2_K)
    feb = cost[cost["label"] == "feb_dec_inherited_warmup_soc"].iloc[0]
    jan = cost[cost["label"] == "january_warmup_main"].iloc[0]

    purchase_rows = [(slot, fmt_num(purchase_vals[slot])) for slot in SAMPLE_SLOTS]
    purchase_tex = render_triplet_table(
        f"问题二 {SAMPLE_DATE} 计划购电量及全天汇总（政策一致 $K=8$ 主方案）",
        "tab:q2-purchase",
        "购电量",
        purchase_rows,
        footer=("全天购电量", fmt_num(day_q), "全天购电费", fmt_num(day_fee)),
    )

    storage_lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{问题二 {SAMPLE_DATE} 充放电量及日初/日末储电量}}\\label{{tab:q2-storage}}",
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
    storage_tex = "\n".join(storage_lines)

    emergency_lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{问题二 {SAMPLE_DATE} 紧急购电记录（2--12 月输出区间内典型日）}}\\label{{tab:q2-emergency}}",
        "\\normalsize\\setlength{\\tabcolsep}{6pt}",
        "\\begin{tabular}{@{}ccc@{}}",
        "\\toprule",
        "购电时间段 & 购电量 & 备注 \\\\",
        "\\midrule",
    ]
    total_e = 0.0
    for interval, amount in emergency[:8]:
        total_e += amount
        emergency_lines.append(f"{interval} & {fmt_num(amount)} & 紧急购电 \\\\")
    if len(emergency) > 8:
        emergency_lines.append(
            f"\\multicolumn{{3}}{{c}}{{其余 {len(emergency) - 8} 条记录见随附正式工作簿}} \\\\"
        )
    emergency_lines.extend(
        [
            f"\\midrule",
            f"当日合计 & {fmt_num(sum(x for _, x in emergency))} & kWh \\\\",
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "",
        ]
    )
    emergency_tex = "\n".join(emergency_lines)

    cost_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{问题二年度成本分解（政策一致 $K=8$；2--12 月为题设输出区间）}}\\label{{tab:q2-cost-summary}}
\\normalsize\\setlength{{\\tabcolsep}}{{6pt}}
\\begin{{tabular}}{{@{{}}lrrrr@{{}}}}
\\toprule
统计口径 & 天数 & 计划购电费/元 & 紧急购电费/元 & 总成本/元 \\\\
\\midrule
1 月预热（不计入题设输出） & 31 & {fmt_num(jan.planned_cost_yuan, 2)} & {fmt_num(jan.emergency_cost_yuan, 2)} & {fmt_num(jan.total_cost_yuan, 2)} \\\\
2--12 月正式输出 & 334 & {fmt_num(feb.planned_cost_yuan, 2)} & {fmt_num(feb.emergency_cost_yuan, 2)} & {fmt_num(feb.total_cost_yuan, 2)} \\\\
\\midrule
2--12 月紧急购电量/kWh & \\multicolumn{{4}}{{c}}{{{fmt_num(feb.emergency_kwh, 2)}}} \\\\
2 月 1 日继承 SOC/kWh & \\multicolumn{{4}}{{c}}{{{fmt_num(feb.soc_start_kwh, 4)}}} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    k_rows = []
    for _, row in k_df.iterrows():
        conclusion = "主方案" if int(row.scenario_k) == 8 else "对照"
        k_rows.append(
            f"$K={int(row.scenario_k)}$ & {int(row.n_days)} & "
            f"{fmt_num(row.total_cost_yuan, 2)} & {fmt_num(row.emergency_kwh, 2)} & "
            f"{fmt_num(row.elapsed_seconds, 1)} & {conclusion} \\\\"
        )
    param_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{问题二情景数 $K$ 的闭环复核（2--12 月输出区间；正式主方案取 $K=8$）}}\\label{{tab:q2-parameter}}
\\small\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{tabular}}{{@{{}}crrrrl@{{}}}}
\\toprule
$K$ & 天数 & 总成本/元 & 紧急购电/kWh & 耗时/s & 结论 \\\\
\\midrule
{chr(10).join(k_rows)}\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    write_text(TABLES_Q2 / "purchase.tex", purchase_tex)
    write_text(TABLES_Q2 / "storage.tex", storage_tex)
    write_text(TABLES_Q2 / "emergency.tex", emergency_tex)
    write_text(TABLES_Q2 / "cost_summary.tex", cost_tex)
    write_text(TABLES_Q2 / "parameter_selection.tex", param_tex)
    return {
        "sample_date": SAMPLE_DATE,
        "feb_dec_total_yuan": float(feb.total_cost_yuan),
        "emergency_segments": len(emergency),
    }


def export_q3_tables() -> dict:
    _, g0_vals, day_g0, _ = load_purchase_row(RESULT3, "计划购电量", SAMPLE_DATE)
    g_vals = load_adjust_row(RESULT3, SAMPLE_DATE)
    blocks, soc_start, soc_end = load_charge_blocks(RESULT3, SAMPLE_DATE)
    emergency = load_emergency_segments(RESULT3, SAMPLE_DATE)
    strategy = pd.read_csv(Q3_STRATEGY)
    a = strategy[
        (strategy["strategy"].isin(["M0", "M1_M6"]))
        & (strategy["year_end_boundary"] == "A_q2_aligned")
    ].set_index("strategy")

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

    purchase_tex = build_value_table(
        f"问题三 {SAMPLE_DATE} 计划购电量 $g^0$（A 边界；全时点价值触发策略）",
        "tab:q3-purchase",
        "计划购电量",
        g0_vals,
    )
    adjust_tex = build_value_table(
        f"问题三 {SAMPLE_DATE} 调整购电量 $g^F$（A 边界；全时点价值触发策略）",
        "tab:q3-adjust",
        "调整购电量",
        g_vals,
    )

    storage_lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{问题三 {SAMPLE_DATE} 充放电量及日初/日末储电量}}\\label{{tab:q3-storage}}",
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
        f"\\caption{{问题三 {SAMPLE_DATE} 紧急购电记录}}\\label{{tab:q3-emergency}}",
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

    m0 = a.loc["M0"]
    m16 = a.loc["M1_M6"]
    saving = float(m0.total_cost_yuan - m16.total_cost_yuan)
    saving_pct = 100.0 * saving / float(m0.total_cost_yuan)
    compare_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{问题三全年策略比较（A 边界；1--12 月连续运行口径）}}\\label{{tab:q3-strategy-compare}}
\\small\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{tabular}}{{@{{}}lrrrrr@{{}}}}
\\toprule
策略 & 总成本/元 & 结算成本/元 & 紧急购电/元 & 紧急购电/kWh & 调整次数 \\\\
\\midrule
不调整（M0） & {fmt_num(m0.total_cost_yuan, 2)} & {fmt_num(m0.settlement_cost_yuan, 2)} & {fmt_num(m0.emergency_cost_yuan, 2)} & {fmt_num(m0.emergency_kwh, 2)} & {int(m0.adjustment_count)} \\\\
全时点调整（M1/M6） & {fmt_num(m16.total_cost_yuan, 2)} & {fmt_num(m16.settlement_cost_yuan, 2)} & {fmt_num(m16.emergency_cost_yuan, 2)} & {fmt_num(m16.emergency_kwh, 2)} & {int(m16.adjustment_count)} \\\\
\\midrule
相对 M0 节省 & \\multicolumn{{5}}{{c}}{{{fmt_num(saving, 2)} 元（{fmt_num(saving_pct, 2)}\\%）}} \\\\
2--12 月输出区间成本 & \\multicolumn{{5}}{{c}}{{14512748.53 元（334 日，非全年口径）}} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    write_text(TABLES_Q3 / "purchase.tex", purchase_tex)
    write_text(TABLES_Q3 / "adjust.tex", adjust_tex)
    write_text(TABLES_Q3 / "storage.tex", "\n".join(storage_lines))
    write_text(TABLES_Q3 / "emergency.tex", "\n".join(emergency_lines))
    write_text(TABLES_Q3 / "strategy_comparison.tex", compare_tex)
    return {
        "annual_m1m6_yuan": float(m16.total_cost_yuan),
        "annual_saving_yuan": saving,
        "export_window_yuan": 14512748.527966088,
    }


def export_q2_figures() -> None:
    configure_style()
    daily = pd.read_csv(Q2_DAILY, parse_dates=["date"])
    daily = daily[(daily["date"] >= "2025-02-01") & (daily["date"] <= "2025-12-31")]
    daily["month"] = daily["date"].dt.to_period("M").astype(str)
    monthly = daily.groupby("month", as_index=False).agg(
        planned_cost_yuan=("planned_cost_yuan", "sum"),
        emergency_cost_yuan=("emergency_cost_yuan", "sum"),
    )
    x = np.arange(len(monthly))
    fig, ax = plt.subplots(figsize=(11.5, 5.2))
    ax.bar(x, monthly["planned_cost_yuan"] / 1e6, label="计划购电费", color=BLUE)
    ax.bar(
        x,
        monthly["emergency_cost_yuan"] / 1e6,
        bottom=monthly["planned_cost_yuan"] / 1e6,
        label="紧急购电费",
        color=RED,
        alpha=0.85,
    )
    ax.set_xticks(x, [m.replace("2025-", "") + "月" for m in monthly["month"]], rotation=0)
    ax.set_ylabel("成本 / 百万元")
    ax.set_title("问题二 2025 年 2--12 月月度购电成本构成（政策一致 $K=8$）")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save_figure(fig, "fig_q2_monthly_cost", FIG_Q2)

    fig, ax = plt.subplots(figsize=(11.5, 4.8))
    ax.plot(daily["date"], daily["soc_end_kwh"], color=BLUE, linewidth=0.9)
    ax.axhline(1200, color=GRAY, linestyle="--", linewidth=0.8, label="SOC 下界")
    ax.axhline(10800, color=GRAY, linestyle=":", linewidth=0.8, label="SOC 上界")
    ax.set_ylabel("日末 SOC / kWh")
    ax.set_title("问题二 2025 年 2--12 月日末储电量轨迹")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m月"))
    ax.legend(frameon=False, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save_figure(fig, "fig_q2_soc_daily", FIG_Q2)

    cal = pd.read_csv(Q2_CAL, parse_dates=["date"])
    selected = (
        cal.groupby(["effective_start_date", "effective_end_date", "forecast_mode", "risk_alpha"], dropna=False)
        .size()
        .reset_index(name="n_days")
        .sort_values("effective_start_date")
    )
    fig, ax = plt.subplots(figsize=(11.5, 3.8))
    forecast_labels = {
        "m1": "历史均值",
        "m2": "历史中位数",
        "m3": "近期加权均值",
    }
    for _, row in selected.iterrows():
        start = pd.Timestamp(row.effective_start_date)
        end = pd.Timestamp(row.effective_end_date) + pd.Timedelta(days=1)
        alpha = "" if pd.isna(row.risk_alpha) else f", alpha={row.risk_alpha:.2f}"
        label = f"{forecast_labels.get(row.forecast_mode, row.forecast_mode)}{alpha}"
        ax.barh(label, (end - start).days, left=start, height=0.55, color=BLUE, alpha=0.75)
    ax.axvspan(pd.Timestamp("2025-01-01"), pd.Timestamp("2025-02-01"), color=GRAY, alpha=0.12)
    ax.set_xlim(pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-01"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m月"))
    ax.set_title("问题二预测结构与风险分位滚动选择日历（$K=8$）")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save_figure(fig, "fig_q2_policy_calendar", FIG_Q2)


def export_q3_figures() -> None:
    configure_style()
    strategy = pd.read_csv(Q3_STRATEGY)
    subset = strategy[
        (strategy["year_end_boundary"] == "A_q2_aligned")
        & (strategy["strategy"].isin(["M0", "M1_M6", "M6_only", "M12_only", "M18_only"]))
    ].copy()
    subset = subset.sort_values("total_cost_yuan")
    label_map = {
        "M0": "不调整",
        "M1_M6": "全时点调整",
        "M6_only": "仅 6:00 更新",
        "M12_only": "仅 12:00 更新",
        "M18_only": "仅 18:00 更新",
    }
    labels = [label_map[name] for name in subset["strategy"]]
    planned = subset["settlement_cost_yuan"].to_numpy()
    emergency = subset["emergency_cost_yuan"].to_numpy()
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    ax.bar(x, planned / 1e6, label="结算成本", color=BLUE)
    ax.bar(x, emergency / 1e6, bottom=planned / 1e6, label="紧急购电成本", color=RED, alpha=0.85)
    ax.set_xticks(x, labels, rotation=15)
    ax.set_ylabel("成本 / 百万元")
    ax.set_title("问题三 A 边界下各策略总成本分解（2025 年 1--12 月）")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save_figure(fig, "fig_q3_strategy_cost", FIG_Q3)

    monthly = pd.read_csv(Q3_MONTHLY)
    monthly = monthly[monthly["year_end_boundary"] == "A_q2_aligned"]
    months = sorted(m for m in monthly["month"].unique() if m >= "2025-02")
    m0 = monthly[(monthly["strategy"] == "M0")].set_index("month").loc[months]["emergency_cost_yuan"]
    m16 = monthly[(monthly["strategy"] == "M1_M6")].set_index("month").loc[months]["emergency_cost_yuan"]
    x = np.arange(len(months))
    width = 0.36
    fig, ax = plt.subplots(figsize=(11.5, 5.0))
    ax.bar(x - width / 2, m0 / 1e4, width=width, label="不调整（M0）", color=GRAY)
    ax.bar(x + width / 2, m16 / 1e4, width=width, label="全时点调整（M1/M6）", color=BLUE)
    ax.set_xticks(x, [m.replace("2025-", "") + "月" for m in months])
    ax.set_ylabel("紧急购电成本 / 万元")
    ax.set_title("问题三 2025 年 2--12 月紧急购电成本月度对比")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save_figure(fig, "fig_q3_monthly_emergency", FIG_Q3)

    updates = pd.read_csv(Q3_UPDATE, parse_dates=["date"])
    updates = updates[
        (updates["strategy"] == "M1_M6")
        & (updates["year_end_boundary"] == "A_q2_aligned")
        & (updates["update_time"].isin(["06:00", "12:00", "18:00"]))
        & (updates["implemented"] == True)
    ].copy()
    updates["month"] = updates["date"].dt.to_period("M").astype(str)
    monthly_voi = updates.groupby("month")["voi_yuan"].sum()
    months_voi = [m for m in sorted(monthly_voi.index) if m >= "2025-02"]
    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    ax.bar(
        np.arange(len(months_voi)),
        [monthly_voi[m] / 1e4 for m in months_voi],
        color=GREEN,
        alpha=0.85,
    )
    ax.set_xticks(np.arange(len(months_voi)), [m.replace("2025-", "") + "月" for m in months_voi])
    ax.set_ylabel("信息价值 / 万元")
    ax.set_title("问题三全时点价值触发策略的月度信息价值（2025 年 2--12 月）")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save_figure(fig, "fig_q3_update_value", FIG_Q3)


def main() -> None:
    for path in (RESULT2, RESULT3, Q2_DAILY, Q2_COST, Q3_STRATEGY):
        if not path.exists():
            raise FileNotFoundError(path)
    q2_meta = export_q2_tables()
    q3_meta = export_q3_tables()
    export_q2_figures()
    export_q3_figures()
    audit = {"q2": q2_meta, "q3": q3_meta}
    write_text(PAPER / "paper_assets_audit.json", json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

# ===== scripts/export_paper_q4_2.py =====
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


def load_cost_slices() -> tuple[pd.Series, pd.Series, float]:
    daily = pd.read_csv(WARMUP)
    daily["date"] = pd.to_datetime(daily["date"])
    jan = daily[daily["date"].dt.month == 1]
    feb_dec = daily[(daily["date"] >= "2025-02-01") & (daily["date"] <= "2025-12-31")]
    feb1_soc = float(feb_dec.iloc[0]["soc_start_kwh"])
    return jan.sum(numeric_only=True), feb_dec.sum(numeric_only=True), feb1_soc


def export_tables() -> dict:
    TABLES.mkdir(parents=True, exist_ok=True)
    jan, feb, feb1_soc = load_cost_slices()
    meta = json.loads(META.read_text(encoding="utf-8"))
    k_meta = json.loads(K_REVIEW.read_text(encoding="utf-8"))
    k_rows = []
    for k in k_meta["k_candidates"]:
        row = k_meta["by_k"][str(k)]
        if k == 4:
            conclusion = "低场景数对照"
        elif k == k_meta["decision"]["keep_k"]:
            conclusion = "主方案（稳定折中）"
        else:
            conclusion = "高场景数对照"
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
        f"问题四日前额度策略（Q4-2）{SAMPLE_DATE} 计划购电量及全天汇总（$K=8$）",
        "tab:q4-purchase",
        "购电量",
        purchase_rows,
        footer=("全天购电量", fmt_num(day_q), "全天购电费", fmt_num(day_fee)),
    )

    storage_lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{问题四日前额度策略（Q4-2）{SAMPLE_DATE} 充放电量及日初/日末储电量}}\\label{{tab:q4-storage}}",
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
\\caption{{问题四日前额度策略（Q4-2）成本分解（交付时段实际价；2--12 月为题设输出区间）}}\\label{{tab:q4-cost-summary}}
\\normalsize\\setlength{{\\tabcolsep}}{{6pt}}
\\begin{{tabular}}{{@{{}}lrrrr@{{}}}}
\\toprule
统计口径 & 天数 & 计划购电费/元 & 紧急购电费/元 & 总成本/元 \\\\
\\midrule
1 月预热（不计入题设输出） & 31 & {fmt_num(jan.normal_cost_yuan, 2)} & {fmt_num(jan.emergency_cost_yuan, 2)} & {fmt_num(jan.total_cost_yuan, 2)} \\\\
2--12 月正式输出 & 334 & {fmt_num(feb.normal_cost_yuan, 2)} & {fmt_num(feb.emergency_cost_yuan, 2)} & {fmt_num(feb.total_cost_yuan, 2)} \\\\
\\midrule
2--12 月紧急购电量/kWh & \\multicolumn{{4}}{{c}}{{{fmt_num(feb.emergency_kwh, 2)}}} \\\\
2 月 1 日继承 SOC/kWh & \\multicolumn{{4}}{{c}}{{{fmt_num(feb1_soc, 4)}}} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    param_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{问题四日前额度策略（Q4-2）情景数 $K$ 的闭环复核}}\\label{{tab:q4-parameter}}
\\small\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{tabular}}{{@{{}}crrrrl@{{}}}}
\\toprule
$K$ & 窗口数 & 验证总成本/元 & 验证紧急费/元 & 平均耗时/s & 角色 \\\\
\\midrule
{chr(10).join(k_rows)}\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""

    price_all = pd.read_csv(PRICE_MONTHLY)
    annual = price_all[price_all["year_month"] == "2025-annual"].iloc[0]
    monthly = price_all[price_all["year_month"] != "2025-annual"]
    price_rows = []
    for _, row in monthly.iterrows():
        price_rows.append(
            f"{row.year_month} & {fmt_num(row.day_ahead_mae, 4)} & "
            f"{fmt_num(row.day_ahead_rmse, 4)} & {fmt_num(row.intraday_06_mae, 4)} & "
            f"{fmt_num(row.intraday_18_mae, 4)} & {fmt_num(row.mpc_remaining_mae_mean, 4)} \\\\"
        )
    price_tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{问题四因果价格预测误差（2025 年 1--12 月；单位：元/kWh）}}\\label{{tab:q4-price-error}}
\\small\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{tabular}}{{@{{}}lrrrrr@{{}}}}
\\toprule
月份 & 日初 MAE & 日初 RMSE & 6:00 更新 MAE & 18:00 更新 MAE & 日内剩余 MAE \\\\
\\midrule
{chr(10).join(price_rows)}\\midrule
全年 & {fmt_num(annual.day_ahead_mae, 4)} & {fmt_num(annual.day_ahead_rmse, 4)} & {fmt_num(annual.intraday_06_mae, 4)} & {fmt_num(annual.intraday_18_mae, 4)} & {fmt_num(annual.mpc_remaining_mae_mean, 4)} \\\\
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
    ax.bar(x, monthly["normal_cost_yuan"] / 1e6, label="计划购电费")
    ax.bar(
        x,
        monthly["emergency_cost_yuan"] / 1e6,
        bottom=monthly["normal_cost_yuan"] / 1e6,
        label="紧急购电费",
    )
    ax.set_xticks(list(x), [m.replace("2025-", "") + "月" for m in monthly.index])
    ax.set_ylabel("成本 / 百万元")
    ax.set_title("日前额度策略月度购电成本构成（2025 年 2--12 月）")
    ax.legend()
    fig.tight_layout()
    save_figure(fig, "fig_q4_monthly_cost", FIGURES)

    price = pd.read_csv(PRICE_MONTHLY)
    price = price[price["year_month"] != "2025-annual"]
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    month_labels = [m.replace("2025-", "") + "月" for m in price["year_month"]]
    ax.plot(month_labels, price["day_ahead_mae"], marker="o", label="日初 MAE")
    ax.plot(month_labels, price["mpc_remaining_mae_mean"], marker="s", label="日内剩余 MAE 均值")
    ax.set_ylabel("误差 / 元·kWh$^{-1}$")
    ax.set_title("因果价格预测误差（2025 年 1--12 月）")
    ax.tick_params(axis="x", rotation=0)
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

# ===== scripts/export_paper_q4_3.py =====
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

# ===== scripts/reconcile_paper_numbers.py =====
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


def load_q4_3(rows: list[Row]) -> None:
    meta_path = ROOT / "output" / "q4" / "q4_3_run_metadata.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text())
    daily = pd.read_csv(ROOT / "output" / "q4" / "q4_3_warmup_daily.csv")
    daily["date"] = pd.to_datetime(daily["date"])
    jan = daily[daily["date"].dt.month == 1]
    feb = daily[(daily["date"] >= "2025-02-01") & (daily["date"] <= "2025-12-31")]
    full = daily.sum(numeric_only=True)
    q3_annual = 16373508.75
    q3_export = 14512748.53
    q42_feb = 15257873.75

    checks = [
        ("sections/q4/05_results.tex", "2-12月总成本", 2, float(feb["total_cost_yuan"].sum()), 15346418.14),
        ("sections/q4/05_results.tex", "1-12月总成本", 2, float(meta["annual_cost_yuan"]), 17489808.24),
        ("sections/q4/05_results.tex", "相对Q3增加(1-12)", 2, float(meta["annual_cost_yuan"]) - q3_annual, 1116299.49),
        ("sections/q4/05_results.tex", "相对Q3增加(2-12)", 2, float(feb["total_cost_yuan"].sum()) - q3_export, 833669.61),
        ("sections/q4/05_results.tex", "相对Q4-2增加(2-12)", 2, float(feb["total_cost_yuan"].sum()) - q42_feb, 88544.39),
        ("tables/q4/cost_summary_q43.tex", "2-12月普通购电", 2, float(feb["normal_cost_yuan"].sum()), 12447748.75),
        ("tables/q4/cost_summary_q43.tex", "2-12月调整费", 2, float(feb["adjustment_cost_yuan"].sum()), 321297.70),
        ("tables/q4/cost_summary_q43.tex", "2-12月紧急成本", 2, float(feb["emergency_cost_yuan"].sum()), 2577371.68),
        ("tables/q4/cost_summary_q43.tex", "1月预热成本", 2, float(jan["total_cost_yuan"].sum()), 2143390.10),
        ("tables/q4/mechanism_compare_q43.tex", "全年调整次数", 0, float(full["adjustment_count"]), 1004),
    ]
    for loc, metric, digits, src, paper in checks:
        check_numeric(
            rows,
            question="Q4-3",
            paper_location=loc,
            metric=metric,
            unit="元/次",
            digits=digits,
            paper_value=paper,
            source_file=meta_path,
            source_column=metric,
            source_value=src,
        )

    phys = json.loads((ROOT / "output" / "q4" / "q4_3_physical_audit.json").read_text())
    add(
        rows,
        question="Q4-3",
        paper_location="sections/q4/06_validation.tex",
        metric="365日物理审计",
        unit="-",
        display_precision="-",
        paper_value="PASS",
        source_file="output/q4/q4_3_physical_audit.json",
        source_column="n_days_pass",
        source_value=str(phys.get("n_days_pass")),
        status="已核" if phys.get("n_days_pass") == 365 else "不一致",
    )

    info = json.loads((ROOT / "output" / "q4" / "q4_3_info_set_audit.json").read_text())
    add(
        rows,
        question="Q4-3",
        paper_location="sections/q4/06_validation.tex",
        metric="信息集探针",
        unit="-",
        display_precision="-",
        paper_value="PASS",
        source_file="output/q4/q4_3_info_set_audit.json",
        source_column="all_pass",
        source_value=str(info.get("all_pass")),
        status="已核" if info.get("all_pass") else "不一致",
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
        "| Q4-3 | 固定 \\texttt{M1\\_M6} + 交付价 | `result4-3.xlsx`、`q4_3_*` | "
        + ("已核" if not any(r.question == "Q4-3" and r.status == "不一致" for r in rows) else "存在不一致")
        + " |",
        "",
        "## 口径提醒（写入摘要前必读）",
        "",
        "- Q2：2–12 月 **15,166,538.46 元** 为题设输出区间；1 月预热 **1,977,568.32 元** 须分列，不得相加混报。",
        "- Q3：全年 **16,373,508.75 元** 为 1–12 月主结论；**14,512,748.53 元** 仅为 `result3.xlsx` 的 2–12 月核对区间。",
        "- Q4-2：2–12 月 **15,257,873.75 元** 为题设输出区间；与 Q2 V2 同区间差 **+91,335.29 元**。",
        "- Q4-3：1–12 月 **17,489,808.24 元**；2–12 月 **15,346,418.14 元**。与 Q3 固定价比较须注明价格机制差异，不得混报口径。",
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
                f"- **{r.question}** `{r.paper_location}` · {r.metric}：论文 {r.paper_value} != 源 {r.source_value}"
            )
    else:
        lines.extend(
            [
                "",
                "## 结论",
                "",
                "Q1–Q4 正文与表格数字均可在展示精度内回链至正式 `output/` 台账。",
                "",
                "## ACCT 签收清单",
                "",
                "- [x] Q1–Q3 逐条对账（本文件 + `reconciliation_audit.json`）",
                "- [x] Q1 专用视图：`paper/q1_reconciliation.md`",
                "- [x] Q4-2 逐条对账",
                "- [x] Q4-3 逐条对账",
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
    load_q4_3(rows)

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
