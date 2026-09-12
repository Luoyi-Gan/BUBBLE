"""Conceptual figures for Q3 paper. No unsigned annual numbers."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

from templates.plotting import FIG, use_cjk_font

OUT = FIG / "q3_paper"
NAVY = "#1f4e79"
TEAL = "#2a9d8f"
ORANGE = "#e09f3e"
PURPLE = "#6d597a"
GRAY = "#6c757d"
LIGHT = "#eef4f8"


def _setup() -> None:
    use_cjk_font()
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "figure.dpi": 160,
            "savefig.dpi": 320,
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "medium",
        }
    )
    OUT.mkdir(parents=True, exist_ok=True)


def _save(fig: plt.Figure, name: str) -> Path:
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def fig_info_timeline() -> Path:
    fig, ax = plt.subplots(figsize=(10.2, 4.6))
    ax.set_xlim(0, 24)
    ax.set_ylim(0, 5.2)
    ax.set_xlabel("时钟时刻 / h")
    ax.set_yticks([1.0, 2.2, 3.4, 4.4])
    ax.set_yticklabels(
        [
            "执行层（每 10 min）",
            "可改写的普通购电承诺",
            "预测信息集",
            "决策时点",
        ]
    )
    ax.set_xticks([0, 6, 12, 18, 24])
    ax.grid(axis="x", linestyle=":", alpha=0.45)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    windows = [
        (0.0, 6.0, NAVY, "g0（0:00 原计划）"),
        (6.0 + 1 / 6, 12.0, TEAL, "6:10 起可调"),
        (12.0 + 1 / 6, 18.0, ORANGE, "12:10 起可调"),
        (18.0 + 1 / 6, 24.0, PURPLE, "18:10 起可调"),
    ]
    for x0, x1, color, label in windows:
        ax.add_patch(
            FancyBboxPatch(
                (x0, 1.85),
                x1 - x0,
                0.7,
                boxstyle="round,pad=0.02,rounding_size=0.08",
                facecolor=color,
                edgecolor="none",
                alpha=0.88,
            )
        )
        ax.text((x0 + x1) / 2, 2.2, label, ha="center", va="center", color="white", fontsize=8.5)

    ax.add_patch(
        FancyBboxPatch(
            (0.0, 0.65),
            24.0,
            0.7,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            facecolor=LIGHT,
            edgecolor=NAVY,
            linewidth=1.1,
        )
    )
    ax.text(
        12,
        1.0,
        "当前步用真实负荷、光伏与 SOC；未来步只用已发布预测",
        ha="center",
        va="center",
        color=NAVY,
        fontsize=9,
    )

    for hour, color, text in [
        (0, NAVY, "0:00\n附件3 + 因果负荷"),
        (6, TEAL, "6:00\n新光伏预报"),
        (12, ORANGE, "12:00\n新光伏预报"),
        (18, PURPLE, "18:00\n新光伏预报"),
    ]:
        ax.scatter([hour], [4.4], s=80, color=color, zorder=5)
        ax.vlines(hour, 2.55, 4.25, colors=color, linestyles="--", linewidth=1.0, alpha=0.75)
        ax.text(hour + 0.15, 3.55, text, color=color, fontsize=8, va="center")

    ax.set_title("问题三的信息到达与承诺锁定窗口")
    return _save(fig, "fig3_info_timeline.png")


def fig_settlement() -> Path:
    g0 = 1.0
    g = np.linspace(0.0, 2.0, 400)
    p = 1.0
    phi = p * g + 0.5 * p * np.abs(g - g0)
    naive = np.where(g <= g0, p * g0 + 0.5 * p * (g0 - g), p * g0 + 1.5 * p * (g - g0))

    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    ax.plot(g, phi, color=NAVY, lw=2.4, label="主口径  phi = p gF + 0.5 p |gF - g0|")
    ax.plot(
        g,
        naive,
        color=ORANGE,
        lw=1.6,
        ls="--",
        label="字面重复计费（仅附录敏感性）",
    )
    ax.axvline(g0, color=GRAY, ls=":", lw=1.2)
    ax.scatter([g0], [p * g0], color=TEAL, s=55, zorder=5)
    ax.annotate(
        "未调整：gF = g0，费用 p g0",
        xy=(g0, p * g0),
        xytext=(1.15, 0.55),
        fontsize=8.5,
        color=TEAL,
        arrowprops=dict(arrowstyle="->", color=TEAL, lw=0.9),
    )
    ax.text(0.22, 1.35, "下调：取用电按正常价\n取消量按 50% 结算", color=NAVY, fontsize=8.5)
    ax.text(1.38, 2.05, "上调：原量正常价\n增量按 1.5 倍", color=PURPLE, fontsize=8.5)
    ax.set_xlabel("最终有效承诺 gF / 相对单位")
    ax.set_ylabel("时段结算费用 phi / 相对单位")
    ax.set_title("调整结算锚定 0:00 原计划，且不对取消量重复收正常电价")
    ax.legend(frameon=False, loc="upper left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _save(fig, "fig3_settlement_phi.png")


def fig_voi_flow() -> Path:
    fig, ax = plt.subplots(figsize=(9.6, 4.8))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("M1/M6：把“是否采用新预测”写成可计算的信息价值")

    boxes = [
        (0.4, 3.4, 2.6, 1.6, NAVY, "更新时点 τ\n已知当前 SOC 与新光伏预报\n已锁定时段保持不变"),
        (3.6, 4.15, 2.7, 1.35, GRAY, "固定承诺 J_fix\n维持更新前计划"),
        (3.6, 2.25, 2.7, 1.35, TEAL, "自由调整 J_free\n未执行承诺可改"),
        (7.0, 3.4, 2.2, 1.6, ORANGE, "VoI = J_fix − J_free"),
        (9.6, 4.25, 2.1, 1.2, TEAL, "VoI > ε\n写入新承诺"),
        (9.6, 2.15, 2.1, 1.2, PURPLE, "VoI ≤ ε\n维持原承诺"),
    ]
    for x, y, w, h, color, text in boxes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.03,rounding_size=0.12",
                facecolor=color,
                edgecolor="none",
                alpha=0.92,
            )
        )
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color="white", fontsize=8.6)

    arrows = [
        ((3.0, 4.2), (3.6, 4.8)),
        ((3.0, 4.2), (3.6, 2.95)),
        ((6.3, 4.8), (7.0, 4.4)),
        ((6.3, 2.95), (7.0, 4.0)),
        ((9.2, 4.5), (9.6, 4.85)),
        ((9.2, 3.9), (9.6, 2.75)),
    ]
    for (x0, y0), (x1, y1) in arrows:
        ax.add_patch(
            FancyArrowPatch(
                (x0, y0),
                (x1, y1),
                arrowstyle="-|>",
                mutation_scale=10,
                lw=1.1,
                color=GRAY,
            )
        )
    ax.text(
        6.0,
        0.7,
        "保持原承诺始终可行，且调整费已进入目标，故 ε=0 时 M1 与 M6 经济等价。\n"
        "ε=0.01 元只抑制浮点微调，不是人为市场阈值。",
        ha="center",
        va="center",
        color=NAVY,
        fontsize=8.5,
    )
    return _save(fig, "fig3_voi_decision.png")


def fig_q2_to_q3() -> Path:
    fig, ax = plt.subplots(figsize=(10.4, 4.2))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    ax.set_title("四问主线中问题三只放宽“承诺何时可改”，不另起物理模型")

    nodes = [
        (0.4, 2.6, 2.6, 1.7, NAVY, "问题一\n完全信息日前 LP\n公共母线 + 日循环 SOC"),
        (3.6, 2.6, 2.8, 1.7, TEAL, "问题二共享框架\n0:00 锁定普通购电\n日内滚动执行，SOC 跨日"),
        (7.1, 2.6, 2.9, 1.7, ORANGE, "问题三\n6/12/18 评估未执行承诺\n调整费 + 实时补救"),
        (10.5, 2.6, 2.2, 1.7, PURPLE, "问题四\n电价亦须因果预测\n（不提前写入本问）"),
    ]
    for x, y, w, h, color, text in nodes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.04,rounding_size=0.12",
                facecolor=color,
                edgecolor="none",
                alpha=0.9,
            )
        )
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color="white", fontsize=8.7)

    for x0, x1 in [(3.0, 3.6), (6.4, 7.1), (10.0, 10.5)]:
        ax.add_patch(
            FancyArrowPatch(
                (x0, 3.45),
                (x1, 3.45),
                arrowstyle="-|>",
                mutation_scale=12,
                lw=1.4,
                color=GRAY,
            )
        )

    ax.add_patch(
        FancyBboxPatch(
            (3.6, 0.45),
            6.4,
            1.7,
            boxstyle="round,pad=0.04,rounding_size=0.12",
            facecolor=LIGHT,
            edgecolor=NAVY,
            linewidth=1.0,
        )
    )
    ax.text(
        6.8,
        1.3,
        "继承：公共母线物理、跨日 SOC、日初锁定普通购电、日内滚动执行。\n"
        "本问新增：6/12/18 改写未执行承诺、非对称调整结算、附件 3 预报更新。",
        ha="center",
        va="center",
        color=NAVY,
        fontsize=8.6,
    )
    return _save(fig, "fig3_q2_to_q3_overview.png")


def main() -> None:
    _setup()
    written = [
        fig_info_timeline(),
        fig_settlement(),
        fig_voi_flow(),
        fig_q2_to_q3(),
    ]
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
