from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import ATTACH1, ATTACH2, DELTA_H, T


def normalize_time(value: object) -> str:
    if isinstance(value, (datetime, time)):
        return value.strftime("%H:%M")
    return str(value).strip()


@dataclass(frozen=True)
class Q2Data:
    dates: pd.DatetimeIndex
    time_labels: tuple[str, ...]
    price: np.ndarray
    fallback_load: np.ndarray
    fallback_pv: np.ndarray
    load: np.ndarray
    pv: np.ndarray


def _finite_nonnegative(values: np.ndarray, name: str) -> None:
    if not np.isfinite(values).all():
        raise ValueError(f"{name} contains missing or non-finite values")
    if np.any(values < 0):
        raise ValueError(f"{name} contains negative values")


def load_q2_data(attach1: Path = ATTACH1, attach2: Path = ATTACH2) -> Q2Data:
    if not attach1.exists() or not attach2.exists():
        raise FileNotFoundError(f"Required attachments not found: {attach1}, {attach2}")

    day = pd.read_excel(attach1, sheet_name="Sheet1")
    expected = ["时间", "电价", "小区负载", "光伏发电预测功率"]
    if list(day.columns) != expected or len(day) != T:
        raise ValueError("附件1 must have the four expected columns and 144 raw-order rows")
    price = pd.to_numeric(day["电价"], errors="coerce").to_numpy(float)
    fallback_load = pd.to_numeric(day["小区负载"], errors="coerce").to_numpy(float) * DELTA_H
    fallback_pv = pd.to_numeric(day["光伏发电预测功率"], errors="coerce").to_numpy(float) * DELTA_H
    _finite_nonnegative(price, "附件1 price")
    _finite_nonnegative(fallback_load, "附件1 load forecast")
    _finite_nonnegative(fallback_pv, "附件1 PV forecast")
    if np.any(price <= 0):
        raise ValueError("Q2 pilot requires strictly positive prices")

    sheets = pd.read_excel(attach2, sheet_name=None, header=None)
    if list(sheets) != ["小区负载", "光伏发电实际功率"]:
        raise ValueError(f"Unexpected 附件2 sheets: {list(sheets)}")
    load_raw = sheets["小区负载"]
    pv_raw = sheets["光伏发电实际功率"]
    if load_raw.shape != (366, 145) or pv_raw.shape != (366, 145):
        raise ValueError(f"附件2 must be 366x145; got {load_raw.shape}, {pv_raw.shape}")
    if load_raw.iloc[0, 0] != "日期\\时间" or pv_raw.iloc[0, 0] != "日期\\时间":
        raise ValueError("附件2 first header must be 日期\\时间")

    time_labels = tuple(normalize_time(x) for x in load_raw.iloc[0, 1:])
    pv_labels = tuple(normalize_time(x) for x in pv_raw.iloc[0, 1:])
    if time_labels != pv_labels or len(time_labels) != T:
        raise ValueError("附件2 load/PV time labels differ")
    if time_labels[0] != "00:10" or time_labels[-1] != "0:00+1":
        raise ValueError(f"Unexpected raw time order: {time_labels[0]} .. {time_labels[-1]}")

    dates = pd.DatetimeIndex(pd.to_datetime(load_raw.iloc[1:, 0], errors="raise")).normalize()
    pv_dates = pd.DatetimeIndex(pd.to_datetime(pv_raw.iloc[1:, 0], errors="raise")).normalize()
    expected_dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    if not dates.equals(expected_dates) or not pv_dates.equals(expected_dates):
        raise ValueError("附件2 dates must be continuous 2025-01-01 through 2025-12-31")
    load = load_raw.iloc[1:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(float) * DELTA_H
    pv = pv_raw.iloc[1:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(float) * DELTA_H
    _finite_nonnegative(load, "附件2 load")
    _finite_nonnegative(pv, "附件2 PV")
    return Q2Data(dates, time_labels, price, fallback_load, fallback_pv, load, pv)


def write_input_audit(data: Q2Data, path: Path) -> None:
    daily = []
    for i, date in enumerate(data.dates):
        load = float(data.load[i].sum())
        pv = float(data.pv[i].sum())
        daily.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "load_kwh": load,
                "pv_kwh": pv,
                "net_load_kwh": load - pv,
            }
        )
    audit = {
        "shape": {"days": len(data.dates), "periods_per_day": T},
        "date_start": data.dates[0].strftime("%Y-%m-%d"),
        "date_end": data.dates[-1].strftime("%Y-%m-%d"),
        "dates_continuous": True,
        "missing_count": int(np.isnan(data.load).sum() + np.isnan(data.pv).sum()),
        "negative_load_count": int(np.sum(data.load < 0)),
        "negative_pv_count": int(np.sum(data.pv < 0)),
        "price_min_yuan_per_kwh": float(data.price.min()),
        "unit_conversion": "attachment powers multiplied by 1/6 h to obtain kWh",
        "time_mapping": (
            "attachment raw column t maps to internal index t=0..143 and template column t; "
            "no sorting, rotation, or invented 0:00-0:10 period"
        ),
        "first_time_label": data.time_labels[0],
        "last_time_label": data.time_labels[-1],
        "daily_energy": daily,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

