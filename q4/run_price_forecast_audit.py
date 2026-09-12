#!/usr/bin/env python3
"""Run the Q4 causal price-forecast audit. Does not start Q4-2/Q4-3 storage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q3.config import PILOT_DATES  # noqa: E402
from q4.config import (  # noqa: E402
    ATTACH4,
    AUDIT_CSV,
    CAUSALITY_JSON,
    OUTPUT_DIR,
    TWODAY_JSON,
)
from q4.data import load_q4_prices  # noqa: E402
from q4.price_forecast import (  # noqa: E402
    assert_no_future_price_leak,
    fit_causal_price_forecasts,
    two_day_regression,
)


def main() -> None:
    data = load_q4_prices()
    archive = fit_causal_price_forecasts(data.price, data.dates)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    archive.audit.to_csv(AUDIT_CSV, index=False)

    twoday = two_day_regression(archive, PILOT_DATES)
    TWODAY_JSON.write_text(
        json.dumps(twoday, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    causality = {"probes": []}
    for date in PILOT_DATES:
        i = data.date_index(date)
        assert_no_future_price_leak(data.price, data.dates, i, tau=0)
        assert_no_future_price_leak(data.price, data.dates, i, tau=36)
        causality["probes"].append(
            {
                "date": date,
                "day_ahead_insensitive_to_future": True,
                "intraday_06_insensitive_to_unended_prices": True,
            }
        )
    causality["all_pass"] = True
    CAUSALITY_JSON.write_text(json.dumps(causality, indent=2) + "\n", encoding="utf-8")

    audit = archive.audit
    valid = audit[audit["chosen_model"] != ""]
    summary = {
        "attach4": str(ATTACH4),
        "n_days": int(len(audit)),
        "n_days_with_day_ahead": int(len(valid)),
        "chosen_counts": valid["chosen_model_name"].value_counts().to_dict(),
        "day_ahead_mae_mean": float(valid["day_ahead_mae"].mean()),
        "day_ahead_rmse_mean": float(valid["day_ahead_rmse"].mean()),
        "intraday_06_mae_mean": float(valid["intraday_06_mae"].mean()),
        "intraday_12_mae_mean": float(valid["intraday_12_mae"].mean()),
        "intraday_18_mae_mean": float(valid["intraday_18_mae"].mean()),
        "audit_csv": str(AUDIT_CSV),
        "twoday_json": str(TWODAY_JSON),
        "causality_json": str(CAUSALITY_JSON),
        "pilot_dates": list(PILOT_DATES),
        "note": "Price module only. Does not run Q4-2/Q4-3 storage or write result4-*.xlsx.",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("--- two-day regression ---")
    for date, payload in twoday.items():
        print(
            json.dumps(
                {
                    "date": date,
                    "train_cutoff_date": payload["train_cutoff_date"],
                    "chosen_model_name": payload["chosen_model_name"],
                    "mae_prev_day": payload["mae_prev_day"],
                    "mae_weekday2": payload["mae_weekday2"],
                    "mae_weekday4": payload["mae_weekday4"],
                    "day_ahead_mae": payload["day_ahead_mae"],
                    "day_ahead_rmse": payload["day_ahead_rmse"],
                    "intraday_06_mae": payload["intraday_06_mae"],
                    "intraday_12_mae": payload["intraday_12_mae"],
                    "intraday_18_mae": payload["intraday_18_mae"],
                    "day_ahead_fallback": payload["day_ahead_fallback"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
