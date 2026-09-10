from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from q2.config import (
    ATTACH1,
    ATTACH2,
    NEXT_DAY_VALUE_GAP_TOL_YUAN,
)
from q2.data import load_q2_data
from q2.forecast import (
    assert_no_forecast_leakage,
    build_forecast_archive,
    forecast_as_of,
)
from q2.optimization import (
    dispatch_balance_residual,
    evaluate_value_cuts,
    solve_fixed_plan_dispatch,
    solve_stochastic_plan,
)
from q2.pilot import build_next_day_value_cuts, scenario_inputs_as_of
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

    def test_next_day_as_of_excludes_current_day(self) -> None:
        _load, _pv, load_sources, pv_sources = forecast_as_of(self.data, 32, 31)
        self.assertTrue(all(j < 31 for j in load_sources + pv_sources))
        scenarios = build_scenarios(
            32, self.data, self.archive, 4, history_end_exclusive=31
        )
        self.assertTrue(np.all(scenarios.pool_indices < 31))

    def test_value_cuts_are_supporting_at_samples(self) -> None:
        cuts, audit = build_next_day_value_cuts(
            self.data, self.archive, current_index=31, k=4
        )
        self.assertGreaterEqual(len(cuts), 2)
        self.assertEqual(len(audit), len(cuts))
        self.assertLessEqual(
            audit[0]["certified_max_gap_yuan"],
            NEXT_DAY_VALUE_GAP_TOL_YUAN,
        )
        for reference_soc, reference_value, _ in cuts:
            self.assertLessEqual(
                max(
                    value + slope * (reference_soc - soc)
                    for soc, value, slope in cuts
                ),
                reference_value + 1e-4,
            )
        loads, pvs, probabilities, _scenarios, _source = scenario_inputs_as_of(
            self.data, self.archive, 32, 31, 4
        )
        for soc in (2400.0, 6000.0, 9600.0):
            exact = solve_stochastic_plan(
                self.data.price, loads, pvs, probabilities, soc
            )
            exact_value = exact.planned_cost + exact.expected_emergency_cost
            gap = exact_value - evaluate_value_cuts(soc, cuts)
            self.assertGreaterEqual(gap, -1e-4)
            self.assertLessEqual(gap, NEXT_DAY_VALUE_GAP_TOL_YUAN + 1e-4)

    def test_next_day_bundle_ignores_current_and_future_actuals(self) -> None:
        original, _ = build_next_day_value_cuts(
            self.data, self.archive, current_index=31, k=4
        )
        load = self.data.load.copy()
        pv = self.data.pv.copy()
        load[31:33] += 99999.0
        pv[31:33] += 88888.0
        poisoned_data = replace(self.data, load=load, pv=pv)
        poisoned_archive = build_forecast_archive(poisoned_data)
        poisoned, _ = build_next_day_value_cuts(
            poisoned_data, poisoned_archive, current_index=31, k=4
        )
        self.assertTrue(np.allclose(original, poisoned, atol=1e-8))

    def test_initial_soc_dual_matches_finite_difference(self) -> None:
        loads, pvs, probabilities, _scenarios, _source = scenario_inputs_as_of(
            self.data, self.archive, 32, 31, 4
        )
        center = solve_stochastic_plan(
            self.data.price, loads, pvs, probabilities, 6000.0
        )
        lower = solve_stochastic_plan(
            self.data.price, loads, pvs, probabilities, 5999.9
        )
        upper = solve_stochastic_plan(
            self.data.price, loads, pvs, probabilities, 6000.1
        )
        lower_value = lower.planned_cost + lower.expected_emergency_cost
        upper_value = upper.planned_cost + upper.expected_emergency_cost
        finite_difference = (upper_value - lower_value) / 0.2
        self.assertAlmostEqual(
            center.initial_soc_marginal, finite_difference, places=4
        )

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

