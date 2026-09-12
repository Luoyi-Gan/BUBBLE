"""Load accepted Q2/Q3 information plus the frozen causal price archive."""

from __future__ import annotations

from dataclasses import dataclass

from q2.data import Q2Data, load_q2_data
from q2.forecast import ForecastArchive, build_forecast_archive
from q3.data import Q3Data, load_q3_data
from q4.data import Q4PriceData, load_q4_prices
from q4.price_forecast import PriceForecastArchive, fit_causal_price_forecasts


@dataclass(frozen=True)
class Q4Bundle:
    q3: Q3Data
    q2: Q2Data
    q2_forecast: ForecastArchive
    prices: Q4PriceData
    price_archive: PriceForecastArchive

    def date_index(self, date: str) -> int:
        return self.prices.date_index(date)

    def n_days(self) -> int:
        return len(self.prices.dates)


def load_q4_bundle(compute_price_mpc: bool = False) -> Q4Bundle:
    q3 = load_q3_data()
    q2 = load_q2_data()
    prices = load_q4_prices()
    if not q3.dates.equals(prices.dates) or not q2.dates.equals(prices.dates):
        raise ValueError("Q2/Q3/附件4 calendars must match")
    price_archive = fit_causal_price_forecasts(
        prices.price, prices.dates, compute_mpc=compute_price_mpc
    )
    return Q4Bundle(
        q3=q3,
        q2=q2,
        q2_forecast=build_forecast_archive(q2),
        prices=prices,
        price_archive=price_archive,
    )
