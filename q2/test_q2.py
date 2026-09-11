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


class Q2PolicyConsistentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not ATTACH1.exists() or not ATTACH2.exists():
            raise unittest.SkipTest("C-problem attachments unavailable")
        cls.data = load_q2_data()
        from q2.policy_consistent import (
            ForecastMode,
            build_forecast_archive_mode,
        )

        cls.archive = build_forecast_archive_mode(cls.data, ForecastMode.M1)

    def test_baseline_plan_has_no_scenario_battery(self) -> None:
        from q2.optimization import solve_baseline_plan

        price = np.array([0.4, 0.8, 1.2])
        load = np.array([20.0, 18.0, 22.0])
        pv = np.array([2.0, 8.0, 1.0])
        q_floor = np.array([1.0, 0.0, 3.0])
        result = solve_baseline_plan(price, load, pv, 6000.0, q_floor=q_floor)
        self.assertFalse(result.has_scenario_specific_battery)
        for name in ("charge", "discharge"):
            self.assertEqual(result.variable_shapes[name], (3,))
        self.assertEqual(result.variable_shapes["soc"], (4,))
        self.assertTrue(np.all(result.q + 1e-8 >= q_floor))
        self.assertNotIn((8, 144), result.variable_shapes.values())
        self.assertTrue(all(len(shape) == 1 for shape in result.variable_shapes.values()))

    def test_forecast_modes_export_prior_sources(self) -> None:
        from q2.policy_consistent import FORECAST_MODES, forecast_as_of_mode

        i = 31
        for mode in FORECAST_MODES:
            forecast = forecast_as_of_mode(self.data, i, i, mode)
            self.assertTrue(all(j < i for j in forecast.load_sources + forecast.pv_sources))
            self.assertEqual(len(forecast.load_hat), 144)
            self.assertFalse(forecast.load_fallback)
            self.assertFalse(forecast.pv_fallback)

    def test_residual_pool_and_medoids_are_strictly_prior(self) -> None:
        from q2.policy_consistent import k8_scenarios

        scenarios = k8_scenarios(31, self.data, self.archive)
        self.assertIsNotNone(scenarios)
        assert scenarios is not None
        self.assertTrue(np.all(scenarios.pool_indices < 31))
        self.assertTrue(np.all(scenarios.medoid_indices < 31))
        self.assertEqual(len(scenarios.probabilities), 8)

    def test_value_cut_history_cutoff_is_last_available_day(self) -> None:
        from q2.policy_consistent import ForecastMode, build_baseline_value_cuts

        _cuts, rows = build_baseline_value_cuts(
            self.data, self.archive, 31, ForecastMode.M1
        )
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["history_cutoff_date"], "2025-01-31")
        self.assertEqual(rows[0]["target_date"], "2025-02-02")
        self.assertTrue(all(row["history_cutoff_date"] == "2025-01-31" for row in rows))

    def test_future_actual_perturbation_does_not_change_earlier_actions(self) -> None:
        from dataclasses import replace

        from q2.policy_consistent import plan_closed_loop_day

        i = 31
        summary_a, frame_a, plan_a, _floor_a, _scenarios_a = plan_closed_loop_day(
            self.data, self.archive, i, 6000.0, mpc_periods=8
        )
        load = self.data.load.copy()
        pv = self.data.pv.copy()
        load[i, 8:] += 99999.0
        pv[i, 8:] += 88888.0
        poisoned = replace(self.data, load=load, pv=pv)
        summary_b, frame_b, plan_b, _floor_b, _scenarios_b = plan_closed_loop_day(
            poisoned, self.archive, i, 6000.0, mpc_periods=8
        )
        self.assertTrue(np.allclose(plan_a.q, plan_b.q, atol=1e-8))
        self.assertEqual(summary_a["planned_q_sha256"], summary_b["planned_q_sha256"])
        cols = [
            "planned_q_kwh",
            "actual_x_kwh",
            "charge_kwh",
            "discharge_kwh",
            "emergency_kwh",
            "curtailment_kwh",
            "soc_kwh",
        ]
        self.assertTrue(np.allclose(frame_a[cols].to_numpy(), frame_b[cols].to_numpy(), atol=1e-6))

    def test_closed_loop_physical_invariants(self) -> None:
        from q2.config import E_MAX_KWH, E_MIN_KWH, NUMERIC_TOL, POWER_LIMIT_KWH, SIMULTANEOUS_CD_TOL
        from q2.pilot import planned_q_hash
        from q2.policy_consistent import plan_closed_loop_day

        summary, frame, plan, _floor, _scenarios = plan_closed_loop_day(
            self.data, self.archive, 31, 6000.0, mpc_periods=12
        )
        q = frame["planned_q_kwh"].to_numpy()
        self.assertEqual(planned_q_hash(plan.q[:12]), planned_q_hash(q))
        self.assertLess(float(np.max(frame["actual_x_kwh"].to_numpy() - q)), NUMERIC_TOL)
        residual = (
            frame["actual_x_kwh"]
            + frame["emergency_kwh"]
            + frame["pv_kwh"]
            - frame["curtailment_kwh"]
            + frame["discharge_kwh"]
            - frame["load_kwh"]
            - frame["charge_kwh"]
        )
        self.assertLess(float(residual.abs().max()), NUMERIC_TOL)
        self.assertGreaterEqual(frame["soc_kwh"].min(), E_MIN_KWH - NUMERIC_TOL)
        self.assertLessEqual(frame["soc_kwh"].max(), E_MAX_KWH + NUMERIC_TOL)
        self.assertLessEqual(
            float((frame["charge_kwh"] * frame["discharge_kwh"]).max()),
            SIMULTANEOUS_CD_TOL,
        )
        self.assertLessEqual(frame["charge_kwh"].max(), POWER_LIMIT_KWH + NUMERIC_TOL)
        self.assertLessEqual(frame["discharge_kwh"].max(), POWER_LIMIT_KWH + NUMERIC_TOL)
        self.assertTrue(summary["pass"])
        self.assertFalse(summary["used_full_day_actual_lp"])
        self.assertFalse(plan.has_scenario_specific_battery)

    def test_february_soc_boundary_only_changes_registered_state(self) -> None:
        from q2.policy_consistent import plan_closed_loop_day

        i = 31
        low = plan_closed_loop_day(self.data, self.archive, i, 5000.0, mpc_periods=4)
        high = plan_closed_loop_day(self.data, self.archive, i, 7000.0, mpc_periods=4)
        self.assertEqual(low[0]["load_source_dates"], high[0]["load_source_dates"])
        self.assertEqual(low[0]["pv_source_dates"], high[0]["pv_source_dates"])
        self.assertEqual(low[0]["forecast_mode"], high[0]["forecast_mode"])
        self.assertEqual(low[0]["risk_alpha"], high[0]["risk_alpha"])
        self.assertAlmostEqual(low[0]["risk_q_floor_kwh"], high[0]["risk_q_floor_kwh"], places=8)
        self.assertAlmostEqual(low[0]["soc_start_kwh"], 5000.0)
        self.assertAlmostEqual(high[0]["soc_start_kwh"], 7000.0)
        self.assertNotAlmostEqual(low[0]["soc_end_kwh"], high[0]["soc_end_kwh"], places=3)


if __name__ == "__main__":
    unittest.main()

