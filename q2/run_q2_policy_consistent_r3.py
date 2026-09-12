#!/usr/bin/env python3
"""C2-R3: official year path, January/Feb-Dec split, SOC and K sensitivities.

Never writes result2.xlsx. Frozen (m, α) calendar comes from C2-R2.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import (  # noqa: E402
    E_INITIAL_KWH,
    FIG_POLICY_CONSISTENT_DIR,
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    K_SENSITIVITY_CANDIDATES,
    OFFICIAL_OUTPUT_START,
    POLICY_CONSISTENT_OUTPUT_DIR,
)
from q2.data import load_q2_data  # noqa: E402
from q2.plot_q2_policy_consistent_r3 import plot_r3_comparison  # noqa: E402
from q2.policy_consistent import (  # noqa: E402
    FORECAST_MODES,
    PERIOD_FEB_DEC_OUTPUT,
    PERIOD_JANUARY_WARMUP,
    aggregate_cost_row,
    build_forecast_archive_mode,
    k_sensitivity_conclusion,
    output_period,
    run_frozen_policy_path,
    selected_calendar_for_dates,
)


R1_COPIES = (
    ("forecast_policy_audit.csv", "r1_forecast_policy_audit.csv"),
    ("physical_audit.csv", "r1_physical_audit.csv"),
    ("next_day_value_audit.csv", "r1_next_day_value_audit.csv"),
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


def preserve_r1_artifacts(output: Path) -> None:
    for source_name, dest_name in R1_COPIES:
        source = output / source_name
        dest = output / dest_name
        if source.exists() and not dest.exists():
            shutil.copy2(source, dest)
    r1_dispatch = output / "r1_dispatch_daily"
    dispatch = output / "dispatch_daily"
    if dispatch.exists() and not r1_dispatch.exists():
        r1_dispatch.mkdir(parents=True, exist_ok=True)
        for path in dispatch.glob("dispatch_*.csv"):
            shutil.copy2(path, r1_dispatch / path.name)


def split_period(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    january = daily.loc[daily["period"] == PERIOD_JANUARY_WARMUP].copy()
    feb_dec = daily.loc[daily["period"] == PERIOD_FEB_DEC_OUTPUT].copy()
    return january, feb_dec


def main() -> None:
    started = perf_counter()
    output = POLICY_CONSISTENT_OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    dispatch_dir = output / "dispatch_daily"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    before = snapshot_protected()
    preserve_r1_artifacts(output)

    calibration_path = output / "closed_loop_calibration.csv"
    if not calibration_path.exists():
        raise FileNotFoundError("C2-R3 requires closed_loop_calibration.csv from C2-R2")

    data = load_q2_data()
    archives = {mode: build_forecast_archive_mode(data, mode) for mode in FORECAST_MODES}
    calendar = selected_calendar_for_dates(
        pd.read_csv(calibration_path), data.dates
    )
    feb_index = int(data.dates.get_loc(pd.Timestamp(OFFICIAL_OUTPUT_START)))
    year_end = len(data.dates) - 1
    cut_cache: dict = {}

    print("C2-R3 main path K=8 with next-day value cuts", flush=True)
    main_daily, main_forecast, main_physical, main_value = run_frozen_policy_path(
        data,
        archives,
        calendar,
        start_index=0,
        end_index=year_end,
        initial_soc=E_INITIAL_KWH,
        requested_k=FIXED_SCENARIO_K,
        soc_source="january_1_E_INITIAL_6000_then_inherited",
        include_value_cuts=True,
        dispatch_dir=dispatch_dir,
        cut_cache=cut_cache,
        progress_label="C2-R3-main",
    )
    daily = pd.DataFrame(main_daily)
    if list(daily["date"]) != [stamp.strftime("%Y-%m-%d") for stamp in data.dates]:
        raise AssertionError("main path does not cover the full year")
    if abs(float(daily["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) > 1e-8:
        raise AssertionError("main path must start at 6000 kWh on 2025-01-01")
    january, feb_dec = split_period(daily)
    if len(january) != 31 or len(feb_dec) != 334:
        raise AssertionError("January warmup / Feb-Dec split is not 31 + 334")
    inherited_feb_soc = float(january["soc_end_kwh"].iloc[-1])
    if abs(float(feb_dec["soc_start_kwh"].iloc[0]) - inherited_feb_soc) > 1e-8:
        raise AssertionError("Feb 1 SOC must inherit January 31 end SOC")
    main_elapsed = perf_counter() - started

    print(
        f"C2-R3 Feb 1 SOC sensitivity: inherited {inherited_feb_soc:.6f} vs registered {E_INITIAL_KWH:.1f}",
        flush=True,
    )
    alt_daily_rows, _alt_forecast, _alt_physical, _alt_value = run_frozen_policy_path(
        data,
        archives,
        calendar,
        start_index=feb_index,
        end_index=year_end,
        initial_soc=E_INITIAL_KWH,
        requested_k=FIXED_SCENARIO_K,
        soc_source="registered_boundary_E_INITIAL_6000",
        include_value_cuts=True,
        dispatch_dir=None,
        cut_cache=cut_cache,
        progress_label="C2-R3-feb-soc",
    )
    alt_feb_dec = pd.DataFrame(alt_daily_rows)
    if list(alt_feb_dec["date"]) != list(feb_dec["date"]):
        raise AssertionError("Feb SOC sensitivity dates differ from the main Feb-Dec path")
    if abs(float(alt_feb_dec["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) > 1e-8:
        raise AssertionError("registered Feb 1 boundary is not 6000 kWh")

    k_daily: dict[int, pd.DataFrame] = {FIXED_SCENARIO_K: daily}
    k_elapsed: dict[int, float] = {FIXED_SCENARIO_K: main_elapsed}
    for k in K_SENSITIVITY_CANDIDATES:
        if k == FIXED_SCENARIO_K:
            continue
        path_started = perf_counter()
        print(f"C2-R3 K sensitivity path K={k}", flush=True)
        rows, _forecast, _physical, _value = run_frozen_policy_path(
            data,
            archives,
            calendar,
            start_index=0,
            end_index=year_end,
            initial_soc=E_INITIAL_KWH,
            requested_k=k,
            soc_source="january_1_E_INITIAL_6000_then_inherited",
            include_value_cuts=True,
            dispatch_dir=None,
            cut_cache=cut_cache,
            progress_label=f"C2-R3-K{k}",
        )
        k_daily[k] = pd.DataFrame(rows)
        k_elapsed[k] = perf_counter() - path_started

    k_rows = []
    for k in K_SENSITIVITY_CANDIDATES:
        frame = k_daily[k]
        _, k_feb_dec = split_period(frame)
        k_rows.append(
            aggregate_cost_row(
                k_feb_dec,
                label=f"feb_dec_k{k}",
                extra={
                    "scenario_k": int(k),
                    "period": PERIOD_FEB_DEC_OUTPUT,
                    "calendar_frozen_from_r2": True,
                    "include_value_cuts": True,
                    "elapsed_seconds": float(k_elapsed[k]),
                    "mean_effective_k": float(k_feb_dec["scenario_k"].mean()),
                },
            )
        )
    conclusion = k_sensitivity_conclusion(k_rows)
    for row in k_rows:
        row["conclusion"] = conclusion

    cost_rows = [
        aggregate_cost_row(
            january,
            label="january_warmup_main",
            extra={
                "period": PERIOD_JANUARY_WARMUP,
                "scenario_k": FIXED_SCENARIO_K,
                "soc_source": "january_1_E_INITIAL_6000_then_inherited",
            },
        ),
        aggregate_cost_row(
            feb_dec,
            label="feb_dec_inherited_warmup_soc",
            extra={
                "period": PERIOD_FEB_DEC_OUTPUT,
                "scenario_k": FIXED_SCENARIO_K,
                "soc_source": "inherited_january_warmup",
                "feb1_soc_start_kwh": inherited_feb_soc,
            },
        ),
        aggregate_cost_row(
            alt_feb_dec,
            label="feb_dec_registered_boundary_6000",
            extra={
                "period": PERIOD_FEB_DEC_OUTPUT,
                "scenario_k": FIXED_SCENARIO_K,
                "soc_source": "registered_boundary_E_INITIAL_6000",
                "feb1_soc_start_kwh": E_INITIAL_KWH,
                "only_registered_boundary_changed": True,
            },
        ),
        aggregate_cost_row(
            daily,
            label="full_year_including_warmup",
            extra={
                "period": "full_year",
                "scenario_k": FIXED_SCENARIO_K,
            },
        ),
    ]

    soc_sensitivity = pd.DataFrame(
        [
            {
                "soc_source": "inherited_january_warmup",
                "feb1_soc_start_kwh": inherited_feb_soc,
                "dec31_soc_end_kwh": float(feb_dec["soc_end_kwh"].iloc[-1]),
                "n_days": int(len(feb_dec)),
                "start_date": str(feb_dec["date"].iloc[0]),
                "end_date": str(feb_dec["date"].iloc[-1]),
                "forecast_modes": ";".join(sorted(feb_dec["forecast_mode"].unique())),
                "requested_k": FIXED_SCENARIO_K,
                "planned_cost_yuan": float(feb_dec["planned_cost_yuan"].sum()),
                "emergency_cost_yuan": float(feb_dec["emergency_cost_yuan"].sum()),
                "total_cost_yuan": float(feb_dec["total_cost_yuan"].sum()),
                "emergency_kwh": float(feb_dec["emergency_kwh"].sum()),
                "unused_plan_kwh": float(feb_dec["unused_plan_kwh"].sum()),
                "curtailment_kwh": float(feb_dec["curtailment_kwh"].sum()),
                "only_registered_boundary_changed": False,
                "main_path": True,
            },
            {
                "soc_source": "registered_boundary_E_INITIAL_6000",
                "feb1_soc_start_kwh": E_INITIAL_KWH,
                "dec31_soc_end_kwh": float(alt_feb_dec["soc_end_kwh"].iloc[-1]),
                "n_days": int(len(alt_feb_dec)),
                "start_date": str(alt_feb_dec["date"].iloc[0]),
                "end_date": str(alt_feb_dec["date"].iloc[-1]),
                "forecast_modes": ";".join(sorted(alt_feb_dec["forecast_mode"].unique())),
                "requested_k": FIXED_SCENARIO_K,
                "planned_cost_yuan": float(alt_feb_dec["planned_cost_yuan"].sum()),
                "emergency_cost_yuan": float(alt_feb_dec["emergency_cost_yuan"].sum()),
                "total_cost_yuan": float(alt_feb_dec["total_cost_yuan"].sum()),
                "emergency_kwh": float(alt_feb_dec["emergency_kwh"].sum()),
                "unused_plan_kwh": float(alt_feb_dec["unused_plan_kwh"].sum()),
                "curtailment_kwh": float(alt_feb_dec["curtailment_kwh"].sum()),
                "only_registered_boundary_changed": True,
                "main_path": False,
            },
        ]
    )

    daily.to_csv(output / "q2_redesign_daily_summary.csv", index=False)
    january.to_csv(output / "january_warmup_summary.csv", index=False)
    feb_dec.to_csv(output / "feb_dec_daily_summary.csv", index=False)
    alt_feb_dec.to_csv(output / "feb_soc_sensitivity_daily.csv", index=False)
    soc_sensitivity.to_csv(output / "feb_soc_sensitivity.csv", index=False)
    pd.DataFrame(k_rows).to_csv(output / "k_sensitivity.csv", index=False)
    pd.DataFrame(cost_rows).to_csv(output / "cost_breakdown.csv", index=False)
    pd.DataFrame(main_forecast).to_csv(output / "forecast_policy_audit.csv", index=False)
    pd.DataFrame(main_physical).to_csv(output / "physical_audit.csv", index=False)
    pd.DataFrame(main_value).to_csv(output / "next_day_value_audit.csv", index=False)
    pd.DataFrame(
        [
            {
                "date": policy.date,
                "forecast_mode": policy.forecast_mode.value,
                "risk_alpha": policy.risk_alpha,
                "fallback_reason": policy.fallback_reason,
                "calibration_date": policy.calibration_date,
                "effective_start_date": policy.effective_start_date,
                "effective_end_date": policy.effective_end_date,
                "period": output_period(policy.date),
            }
            for policy in calendar
        ]
    ).to_csv(output / "frozen_policy_calendar.csv", index=False)

    figures = plot_r3_comparison(
        daily,
        pd.read_csv(FULL_K8_RISK_OUTPUT_DIR / "daily_summary.csv"),
        FIG_POLICY_CONSISTENT_DIR,
    )

    after = snapshot_protected()
    protected_ok = after == before
    status = bool(
        daily["pass"].all()
        and not daily["used_full_day_actual_lp"].any()
        and not daily["future_actuals_in_optimizer"].any()
        and not alt_feb_dec["used_full_day_actual_lp"].any()
        and protected_ok
        and conclusion
    )
    consistency = {
        "stage": "C2-R3",
        "policy": (
            "single baseline-forecast day-ahead LP plus K=8 risk reserve "
            "and residual-matching 10-minute MPC"
        ),
        "k_used_for": ["risk_reserve_R", "intra_day_residual_weights"],
        "k_not_used_for": [
            "scenario_specific_charge",
            "scenario_specific_discharge",
            "scenario_specific_soc",
            "full_path_scenario_storage_recourse",
        ],
        "calendar_frozen_from_r2": True,
        "calibration_closed_loop": True,
        "mae_is_diagnostic_only": True,
        "mae_used_for_selection": False,
        "include_value_cuts": True,
        "calibration_include_value_cuts": True,
        "deployment_include_value_cuts": True,
        "annual_run_include_value_cuts": True,
        "include_value_cuts_consistent": True,
        "main_path_initial_soc_kwh": E_INITIAL_KWH,
        "main_path_initial_rule_unchanged": True,
        "january_warmup_days": int(len(january)),
        "feb_dec_days": int(len(feb_dec)),
        "february_1_inherited_soc_kwh": inherited_feb_soc,
        "february_1_sensitivity_soc_kwh": E_INITIAL_KWH,
        "k_sensitivity_candidates": list(K_SENSITIVITY_CANDIDATES),
        "k_sensitivity_conclusion": conclusion,
        "validation_uses_full_day_actual_lp": False,
        "formal_execution_uses_full_day_actual_lp": False,
        "calibration_and_execution_exclude_future_actuals": True,
        "forecast_history_strictly_prior": True,
        "residual_pool_strictly_prior": True,
        "current_period_actuals_only": True,
        "annual_run": True,
        "candidate_result2_xlsx": False,
        "elapsed_seconds": perf_counter() - started,
    }
    (output / "policy_consistency_audit.json").write_text(
        json.dumps(consistency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "status": "PASS" if status else "FAIL",
        "stage": "C2-R3",
        "january_warmup": cost_rows[0],
        "feb_dec_inherited": cost_rows[1],
        "feb_dec_soc_sensitivity": cost_rows[2],
        "k_sensitivity_conclusion": conclusion,
        "figures": figures,
        "protected_outputs_unchanged": protected_ok,
        "candidate_result2_xlsx": False,
        "annual_run": True,
        "include_value_cuts": True,
        "include_value_cuts_consistent": True,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "run_metadata.json").write_text(
        json.dumps(
            {
                "stage": "C2-R3",
                "elapsed_seconds": consistency["elapsed_seconds"],
                "n_cut_cache_entries": len(cut_cache),
                "main_path_days": int(len(daily)),
                "dispatch_dir": str(dispatch_dir.relative_to(ROOT)),
                "figure_dir": str(FIG_POLICY_CONSISTENT_DIR.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Q2 政策一致重设计 · C2-R3",
        "",
        f"- 状态：**{report['status']}**",
        "- 全年主路径从 2025-01-01 的 6000 kWh 起步，冻结 C2-R2 选定的 (m, α) 日历，"
        "并加入次日基准预测价值割。",
        "- 校准评分、获选部署与全年正式运行的 `include_value_cuts=true` 一致。",
        "- 1 月预热与 2—12 月正式输出分栏；主路径 2 月 1 日 SOC 继承 1 月 31 日末值，"
        "不修改年初初值规则。",
        f"- 1 月预热实际成本 {cost_rows[0]['total_cost_yuan']:.2f} 元；"
        f"回退预测日 {int(january['load_fallback'].sum() + january['pv_fallback'].sum())} 条"
        "（负荷/光伏回退计数）。",
        f"- 2 月 1 日继承 SOC {inherited_feb_soc:.6f} kWh；"
        f"2—12 月正式成本 {cost_rows[1]['total_cost_yuan']:.2f} 元，"
        f"紧急购电 {cost_rows[1]['emergency_kwh']:.2f} kWh。",
        f"- 2 月初登记边界敏感性（6000 kWh）2—12 月成本 "
        f"{cost_rows[2]['total_cost_yuan']:.2f} 元。",
        f"- K∈{{4,8,12}} 闭环敏感性结论：`{conclusion}`。",
        "- 未导出候选 result2.xlsx；正式附件留到 C2-R4。",
        f"- 对照图写入 `{FIG_POLICY_CONSISTENT_DIR.relative_to(ROOT)}/`。",
        "",
        "## 1 月预热",
        "",
        f"- 日数 {len(january)}，初值 {float(january['soc_start_kwh'].iloc[0]):.6f} kWh，"
        f"2 月 1 日初值 {inherited_feb_soc:.6f} kWh。",
        f"- 负荷附件1回退 {int(january['load_fallback'].sum())} 日，"
        f"光伏附件1回退 {int(january['pv_fallback'].sum())} 日。",
        "",
        "## K 敏感性（2—12 月，冻结日历）",
        "",
    ]
    for row in k_rows:
        lines.append(
            f"- K={row['scenario_k']}：总成本 {row['total_cost_yuan']:.2f} 元，"
            f"紧急购电 {row['emergency_kwh']:.2f} kWh。"
        )
    (output / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if after != before:
        raise RuntimeError("Protected old Q2 outputs were modified")
    if not status:
        raise AssertionError("C2-R3 validation failed")
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
