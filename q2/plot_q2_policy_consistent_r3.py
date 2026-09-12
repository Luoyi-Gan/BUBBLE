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
            labels.append(f"{mode}, α={alpha:.2f}")

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
