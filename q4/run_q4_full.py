#!/usr/bin/env python3
"""365-day Q4-2 / Q4-3 stream with daily 10-minute dispatch. Does not touch result3.xlsx."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q4.audit import warmup_soc_continuity, write_json  # noqa: E402
from q4.bundle import load_q4_bundle  # noqa: E402
from q4.campaign import run_q4_2_campaign, run_q4_3_campaign  # noqa: E402
from q4.config import OUTPUT_DIR, PAM_SEED  # noqa: E402
import pandas as pd  # noqa: E402


def _git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Q4 full-year stream")
    parser.add_argument("--system", choices=("q4_2", "q4_3"), required=True)
    args = parser.parse_args(argv)
    started = perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = load_q4_bundle(compute_price_mpc=False)
    end_index = bundle.n_days() - 1
    print(
        f"Full-year {args.system} through {bundle.prices.dates[end_index].strftime('%Y-%m-%d')} "
        f"({end_index + 1} days)",
        flush=True,
    )
    if args.system == "q4_2":
        result = run_q4_2_campaign(
            bundle, end_index, detail_dates=(), out_dir=OUTPUT_DIR, write_all_dispatch=True
        )
        daily = pd.read_csv(OUTPUT_DIR / "q4_2_warmup_daily.csv")
        audit_path = OUTPUT_DIR / "q4_2_physical_audit.json"
        meta_path = OUTPUT_DIR / "q4_2_run_metadata.json"
        alpha_path = OUTPUT_DIR / "q4_2_alpha_selection.csv"
        if alpha_path.exists():
            alpha = pd.read_csv(alpha_path)
            selected = (
                alpha.loc[alpha["selected"].astype(str).str.lower().isin(("true", "1"))]
                if "selected" in alpha.columns
                else alpha
            )
            meta_alpha = {
                "n_calibration_windows": int(selected["calibration_date"].nunique())
                if "calibration_date" in selected.columns
                else int(len(selected)),
                "selected_alphas": sorted(
                    {float(v) for v in selected["risk_alpha"].dropna().unique()}
                )
                if "risk_alpha" in selected.columns
                else [],
            }
        else:
            meta_alpha = {}
    else:
        result = run_q4_3_campaign(
            bundle, end_index, detail_dates=(), out_dir=OUTPUT_DIR, write_all_dispatch=True
        )
        daily = pd.read_csv(OUTPUT_DIR / "q4_3_warmup_daily.csv")
        audit_path = OUTPUT_DIR / "q4_3_physical_audit.json"
        meta_path = OUTPUT_DIR / "q4_3_run_metadata.json"
        meta_alpha = {}
    soc = warmup_soc_continuity(daily)
    n_pass = int(daily["pass"].sum()) if "pass" in daily.columns else 0
    meta = {
        "git_commit": _git_hash(),
        "system": args.system,
        "full_year": True,
        "n_days": int(len(daily)),
        "annual_cost_yuan": float(daily["total_cost_yuan"].sum()),
        "soc_continuity": soc,
        "n_days_pass": n_pass,
        "end_soc": float(result["end_soc"]),
        "pam_seed": PAM_SEED,
        "load_information_case": "causal_load_main",
        "settlement_rule": "delivery_time_actual_price",
        "elapsed_seconds": float(perf_counter() - started),
        "wrote_result4_xlsx": False,
    }
    meta.update(meta_alpha)
    if args.system == "q4_2":
        meta["alpha_policy_loop"] = (
            "day_ahead_joint_q+locked_q+causal_mpc+next_day_value_cuts"
        )
        meta["used_full_day_actual_scheduler"] = False
        two_day = {}
        for date in ("2025-02-01", "2025-06-21"):
            hit = daily.loc[daily["date"].astype(str) == date]
            if not hit.empty:
                two_day[date] = float(hit.iloc[0]["total_cost_yuan"])
        if two_day:
            meta["two_day_costs"] = two_day
    write_json(audit_path, {"soc_continuity": soc, "n_days": int(len(daily)), "n_days_pass": n_pass})
    write_json(meta_path, meta)
    print(json.dumps({k: meta[k] for k in ("system", "n_days", "annual_cost_yuan", "elapsed_seconds")}, indent=2))
    if not soc["pass"] or n_pass != len(daily):
        raise SystemExit(f"{args.system} annual stream failed physical/pass checks")


if __name__ == "__main__":
    main()
