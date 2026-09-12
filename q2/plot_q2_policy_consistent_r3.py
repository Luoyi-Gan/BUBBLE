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
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import FIG_POLICY_CONSISTENT_DIR, OFFICIAL_OUTPUT_START


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

    names = ["旧 Q2：K=8 风险分位", "新政策：基准 LP + 残差 MPC"]
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
    ax.set_title("政策一致重设计与旧 Q2 方案的成本构成对照", pad=18)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value / 1e6:.1f} 百万"))
    ax.set_ylim(0, total.max() * 1.12)
    ax.set_xlim(-0.55, 1.55)
    style_axes(ax)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2, frameon=False, borderaxespad=0.0)
    fig.subplots_adjust(bottom=0.22, top=0.86)
    fig.text(
        0.5,
        0.085,
        f"新政策相对旧 K=8：总成本变化 {total[1] - total[0]:,.2f} 元；"
        f"紧急购电量变化 {emergency_kwh[1] - emergency_kwh[0]:,.2f} kWh",
        ha="center",
        fontsize=9.5,
        bbox={"boxstyle": "round,pad=0.38", "facecolor": LIGHT_GRAY, "edgecolor": GRAY},
    )
    fig.text(
        0.5,
        0.02,
        "注：1 月仅作预热，不进入正式对照；两套方案均按计划额度 q 计费、紧急电价 5 倍。",
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
        ax.plot(old["date"], old[column], color=GRAY, linewidth=1.05, label="旧 Q2：K=8", zorder=2)
        ax.plot(new["date"], new[column], color=color, linewidth=1.25, label="新政策", zorder=3)
        ax.set_ylabel(ylabel)
        style_axes(ax)
        ax.legend(frameon=False, loc="upper right")
    axes[0].set_title("2—12 月紧急购电与弃光逐日对照")
    style_time_axis(axes[1])
    fig.tight_layout()
    save_figure(fig, "fig_q2_pc_emergency_curtailment", target)

    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    ax.plot(old["date"], old["soc_end_kwh"], color=GRAY, linewidth=1.1, label="旧 Q2：K=8")
    ax.plot(new["date"], new["soc_end_kwh"], color=BLUE, linewidth=1.3, label="新政策")
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
        label="旧 Q2：K=8",
    )
    ax.plot(
        new["date"],
        new["total_cost_yuan"].cumsum(),
        color=BLUE,
        linewidth=1.4,
        label="新政策",
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


if __name__ == "__main__":
    from q2.config import FULL_K8_RISK_OUTPUT_DIR, POLICY_CONSISTENT_OUTPUT_DIR

    plot_r3_comparison(
        pd.read_csv(POLICY_CONSISTENT_OUTPUT_DIR / "q2_redesign_daily_summary.csv"),
        pd.read_csv(FULL_K8_RISK_OUTPUT_DIR / "daily_summary.csv"),
    )
