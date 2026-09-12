#!/usr/bin/env python3
"""C2-R4: candidate result2.xlsx, final Q2 figures, and cell-by-cell audit.

Never overwrites output/result2.xlsx. Writes only under output/q2_policy_consistent/
and fig/q2_policy_consistent/.
"""

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
    CANDIDATE_RESULT2,
    E_INITIAL_KWH,
    FIG_POLICY_CONSISTENT_DIR,
    FIG_Q2_FINAL_DIR,
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    NUMERIC_TOL,
    OFFICIAL_OUTPUT_START,
    POLICY_CONSISTENT_OUTPUT_DIR,
    RESULT2_SIGNED_OFF_BACKUP,
    SIGNED_OFF_RESULT2,
    SIGNED_OFF_RESULT2_SHA256,
)
from q2.data import load_q2_data  # noqa: E402
from q2.export_result2 import (  # noqa: E402
    N_OUTPUT_DAYS,
    audit_candidate_result2,
    file_sha256,
    preserve_signed_off_backup,
    write_candidate_result2,
    write_result2_audit,
)
from q2.plot_q2_policy_consistent_r3 import plot_r4_final_figures  # noqa: E402
from q2.policy_consistent import PERIOD_FEB_DEC_OUTPUT, PERIOD_JANUARY_WARMUP  # noqa: E402


def snapshot_protected() -> dict[str, str | None]:
    protected = [SIGNED_OFF_RESULT2]
    if FULL_K8_RISK_OUTPUT_DIR.exists():
        protected.extend(sorted(FULL_K8_RISK_OUTPUT_DIR.rglob("*")))
    if FIG_Q2_FINAL_DIR.exists():
        protected.extend(sorted(FIG_Q2_FINAL_DIR.rglob("*")))
    hashes: dict[str, str | None] = {}
    for path in protected:
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            hashes[str(path.relative_to(ROOT))] = digest.hexdigest()
    return hashes


def require_locked_main_scheme(daily: pd.DataFrame, january: pd.DataFrame, feb_dec: pd.DataFrame) -> float:
    if int(feb_dec["scenario_k"].nunique()) != 1 or int(feb_dec["scenario_k"].iloc[0]) != FIXED_SCENARIO_K:
        raise AssertionError("official Feb-Dec path is not K=8")
    if not bool(feb_dec["include_value_cuts"].all()) or not bool(january["include_value_cuts"].all()):
        raise AssertionError("official year path must keep next-day value cuts")
    if abs(float(daily["soc_start_kwh"].iloc[0]) - E_INITIAL_KWH) > NUMERIC_TOL:
        raise AssertionError("year path does not start at 6000 kWh on 2025-01-01")
    jan_dates = pd.to_datetime(january["date"])
    feb_dates = pd.to_datetime(feb_dec["date"])
    if jan_dates.iloc[0] != pd.Timestamp("2025-01-01") or jan_dates.iloc[-1] != pd.Timestamp("2025-01-31"):
        raise AssertionError("January warmup window mismatch")
    if feb_dates.iloc[0] != pd.Timestamp(OFFICIAL_OUTPUT_START) or feb_dates.iloc[-1] != pd.Timestamp("2025-12-31"):
        raise AssertionError("official output window mismatch")
    if len(january) != 31 or len(feb_dec) != N_OUTPUT_DAYS:
        raise AssertionError("January/Feb-Dec day counts mismatch")
    inherited = float(january["soc_end_kwh"].iloc[-1])
    if abs(float(feb_dec["soc_start_kwh"].iloc[0]) - inherited) > NUMERIC_TOL:
        raise AssertionError("Feb 1 does not inherit January 31 SOC")
    if (january["period"] != PERIOD_JANUARY_WARMUP).any() or (feb_dec["period"] != PERIOD_FEB_DEC_OUTPUT).any():
        raise AssertionError("period labels mismatch")
    return inherited


