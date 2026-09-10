#!/usr/bin/env python3
"""Build Q2 annual comparison baselines on the completed linked-policy path."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q2.config import EMERGENCY_PRICE_MULTIPLIER, FULL_OUTPUT_DIR  # noqa: E402
from q2.data import load_q2_data  # noqa: E402
from q2.forecast import build_forecast_archive  # noqa: E402
from q2.pilot import planned_q_hash, run_perfect_information  # noqa: E402
from q2.scenarios import build_scenarios, scenario_trajectories  # noqa: E402


def weighted_quantile(values: np.ndarray, weights: np.ndarray, probability: float) -> float:
    order = np.argsort(values)
    sorted_values = values[order]
    cumulative = np.cumsum(weights[order])
    return float(sorted_values[np.searchsorted(cumulative, probability, side="left")])


def run_no_storage_baseline(data, archive, linked: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for i, date in enumerate(data.dates):
        k = int(linked.loc[i, "selected_k"])
        if i == 0:
            scenario_net = np.maximum(archive.load_hat[i] - archive.pv_hat[i], 0.0)[None, :]
            probability = np.ones(1)
        else:
            scenarios = build_scenarios(i, data, archive, k)
            loads, pvs = scenario_trajectories(scenarios, archive)
            scenario_net = np.maximum(loads - pvs, 0.0)
            probability = scenarios.probabilities
        q = np.array(
            [weighted_quantile(scenario_net[:, t], probability, 0.8) for t in range(len(data.price))]
        )
        actual_net = np.maximum(data.load[i] - data.pv[i], 0.0)
        x = np.minimum(q, actual_net)
        emergency = np.maximum(actual_net - q, 0.0)
        curtailment = np.maximum(data.pv[i] - data.load[i], 0.0)
        residual = x + emergency + data.pv[i] - curtailment - data.load[i]
        plan_cost = float(data.price @ q)
        emergency_cost = float(EMERGENCY_PRICE_MULTIPLIER * data.price @ emergency)
        rows.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "selected_k": k,
                "planned_cost_yuan": plan_cost,
                "emergency_cost_yuan": emergency_cost,
                "total_cost_yuan": plan_cost + emergency_cost,
                "planned_q_kwh": float(q.sum()),
                "planned_q_sha256": planned_q_hash(q),
                "actual_x_kwh": float(x.sum()),
                "unused_plan_kwh": float((q - x).sum()),
                "emergency_kwh": float(emergency.sum()),
                "curtailment_kwh": float(curtailment.sum()),
                "max_balance_residual_kwh": float(np.max(np.abs(residual))),
                "max_x_minus_q_kwh": float(np.max(x - q)),
                "pass": bool(np.max(np.abs(residual)) < 1e-6 and np.max(x - q) < 1e-6),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    linked_path = FULL_OUTPUT_DIR / "daily_summary.csv"
    if not linked_path.exists():
        raise FileNotFoundError("Run q2/run_q2_full.py before comparison baselines.")
    data = load_q2_data()
    archive = build_forecast_archive(data)
    linked = pd.read_csv(linked_path)
    no_storage = run_no_storage_baseline(data, archive, linked)
    if not no_storage["pass"].all():
        raise AssertionError("no-storage baseline physical validation failed")
    no_storage.to_csv(FULL_OUTPUT_DIR / "no_storage_daily.csv", index=False)

    perfect_path = FULL_OUTPUT_DIR / "perfect_information_daily.csv"
    run_perfect_information(data, perfect_path)
    perfect = pd.read_csv(perfect_path)
    if abs(float(perfect["soc_end_kwh"].iloc[-1]) - float(linked["soc_end_kwh"].iloc[-1])) >= 1e-6:
        raise AssertionError("linked and perfect-information terminal SOC differ")
    comparison = {
        "main_linked_total_cost_yuan": float(linked["total_cost_yuan"].sum()),
        "no_storage_total_cost_yuan": float(no_storage["total_cost_yuan"].sum()),
        "perfect_information_total_cost_yuan": float(perfect["total_cost_yuan"].sum()),
        "linked_minus_no_storage_yuan": float(linked["total_cost_yuan"].sum() - no_storage["total_cost_yuan"].sum()),
        "linked_minus_perfect_information_yuan": float(linked["total_cost_yuan"].sum() - perfect["total_cost_yuan"].sum()),
        "main_start_soc_kwh": float(linked["soc_start_kwh"].iloc[0]),
        "main_terminal_soc_kwh": float(linked["soc_end_kwh"].iloc[-1]),
        "perfect_terminal_soc_kwh": float(perfect["soc_end_kwh"].iloc[-1]),
        "comparison_note": "The no-storage baseline is not SOC-comparable because it has no initial stored energy; use it only as an operational benchmark, not as a pure storage-value claim.",
    }
    (FULL_OUTPUT_DIR / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
