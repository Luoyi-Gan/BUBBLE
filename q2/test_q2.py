from __future__ import annotations

import unittest

import numpy as np

from q2.config import ATTACH1, ATTACH2
from q2.data import load_q2_data
from q2.forecast import assert_no_forecast_leakage, build_forecast_archive
from q2.optimization import dispatch_balance_residual, solve_fixed_plan_dispatch
from q2.scenarios import build_scenarios, pam


class Q2PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not ATTACH1.exists() or not ATTACH2.exists():
            raise unittest.SkipTest("C-problem attachments unavailable")
        cls.data = load_q2_data()
        cls.archive = build_forecast_archive(cls.data)

    def test_raw_shape_and_order(self) -> None:
        self.assertEqual(self.data.load.shape, (365, 144))
        self.assertEqual(self.data.pv.shape, (365, 144))
        self.assertEqual(self.data.time_labels[0], "00:10")
        self.assertEqual(self.data.time_labels[-1], "0:00+1")

    def test_forecasts_use_only_prior_dates(self) -> None:
        assert_no_forecast_leakage(self.archive)
        i = 31
        self.assertTrue(all(j < i for j in self.archive.load_sources[i]))
        self.assertTrue(all(j < i for j in self.archive.pv_sources[i]))

    def test_scenario_probabilities(self) -> None:
        scenarios = build_scenarios(31, self.data, self.archive, 4)
        self.assertAlmostEqual(float(scenarios.probabilities.sum()), 1.0)
        self.assertTrue(np.all(scenarios.medoid_indices < 31))
        self.assertTrue(np.all(scenarios.pool_indices < 31))

    def test_pam_returns_real_points(self) -> None:
        d = np.array([[0, 1, 3], [1, 0, 2], [3, 2, 0]], dtype=float)
        medoids, labels = pam(d, 2)
        self.assertEqual(len(medoids), 2)
        self.assertEqual(len(labels), 3)
        self.assertTrue(set(medoids).issubset({0, 1, 2}))

    def test_fixed_plan_contract_and_balance(self) -> None:
        price = np.ones(3)
        q = np.array([10.0, 10.0, 10.0])
        load = np.array([12.0, 8.0, 11.0])
        pv = np.zeros(3)
        result = solve_fixed_plan_dispatch(price, q, load, pv, 6000.0)
        residual = dispatch_balance_residual(load, pv, result)
        self.assertLess(np.max(np.abs(residual)), 1e-6)
        self.assertTrue(np.all(result.x <= q + 1e-6))


if __name__ == "__main__":
    unittest.main()

