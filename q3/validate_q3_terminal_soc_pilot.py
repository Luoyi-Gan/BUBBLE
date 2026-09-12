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
