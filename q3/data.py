from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

from q3.config import ATTACH1, ATTACH2, ATTACH3, DELTA_H, PILOT_DATES, T, UPDATE_HOURS


def normalize_time(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    text = str(value).strip()
    if text in {"0:00+1", "24:00"}:
        return text
    if len(text) == 4 and text[1] == ":":
        return "0" + text
    return text


def normalize_clock_hour(value: object) -> int:
    text = normalize_time(value).replace("：", ":")
    if text in {"0:00", "00:00"}:
        return 0
    hour, minute = text.split(":")[:2]
    if int(minute) != 0:
        raise ValueError(f"Attachment 3 issue time is not on the hour: {value!r}")
    return int(hour)


def _finite_nonnegative(values: np.ndarray, name: str) -> None:
    if not np.isfinite(values).all():
        raise ValueError(f"{name} contains missing or non-finite values")
    if np.any(values < 0):
        raise ValueError(f"{name} contains negative values")


@dataclass(frozen=True)
class Q3Data:
    dates: pd.DatetimeIndex
    time_labels: tuple[str, ...]
    price: np.ndarray
    fallback_load: np.ndarray
    fallback_pv: np.ndarray
    load: np.ndarray
    pv: np.ndarray
    # issue_hour -> (n_days, 24) hourly PV forecast in kW
    hourly_forecast_kw: dict[int, np.ndarray]

    def date_index(self, date: str) -> int:
        return int(self.dates.get_loc(pd.Timestamp(date)))


def load_q3_data(
    attach1: Path = ATTACH1,
    attach2: Path = ATTACH2,
    attach3: Path = ATTACH3,
) -> Q3Data:
    missing = [str(path) for path in (attach1, attach2, attach3) if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Required attachments not found: "
            + ", ".join(missing)
            + ". Set CUMCM_C_ATTACH_DIR to the folder containing 附件1/2/3.xlsx."
        )

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
        raise ValueError("Q3 requires strictly positive prices")

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

    forecast = pd.read_excel(attach3, sheet_name=0)
    expected_forecast_cols = ["日期", "预报时刻"] + [f"预报{h}小时" for h in range(1, 25)]
    if list(forecast.columns) != expected_forecast_cols:
        raise ValueError(f"Unexpected 附件3 columns: {list(forecast.columns)}")
    if len(forecast) != 4 * len(dates):
        raise ValueError(f"附件3 must have 4 rows per day; got {len(forecast)}")
    forecast = forecast.copy()
    forecast["日期"] = forecast["日期"].ffill()
    forecast["date"] = pd.to_datetime(forecast["日期"], errors="raise").dt.normalize()
    forecast["issue_hour"] = forecast["预报时刻"].map(normalize_clock_hour)
    hourly_values = (
        forecast[[f"预报{h}小时" for h in range(1, 25)]]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(float)
    )
    _finite_nonnegative(hourly_values, "附件3 PV forecast")
    if set(forecast["issue_hour"].unique()) != set(UPDATE_HOURS):
        raise ValueError(f"Unexpected 附件3 issue hours: {sorted(forecast['issue_hour'].unique())}")
    forecast_dates = pd.DatetimeIndex(forecast["date"].drop_duplicates()).normalize()
    if not forecast_dates.equals(dates):
        raise ValueError("附件3 dates do not match 附件2")

    hourly_forecast_kw = {}
    for hour in UPDATE_HOURS:
        block = forecast.loc[forecast["issue_hour"] == hour].sort_values("date")
        if len(block) != len(dates):
            raise ValueError(f"附件3 is missing {hour:02d}:00 rows")
        if not pd.DatetimeIndex(block["date"]).equals(dates):
            raise ValueError(f"附件3 {hour:02d}:00 dates are not aligned")
        hourly_forecast_kw[hour] = block[[f"预报{h}小时" for h in range(1, 25)]].to_numpy(float)

    return Q3Data(
        dates=dates,
        time_labels=time_labels,
        price=price,
        fallback_load=fallback_load,
        fallback_pv=fallback_pv,
        load=load,
        pv=pv,
        hourly_forecast_kw=hourly_forecast_kw,
    )


def period_end_minutes(index: int) -> int:
    """Minutes after 0:00 at the end of the 10-minute period with internal index."""
    return 10 * (index + 1)


def write_input_audit(data: Q3Data, path: Path) -> None:
    attach3_rows = []
    for date in PILOT_DATES:
        i = data.date_index(date)
        for hour in UPDATE_HOURS:
            hourly = data.hourly_forecast_kw[hour][i]
            attach3_rows.append(
                {
                    "date": date,
                    "issue_hour": hour,
                    "n_hourly_nodes": 24,
                    "first_hour_kw": float(hourly[0]),
                    "hour12_kw": float(hourly[11]),
                    "last_hour_kw": float(hourly[23]),
                    "sum_kw": float(hourly.sum()),
                    "zero_count": int(np.sum(hourly == 0.0)),
                }
            )
    audit = {
        "shape": {
            "days": len(data.dates),
            "periods_per_day": T,
            "attach3_rows": 4 * len(data.dates),
        },
        "date_start": data.dates[0].strftime("%Y-%m-%d"),
        "date_end": data.dates[-1].strftime("%Y-%m-%d"),
        "dates_continuous": True,
        "missing_count": int(
            np.isnan(data.load).sum()
            + np.isnan(data.pv).sum()
            + sum(np.isnan(arr).sum() for arr in data.hourly_forecast_kw.values())
        ),
        "negative_load_count": int(np.sum(data.load < 0)),
        "negative_pv_count": int(np.sum(data.pv < 0)),
        "negative_forecast_count": int(
            sum(np.sum(arr < 0) for arr in data.hourly_forecast_kw.values())
        ),
        "price_min_yuan_per_kwh": float(data.price.min()),
        "unit_conversion": "attachment powers multiplied by 1/6 h to obtain kWh",
        "time_mapping": (
            "attachment raw column t maps to internal index t=0..143 and template column t; "
            "no sorting, rotation, or invented 0:00-0:10 period"
        ),
        "first_time_label": data.time_labels[0],
        "last_time_label": data.time_labels[-1],
        "attach3_issue_hours": list(UPDATE_HOURS),
        "attach3_complete_four_rows_per_day": True,
        "forecast_horizon": (
            "each 附件3 row is a 24-hour-ahead on-the-hour forecast in kW; "
            "hour k after issue hour H is clock time H+k, wrapping into the next day"
        ),
        "update_index_map": {
            "0:00": {"first_mutable_index": 0, "label": data.time_labels[0]},
            "6:00": {
                "last_locked_index": 35,
                "last_locked_label": data.time_labels[35],
                "first_mutable_index": 36,
                "first_mutable_label": data.time_labels[36],
            },
            "12:00": {
                "last_locked_index": 71,
                "last_locked_label": data.time_labels[71],
                "first_mutable_index": 72,
                "first_mutable_label": data.time_labels[72],
            },
            "18:00": {
                "last_locked_index": 107,
                "last_locked_label": data.time_labels[107],
                "first_mutable_index": 108,
                "first_mutable_label": data.time_labels[108],
            },
        },
        "pilot_attach3_spotcheck": attach3_rows,
        "daily_energy_pilot": [
            {
                "date": date,
                "load_kwh": float(data.load[data.date_index(date)].sum()),
                "pv_kwh": float(data.pv[data.date_index(date)].sum()),
                "net_load_kwh": float(
                    data.load[data.date_index(date)].sum()
                    - data.pv[data.date_index(date)].sum()
                ),
            }
            for date in PILOT_DATES
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
