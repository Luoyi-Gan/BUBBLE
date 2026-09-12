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
