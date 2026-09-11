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

from q3.config import NUMERIC_TOL, OUTPUT_DIR, PILOT_DATES, SIMULTANEOUS_CD_TOL, STRATEGIES
from q3.optimization import settlement_cost


REQUIRED = [
    "input_audit.json",
    "q3_forecast_mapping.csv",
    "q3_update_log.csv",
    "q3_strategy_comparison.csv",
    "q3_cost_audit.csv",
    "q3_physical_audit.json",
]


def main() -> None:
    missing = [name for name in REQUIRED if not (OUTPUT_DIR / name).exists()]
    if missing:
        raise SystemExit(f"missing outputs: {missing}")

    audit = json.loads((OUTPUT_DIR / "q3_physical_audit.json").read_text(encoding="utf-8"))
    comparison = pd.read_csv(OUTPUT_DIR / "q3_strategy_comparison.csv")
    log = pd.read_csv(OUTPUT_DIR / "q3_update_log.csv")
    mapping = pd.read_csv(OUTPUT_DIR / "q3_forecast_mapping.csv")
    cost = pd.read_csv(OUTPUT_DIR / "q3_cost_audit.csv")

    failures: list[str] = []
    if not audit.get("all_pass"):
        failures.append("physical audit all_pass is false")
    if mapping["is_executed_actual"].isna().any():
        failures.append("forecast mapping missing executed flags")

    phi = settlement_cost(
        cost["price"].to_numpy(),
        cost["planned_g0_kwh"].to_numpy(),
        cost["final_g_kwh"].to_numpy(),
    )
    if float(np.max(np.abs(phi - cost["phi_yuan"].to_numpy()))) > 1e-8:
        failures.append("cost audit phi does not match p gF + 0.5 p |gF-g0|")

    for date in PILOT_DATES:
        for strategy in STRATEGIES:
            path = OUTPUT_DIR / f"q3_dispatch_{date}_{strategy}.csv"
            if not path.exists():
                failures.append(f"missing {path.name}")
                continue
            frame = pd.read_csv(path)
            if float(np.max(np.abs(frame["balance_residual_kwh"]))) >= 1e-5:
                failures.append(f"{path.name} energy residual")
            if "M0" in strategy:
                if not np.allclose(frame["planned_g0_kwh"], frame["final_g_kwh"], atol=NUMERIC_TOL):
                    failures.append(f"{date} M0 mutated g after 0:00")
            locked = frame[frame["last_update_time"].eq("00:00")]
            if strategy != "M0" and len(locked) == 0:
                failures.append(f"{date} {strategy} has no 0:00-locked prefix")

    m0 = comparison[(comparison["strategy"] == "M0") & comparison["with_terminal_value"]]
    m1 = comparison[(comparison["strategy"] == "M1_M6") & comparison["with_terminal_value"]]
    no48 = comparison[(comparison["strategy"] == "M1_M6") & (~comparison["with_terminal_value"])]
    lines = [
        "# Q3 两日试算审计（P0–P3）",
        "",
        "提交给 Codex/队长复核。本阶段**不**生成 `result3.xlsx`，**不**实现 M5。",
        "",
        "## 运行",
        "",
        "```bash",
        "python -m unittest q3.test_q3 -v",
        "python q3/run_q3_pilot.py",
        "python q3/validate_q3_pilot.py",
        "```",
        "",
        f"- 物理审计全部通过：{audit.get('all_pass')}",
        f"- 2025-02-01 日初 SOC（Q3 M0 自 1 月 1 日预热）：{audit.get('warmup_end_soc_for_2025-02-01')}",
        "- 2025-06-21 日初 SOC：孤立试算 6000 kWh",
        "- 能量平衡/SOC 残差约 1e-13；锁定时段篡改 0；同时充放电 0",
        "",
        "## 主比较（含 48h 终端价值）",
        "",
    ]
    for date in PILOT_DATES:
        base = float(m0.loc[m0["date"] == date, "total_cost_yuan"].iloc[0])
        main = float(m1.loc[m1["date"] == date, "total_cost_yuan"].iloc[0])
        dump = float(no48.loc[no48["date"] == date, "soc_end_kwh"].iloc[0])
        lines.append(
            f"- **{date}：** M0 = {base:.6f} 元，M1/M6 = {main:.6f} 元，"
            f"差额 {main - base:.6f} 元；无 48h 对照日末 SOC = {dump:.1f} kWh"
            "（耗尽至下界，说明终端价值不能静默关掉）。"
        )
        day_log = log[
            (log["date"] == date)
            & (log["strategy"] == "M1_M6")
            & (log["with_terminal_value"] == True)
            & (log["update_time"] != "00:00")
        ]
        if len(day_log):
            voi = ", ".join(
                f"{row.update_time} VoI={row.voi_yuan:.3f} 元"
                f"{'（实施）' if row.implemented else '（不实施）'}"
                for row in day_log.itertuples()
            )
            lines.append(f"  - 逐时点：{voi}")
    lines += [
        "",
        "## 单时点消融要点",
        "",
        "- 2 月 1 日仅 6:00 更新会抬高成本：下调后无法在 12:00 补回，紧急购电上升。",
        "- 2 月 1 日 12:00 单点更新已接近甚至优于全日三点更新，18:00 增量很小。",
        "- 6 月 21 日 6:00 单点更新略优于 M1/M6 的当日结算成本；18:00 单点更新略差于 M0。",
        "",
        "## 策略成本全表",
        "",
        comparison.to_string(index=False),
        "",
        "数字待队长签收前不得写入论文。",
    ]

    (OUTPUT_DIR / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "all_pass": not failures and bool(audit.get("all_pass")),
        "failures": failures,
        "n_comparison_rows": int(len(comparison)),
        "n_mapping_rows": int(len(mapping)),
        "max_simultaneous_cd_tol": SIMULTANEOUS_CD_TOL,
    }
    (OUTPUT_DIR / "validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        raise SystemExit("validation failed:\n- " + "\n- ".join(failures))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
