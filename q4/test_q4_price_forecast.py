from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from q4.config import ATTACH4, T
from q4.price_forecast import (
    assert_no_future_price_leak,
    construct_candidate,
    fit_causal_price_forecasts,
    intraday_price_forecast,
    ols_remaining,
)


def _calendar(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2025-01-01", periods=n, freq="D")


class CandidateConstructionTests(unittest.TestCase):
    def test_prev_day_and_weekday_windows(self) -> None:
        dates = _calendar(15)
        weekdays = dates.weekday.to_numpy()
        prices = np.arange(15 * T, dtype=float).reshape(15, T)
        self.assertIsNone(construct_candidate(prices, weekdays, 0, 1))
        np.testing.assert_allclose(construct_candidate(prices, weekdays, 3, 1), prices[2])
        # 2025-01-01 is Wednesday; day 14 is also Wednesday with two prior Wednesdays (0 and 7).
        hat2 = construct_candidate(prices, weekdays, 14, 2)
        self.assertIsNotNone(hat2)
        np.testing.assert_allclose(hat2, 0.5 * (prices[0] + prices[7]))
        self.assertIsNone(construct_candidate(prices, weekdays, 7, 4))


class OnlineSelectionTests(unittest.TestCase):
    def test_tie_break_prefers_shorter_history(self) -> None:
        dates = _calendar(10)
        prices = np.ones((10, T))
        archive = fit_causal_price_forecasts(prices, dates)
        # After day 0 (no forecast), day 1 has only prev-day. Later all MAEs are ~0 so pick 1.
        self.assertEqual(int(archive.chosen_model[0]), -1)
        self.assertEqual(int(archive.chosen_model[1]), 1)
        self.assertTrue(np.all(archive.chosen_model[1:] == 1))

    def test_selection_ignores_current_and_future_prices(self) -> None:
        dates = _calendar(12)
        rng = np.random.default_rng(0)
        prices = rng.uniform(0.2, 0.8, size=(12, T))
        assert_no_future_price_leak(prices, dates, day_index=8, tau=0)
        assert_no_future_price_leak(prices, dates, day_index=8, tau=36)

    def test_weekday_fallback_to_previous_day(self) -> None:
        dates = _calendar(3)
        prices = np.linspace(0.1, 0.9, 3 * T).reshape(3, T)
        archive = fit_causal_price_forecasts(prices, dates)
        self.assertEqual(archive.audit.loc[1, "day_ahead_fallback"], "previous_day_only")
        self.assertEqual(archive.audit.loc[1, "chosen_model_name"], "prev_day")


class OLSTests(unittest.TestCase):
    def test_fallback_when_too_few_or_zero_variance(self) -> None:
        delta, fb = ols_remaining(np.zeros((0, 3)), np.zeros(0), 0.1)
        np.testing.assert_allclose(delta, np.zeros(3))
        self.assertTrue(fb)
        delta, fb = ols_remaining(np.array([[1.0, 2.0, 3.0]]), np.array([0.5]), 0.2)
        np.testing.assert_allclose(delta, [1.0, 2.0, 3.0])
        self.assertTrue(fb)
        r = np.array([[1.0, 2.0], [3.0, 4.0]])
        z = np.array([5.0, 5.0])
        delta, fb = ols_remaining(r, z, 5.0)
        np.testing.assert_allclose(delta, r.mean(axis=0))
        self.assertTrue(fb)

    def test_recovers_linear_residual(self) -> None:
        z = np.array([0.0, 1.0, 2.0, 3.0])
        r = np.stack([1.0 + 2.0 * z, 4.0 - 0.5 * z], axis=1)
        delta, fb = ols_remaining(r, z, 2.5)
        self.assertFalse(fb)
        np.testing.assert_allclose(delta, [1.0 + 2.0 * 2.5, 4.0 - 0.5 * 2.5])

    def test_clamp_at_zero(self) -> None:
        actual = np.zeros(T)
        da = np.full(T, 0.1)
        hist_a = np.zeros((3, T))
        hist_da = np.full((3, T), 1.0)  # large positive residual historically? actual-da = -1
        # z_now = mean(0-0.1)= -0.1; hist residuals are -1, so remaining forecast can go negative before clamp.
        pred, _fb = intraday_price_forecast(actual, da, hist_a, hist_da, tau=10)
        self.assertTrue(np.all(pred >= 0.0))


class LeakageTests(unittest.TestCase):
    def test_six_am_uses_only_ended_prefix(self) -> None:
        dates = _calendar(8)
        rng = np.random.default_rng(1)
        prices = rng.uniform(0.3, 1.2, size=(8, T))
        archive = fit_causal_price_forecasts(prices, dates)
        d = 6
        hist_idx = [i for i in range(d) if archive.chosen_model[i] > 0]
        pred, _ = intraday_price_forecast(
            prices[d],
            archive.day_ahead[d],
            prices[hist_idx],
            archive.day_ahead[hist_idx],
            36,
        )
        alt = prices.copy()
        alt[d, 36:] += 9.0
        pred2, _ = intraday_price_forecast(
            alt[d],
            archive.day_ahead[d],
            prices[hist_idx],
            archive.day_ahead[hist_idx],
            36,
        )
        np.testing.assert_allclose(pred[36:], pred2[36:])
        alt_prefix = prices.copy()
        alt_prefix[d, :36] += 1.0
        pred3, _ = intraday_price_forecast(
            alt_prefix[d],
            archive.day_ahead[d],
            prices[hist_idx],
            archive.day_ahead[hist_idx],
            36,
        )
        self.assertGreater(float(np.max(np.abs(pred[36:] - pred3[36:]))), 0.0)


@unittest.skipUnless(ATTACH4.exists(), "附件4 unavailable")
class AttachmentRegressionTests(unittest.TestCase):
    def test_two_pilot_days_are_causal(self) -> None:
        from q4.data import load_q4_prices

        data = load_q4_prices()
        archive = fit_causal_price_forecasts(data.price, data.dates)
        for date in ("2025-02-01", "2025-06-21"):
            i = data.date_index(date)
            self.assertGreater(int(archive.chosen_model[i]), 0)
            self.assertEqual(archive.audit.loc[i, "train_cutoff_date"], data.dates[i - 1].strftime("%Y-%m-%d"))
            self.assertTrue(np.isfinite(archive.day_ahead[i]).all())
            assert_no_future_price_leak(data.price, data.dates, i, tau=0)
            assert_no_future_price_leak(data.price, data.dates, i, tau=36)


if __name__ == "__main__":
    unittest.main()
