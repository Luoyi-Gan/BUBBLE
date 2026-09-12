#!/usr/bin/env python3
"""Q4-3 sensitivities. Does not overwrite result4-3.xlsx or the official dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from q3.config import PILOT_DATES
from q4.audit import warmup_soc_continuity, write_json
from q4.bundle import load_q4_bundle
from q4.campaign import run_q4_3_campaign
from q4.config import (
    OUTPUT_DIR,
    PAM_SEED,
    Q4_3_ORACLE_DAILY_CSV,
    Q4_3_ORACLE_DISPATCH_DIR,
    Q4_3_SENSITIVITY_SUMMARY_JSON,
)
from q4.q4_3_sensitivity import run_settlement_sensitivity, write_sensitivity_summary


def _run_oracle(end_index: int | None = None, write_all_dispatch: bool = True) -> dict:
    started = perf_counter()
    bundle = load_q4_bundle(compute_price_mpc=False)
    if end_index is None:
        end_index = bundle.n_days() - 1
    result = run_q4_3_campaign(
        bundle,
        end_index,
        detail_dates=PILOT_DATES,
        out_dir=OUTPUT_DIR,
        write_all_dispatch=write_all_dispatch,
        price_mode="oracle",
        dispatch_dir=Q4_3_ORACLE_DISPATCH_DIR,
        daily_name=Q4_3_ORACLE_DAILY_CSV.name,
        update_name="q4_3_oracle_update_log.csv",
        ledger_name="q4_3_oracle_cost_ledger.csv",
        commitment_prefix="q4_3_oracle_commitment_versions",
        unlink_existing=True,
    )
    daily = pd.read_csv(Q4_3_ORACLE_DAILY_CSV)
    soc = warmup_soc_continuity(daily)
    n_pass = int(daily["pass"].sum()) if "pass" in daily.columns else 0
    meta = {
        "system": "q4_3_price_oracle",
        "executable": False,
        "changes_main_scheme": False,
        "n_days": int(len(daily)),
        "annual_cost_yuan": float(daily["total_cost_yuan"].sum()),
        "end_soc": float(result["end_soc"]),
        "soc_continuity": soc,
        "n_days_pass": n_pass,
        "pam_seed": PAM_SEED,
        "elapsed_seconds": float(perf_counter() - started),
        "note": (
            "Day-ahead and remaining prices equal today's actual path. "
            "Next-day value cuts remain causal. Not an official Q4-3 result."
        ),
    }
    write_json(OUTPUT_DIR / "q4_3_oracle_run_metadata.json", meta)
    if not soc["pass"] or n_pass != len(daily):
        raise SystemExit("Q4-3 price-oracle stream failed physical/pass checks")
    return meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Q4-3 settlement and oracle sensitivities")
    parser.add_argument("--skip-settlement", action="store_true")
    parser.add_argument("--skip-oracle", action="store_true")
    parser.add_argument("--oracle-end-index", type=int, default=None)
    args = parser.parse_args(argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settlement = None
    if not args.skip_settlement:
        settlement = run_settlement_sensitivity()
        print(json.dumps(settlement["summary"], ensure_ascii=False, indent=2))
    oracle_daily = None
    if not args.skip_oracle:
        meta = _run_oracle(end_index=args.oracle_end_index)
        print(json.dumps({k: meta[k] for k in ("n_days", "annual_cost_yuan", "elapsed_seconds")}, indent=2))
        oracle_daily = pd.read_csv(Q4_3_ORACLE_DAILY_CSV)
    if settlement is None:
        settlement = {"summary": json.loads(Path(OUTPUT_DIR / "q4_3_settlement_sensitivity.json").read_text())} if (OUTPUT_DIR / "q4_3_settlement_sensitivity.json").exists() else {"summary": {}}
    payload = write_sensitivity_summary(settlement, oracle_daily)
    print(json.dumps({"wrote": str(Q4_3_SENSITIVITY_SUMMARY_JSON), "keys": list(payload)}, indent=2))


if __name__ == "__main__":
    main()
