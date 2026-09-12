from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from q3.data import normalize_time
from q4.config import ATTACH4, T


def _finite_nonnegative(values: np.ndarray, name: str) -> None:
    if not np.isfinite(values).all():
        raise ValueError(f"{name} contains missing or non-finite values")
    if np.any(values < 0):
        raise ValueError(f"{name} contains negative values")


@dataclass(frozen=True)
class Q4PriceData:
    dates: pd.DatetimeIndex
    time_labels: tuple[str, ...]
    price: np.ndarray

    def date_index(self, date: str) -> int:
        return int(self.dates.get_loc(pd.Timestamp(date)))


def load_q4_prices(attach4: Path = ATTACH4) -> Q4PriceData:
    if not attach4.exists():
        raise FileNotFoundError(
            f"附件4 not found: {attach4}. Set CUMCM_C_ATTACH_DIR to the attachments folder."
        )
    raw = pd.read_excel(attach4, sheet_name=0, header=None)
    if raw.shape != (366, 145):
        raise ValueError(f"附件4 must be 366x145; got {raw.shape}")
    if raw.iloc[0, 0] != "日期\\时间":
        raise ValueError("附件4 first header must be 日期\\时间")
    time_labels = tuple(normalize_time(x) for x in raw.iloc[0, 1:])
    if len(time_labels) != T or time_labels[0] != "00:10" or time_labels[-1] != "0:00+1":
        raise ValueError(f"Unexpected 附件4 time order: {time_labels[0]} .. {time_labels[-1]}")
    dates = pd.DatetimeIndex(pd.to_datetime(raw.iloc[1:, 0], errors="raise")).normalize()
    expected = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    if not dates.equals(expected):
        raise ValueError("附件4 dates must be continuous 2025-01-01 through 2025-12-31")
    price = raw.iloc[1:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    _finite_nonnegative(price, "附件4 price")
    return Q4PriceData(dates=dates, time_labels=time_labels, price=price)
