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
    ytick_labels = ["预热 / 无风险分位", "α = 0.60", "α = 0.70", "α = 0.80", "α = 0.90"]
    year_start = mdates.date2num(pd.Timestamp("2025-01-01").to_pydatetime())
    year_end = mdates.date2num(pd.Timestamp("2026-01-01").to_pydatetime())
    for y in range(5):
        ax.barh(y, year_end - year_start, left=year_start, height=0.62, color=LIGHT_GRAY, edgecolor="none", zorder=0)
    ax.axvspan(pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-29"), color=GRAY, alpha=0.10, zorder=1)
    for row in selected.itertuples():
        start = mdates.date2num(pd.Timestamp(row.effective_start_date).to_pydatetime())
        end = mdates.date2num((pd.Timestamp(row.effective_end_date) + pd.Timedelta(days=1)).to_pydatetime())
        if row.risk_alpha is None:
            y = y_map[None]
            ax.barh(y, end - start, left=start, height=0.62, color="white", edgecolor=BLACK, linewidth=0.8, hatch="///", zorder=3)
        else:
            alpha = float(row.risk_alpha)
            y = y_map[alpha]
            ax.barh(y, end - start, left=start, height=0.62, color=BLUE, edgecolor=BLUE, linewidth=0.8, zorder=3)
            if alpha == 0.7:
                ax.text((start + end) / 2, y, "α=0.70", ha="center", va="center", fontsize=8.2, color="white", zorder=4)
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
        f"候选集 α∈{{0.60, 0.70, 0.80, 0.90}}；校准走官方闭环。"
        f"{EXPECTED_Q4_2_ALPHA070_START[5:]}–{EXPECTED_Q4_2_ALPHA070_END[5:]} 为唯一 α=0.70 窗口，其余预热后为 α=0.60。",
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
        f"- α=0.60 为 {f4['alpha_060_days']} 日，α=0.70 为 {f4['alpha_070_days']} 日（{f4['alpha_070_window']}）。",
        "",
        "## 只读保护",
        "",
        "- 绘图脚本对日汇总、α 选择表与 result4/result3 工作簿执行前后 SHA-256 校验。",
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
