#!/usr/bin/env python3
"""C2-R1: two-day policy-consistent closed loop. Never writes result2.xlsx."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    E_INITIAL_KWH,
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    PILOT_DATES,
    POLICY_CONSISTENT_OUTPUT_DIR,
)
from q2.data import load_q2_data, write_input_audit  # noqa: E402
from q2.policy_consistent import (  # noqa: E402
    FORECAST_MODES,
    R1_DEFAULT_ALPHA,
    R1_DEFAULT_MODE,
    build_baseline_value_cuts,
    build_forecast_archive_mode,
    mode_diagnostics,
    plan_closed_loop_day,
)


def file_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_protected() -> dict[str, str | None]:
    protected = [ROOT / "output" / "result2.xlsx"]
    if FULL_K8_RISK_OUTPUT_DIR.exists():
        protected.extend(sorted(FULL_K8_RISK_OUTPUT_DIR.rglob("*")))
    return {str(path.relative_to(ROOT)): file_hash(path) for path in protected if path.is_file()}


def main() -> None:
    started = perf_counter()
    output = POLICY_CONSISTENT_OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    dispatch_dir = output / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    before = snapshot_protected()

    data = load_q2_data()
    write_input_audit(data, output / "input_audit.json")
    archives = {mode: build_forecast_archive_mode(data, mode) for mode in FORECAST_MODES}
    archive = archives[R1_DEFAULT_MODE]

    forecast_rows: list[dict] = []
    diagnostic_rows: list[dict] = []
    summaries: list[dict] = []
    value_rows: list[dict] = []
    physical_rows: list[dict] = []

    for date_text in PILOT_DATES:
        i = int(data.dates.get_loc(pd.Timestamp(date_text)))
        diagnostic_rows.extend(
            mode_diagnostics(data, i, archives, R1_DEFAULT_ALPHA, k=FIXED_SCENARIO_K)
        )
        cuts, cut_rows = build_baseline_value_cuts(
            data,
            archive,
            i,
            R1_DEFAULT_MODE,
            k=FIXED_SCENARIO_K,
            risk_alpha=R1_DEFAULT_ALPHA,
        )
        value_rows.extend({"decision_date": date_text, **row} for row in cut_rows)
        summary, _frame, plan, q_floor, scenarios = plan_closed_loop_day(
            data,
            archive,
            i,
            E_INITIAL_KWH,
            mode=R1_DEFAULT_MODE,
            risk_alpha=R1_DEFAULT_ALPHA,
            k=FIXED_SCENARIO_K,
            terminal_value_cuts=cuts,
            dispatch_path=dispatch_dir / f"dispatch_{date_text}.csv",
        )
        if not summary["pass"]:
            raise AssertionError(f"physical validation failed on {date_text}")
        summary["soc_source"] = "R1_isolated_E_INITIAL_6000"
        summary["stage"] = "C2-R1"
        summaries.append(summary)
        forecast_rows.append(
            {
                "date": date_text,
                "forecast_mode": summary["forecast_mode"],
                "risk_alpha": summary["risk_alpha"],
                "scenario_k": summary["scenario_k"],
                "load_source_dates": summary["load_source_dates"],
                "pv_source_dates": summary["pv_source_dates"],
                "residual_pool_end_date": summary["residual_pool_end_date"],
                "medoid_dates": summary["medoid_dates"],
                "load_fallback": summary["load_fallback"],
                "pv_fallback": summary["pv_fallback"],
                "risk_q_floor_kwh": summary["risk_q_floor_kwh"],
                "has_scenario_specific_battery": summary["has_scenario_specific_battery"],
                "day_ahead_variable_shapes": json.dumps(
                    summary["day_ahead_variable_shapes"], ensure_ascii=False
                ),
            }
        )
        physical_rows.append(
            {
                "date": date_text,
                "pass": summary["pass"],
                "planned_q_sha256": summary["planned_q_sha256"],
                "max_balance_residual_kwh": summary["max_balance_residual_kwh"],
                "max_x_minus_q_kwh": summary["max_x_minus_q_kwh"],
                "max_simultaneous_cd_kwh2": summary["max_simultaneous_cd_kwh2"],
                "soc_start_kwh": summary["soc_start_kwh"],
                "soc_end_kwh": summary["soc_end_kwh"],
                "unused_plan_kwh": summary["unused_plan_kwh"],
                "emergency_kwh": summary["emergency_kwh"],
                "curtailment_kwh": summary["curtailment_kwh"],
                "used_full_day_actual_lp": summary["used_full_day_actual_lp"],
                "future_actuals_in_optimizer": summary["future_actuals_in_optimizer"],
            }
        )
        _ = plan, q_floor, scenarios

    pd.DataFrame(forecast_rows).to_csv(output / "forecast_policy_audit.csv", index=False)
    pd.DataFrame(diagnostic_rows).to_csv(output / "forecast_diagnostics.csv", index=False)
    pd.DataFrame(summaries).drop(columns=["day_ahead_variable_shapes"]).to_csv(
        output / "r1_day_summary.csv", index=False
    )
    pd.DataFrame(value_rows).to_csv(output / "next_day_value_audit.csv", index=False)
    pd.DataFrame(physical_rows).to_csv(output / "physical_audit.csv", index=False)

    consistency = {
        "stage": "C2-R1",
        "policy": (
            "single baseline-forecast day-ahead LP plus K=8 risk reserve "
            "and residual-matching 10-minute MPC"
        ),
        "forecast_mode_main_path": R1_DEFAULT_MODE.value,
        "risk_alpha_main_path": R1_DEFAULT_ALPHA,
        "scenario_k": FIXED_SCENARIO_K,
        "k_used_for": ["risk_reserve_R", "intra_day_residual_weights"],
        "k_not_used_for": [
            "scenario_specific_charge",
            "scenario_specific_discharge",
            "scenario_specific_soc",
            "full_path_scenario_storage_recourse",
        ],
        "calibration_closed_loop": False,
        "annual_run": False,
        "candidate_result2_xlsx": False,
        "validation_uses_full_day_actual_lp": False,
        "formal_execution_uses_full_day_actual_lp": False,
        "forecast_history_strictly_prior": True,
        "residual_pool_strictly_prior": True,
        "current_period_actuals_only": True,
        "soc_source_r1": "isolated E_INITIAL=6000 kWh; January warmup is deferred to C2-R3",
        "dates": list(PILOT_DATES),
        "elapsed_seconds": perf_counter() - started,
    }
    (output / "policy_consistency_audit.json").write_text(
        json.dumps(consistency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "status": "PASS" if all(row["pass"] for row in summaries) else "FAIL",
        "stage": "C2-R1",
        "days": summaries,
        "protected_outputs_unchanged": snapshot_protected() == before,
        "candidate_result2_xlsx": False,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Q2 政策一致重设计 · C2-R1",
        "",
        f"- 状态：**{report['status']}**",
        "- 本阶段只交付独立模块、单元测试和 2025-02-01、2025-06-21 两日闭环试运行。",
        "- 日前 LP 只在单一基准预测轨迹上锁定 q，并施加 q≥R(α)。",
        "- K=8 只用于风险储备 R 与日内残差匹配权重，不创建情景专属充放电/SOC 变量。",
        "- 日内只把当期实际负荷/光伏写入当前时段；未来时段使用残差匹配点预测。",
        "- 未运行 14 日联合校准、未运行全年、未导出候选 result2.xlsx。",
        "- 两日初值均记录为孤立试算的 6000 kWh；1 月预热与 2 月初 SOC 敏感性留到 C2-R3。",
        f"- 主路径预注册：m={R1_DEFAULT_MODE.value}，α={R1_DEFAULT_ALPHA}，K={FIXED_SCENARIO_K}。",
        "- MAE/覆盖率只写入 `forecast_diagnostics.csv`，不作为选择准则。",
        "",
    ]
    for item in summaries:
        lines += [
            f"## {item['date']}",
            "",
            f"- 计划费 {item['planned_cost_yuan']:.6f} 元，紧急费 {item['emergency_cost_yuan']:.6f} 元，"
            f"实际总成本 {item['total_cost_yuan']:.6f} 元。",
            f"- 未用计划电 {item['unused_plan_kwh']:.6f} kWh，紧急购电 {item['emergency_kwh']:.6f} kWh。",
            f"- SOC {item['soc_start_kwh']:.6f} → {item['soc_end_kwh']:.6f} kWh。",
            f"- 最大平衡残差 {item['max_balance_residual_kwh']:.3e} kWh；通过={item['pass']}。",
            "",
        ]
    (output / "validation.md").write_text("\n".join(lines), encoding="utf-8")

    after = snapshot_protected()
    if after != before:
        raise RuntimeError("Protected old Q2 outputs were modified")
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
