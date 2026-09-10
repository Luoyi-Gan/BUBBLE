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


def build_forecast_archive(data: Q2Data) -> ForecastArchive:
    n = len(data.dates)
    load_hat = np.empty_like(data.load)
    pv_hat = np.empty_like(data.pv)
    load_sources: list[tuple[int, ...]] = []
    pv_sources: list[tuple[int, ...]] = []
    for i, date in enumerate(data.dates):
        same_weekday = [j for j in range(i) if data.dates[j].weekday() == date.weekday()]
        ls = tuple(same_weekday[-LOAD_HISTORY_SAME_WEEKDAY:])
        ps = tuple(range(max(0, i - PV_HISTORY_DAYS), i))
        load_hat[i] = data.load[list(ls)].mean(axis=0) if ls else data.fallback_load
        pv_hat[i] = data.pv[list(ps)].mean(axis=0) if ps else data.fallback_pv
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
        frames.append(
            pd.DataFrame(
                {
                    "date": date.strftime("%Y-%m-%d"),
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

