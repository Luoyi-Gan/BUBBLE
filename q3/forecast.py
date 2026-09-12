from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from q3.config import (
    DELTA_H,
    HOUR_TO_FIRST_MUTABLE,
    LOAD_HISTORY_SAME_WEEKDAY,
    LOAD_INFORMATION_MAIN,
    LOAD_INFORMATION_PROXY,
    NEXT_DAY_PV_HISTORY_DAYS,
    PILOT_DATES,
    PV_MAPPING_LINEAR,
    PV_MAPPING_STEP,
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
    pv_mapping_mode: str
    today_source_k: np.ndarray
    next_source_k: np.ndarray
    today_covered: np.ndarray
    next_covered: np.ndarray


def forecast_hour_k(end_minutes: float, issue_hour: int) -> int:
    """1-based 预报k小时 index for a period ending at end_minutes after today's 0:00."""
    delta_min = float(end_minutes) - 60.0 * issue_hour
    if delta_min <= 1e-9:
        return 0
    return int(np.ceil(delta_min / 60.0 - 1e-12))


def step_hourly_energy(hourly_kw: np.ndarray, issue_hour: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Piecewise-constant map: 预报 k 小时 fills (H+k-1, H+k]."""
    hourly_kw = np.asarray(hourly_kw, dtype=float).ravel()
    today = np.zeros(T)
    nxt = np.zeros(T)
    today_k = np.zeros(T, dtype=int)
    next_k = np.zeros(T, dtype=int)
    for t in range(T):
        end_today = float(period_end_minutes(t))
        k_today = forecast_hour_k(end_today, issue_hour)
        today_k[t] = k_today if 1 <= k_today <= 24 else 0
        if 1 <= k_today <= 24:
            today[t] = hourly_kw[k_today - 1] * DELTA_H
        k_next = forecast_hour_k(end_today + 24 * 60, issue_hour)
        next_k[t] = k_next if 1 <= k_next <= 24 else 0
        if 1 <= k_next <= 24:
            nxt[t] = hourly_kw[k_next - 1] * DELTA_H
    return today, nxt, today_k, next_k


def map_issue_forecast(
    data: Q3Data,
    day_index: int,
    issue_hour: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> MappedForecast:
    """Map one 附件3 row onto today/next-day 10-minute energy using only causal anchors."""
    hourly_kw = data.hourly_forecast_kw[issue_hour][day_index]
    first_mutable = HOUR_TO_FIRST_MUTABLE[issue_hour]
    if pv_mapping_mode == PV_MAPPING_STEP:
        today_kwh, next_kwh, today_k, next_k = step_hourly_energy(hourly_kw, issue_hour)
        knot_minutes = issue_hour * 60 + 60 * np.arange(1, 25, dtype=float)
        knot_kw = np.asarray(hourly_kw, dtype=float).ravel()
        today_covered = today_k > 0
        next_covered = next_k > 0
    elif pv_mapping_mode == PV_MAPPING_LINEAR:
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
        last_knot = float(knot_minutes[-1])
        today_covered = today_minutes <= last_knot + 1e-9
        next_covered = next_minutes <= last_knot + 1e-9
        today_k = np.array([forecast_hour_k(m, issue_hour) for m in today_minutes], dtype=int)
        next_k = np.array([forecast_hour_k(m, issue_hour) for m in next_minutes], dtype=int)
        today_k = np.where((today_k >= 1) & (today_k <= 24), today_k, 0)
        next_k = np.where((next_k >= 1) & (next_k <= 24), next_k, 0)
    else:
        raise ValueError(f"unknown pv_mapping_mode: {pv_mapping_mode}")

    # Periods already observed at the issue time are filled with actuals for the
    # mapping table, but they are never used as future interpolation anchors.
    if first_mutable > 0:
        today_kwh[:first_mutable] = data.pv[day_index, :first_mutable]
        today_k[:first_mutable] = 0
        today_covered[:first_mutable] = False
    today_kwh = np.maximum(today_kwh, 0.0)
    next_kwh = np.maximum(next_kwh, 0.0)
    return MappedForecast(
        today_kwh=today_kwh,
        next_day_kwh=next_kwh,
        knot_minutes=knot_minutes,
        knot_kw=knot_kw,
        issue_hour=issue_hour,
        first_mutable_index=first_mutable,
        pv_mapping_mode=pv_mapping_mode,
        today_source_k=today_k,
        next_source_k=next_k,
        today_covered=today_covered,
        next_covered=next_covered,
    )


def causal_load_sources(
    data: Q3Data, target_index: int, history_end_exclusive: int
) -> tuple[np.ndarray, tuple[int, ...], str]:
    """Q2-style day-ahead load forecast: last <=4 same-weekday complete days."""
    if history_end_exclusive > target_index:
        raise ValueError("load forecast cutoff must not exceed the target date")
    if history_end_exclusive <= 0:
        return data.fallback_load.copy(), (), "attachment1_fallback"
    target_weekday = data.dates[target_index].weekday()
    sources = tuple(
        j
        for j in range(history_end_exclusive)
        if data.dates[j].weekday() == target_weekday
    )[-LOAD_HISTORY_SAME_WEEKDAY:]
    if not sources:
        return data.fallback_load.copy(), (), "attachment1_fallback"
    label = ";".join(data.dates[j].strftime("%Y-%m-%d") for j in sources)
    return data.load[list(sources)].mean(axis=0), sources, label


def causal_load_forecast(
    data: Q3Data, target_index: int, history_end_exclusive: int
) -> np.ndarray:
    """Load forecast for target_index using only complete days before the cutoff."""
    hat, _sources, _label = causal_load_sources(data, target_index, history_end_exclusive)
    return hat


def planning_load_curve(
    data: Q3Data, day_index: int, load_information_case: str
) -> np.ndarray:
    """Future-load vector used at 0:00 and later updates.

    causal_load_main: day-ahead hat formed at 0:00; never reread today's actuals.
    actual_load_proxy: full Attachment 2 path, idealized information only.
    """
    if load_information_case == LOAD_INFORMATION_MAIN:
        return causal_load_forecast(data, day_index, day_index)
    if load_information_case == LOAD_INFORMATION_PROXY:
        return data.load[day_index].copy()
    raise ValueError(f"unknown load_information_case: {load_information_case}")


def execution_load_horizon(
    plan_load: np.ndarray, actual_load: np.ndarray, t: int
) -> np.ndarray:
    """Current 10-minute step uses actual load; later steps keep the 0:00 hat."""
    horizon = np.asarray(plan_load[t:], dtype=float).copy()
    horizon[0] = float(np.asarray(actual_load, dtype=float)[t])
    return horizon


def load_forecast_audit_rows(data: Q3Data, day_index: int) -> list[dict]:
    """Day-ahead causal load vs Attachment 2 actuals; future periods are not executed yet."""
    date = data.dates[day_index].strftime("%Y-%m-%d")
    hat, _sources, label = causal_load_sources(data, day_index, day_index)
    actual = data.load[day_index]
    rows: list[dict] = []
    for t in range(T):
        forecast = float(hat[t])
        observed = float(actual[t])
        rows.append(
            {
                "date": date,
                "period": t,
                "time": data.time_labels[t],
                "forecast_load_kwh": forecast,
                "actual_load_kwh": observed,
                "source_dates": label,
                "is_current_execution_period": False,
                "abs_error_kwh": abs(forecast - observed),
                "load_information_case": LOAD_INFORMATION_MAIN,
                "snapshot": "day_ahead_planning",
            }
        )
    return rows


def causal_next_day_pv_base(
    data: Q3Data,
    day_index: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> np.ndarray:
    """Causal stand-in for the next day's 0:00 PV forecast, in kWh."""
    start = max(0, day_index - NEXT_DAY_PV_HISTORY_DAYS)
    if start >= day_index:
        return data.fallback_pv.copy()
    mapped = np.vstack(
        [
            map_issue_forecast(data, j, 0, pv_mapping_mode).today_kwh
            for j in range(start, day_index)
        ]
    )
    return mapped.mean(axis=0)


def next_day_pv_forecast(
    data: Q3Data,
    day_index: int,
    issue_hour: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> np.ndarray:
    """Next-day PV used only in the terminal-value / 48h module."""
    if day_index + 1 >= len(data.dates):
        return np.zeros(T)
    mapped = map_issue_forecast(data, day_index, issue_hour, pv_mapping_mode)
    overlay = mapped.next_day_kwh.copy()
    base = causal_next_day_pv_base(data, day_index + 1, pv_mapping_mode)
    overlay[~mapped.next_covered] = base[~mapped.next_covered]
    return np.maximum(overlay, 0.0)


def _source_interval_label(issue_hour: int, k: int) -> str:
    if k <= 0:
        return ""
    start = issue_hour + k - 1
    end = issue_hour + k
    def clock(h: int) -> str:
        day = ""
        if h >= 24:
            h -= 24
            day = "+1"
        return f"{h:02d}:00{day}"
    return f"({clock(start)},{clock(end)}]"


def mapping_rows_for_day(
    data: Q3Data,
    day_index: int,
    pv_mapping_mode: str = PV_MAPPING_LINEAR,
) -> list[dict]:
    date = data.dates[day_index].strftime("%Y-%m-%d")
    rows: list[dict] = []
    for hour in UPDATE_HOURS:
        mapped = map_issue_forecast(data, day_index, hour, pv_mapping_mode)
        for t in range(T):
            query = float(period_end_minutes(t))
            executed = t < mapped.first_mutable_index
            k = int(mapped.today_source_k[t])
            if pv_mapping_mode == PV_MAPPING_LINEAR and not executed:
                weights = interpolate_weights(query, mapped.knot_minutes, mapped.knot_kw)
            elif executed:
                weights = {
                    "left_node_minute": query,
                    "right_node_minute": query,
                    "left_weight": 1.0,
                    "right_weight": 0.0,
                    "left_kw": float(data.pv[day_index, t] / DELTA_H),
                    "right_kw": float(data.pv[day_index, t] / DELTA_H),
                }
            else:
                left_min = (hour + max(k, 1) - 1) * 60
                right_min = (hour + max(k, 1)) * 60
                weights = {
                    "left_node_minute": float(left_min),
                    "right_node_minute": float(right_min),
                    "left_weight": 1.0 if k else 0.0,
                    "right_weight": 0.0,
                    "left_kw": float(mapped.today_kwh[t] / DELTA_H) if k else 0.0,
                    "right_kw": float(mapped.today_kwh[t] / DELTA_H) if k else 0.0,
                }
            forecast_kwh = (
                float(data.pv[day_index, t]) if executed else float(mapped.today_kwh[t])
            )
            source = "actual_executed" if executed else (
                "step_hourly" if pv_mapping_mode == PV_MAPPING_STEP else "causal_hourly_interpolation"
            )
            rows.append(
                {
                    "date": date,
                    "update_time": f"{hour:02d}:00",
                    "period": t,
                    "time": data.time_labels[t],
                    "forecast_kwh": forecast_kwh,
                    "actual_pv_kwh": float(data.pv[day_index, t]),
                    "pv_mapping_mode": pv_mapping_mode,
                    "source_forecast_hour": k,
                    "source_interval": "" if executed else _source_interval_label(hour, k),
                    "left_node_minute": weights["left_node_minute"],
                    "right_node_minute": weights["right_node_minute"],
                    "left_weight": weights["left_weight"],
                    "right_weight": weights["right_weight"],
                    "is_executed_actual": bool(executed),
                    "source": source,
                }
            )
    return rows


def write_forecast_mapping(data: Q3Data, path, pv_mapping_mode: str = PV_MAPPING_LINEAR) -> pd.DataFrame:
    frames = []
    for date in PILOT_DATES:
        frames.extend(mapping_rows_for_day(data, data.date_index(date), pv_mapping_mode))
    frame = pd.DataFrame(frames)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def write_forecast_mapping_modes(data: Q3Data, path, modes: tuple[str, ...] | None = None) -> pd.DataFrame:
    modes = modes or (PV_MAPPING_LINEAR, PV_MAPPING_STEP)
    rows: list[dict] = []
    for mode in modes:
        for date in PILOT_DATES:
            rows.extend(mapping_rows_for_day(data, data.date_index(date), mode))
    frame = pd.DataFrame(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame
