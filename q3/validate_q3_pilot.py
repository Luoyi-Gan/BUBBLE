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
        "提交给 Codex/队长复核。本阶段**不**生成 `result3.xlsx`，**不**实现 M5。",
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