def main() -> None:
    started = perf_counter()
    output = POLICY_CONSISTENT_OUTPUT_DIR
    dispatch_dir = output / "dispatch_daily"
    before = snapshot_protected()
    signed_hash = preserve_signed_off_backup()
    data = load_q2_data()
    daily = pd.read_csv(output / "q2_redesign_daily_summary.csv")
    january = pd.read_csv(output / "january_warmup_summary.csv")
    feb_dec = pd.read_csv(output / "feb_dec_daily_summary.csv")
    calibration = pd.read_csv(output / "closed_loop_calibration.csv")
    k_table = pd.read_csv(output / "k_sensitivity.csv")
    inherited = require_locked_main_scheme(daily, january, feb_dec)
    conclusion = str(k_table["conclusion"].iloc[0])
    if conclusion != "retain_k8_stable":
        raise AssertionError("K=8 is not retained as the stable pre-registered scheme")
    if not dispatch_dir.exists():
        raise FileNotFoundError("C2-R4 requires the C2-R3 dispatch_daily archive")

    print("C2-R4 writing candidate result2.xlsx under output/q2_policy_consistent/", flush=True)
    write_candidate_result2(CANDIDATE_RESULT2, dispatch_dir, feb_dec, data)
    audit = audit_candidate_result2(CANDIDATE_RESULT2, dispatch_dir, feb_dec, data, inherited)
    write_result2_audit(audit, output)
    if not audit["summary"]["pass"]:
        raise AssertionError("candidate result2 cell audit failed")

    figures = plot_r4_final_figures(
        daily,
        pd.read_csv(FULL_K8_RISK_OUTPUT_DIR / "daily_summary.csv"),
        calibration,
        dispatch_dir,
        data.price,
        fig_dir=FIG_POLICY_CONSISTENT_DIR,
    )

    after = snapshot_protected()
    protected_ok = after == before and signed_hash == SIGNED_OFF_RESULT2_SHA256
    if file_sha256(SIGNED_OFF_RESULT2) != SIGNED_OFF_RESULT2_SHA256:
        raise RuntimeError("signed-off output/result2.xlsx changed during C2-R4")
    if file_sha256(RESULT2_SIGNED_OFF_BACKUP) != SIGNED_OFF_RESULT2_SHA256:
        raise RuntimeError("signed-off result2 backup is not bit-identical")
    if CANDIDATE_RESULT2.resolve() == SIGNED_OFF_RESULT2.resolve():
        raise RuntimeError("candidate path collapsed onto the signed-off file")

    previous = json.loads((output / "policy_consistency_audit.json").read_text(encoding="utf-8"))
    previous.update(
        {
            "stage": "C2-R4",
            "candidate_result2_xlsx": True,
            "candidate_result2_path": str(CANDIDATE_RESULT2.relative_to(ROOT)),
            "signed_off_result2_path": str(SIGNED_OFF_RESULT2.relative_to(ROOT)),
            "signed_off_result2_sha256": SIGNED_OFF_RESULT2_SHA256,
            "signed_off_result2_unchanged": protected_ok,
            "k8_paper_language": "预注册且对 K=4/12 稳定的简洁主方案",
            "k8_not_cost_optimal": True,
            "old_full_path_role": "信息更强的近似对照",
            "r4_elapsed_seconds": perf_counter() - started,
        }
    )
    (output / "policy_consistency_audit.json").write_text(
        json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    previous_report = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    report = {
        **previous_report,
        "status": "PASS" if audit["summary"]["pass"] and protected_ok else "FAIL",
        "stage": "C2-R4",
        "candidate_result2_xlsx": True,
        "candidate_result2_path": str(CANDIDATE_RESULT2.relative_to(ROOT)),
        "signed_off_result2_unchanged": protected_ok,
        "signed_off_result2_sha256": SIGNED_OFF_RESULT2_SHA256,
        "result2_cell_audit_pass": bool(audit["summary"]["pass"]),
        "result2_max_q_abs_kwh": audit["summary"]["max_q_abs_kwh"],
        "result2_max_planned_cost_abs_yuan": audit["summary"]["max_planned_cost_abs_yuan"],
        "result2_max_emergency_recon_abs_kwh": audit["summary"]["max_emergency_recon_abs_kwh"],
        "result2_max_soc_abs_kwh": audit["summary"]["max_soc_abs_kwh"],
        "figures": figures,
        "k8_paper_language": "预注册且对 K=4/12 稳定的简洁主方案",
        "k8_not_cost_optimal": True,
        "old_full_path_role": "信息更强的近似对照",
        "protected_outputs_unchanged": protected_ok,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata = json.loads((output / "run_metadata.json").read_text(encoding="utf-8"))
    metadata.update(
        {
            "stage": "C2-R4",
            "candidate_result2": str(CANDIDATE_RESULT2.relative_to(ROOT)),
            "signed_off_backup": str(RESULT2_SIGNED_OFF_BACKUP.relative_to(ROOT)),
            "r4_elapsed_seconds": previous["r4_elapsed_seconds"],
            "figure_dir": str(FIG_POLICY_CONSISTENT_DIR.relative_to(ROOT)),
        }
    )
    (output / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    jan_cost = float(january["total_cost_yuan"].sum())
    feb_cost = float(feb_dec["total_cost_yuan"].sum())
    feb_emergency = float(feb_dec["emergency_kwh"].sum())
    lines = [
        "# Q2 政策一致重设计 · C2-R4",
        "",
        f"- 状态：**{report['status']}**",
        "- 正式主方案固定为：K=8；C2-R2 冻结的 (m, α) 日历；校准、部署与全年路径均启用次日价值割；"
        "全年从 2025-01-01 的 6000 kWh 起步，1 月仅预热，2—12 月正式输出继承 1 月末 SOC。",
        "- **K=8 表述为「预注册且对 K=4/12 稳定的简洁主方案」，不得称为成本最优。**",
        "- **旧全路径 K=8 风险方案仅作信息更强的近似对照，不是正式答卷。**",
        f"- 1 月预热实际成本 {jan_cost:.2f} 元；2 月 1 日继承 SOC {inherited:.6f} kWh。",
        f"- 2—12 月正式成本 {feb_cost:.2f} 元，紧急购电 {feb_emergency:.2f} kWh。",
        f"- K∈{{4,8,12}} 闭环敏感性结论：`{conclusion}`。",
        f"- 候选附件写入 `{CANDIDATE_RESULT2.relative_to(ROOT)}`；"
        f"旧签收文件 `{SIGNED_OFF_RESULT2.relative_to(ROOT)}` 未覆盖，"
        f"可回退副本 `{RESULT2_SIGNED_OFF_BACKUP.relative_to(ROOT)}`。",
        f"- 旧 result2.xlsx SHA-256：`{SIGNED_OFF_RESULT2_SHA256}`。",
        f"- 逐格对账：`result2_cell_audit.json` / `result2_cell_audit.csv`；pass={audit['summary']['pass']}。",
        f"- 最终图写入 `{FIG_POLICY_CONSISTENT_DIR.relative_to(ROOT)}/`，未改写 `fig/q2_final/`。",
        "",
        "## 候选附件对账",
        "",
        f"- 日期：2 月 1 日至 12 月 31 日，共 {N_OUTPUT_DAYS} 日。",
        "- 每行 144 时段，按附件原始行序写入，不旋转。",
        "- 计划购电量/全天购电费与台账 `planned_q_kwh` / `planned_cost_yuan` 一致；单位 kWh / 元。",
        "- 紧急购电量按连续正量合并时段，日合计与台账 `emergency_kwh` 一致。",
        "- 充放电量按 4 小时块汇总；00:00 / 24:00 储电量与日初/日末 SOC 一致，且跨日连续。",
        "- 功率上限、能量平衡、x≤q 与全年物理审计一致。",
        "",
        "## 论文口径",
        "",
        "- 可写：基于历史残差风险储备的日前购电计划，配合逐时段残差匹配 MPC。",
        "- 不可写：K=8 成本最优、严格多阶段随机最优控制、旧全路径方案为正式主方案。",
    ]
    (output / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if after != before:
        raise RuntimeError("Protected old Q2 outputs were modified")
    if not audit["summary"]["pass"]:
        raise AssertionError("C2-R4 validation failed")
    print(
        json.dumps(
            {
                "status": report["status"],
                "candidate": str(CANDIDATE_RESULT2.relative_to(ROOT)),
                "signed_off_unchanged": protected_ok,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
