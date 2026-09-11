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
GRAY = "#777777"
BLACK = "#202020"


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
        boxstyle="round,pad=0.012,rounding_size=0.018",
        linewidth=1.4,
        edgecolor=BLACK,
        facecolor=facecolor,
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height / 2, text, ha="center", va="center", linespacing=1.45)


def draw_arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    label: str,
    label_y_offset: float = 0.18,
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=1.4,
            color=BLACK,
            shrinkA=3,
            shrinkB=3,
        )
    )
    ax.text(
        (start[0] + end[0]) / 2,
        (start[1] + end[1]) / 2 + label_y_offset,
        label,
        ha="center",
        va="bottom",
        fontsize=9,
    )


def plot_f1() -> None:
    fig, ax = plt.subplots(figsize=(15.0, 5.0))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    y, width, height = 0.42, 0.16, 0.28
    xs = [0.02, 0.22, 0.42, 0.62, 0.82]
    texts = [
        "历史负荷—光伏\n配对残差\n（仅已结束日）",
        "日前预测\n8 个联合情景\n风险分位购电下限",
        "0:00 锁定\n计划购电量\n$q_{d,t}$",
        "每 10 分钟观测实际值\n更新 $x,c,d,e$\n仅执行当前一步",
        "实际日末 SOC\n$E_{d,144}$\n传至下一日",
    ]
    faces = ["#E9EEF5", "#DDEAF7", "#DDEAF7", "#FBE7E5", "#E9EEF5"]
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
        )
    ax.text(
        xs[3] + width / 2,
        y - 0.08,
        "日内仅修正储能动作与实际取用；紧急购电 $e$ 只补当期缺口",
        ha="center",
        color=RED,
        fontsize=9.5,
    )
    return_arrow = FancyArrowPatch(
        (xs[4] + width / 2, y),
        (xs[1] + width / 2, y),
        connectionstyle="arc3,rad=-0.42",
        arrowstyle="-|>",
        mutation_scale=13,
        linewidth=1.4,
        linestyle="--",
        color=BLUE,
    )
    ax.add_patch(return_arrow)
    ax.text(
        0.60,
        0.11,
        "次日 0:00 重新预测并锁定自己的购电计划；不提前锁定次日 $q$",
        ha="center",
        color=BLUE,
        fontsize=9.5,
    )
    ax.set_title("Q2 日前计划—日内执行—跨日 SOC 闭环机制", pad=15, fontweight="bold")
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

    fig, ax = plt.subplots(figsize=(9.0, 6.0))
    x = np.arange(2)
    ax.bar(
        x,
        planned,
        width=0.55,
        color=BLUE,
        edgecolor=BLACK,
        linewidth=0.8,
        label="计划购电费",
    )
    ax.bar(
        x,
        emergency_cost,
        width=0.55,
        bottom=planned,
        color="white",
        edgecolor=RED,
        linewidth=1.3,
        hatch="///",
        label="紧急购电费",
    )
    for index, value in enumerate(total):
        ax.text(
            x[index],
            value + total.max() * 0.018,
            f"{value:,.2f} 元",
            ha="center",
            va="bottom",
            fontweight="bold",
        )
    ax.text(
        0.5,
        total.max() * 0.70,
        f"K=8 相对原动态 K\n总成本变化 {cost_change:,.2f} 元\n"
        f"紧急购电量变化 {emergency_change:,.2f} kWh",
        ha="center",
        va="center",
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": GRAY},
    )
    ax.set_xticks(x, names)
    ax.set_ylabel("2—12 月购电成本（元）")
    ax.set_title("Q2 两套日前风险处理策略的成本构成对照", fontweight="bold")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value / 1e6:.1f} 百万"))
    ax.set_ylim(0, total.max() * 1.13)
    ax.grid(axis="y", linestyle=":", color=GRAY, alpha=0.45)
    ax.legend(loc="upper left", frameon=False)
    ax.text(
        0.0,
        -0.17,
        "注：仅比较两套日前风险处理策略；不表示储能净收益或投资成本节省。",
        transform=ax.transAxes,
        fontsize=9,
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

    fig, axes = plt.subplots(3, 1, figsize=(12.0, 10.0), sharex=True)
    ax = axes[0]
    ax.plot(hours, net_load, color=BLACK, linewidth=1.4, label="实际净负荷 $L-P$")
    ax.plot(hours, frame["planned_q_kwh"], color=BLUE, linewidth=1.25, label="锁定计划 $q$")
    ax.plot(
        hours,
        frame["actual_x_kwh"],
        color=GRAY,
        linestyle="--",
        linewidth=1.2,
        label="实际普通取电 $x$",
    )
    ax.plot(
        hours,
        frame["emergency_kwh"],
        color=RED,
        linestyle="-.",
        linewidth=1.5,
        label="紧急购电 $e$",
    )
    ax.fill_between(hours, 0, frame["emergency_kwh"], color=RED, alpha=0.12)
    ax.set_ylabel("时段电量（kWh）")
    ax.legend(ncol=4, loc="upper center", frameon=False)
    ax.grid(linestyle=":", color=GRAY, alpha=0.4)

    ax = axes[1]
    ax.axhline(0, color=GRAY, linewidth=0.8)
    ax.plot(hours, battery_net, color=BLACK, linewidth=1.2, label="电池净动作 $d-c$")
    ax.fill_between(hours, 0, battery_net, color=BLACK, alpha=0.12)
    ax.set_ylabel("$d-c$（kWh）")
    ax_price = ax.twinx()
    ax_price.step(
        hours,
        price,
        where="mid",
        color=RED,
        linestyle="--",
        linewidth=1.1,
        label="分时电价",
    )
    ax_price.set_ylabel("电价（元/kWh）", color=RED)
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax_price.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, loc="upper center", ncol=2, frameon=False)
    ax.grid(linestyle=":", color=GRAY, alpha=0.4)

    ax = axes[2]
    ax.plot(hours, frame["soc_kwh"], color=BLUE, linewidth=1.5, label="SOC")
    ax.axhline(1200, color=GRAY, linestyle="--", linewidth=1.0, label="SOC 边界")
    ax.axhline(10800, color=GRAY, linestyle="--", linewidth=1.0)
    ax.set_ylabel("SOC（kWh）")
    ax.set_xlabel("时刻")
    ax.set_ylim(700, 11300)
    ax.legend(loc="upper center", ncol=2, frameon=False)
    ax.grid(linestyle=":", color=GRAY, alpha=0.4)
    axes[-1].set_xlim(0, 24)
    axes[-1].set_xticks(np.arange(0, 25, 2))
    axes[-1].set_xticklabels([f"{hour:02d}:00" for hour in range(0, 25, 2)])
    fig.suptitle(
        f"Q2 日前—日内联动轨迹：{date:%Y-%m-%d}（紧急费用最高日）",
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.965))
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

    fig, ax = plt.subplots(figsize=(13.0, 5.2))
    for index, row in selected.iterrows():
        start = row["effective_start_date"]
        end_exclusive = row["effective_end_date"] + pd.Timedelta(days=1)
        if row["fixed_k"] == 1:
            y = 0.555
            color = GRAY
            linestyle = "--"
        else:
            y = float(row["risk_alpha"])
            color = BLUE
            linestyle = "-"
        ax.hlines(y, start, end_exclusive, color=color, linewidth=4.0, linestyle=linestyle)
        ax.plot(start, y, marker="o", markersize=3.5, color=color)
        ax.axvline(start, color=GRAY, linewidth=0.45, linestyle=":", alpha=0.55)
    ax.axvspan(
        pd.Timestamp("2025-01-01"),
        pd.Timestamp("2025-01-29"),
        color=GRAY,
        alpha=0.10,
        label="前 28 日：K=1 / 无风险储备",
    )
    ax.text(
        pd.Timestamp("2025-01-15"),
        0.575,
        "K=1\n无风险储备",
        ha="center",
        va="bottom",
        color=BLACK,
    )
    ax.text(
        0.995,
        0.96,
        "K=8 阶段候选集：α∈{0.60, 0.70, 0.80, 0.90}\n"
        "每次仅使用此前已结束日的结果选择",
        transform=ax.transAxes,
        ha="right",
        va="top",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": GRAY},
    )
    ax.set_ylim(0.53, 0.94)
    ax.set_yticks([0.6, 0.7, 0.8, 0.9])
    ax.set_ylabel("选定风险分位 α")
    ax.set_xlabel("风险分位生效区间（每 14 日一块）")
    ax.set_title("Q2 滚动风险分位的因果校准时间线", fontweight="bold")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_xlim(pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-01"))
    ax.grid(axis="y", linestyle=":", color=GRAY, alpha=0.45)
    fig.autofmt_xdate(rotation=30, ha="right")
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
        f"- 日数核验：α=0.60 为 {f4['alpha_060_days']} 日，α=0.70 为 "
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

