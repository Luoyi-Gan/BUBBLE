from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import LOAD_HISTORY_SAME_WEEKDAY, PV_HISTORY_DAYS, T
from q2.data import Q2Data


@dataclass(frozen=True)
class ForecastArchive:
    load_hat: np.ndarray
    pv_hat: np.ndarray
    load_residual: np.ndarray
    pv_residual: np.ndarray
    load_sources: tuple[tuple[int, ...], ...]
    pv_sources: tuple[tuple[int, ...], ...]


def forecast_as_of(
    data: Q2Data, target_index: int, history_end_exclusive: int
) -> tuple[np.ndarray, np.ndarray, tuple[int, ...], tuple[int, ...]]:
    """Forecast target using actual observations with index < history_end_exclusive."""
    if not 0 <= history_end_exclusive <= target_index:
        raise ValueError("forecast cutoff must not exceed target date")
    target = data.dates[target_index]
    same_weekday = [
        j
        for j in range(history_end_exclusive)
        if data.dates[j].weekday() == target.weekday()
    ]
    load_sources = tuple(same_weekday[-LOAD_HISTORY_SAME_WEEKDAY:])
    pv_sources = tuple(
        range(max(0, history_end_exclusive - PV_HISTORY_DAYS), history_end_exclusive)
    )
    load_hat = (
        data.load[list(load_sources)].mean(axis=0)
        if load_sources
        else data.fallback_load.copy()
    )
    pv_hat = (
        data.pv[list(pv_sources)].mean(axis=0)
        if pv_sources
        else data.fallback_pv.copy()
    )
    return load_hat, pv_hat, load_sources, pv_sources


def build_forecast_archive(data: Q2Data) -> ForecastArchive:
    n = len(data.dates)
    load_hat = np.empty_like(data.load)
    pv_hat = np.empty_like(data.pv)
    load_sources: list[tuple[int, ...]] = []
    pv_sources: list[tuple[int, ...]] = []
    for i in range(n):
        load_hat[i], pv_hat[i], ls, ps = forecast_as_of(data, i, i)
        load_sources.append(ls)
        pv_sources.append(ps)
    return ForecastArchive(
        load_hat=load_hat,
        pv_hat=pv_hat,
        load_residual=data.load - load_hat,
        pv_residual=data.pv - pv_hat,
        load_sources=tuple(load_sources),
        pv_sources=tuple(pv_sources),
    )


def assert_no_forecast_leakage(archive: ForecastArchive) -> None:
    for i, (load_sources, pv_sources) in enumerate(
        zip(archive.load_sources, archive.pv_sources)
    ):
        if any(j >= i for j in load_sources + pv_sources):
            raise AssertionError(f"forecast leakage at day index {i}")


def write_forecast_archive(
    data: Q2Data, archive: ForecastArchive, csv_path: Path, audit_path: Path
) -> None:
    frames = []
    for i, date in enumerate(data.dates):
        load_source_dates = ";".join(
            data.dates[j].strftime("%Y-%m-%d") for j in archive.load_sources[i]
        )
        pv_source_dates = ";".join(
            data.dates[j].strftime("%Y-%m-%d") for j in archive.pv_sources[i]
        )
        frames.append(
            pd.DataFrame(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "information_cutoff": (
                        data.dates[i - 1].strftime("%Y-%m-%d") if i else "attachment1_fallback"
                    ),
                    "load_source_dates": load_source_dates or "attachment1_fallback",
                    "pv_source_dates": pv_source_dates or "attachment1_fallback",
                    "period": np.arange(T),
                    "time": data.time_labels,
                    "load_hat_kwh": archive.load_hat[i],
                    "pv_hat_kwh": archive.pv_hat[i],
                    "actual_load_kwh": data.load[i],
                    "actual_pv_kwh": data.pv[i],
                    "load_residual_kwh": archive.load_residual[i],
                    "pv_residual_kwh": archive.pv_residual[i],
                }
            )
        )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(csv_path, index=False)

    lines = [
        "# Q2 预测无泄漏审计",
        "",
        "- 负荷：日期严格早于目标日的最近至多 4 个同星期历史日。",
        "- 光伏：日期严格早于目标日的最近至多 7 个历史日。",
        "- 若没有可用历史日，使用附件 1 固定预测曲线；不读取目标日实际值。",
        "",
    ]
    for target in ("2025-02-01", "2025-06-21"):
        i = int(data.dates.get_loc(pd.Timestamp(target)))
        load_dates = [data.dates[j].strftime("%Y-%m-%d") for j in archive.load_sources[i]]
        pv_dates = [data.dates[j].strftime("%Y-%m-%d") for j in archive.pv_sources[i]]
        valid = all(j < i for j in archive.load_sources[i] + archive.pv_sources[i])
        lines += [
            f"## {target}",
            "",
            f"- 负荷样本日期：{', '.join(load_dates) or '无（附件1回退）'}",
            f"- 光伏样本日期：{', '.join(pv_dates) or '无（附件1回退）'}",
            f"- 所有样本日期严格早于目标日期：{valid}",
            "",
        ]
    audit_path.write_text("\n".join(lines), encoding="utf-8")

