#!/usr/bin/env python3
"""C2-R2: 12-candidate closed-loop rolling calibration. Never writes result2.xlsx."""

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
    FIXED_SCENARIO_K,
    FULL_K8_RISK_OUTPUT_DIR,
    POLICY_CONSISTENT_OUTPUT_DIR,
    RISK_ALPHA_CANDIDATES,
)
from q2.data import load_q2_data  # noqa: E402
from q2.policy_consistent import (  # noqa: E402
    FORECAST_MODES,
    build_forecast_archive_mode,
    run_rolling_closed_loop_calibration,
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
    before = snapshot_protected()

    data = load_q2_data()
    archives = {mode: build_forecast_archive_mode(data, mode) for mode in FORECAST_MODES}
    calibration_rows, diagnostic_rows, deployed_rows, cut_stats = run_rolling_closed_loop_calibration(
        data, archives, k=FIXED_SCENARIO_K, include_value_cuts=True
    )
    calibration = pd.DataFrame(calibration_rows)
    diagnostics = pd.DataFrame(diagnostic_rows)
    deployed = pd.DataFrame(deployed_rows)
    calibration.to_csv(output / "closed_loop_calibration.csv", index=False)
    diagnostics.to_csv(output / "forecast_diagnostics.csv", index=False)
    deployed.to_csv(output / "r2_deployed_daily.csv", index=False)

    scored = calibration.loc[calibration["fallback_reason"].fillna("") == ""]
    selected = calibration.loc[calibration["selected"].astype(bool)]
    n_candidates = len(FORECAST_MODES) * len(RISK_ALPHA_CANDIDATES)
    scored_groups = scored.groupby("calibration_date").size() if len(scored) else pd.Series(dtype=int)
    consistency = {
        "stage": "C2-R2",
        "policy": (
            "single baseline-forecast day-ahead LP plus K=8 risk reserve "
            "and residual-matching 10-minute MPC"
        ),
        "n_forecast_modes": len(FORECAST_MODES),
        "risk_alpha_candidates": list(RISK_ALPHA_CANDIDATES),
        "n_candidates_per_block": n_candidates,
        "selection_criterion": "mean_actual_cost_sum_pq_plus_5pe",
        "tiebreak": "one_se_then_unused_plan_then_m1_then_smaller_alpha",
        "mae_is_diagnostic_only": True,
        "mae_used_for_selection": False,
        "calibration_closed_loop": True,
        "candidate_window_carries_own_soc": True,
        "window_start_soc_from_deployed_policy": True,
        "validation_uses_full_day_actual_lp": False,
        "formal_execution_uses_full_day_actual_lp": False,
        "calibration_and_execution_exclude_future_actuals": True,
        "include_value_cuts": True,
        "calibration_include_value_cuts": True,
        "deployment_include_value_cuts": True,
        "include_value_cuts_consistent": True,
        "value_cut_cache_entries": int(cut_stats["value_cut_cache_entries"]),
        "annual_run": False,
        "candidate_result2_xlsx": False,
        "k_used_for": ["risk_reserve_R", "intra_day_residual_weights"],
        "fallback_blocks": int((calibration["fallback_reason"].fillna("") != "").sum()),
        "scored_blocks": int(scored["calibration_date"].nunique()) if len(scored) else 0,
        "selected_blocks": int(len(selected)),
        "elapsed_seconds": perf_counter() - started,
    }
    (output / "policy_consistency_audit.json").write_text(
        json.dumps(consistency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    status = (
        deployed["pass"].all()
        and not deployed["used_full_day_actual_lp"].any()
        and not deployed["future_actuals_in_optimizer"].any()
        and diagnostics["selection_role"].eq("diagnostic_only").all()
        and (scored_groups == n_candidates).all()
        and selected.groupby("calibration_date").size().eq(1).all()
        and calibration["include_value_cuts"].all()
        and deployed["include_value_cuts"].all()
    )
    report = {
        "status": "PASS" if bool(status) else "FAIL",
        "stage": "C2-R2",
        "n_candidates_per_block": n_candidates,
        "scored_blocks": consistency["scored_blocks"],
        "fallback_blocks": consistency["fallback_blocks"],
        "selected_pairs": selected[["calibration_date", "forecast_mode", "risk_alpha"]].to_dict(
            orient="records"
        ),
        "deployed_days": int(len(deployed)),
        "protected_outputs_unchanged": snapshot_protected() == before,
        "candidate_result2_xlsx": False,
        "mae_is_diagnostic_only": True,
        "include_value_cuts": True,
        "include_value_cuts_consistent": True,
    }
    (output / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Q2 政策一致重设计 · C2-R2",
        "",
        f"- 状态：**{report['status']}**",
        f"- 每个可评分校准块评估 {n_candidates} 组 "
        f"(m∈{{m1,m2,m3}} × α∈{list(RISK_ALPHA_CANDIDATES)})。",
        "- 主选择准则是验证窗口内闭环实际成本均值 $\\sum(pq+5pe)$；"
        "一倍标准误内再按未用计划电、m1、较小 α 打破平局。",
        "- MAE / 净负荷 MAE / 覆盖率只写入 `forecast_diagnostics.csv`，不参与选择。",
        "- 每个候选在 14 日窗口内连续传递自己的 SOC；窗口初值取已部署主政策记录的 SOC。",
        "- 校准评分与获选策略部署均纳入次日基准预测价值割；同一日、同一 (m, α, K) 的割缓存复用。",
        "- 校准与部署均未把验证日未来实际值输入优化问题，也未调用全视域真实路径 LP。",
        "- 未导出候选 result2.xlsx；全年台账、K 敏感性与 2 月初 SOC 敏感性留到 C2-R3。",
        f"- 回退块 {consistency['fallback_blocks']} 个，评分块 {consistency['scored_blocks']} 个。",
        "",
        "## 各块选定 (m, α)",
        "",
    ]
    for row in selected.itertuples():
        lines.append(
            f"- {row.calibration_date} 至 {row.effective_end_date}："
            f"{row.forecast_mode}, α={row.risk_alpha}；"
            f"回退={row.fallback_reason or '无'}"
        )
    (output / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    after = snapshot_protected()
    if after != before:
        raise RuntimeError("Protected old Q2 outputs were modified")
    if not status:
        raise AssertionError("C2-R2 validation failed")
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
