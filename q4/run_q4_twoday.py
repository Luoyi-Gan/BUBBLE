#!/usr/bin/env python3
"""Q4-2 and Q4-3 two-day regression. Does not write result4-*.xlsx or run 365 days."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import PILOT_DATES  # noqa: E402
from q4.audit import (  # noqa: E402
    ledger_from_dispatch_q42,
    ledger_from_dispatch_q43,
    physical_from_dispatch,
    prefix_lock_probe,
    q_unchanged_probe,
    warmup_soc_continuity,
    write_json,
)
from q4.bundle import load_q4_bundle  # noqa: E402
from q4.campaign import last_index_for_dates, run_q4_2_campaign, run_q4_3_campaign  # noqa: E402
from q4.config import OUTPUT_DIR, PAM_SEED  # noqa: E402
from q4.info_set import probe_executed_prefix  # noqa: E402


def _git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _run_unittest() -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "q2.test_q2",
            "q3.test_q3",
            "q3.test_q3_result3_export",
            "q4.test_q4_price_forecast",
            "q4.test_q4_dispatch",
            "-v",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return {
        "command": (
            "python -m unittest q2.test_q2 q3.test_q3 q3.test_q3_result3_export "
            "q4.test_q4_price_forecast q4.test_q4_dispatch -v"
        ),
        "returncode": proc.returncode,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-60:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-40:]),
    }


def _audit_detail(q42, q43):
    phys2, phys3 = {"days": {}}, {"days": {}}
    all_pass = True
    for date, result in q42.items():
        phys = physical_from_dispatch(result.dispatch, q4_3=False)
        ledger = ledger_from_dispatch_q42(result.dispatch)
        recon = float(ledger["total_cost_yuan"].sum())
        ok = (
            phys["pass"]
            and q_unchanged_probe(result.q, result.dispatch)
            and abs(recon - result.summary["total_cost_yuan"]) < 1e-4
        )
        all_pass = all_pass and ok
        phys2["days"][date] = {**phys, "ledger_recompute_yuan": recon, "ok": ok}
    for date, result in q43.items():
        phys = physical_from_dispatch(result.dispatch, q4_3=True)
        ledger = ledger_from_dispatch_q43(result.dispatch)
        recon = float(ledger["total_cost_yuan"].sum())
        ok = (
            phys["pass"]
            and prefix_lock_probe(result.update_log)
            and abs(recon - result.summary["total_cost_yuan"]) < 1e-4
            and result.summary["locked_period_violations"] == 0
        )
        all_pass = all_pass and ok
        phys3["days"][date] = {**phys, "ledger_recompute_yuan": recon, "ok": ok}
    phys2["all_pass"] = all(day["ok"] for day in phys2["days"].values()) if phys2["days"] else False
    phys3["all_pass"] = all(day["ok"] for day in phys3["days"].values()) if phys3["days"] else False
    return phys2, phys3, all_pass and phys2["all_pass"] and phys3["all_pass"]


def main() -> None:
    started = perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tests = _run_unittest()
    if tests["returncode"] != 0:
        write_json(OUTPUT_DIR / "q4_twoday_run_metadata.json", {"tests": tests, "aborted": True})
        raise SystemExit(f"unit tests failed:\n{tests['stderr_tail']}\n{tests['stdout_tail']}")
    bundle = load_q4_bundle(compute_price_mpc=False)
    end_index = last_index_for_dates(bundle, PILOT_DATES)
    print(f"Two-day regression with warmup through {bundle.prices.dates[end_index].strftime('%Y-%m-%d')}", flush=True)
    q42 = run_q4_2_campaign(bundle, end_index, PILOT_DATES, OUTPUT_DIR)
    q43 = run_q4_3_campaign(bundle, end_index, PILOT_DATES, OUTPUT_DIR)
    phys2, phys3, all_pass = _audit_detail(q42["detail"], q43["detail"])
    soc2 = warmup_soc_continuity(pd.read_csv(OUTPUT_DIR / "q4_2_warmup_daily.csv"))
    soc3 = warmup_soc_continuity(pd.read_csv(OUTPUT_DIR / "q4_3_warmup_daily.csv"))
    info_rows = []
    for date, result in q42["detail"].items():
        q43_res = q43["detail"][date]
        alpha = result.summary["risk_alpha"]
        if alpha is not None:
            alpha = float(alpha)
        info = probe_executed_prefix(
            bundle,
            result.day_index,
            float(result.summary["soc_start_kwh"]),
            alpha,
            result.dispatch,
            q43_res,
            tau=40,
        )
        info_rows.append(info)
        all_pass = all_pass and info["pass"]
        print(f"info-set {date}: {info}", flush=True)
    info_payload = {"days": info_rows, "all_pass": all(row["pass"] for row in info_rows)}
    write_json(OUTPUT_DIR / "q4_2_physical_audit.json", {**phys2, "soc_continuity": soc2})
    write_json(OUTPUT_DIR / "q4_3_physical_audit.json", {**phys3, "soc_continuity": soc3})
    write_json(OUTPUT_DIR / "q4_2_info_set_audit.json", info_payload)
    write_json(OUTPUT_DIR / "q4_3_info_set_audit.json", info_payload)
    all_pass = all_pass and soc2["pass"] and soc3["pass"] and info_payload["all_pass"]
    meta = {
        "git_commit": _git_hash(),
        "pilot_dates": list(PILOT_DATES),
        "warmup_start": "2025-01-01",
        "warmup_end": bundle.prices.dates[end_index].strftime("%Y-%m-%d"),
        "n_days_solved_each_system": end_index + 1,
        "pam_seed": PAM_SEED,
        "pam_algorithm": "deterministic_build_then_swap",
        "load_information_case": "causal_load_main",
        "q4_2_year_end_rule": "q2_accepted_no_hard_terminal",
        "q4_3_year_end": "A_q2_aligned_1200",
        "q4_3_strategy": "M1_M6",
        "settlement_rule": "delivery_time_actual_price",
        "wrote_result4_xlsx": False,
        "full_year": False,
        "elapsed_seconds": float(perf_counter() - started),
        "tests": tests,
        "q4_2_all_pass": phys2["all_pass"],
        "q4_3_all_pass": phys3["all_pass"],
        "all_pass": all_pass,
        "note": (
            "Two-day regression only. January through each target date is causal "
            "SOC warmup. result4-2/result4-3 are not written in this stage."
        ),
    }
    write_json(OUTPUT_DIR / "q4_2_run_metadata.json", {**meta, "system": "Q4-2"})
    write_json(OUTPUT_DIR / "q4_3_run_metadata.json", {**meta, "system": "Q4-3"})
    write_json(OUTPUT_DIR / "q4_twoday_run_metadata.json", meta)
    print(json.dumps({"all_pass": all_pass, "elapsed_seconds": meta["elapsed_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
