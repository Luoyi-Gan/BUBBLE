from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from q3.config import (
    DELTA_H,
    HOUR_TO_FIRST_MUTABLE,
    LOAD_HISTORY_SAME_WEEKDAY,
    NEXT_DAY_PV_HISTORY_DAYS,
    PILOT_DATES,
    T,
    UPDATE_HOURS,
)
from q3.data import Q3Data, period_end_minutes


def previous_end_pv_kw(data: Q3Data, day_index: int) -> float:
    """Actual PV at today's 0:00, i.e. the previous day's 24:00 observation."""
    if day_index <= 0:
        return 0.0
    return float(data.pv[day_index - 1, -1] / DELTA_H)


def actual_kw(data: Q3Data, day_index: int, index: int) -> float:
    return float(data.pv[day_index, index] / DELTA_H)


def forecast_knots_minutes_kw(
    issue_hour: int, hourly_kw: np.ndarray, anchor_kw: float
) -> tuple[np.ndarray, np.ndarray]:
    """On-the-hour knots for one 24-hour-ahead forecast, plus the causal actual anchor."""
    hourly_kw = np.asarray(hourly_kw, dtype=float).ravel()
    if hourly_kw.shape != (24,):
        raise ValueError("hourly forecast must have 24 nodes")
    minutes = [issue_hour * 60]
    values = [float(anchor_kw)]
    for step, value in enumerate(hourly_kw, start=1):
        minutes.append(issue_hour * 60 + 60 * step)
        values.append(float(value))
    return np.asarray(minutes, dtype=float), np.asarray(values, dtype=float)


def interpolate_series(query_minutes: np.ndarray, knot_minutes: np.ndarray, knot_values: np.ndarray) -> np.ndarray:
    order = np.argsort(knot_minutes)
    return np.interp(query_minutes, knot_minutes[order], knot_values[order])


def interpolate_weights(
    query_minute: float, knot_minutes: np.ndarray, knot_values: np.ndarray
) -> dict:
    order = np.argsort(knot_minutes)
    minutes = knot_minutes[order]
    values = knot_values[order]
    if query_minute <= minutes[0]:
        return {
            "left_node_minute": float(minutes[0]),
            "right_node_minute": float(minutes[0]),
            "left_weight": 1.0,
            "right_weight": 0.0,
            "left_kw": float(values[0]),
            "right_kw": float(values[0]),
        }
    if query_minute >= minutes[-1]:
        return {
            "left_node_minute": float(minutes[-1]),
            "right_node_minute": float(minutes[-1]),
            "left_weight": 1.0,
            "right_weight": 0.0,
            "left_kw": float(values[-1]),
            "right_kw": float(values[-1]),
        }
    right = int(np.searchsorted(minutes, query_minute, side="left"))
    left = right - 1
    span = minutes[right] - minutes[left]
    right_weight = (query_minute - minutes[left]) / span
    left_weight = 1.0 - right_weight
    return {
        "left_node_minute": float(minutes[left]),
        "right_node_minute": float(minutes[right]),
        "left_weight": float(left_weight),
        "right_weight": float(right_weight),
        "left_kw": float(values[left]),
        "right_kw": float(values[right]),
    }


@dataclass(frozen=True)
class MappedForecast:
    today_kwh: np.ndarray
    next_day_kwh: np.ndarray
    knot_minutes: np.ndarray
    knot_kw: np.ndarray
    issue_hour: int
    first_mutable_index: int


def map_issue_forecast(
    data: Q3Data, day_index: int, issue_hour: int
) -> MappedForecast:
    """Map one 附件3 row onto today/next-day 10-minute energy using only causal anchors."""
    hourly_kw = data.hourly_forecast_kw[issue_hour][day_index]
    if issue_hour == 0:
        anchor_kw = previous_end_pv_kw(data, day_index)
    else:
        anchor_index = 6 * issue_hour - 1
        anchor_kw = actual_kw(data, day_index, anchor_index)
    knot_minutes, knot_kw = forecast_knots_minutes_kw(issue_hour, hourly_kw, anchor_kw)
    today_minutes = np.array([period_end_minutes(t) for t in range(T)], dtype=float)
    next_minutes = today_minutes + 24 * 60
    today_kwh = interpolate_series(today_minutes, knot_minutes, knot_kw) * DELTA_H
    next_kwh = interpolate_series(next_minutes, knot_minutes, knot_kw) * DELTA_H
    # Periods already observed at the issue time are filled with actuals for the
    # mapping table, but they are never used as future interpolation anchors.
    first_mutable = HOUR_TO_FIRST_MUTABLE[issue_hour]
    if first_mutable > 0:
        today_kwh[:first_mutable] = data.pv[day_index, :first_mutable]
    today_kwh = np.maximum(today_kwh, 0.0)
    next_kwh = np.maximum(next_kwh, 0.0)
    return MappedForecast(
        today_kwh=today_kwh,
        next_day_kwh=next_kwh,
        knot_minutes=knot_minutes,
        knot_kw=knot_kw,
        issue_hour=issue_hour,
        first_mutable_index=first_mutable,
    )


