#!/usr/bin/env python3
"""Monthly MAE/RMSE from the accepted P1 price-forecast audit. Does not refit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from q4.config import AUDIT_CSV, PRICE_MONTHLY_CSV, PRICE_MONTHLY_JSON

METRIC_PAIRS = (
    ("day_ahead_mae", "day_ahead_rmse"),
    ("intraday_06_mae", "intraday_06_rmse"),
    ("intraday_12_mae", "intraday_12_rmse"),
    ("intraday_18_mae", "intraday_18_rmse"),
)
MAE_ONLY = ("mpc_remaining_mae_mean",)


def _pooled_rmse(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").to_numpy(float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan")
    return float(np.sqrt(np.mean(np.square(values))))


def monthly_from_audit(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["date"] = pd.to_datetime(work["date"])
    work["year_month"] = work["date"].dt.strftime("%Y-%m")
    rows = []
    for year_month, group in work.groupby("year_month", sort=True):
        row: dict = {
            "year_month": year_month,
            "n_days": int(len(group)),
            "n_days_with_day_ahead": int(pd.to_numeric(group["day_ahead_mae"], errors="coerce").notna().sum()),
        }
        for mae_col, rmse_col in METRIC_PAIRS:
            mae = pd.to_numeric(group[mae_col], errors="coerce")
            rmse = pd.to_numeric(group[rmse_col], errors="coerce")
            row[mae_col] = float(mae.mean()) if mae.notna().any() else float("nan")
            row[rmse_col] = _pooled_rmse(rmse)
            row[f"{rmse_col}_mean_daily"] = float(rmse.mean()) if rmse.notna().any() else float("nan")
        for col in MAE_ONLY:
            series = pd.to_numeric(group[col], errors="coerce")
            row[col] = float(series.mean()) if series.notna().any() else float("nan")
        rows.append(row)
    monthly = pd.DataFrame(rows)
    annual = {
        "year_month": "2025-annual",
        "n_days": int(len(work)),
        "n_days_with_day_ahead": int(
            pd.to_numeric(work["day_ahead_mae"], errors="coerce").notna().sum()
        ),
    }
    for mae_col, rmse_col in METRIC_PAIRS:
        mae = pd.to_numeric(work[mae_col], errors="coerce")
        rmse = pd.to_numeric(work[rmse_col], errors="coerce")
        annual[mae_col] = float(mae.mean()) if mae.notna().any() else float("nan")
        annual[rmse_col] = _pooled_rmse(rmse)
        annual[f"{rmse_col}_mean_daily"] = float(rmse.mean()) if rmse.notna().any() else float("nan")
    for col in MAE_ONLY:
        series = pd.to_numeric(work[col], errors="coerce")
        annual[col] = float(series.mean()) if series.notna().any() else float("nan")
    return pd.concat([monthly, pd.DataFrame([annual])], ignore_index=True)


def export_price_monthly(
    audit_csv: Path = AUDIT_CSV,
    dest_csv: Path = PRICE_MONTHLY_CSV,
    dest_json: Path = PRICE_MONTHLY_JSON,
) -> dict:
    if not audit_csv.exists():
        raise FileNotFoundError(f"price audit not found: {audit_csv}")
    frame = pd.read_csv(audit_csv)
    monthly = monthly_from_audit(frame)
    dest_csv.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(dest_csv, index=False)
    payload = {
        "source": str(audit_csv),
        "aggregation": {
            "mae": "mean of daily MAE over days with a finite value",
            "rmse": "pooled RMSE = sqrt(mean of daily RMSE squared); equal slot count per day",
            "rmse_mean_daily": "mean of daily RMSE, not pooled",
            "note": "Derived from the accepted P1 audit; the price module was not refit.",
        },
        "n_months": int((monthly["year_month"] != "2025-annual").sum()),
        "rows": monthly.to_dict("records"),
    }
    dest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    report = export_price_monthly()
    print(json.dumps({"csv": str(PRICE_MONTHLY_CSV), "n_rows": len(report["rows"])}, indent=2))
