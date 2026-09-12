#!/usr/bin/env python3
"""Write Q4 closeout reports from signed-off daily/dispatch artifacts. Does not re-solve."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q4.audit import write_json
from q4.closeout import (
    build_fair_comparison,
    build_residual_correlation_from_bundle,
    cost_components,
    load_q2_k8_daily,
    load_q3_official_daily,
    load_q4_2_daily,
    load_q4_3_daily,
    price_error_stats,
    scan_dispatch_year,
    selected_alpha_blocks,
)
from q4.config import (
    AUDIT_CSV,
    FAIR_COMPARISON_CSV,
    FAIR_COMPARISON_JSON,
    OUTPUT_DIR,
    PHYSICAL_YEAR_AUDIT_JSON,
    PRICE_MONTHLY_JSON,
    Q4_2_ALPHA_SELECTION_CSV,
    Q4_2_DISPATCH_DIR,
    Q4_3_DISPATCH_DIR,
    SCENARIO_CORR_JSON,
    TAIL_STATS_CSV,
    TAIL_STATS_JSON,
)


def _tail_row(name: str, window: str, components: dict) -> dict:
    return {
        "scheme": name,
        "window": window,
        "n_days": components["n_days"],
        "total_cost_yuan": components["total_cost_yuan"],
        "emergency_cost_yuan": components["emergency_cost_yuan"],
        "emergency_kwh": components["emergency_kwh"],
        "max_day_cost_yuan": components["max_day_cost_yuan"],
        "max_day_cost_date": components["max_day_cost_date"],
        "max_emergency_cost_date": components["max_emergency_cost_date"],
        "p90_yuan": components["daily_cost_p90_yuan"],
        "p95_yuan": components["daily_cost_p95_yuan"],
        "cvar_0_90_yuan": components["daily_cost_cvar_0_90_yuan"],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Q4 reporting-only closeout")
    parser.add_argument("--skip-correlation", action="store_true")
    parser.add_argument("--skip-physical", action="store_true")
    args = parser.parse_args(argv)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    q42 = load_q4_2_daily()
    q43 = load_q4_3_daily()
    q2 = load_q2_k8_daily()
    q3 = load_q3_official_daily()
    comparison = build_fair_comparison(q42, q43, q2, q3)
    price_audit = pd.read_csv(AUDIT_CSV)
    price_export = price_error_stats(price_audit, "2025-02-01", "2025-12-31")
    price_annual = price_error_stats(price_audit, "2025-01-01", "2025-12-31")
    monthly = json.loads(PRICE_MONTHLY_JSON.read_text(encoding="utf-8")) if PRICE_MONTHLY_JSON.exists() else {}
    annual_row = next((row for row in monthly.get("rows", []) if row.get("year_month") == "2025-annual"), {})
    if annual_row:
        if abs(price_annual["day_ahead_mae"] - float(annual_row["day_ahead_mae"])) >= 1e-8:
            raise AssertionError("annual day-ahead MAE does not match signed-off monthly table")
        if abs(price_annual["day_ahead_rmse_pooled"] - float(annual_row["day_ahead_rmse"])) >= 1e-8:
            raise AssertionError("annual pooled RMSE does not match signed-off monthly table")

    tail_rows = [
        _tail_row("Q4-2", "1-12", cost_components(q42, "q4_2")),
        _tail_row("Q4-2", "2-12", comparison["export"]["q4_2"]),
        _tail_row("Q4-3", "1-12", cost_components(q43, "q4_3")),
        _tail_row("Q4-3", "2-12", comparison["export"]["q4_3"]),
        _tail_row("Q2-K8", "2-12", comparison["export"]["q2_k8"]),
        _tail_row("Q3-M1_M6", "2-12", comparison["export"]["q3_m1_m6"]),
        _tail_row("Q3-M1_M6", "1-12", comparison["q3_annual"]),
    ]
    tail = {
        "price_note": comparison["price_note"],
        "price_errors": {"export_2_12": price_export, "annual_1_12": price_annual},
        "rows": tail_rows,
    }
    write_json(TAIL_STATS_JSON, tail)
    pd.DataFrame(tail_rows).to_csv(TAIL_STATS_CSV, index=False)

    fair_rows = [
        {
            "pair": "Q4-2 vs Q2 K=8",
            "window": "2-12",
            "left": "Q4-2",
            "right": "Q2 K=8",
            "left_total_yuan": comparison["export"]["q4_2"]["total_cost_yuan"],
            "right_total_yuan": comparison["export"]["q2_k8"]["total_cost_yuan"],
            "delta_total_yuan": comparison["pairs"]["q4_2_minus_q2_k8_export_yuan"],
            "left_emergency_kwh": comparison["export"]["q4_2"]["emergency_kwh"],
            "right_emergency_kwh": comparison["export"]["q2_k8"]["emergency_kwh"],
            "delta_emergency_kwh": comparison["pairs"]["q4_2_minus_q2_k8_emergency_kwh"],
        },
        {
            "pair": "Q4-3 vs Q3 M1_M6",
            "window": "2-12",
            "left": "Q4-3",
            "right": "Q3 M1_M6",
            "left_total_yuan": comparison["export"]["q4_3"]["total_cost_yuan"],
            "right_total_yuan": comparison["export"]["q3_m1_m6"]["total_cost_yuan"],
            "delta_total_yuan": comparison["pairs"]["q4_3_minus_q3_m1_m6_export_yuan"],
            "left_emergency_kwh": comparison["export"]["q4_3"]["emergency_kwh"],
            "right_emergency_kwh": comparison["export"]["q3_m1_m6"]["emergency_kwh"],
            "delta_emergency_kwh": comparison["pairs"]["q4_3_minus_q3_m1_m6_emergency_kwh"],
        },
    ]
    write_json(FAIR_COMPARISON_JSON, comparison)
    pd.DataFrame(fair_rows).to_csv(FAIR_COMPARISON_CSV, index=False)

    physical = {"skipped": True}
    if not args.skip_physical:
        physical = {
            "q4_2": scan_dispatch_year(Q4_2_DISPATCH_DIR, q42, q4_3=False),
            "q4_3": scan_dispatch_year(Q4_3_DISPATCH_DIR, q43, q4_3=True),
        }
        if not physical["q4_2"]["pass"] or not physical["q4_3"]["pass"]:
            raise SystemExit("physical year audit failed")
        write_json(PHYSICAL_YEAR_AUDIT_JSON, physical)

    correlation = {"skipped": True}
    if not args.skip_correlation:
        from q4.bundle import load_q4_bundle

        bundle = load_q4_bundle(compute_price_mpc=False)
        correlation = build_residual_correlation_from_bundle(bundle)
        write_json(SCENARIO_CORR_JSON, correlation)

    alpha_blocks = selected_alpha_blocks(q42, pd.read_csv(Q4_2_ALPHA_SELECTION_CSV))
    summary = {
        "tail_stats": str(TAIL_STATS_JSON.relative_to(ROOT)),
        "fair_comparison": str(FAIR_COMPARISON_JSON.relative_to(ROOT)),
        "physical_audit": None
        if args.skip_physical
        else str(PHYSICAL_YEAR_AUDIT_JSON.relative_to(ROOT)),
        "residual_correlation": None
        if args.skip_correlation
        else str(SCENARIO_CORR_JSON.relative_to(ROOT)),
        "q4_2_alpha_blocks": [
            {
                "start": row.effective_start_date.strftime("%Y-%m-%d"),
                "end": row.effective_end_date.strftime("%Y-%m-%d"),
                "n_days": int(row.n_days),
                "risk_alpha": row.risk_alpha,
            }
            for row in alpha_blocks.itertuples()
        ],
        "physical_pass": None if args.skip_physical else physical["q4_2"]["pass"] and physical["q4_3"]["pass"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