def causal_load_forecast(
    data: Q3Data, target_index: int, history_end_exclusive: int
) -> np.ndarray:
    """Load forecast for target_index using only complete days before the cutoff."""
    if history_end_exclusive <= 0:
        return data.fallback_load.copy()
    if history_end_exclusive > target_index:
        raise ValueError("load forecast cutoff must not exceed the target date")
    target_weekday = data.dates[target_index].weekday()
    sources = [
        j
        for j in range(history_end_exclusive)
        if data.dates[j].weekday() == target_weekday
    ][-LOAD_HISTORY_SAME_WEEKDAY:]
    if not sources:
        return data.fallback_load.copy()
    return data.load[sources].mean(axis=0)


def causal_next_day_pv_base(data: Q3Data, day_index: int) -> np.ndarray:
    """Causal stand-in for the next day's 0:00 PV forecast, in kWh."""
    start = max(0, day_index - NEXT_DAY_PV_HISTORY_DAYS)
    if start >= day_index:
        return data.fallback_pv.copy()
    mapped = np.vstack(
        [map_issue_forecast(data, j, 0).today_kwh for j in range(start, day_index)]
    )
    return mapped.mean(axis=0)


def next_day_pv_forecast(data: Q3Data, day_index: int, issue_hour: int) -> np.ndarray:
    """Next-day PV used only in the terminal-value / 48h module."""
    if day_index + 1 >= len(data.dates):
        return np.zeros(T)
    mapped = map_issue_forecast(data, day_index, issue_hour)
    overlay = mapped.next_day_kwh.copy()
    # Hours not covered by the current 24h forecast stay at the causal 0:00 base.
    # np.interp holds the last knot constantly after the horizon; those held-forward
    # daytime values would leak a stale evening forecast, so replace them.
    last_knot = float(mapped.knot_minutes[-1])
    uncovered = np.array(
        [period_end_minutes(t) + 24 * 60 > last_knot + 1e-9 for t in range(T)],
        dtype=bool,
    )
    base = causal_next_day_pv_base(data, day_index + 1)
    overlay[uncovered] = base[uncovered]
    return np.maximum(overlay, 0.0)


def mapping_rows_for_day(data: Q3Data, day_index: int) -> list[dict]:
    date = data.dates[day_index].strftime("%Y-%m-%d")
    rows: list[dict] = []
    for hour in UPDATE_HOURS:
        mapped = map_issue_forecast(data, day_index, hour)
        for t in range(T):
            query = float(period_end_minutes(t))
            executed = t < mapped.first_mutable_index
            weights = interpolate_weights(query, mapped.knot_minutes, mapped.knot_kw)
            forecast_kwh = (
                float(data.pv[day_index, t]) if executed else float(mapped.today_kwh[t])
            )
            rows.append(
                {
                    "date": date,
                    "update_time": f"{hour:02d}:00",
                    "period": t,
                    "time": data.time_labels[t],
                    "forecast_kwh": forecast_kwh,
                    "actual_pv_kwh": float(data.pv[day_index, t]),
                    "left_node_minute": weights["left_node_minute"],
                    "right_node_minute": weights["right_node_minute"],
                    "left_weight": weights["left_weight"],
                    "right_weight": weights["right_weight"],
                    "is_executed_actual": bool(executed),
                    "source": "actual_executed" if executed else "causal_hourly_interpolation",
                }
            )
    return rows


def write_forecast_mapping(data: Q3Data, path) -> pd.DataFrame:
    frames = []
    for date in PILOT_DATES:
        frames.extend(mapping_rows_for_day(data, data.date_index(date)))
    frame = pd.DataFrame(frames)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame
