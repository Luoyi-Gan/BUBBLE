from __future__ import annotations

import json
from pathlib import Path
import unittest

import numpy as np

from q3.config import (
    ATTACH1,
    ATTACH3,
    DELTA_H,
    E_INITIAL_KWH,
    HOUR_TO_FIRST_MUTABLE,
    T,
)
from q3.data import load_q3_data, period_end_minutes
from q3.forecast import (
    forecast_knots_minutes_kw,
    interpolate_series,
    map_issue_forecast,
)
from q3.optimization import settlement_cost, solve_horizon


class SettlementTests(unittest.TestCase):
    def test_three_settlement_cases(self) -> None:
        p = np.array([2.0])
        g0 = np.array([10.0])
        equal = settlement_cost(p, g0, np.array([10.0]))
        down = settlement_cost(p, g0, np.array([6.0]))
        up = settlement_cost(p, g0, np.array([14.0]))
        self.assertAlmostEqual(float(equal[0]), 2.0 * 10.0)
        self.assertAlmostEqual(float(down[0]), 2.0 * 6.0 + 0.5 * 2.0 * 4.0)
        self.assertAlmostEqual(float(up[0]), 2.0 * 10.0 + 1.5 * 2.0 * 4.0)

    def test_no_double_charge_on_cancelled_energy(self) -> None:
        p, g0, gf = np.array([1.0]), np.array([8.0]), np.array([5.0])
        phi = float(settlement_cost(p, g0, gf)[0])
        wrong_repeat = 1.0 * 8.0 + 0.5 * 1.0 * 3.0
        self.assertLess(phi, wrong_repeat - 1e-9)
        self.assertAlmostEqual(phi, 5.0 + 0.5 * 3.0)


class InterpolationTests(unittest.TestCase):
    def test_hourly_nodes_and_midpoints(self) -> None:
        hourly = np.zeros(24)
        hourly[1] = 120.0  # 预报2小时 after 0:00 = 02:00
        minutes, values = forecast_knots_minutes_kw(0, hourly, anchor_kw=0.0)
        self.assertEqual(minutes[0], 0)
        self.assertEqual(minutes[2], 120)
        series = interpolate_series(np.array([60.0, 90.0, 120.0]), minutes, values)
        self.assertAlmostEqual(series[0], 0.0)
        self.assertAlmostEqual(series[1], 60.0)
        self.assertAlmostEqual(series[2], 120.0)

    def test_period_end_minutes_align_with_labels(self) -> None:
        self.assertEqual(period_end_minutes(0), 10)
        self.assertEqual(period_end_minutes(35), 360)
        self.assertEqual(period_end_minutes(36), 370)
        self.assertEqual(period_end_minutes(143), 1440)
        self.assertEqual(HOUR_TO_FIRST_MUTABLE[6], 36)
        self.assertEqual(HOUR_TO_FIRST_MUTABLE[12], 72)
        self.assertEqual(HOUR_TO_FIRST_MUTABLE[18], 108)


class HorizonLPTests(unittest.TestCase):
    def test_keep_commitment_is_feasible(self) -> None:
        n = 6
        price = np.full(n, 0.5)
        load = np.full(n, 10.0)
        pv = np.zeros(n)
        plan = solve_horizon(price, load, pv, E_INITIAL_KWH, bill_as_day_ahead=True)
        fixed = solve_horizon(
            price, load, pv, E_INITIAL_KWH, g0=plan.g, g_fixed=plan.g
        )
        free = solve_horizon(price, load, pv, E_INITIAL_KWH, g0=plan.g)
        self.assertLessEqual(free.objective, fixed.objective + 1e-6)
        self.assertTrue(np.all(plan.x <= plan.g + 1e-8))


@unittest.skipUnless(ATTACH1.exists() and ATTACH3.exists(), "C-problem attachments unavailable")
class AttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_q3_data()

    def test_shapes_and_issue_times(self) -> None:
        self.assertEqual(self.data.load.shape, (365, T))
        self.assertEqual(self.data.hourly_forecast_kw[0].shape, (365, 24))
        self.assertEqual(self.data.time_labels[0], "00:10")
        self.assertEqual(self.data.time_labels[35], "06:00")
        self.assertEqual(self.data.time_labels[36], "06:10")
        self.assertEqual(self.data.time_labels[-1], "0:00+1")

    def test_forecast_does_not_use_future_actual_pv(self) -> None:
        i = self.data.date_index("2025-02-01")
        before = map_issue_forecast(self.data, i, 6)
        original = self.data.pv[i].copy()
        try:
            self.data.pv[i, 36:] += 9999.0
            after = map_issue_forecast(self.data, i, 6)
        finally:
            self.data.pv[i] = original
        np.testing.assert_allclose(before.today_kwh[36:], after.today_kwh[36:])
        np.testing.assert_allclose(before.next_day_kwh, after.next_day_kwh)
        self.assertEqual(before.first_mutable_index, 36)

    def test_six_am_anchor_is_observed_actual(self) -> None:
        i = self.data.date_index("2025-06-21")
        mapped = map_issue_forecast(self.data, i, 6)
        self.assertAlmostEqual(mapped.today_kwh[35], self.data.pv[i, 35])
        # 07:00 node is 预报1小时 and lands on index 41.
        expected = self.data.hourly_forecast_kw[6][i, 0] * DELTA_H
        self.assertAlmostEqual(mapped.today_kwh[41], expected, places=6)


if __name__ == "__main__":
    unittest.main()
