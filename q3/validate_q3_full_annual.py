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
    if (ROOT / "output" / "result3.xlsx").exists():
        raise SystemExit("result3.xlsx must not be written by the annual run")

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
        "**不**生成 `result3.xlsx`，**不**实现 M5，**不**把两案平均成一个主结论。",
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
