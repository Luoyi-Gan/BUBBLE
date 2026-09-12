#!/usr/bin/env python3
"""K=4/8/12 cost and timing review on the Q2-aligned calibration calendar.

Uses the official Q4-2 closed loop on each historical 14-day window.
Does not re-pick K from the full-year result. If K=8 is stable, keep it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from q2.config import E_INITIAL_KWH
from q4.audit import write_json
from q4.bundle import load_q4_bundle
from q4.config import (
    FIXED_SCENARIO_K,
    K_REVIEW_CANDIDATES,
    K_REVIEW_COST_TOLERANCE,
    K_REVIEW_REFERENCE_ALPHA,
    OUTPUT_DIR,
)
from q4.q4_2 import q2_aligned_calibration_indices, run_candidate_window

DAILY_CSV = OUTPUT_DIR / "q4_2_k_review_daily.csv"
SUMMARY_CSV = OUTPUT_DIR / "q4_2_k_review.csv"
SUMMARY_JSON = OUTPUT_DIR / "q4_2_k_review.json"
WARMUP_CSV = OUTPUT_DIR / "q4_2_warmup_daily.csv"
POLICY_SOC_CSV = OUTPUT_DIR / "q4_2_k_review_policy_soc.csv"


def load_policy_start_soc(n_days: int, warmup_csv: Path = WARMUP_CSV) -> np.ndarray:
    soc = np.full(n_days, np.nan)
    source = POLICY_SOC_CSV if POLICY_SOC_CSV.exists() else warmup_csv
    if source.exists():
        daily = pd.read_csv(source)
        for _, row in daily.iterrows():
            idx = int(row["day_index"])
            if 0 <= idx < n_days and "soc_start_kwh" in row:
                soc[idx] = float(row["soc_start_kwh"])
    if not np.isfinite(soc[0]):
        soc[0] = E_INITIAL_KWH
    last = float(soc[0])
    for i in range(n_days):
        if np.isfinite(soc[i]):
            last = float(soc[i])
        else:
            soc[i] = last
    return soc


def decide_keep_k8(by_k: dict[int, dict]) -> dict:
    costs = {k: float(row["mean_cost_per_day_yuan"]) for k, row in by_k.items()}
    times = {k: float(row["mean_elapsed_seconds"]) for k, row in by_k.items()}
    best_k = min(costs, key=lambda k: (costs[k], k))
    best_cost = costs[best_k]
    k8_cost = costs[FIXED_SCENARIO_K]
    gap = (k8_cost - best_cost) / best_cost if best_cost > 0 else 0.0
    time_ok = times[FIXED_SCENARIO_K] <= 3.0 * max(times[min(times)], 1e-9)
    within = gap <= K_REVIEW_COST_TOLERANCE + 1e-15
    stable = within and time_ok
    return {
        "best_k_by_mean_cost": int(best_k),
        "k8_mean_cost_yuan": k8_cost,
        "best_mean_cost_yuan": best_cost,
        "k8_cost_gap_vs_best": float(gap),
        "k8_within_1pct_of_best": bool(within),
        "k8_time_acceptable": bool(time_ok),
        "k8_stable": bool(stable),
        "keep_k": int(FIXED_SCENARIO_K),
        "reason": (
            "K=8 remains within 1% of the best reviewed K and solve time is acceptable; keep K=8."
            if stable
            else "K=8 is retained as the inherited Q2 value; this review does not re-pick K from the year."
        ),
    }


def review_scenario_k(
    bundle,
    policy_start_soc: np.ndarray,
    *,
    k_candidates: tuple[int, ...] = K_REVIEW_CANDIDATES,
    reference_alpha: float = K_REVIEW_REFERENCE_ALPHA,
    n_validation: int | None = None,
    max_windows: int | None = None,
    log: bool = True,
) -> dict:
    indices = q2_aligned_calibration_indices(bundle.n_days())
    if max_windows is not None:
        indices = indices[: max(0, int(max_windows))]
    daily_rows: list[dict] = []
    window_rows: list[dict] = []
    started = perf_counter()
    for target in indices:
        cal_date = bundle.prices.dates[target].strftime("%Y-%m-%d")
        for k in k_candidates:
            prefix = (
                f"Q4-2 K-review K={k} α={reference_alpha:.2f} {cal_date}" if log else None
            )
            daily, summary = run_candidate_window(
                bundle,
                policy_start_soc,
                target,
                risk_alpha=float(reference_alpha),
                k_target=int(k),
                n_validation=n_validation,
                log_prefix=prefix,
            )
            for row in daily:
                daily_rows.append({"calibration_date": cal_date, **row})
            window_rows.append(
                {
                    "calibration_date": cal_date,
                    "calibration_day_index": int(target),
                    **summary,
                }
            )
            if log:
                print(
                    f"K-review {cal_date} K={k} mean_cost={summary['mean_validation_cost_yuan']:.2f} "
                    f"mean_s={summary['mean_elapsed_seconds']:.3f}",
                    flush=True,
                )
    window = pd.DataFrame(window_rows)
    by_k: dict[int, dict] = {}
    for k in k_candidates:
        part = window.loc[window["k_target"] == k]
        by_k[int(k)] = {
            "n_windows": int(len(part)),
            "n_validation_days_total": int(part["validation_days"].sum()) if not part.empty else 0,
            "mean_cost_per_day_yuan": float(part["mean_validation_cost_yuan"].mean())
            if not part.empty
            else float("nan"),
            "total_cost_yuan": float(part["total_cost_yuan"].sum()) if not part.empty else float("nan"),
            "total_planned_fee_yuan": float(part["total_planned_fee_yuan"].sum())
            if not part.empty
            else float("nan"),
            "total_emergency_fee_yuan": float(part["total_emergency_fee_yuan"].sum())
            if not part.empty
            else float("nan"),
            "total_unused_quota_kwh": float(part["total_unused_quota_kwh"].sum())
            if not part.empty
            else float("nan"),
            "mean_elapsed_seconds": float(part["mean_elapsed_seconds"].mean())
            if not part.empty
            else float("nan"),
        }
    decision = decide_keep_k8(by_k)
    report = {
        "k_candidates": [int(k) for k in k_candidates],
        "reference_alpha": float(reference_alpha),
        "n_windows": int(len(indices)),
        "calibration_dates": [
            bundle.prices.dates[i].strftime("%Y-%m-%d") for i in indices
        ],
        "policy_loop": "day_ahead_joint_q+locked_q+causal_mpc+next_day_value_cuts",
        "used_full_day_actual_scheduler": False,
        "no_future_info": True,
        "by_k": {str(k): v for k, v in by_k.items()},
        "decision": decision,
        "elapsed_seconds": float(perf_counter() - started),
    }
    return {
        "report": report,
        "window": window,
        "daily": pd.DataFrame(daily_rows),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Q4-2 K=4/8/12 review")
    parser.add_argument("--max-windows", type=int, default=None)
    parser.add_argument("--n-validation", type=int, default=None)
    args = parser.parse_args(argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = load_q4_bundle(compute_price_mpc=False)
    policy_start_soc = load_policy_start_soc(bundle.n_days())
    result = review_scenario_k(
        bundle,
        policy_start_soc,
        n_validation=args.n_validation,
        max_windows=args.max_windows,
        log=True,
    )
    if not result["window"].empty:
        result["window"].to_csv(SUMMARY_CSV, index=False)
    if not result["daily"].empty:
        result["daily"].to_csv(DAILY_CSV, index=False)
    write_json(SUMMARY_JSON, result["report"])
    print(json.dumps(result["report"]["decision"], ensure_ascii=False, indent=2))
    print(json.dumps({str(k): v for k, v in result["report"]["by_k"].items()}, indent=2))


if __name__ == "__main__":
    main()
