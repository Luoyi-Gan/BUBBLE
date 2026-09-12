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
    LOAD_INFORMATION_MAIN,
    LOAD_INFORMATION_PROXY,
    PV_MAPPING_LINEAR,
    PV_MAPPING_STEP,
    SETTLEMENT_ALT,
    SETTLEMENT_MAIN,
    T,
    YEAR_N_DAYS,
    dispatch_stem,
    make_run_id,
    next_day_year_end_soc,
    today_year_end_soc,
)
from q3.data import load_q3_data, period_end_minutes
from q3.forecast import (
    causal_load_forecast,
    causal_load_sources,
    execution_load_horizon,
    forecast_knots_minutes_kw,
    interpolate_series,
    map_issue_forecast,
    planning_load_curve,
)
from q3.optimization import realized_settlement, settlement_cost, solve_horizon


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


class CausalLoadTests(unittest.TestCase):
    def test_execution_horizon_uses_actual_only_at_current_step(self) -> None:
        plan = np.arange(5, dtype=float)
        actual = np.full(5, 99.0)
        horizon = execution_load_horizon(plan, actual, 2)
        np.testing.assert_allclose(horizon, np.array([99.0, 3.0, 4.0]))


@unittest.skipUnless(ATTACH1.exists() and ATTACH3.exists(), "C-problem attachments unavailable")
class CausalLoadAttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_q3_data()

    def test_load_sources_are_strictly_before_target(self) -> None:
        i = self.data.date_index("2025-02-01")
        hat, sources, label = causal_load_sources(self.data, i, i)
        self.assertTrue(len(sources) > 0)
        self.assertTrue(all(j < i for j in sources))
        self.assertNotIn(self.data.dates[i].strftime("%Y-%m-%d"), label)
        np.testing.assert_allclose(hat, causal_load_forecast(self.data, i, i))
        np.testing.assert_allclose(
            planning_load_curve(self.data, i, LOAD_INFORMATION_MAIN), hat
        )
        np.testing.assert_allclose(
            planning_load_curve(self.data, i, LOAD_INFORMATION_PROXY),
            self.data.load[i],
        )

    def test_future_same_day_load_does_not_change_main_forecast(self) -> None:
        i = self.data.date_index("2025-06-21")
        before_main = causal_load_forecast(self.data, i, i)
        before_proxy = planning_load_curve(self.data, i, LOAD_INFORMATION_PROXY)
        original = self.data.load[i].copy()
        try:
            self.data.load[i, 36:] += 777.0
            after_main = causal_load_forecast(self.data, i, i)
            after_proxy = planning_load_curve(self.data, i, LOAD_INFORMATION_PROXY)
            after_next = causal_load_forecast(self.data, i + 1, i)
        finally:
            self.data.load[i] = original
        before_next = causal_load_forecast(self.data, i + 1, i)
        np.testing.assert_allclose(before_main, after_main)
        np.testing.assert_allclose(before_next, after_next)
        self.assertGreater(float(np.max(np.abs(after_proxy - before_proxy))), 1.0)

    def test_main_g0_ignores_future_actual_load_proxy_does_not(self) -> None:
        from q3.forecast import map_issue_forecast
        from q3.optimization import solve_horizon

        i = self.data.date_index("2025-02-01")
        pv = map_issue_forecast(self.data, i, 0).today_kwh
        main = planning_load_curve(self.data, i, LOAD_INFORMATION_MAIN)
        proxy = planning_load_curve(self.data, i, LOAD_INFORMATION_PROXY)
        g0_main_before = solve_horizon(
            self.data.price, main, pv, E_INITIAL_KWH, bill_as_day_ahead=True, throughput_tiebreak=False
        ).g
        g0_proxy_before = solve_horizon(
            self.data.price, proxy, pv, E_INITIAL_KWH, bill_as_day_ahead=True, throughput_tiebreak=False
        ).g
        original = self.data.load[i].copy()
        try:
            self.data.load[i, 36:] += 500.0
            g0_main_after = solve_horizon(
                self.data.price,
                planning_load_curve(self.data, i, LOAD_INFORMATION_MAIN),
                pv,
                E_INITIAL_KWH,
                bill_as_day_ahead=True,
                throughput_tiebreak=False,
            ).g
            g0_proxy_after = solve_horizon(
                self.data.price,
                planning_load_curve(self.data, i, LOAD_INFORMATION_PROXY),
                pv,
                E_INITIAL_KWH,
                bill_as_day_ahead=True,
                throughput_tiebreak=False,
            ).g
        finally:
            self.data.load[i] = original
        np.testing.assert_allclose(g0_main_before, g0_main_after, atol=1e-6)
        self.assertGreater(float(np.max(np.abs(g0_proxy_after - g0_proxy_before))), 1e-6)


class AdjacentSettlementTests(unittest.TestCase):
    def test_four_settlement_paths(self) -> None:
        p = np.array([2.0])
        g0 = np.array([10.0])
        none = realized_settlement(p, [g0], SETTLEMENT_MAIN)
        up = realized_settlement(p, [g0, np.array([14.0])], SETTLEMENT_MAIN)
        down = realized_settlement(p, [g0, np.array([6.0])], SETTLEMENT_MAIN)
        self.assertAlmostEqual(float(none[0]), 2.0 * 10.0)
        self.assertAlmostEqual(float(up[0]), 2.0 * 14.0 + 0.5 * 2.0 * 4.0)
        self.assertAlmostEqual(float(down[0]), 2.0 * 6.0 + 0.5 * 2.0 * 4.0)

        alt_none = realized_settlement(p, [g0], SETTLEMENT_ALT)
        alt_up = realized_settlement(p, [g0, np.array([14.0])], SETTLEMENT_ALT)
        alt_down = realized_settlement(p, [g0, np.array([6.0])], SETTLEMENT_ALT)
        alt_up_down = realized_settlement(
            p, [g0, np.array([14.0]), np.array([6.0])], SETTLEMENT_ALT
        )
        self.assertAlmostEqual(float(alt_none[0]), 2.0 * 10.0)
        self.assertAlmostEqual(float(alt_up[0]), 2.0 * 10.0 + 1.5 * 2.0 * 4.0)
        self.assertAlmostEqual(float(alt_down[0]), 2.0 * 10.0 + 0.5 * 2.0 * 4.0)
        self.assertAlmostEqual(
            float(alt_up_down[0]), 2.0 * 10.0 + 1.5 * 2.0 * 4.0 + 0.5 * 2.0 * 8.0
        )
        main_up_down = realized_settlement(
            p, [g0, np.array([14.0]), np.array([6.0])], SETTLEMENT_MAIN
        )
        self.assertAlmostEqual(float(main_up_down[0]), float(down[0]))
        self.assertLess(float(main_up_down[0]), float(alt_up_down[0]) - 1e-9)


@unittest.skipUnless(ATTACH1.exists() and ATTACH3.exists(), "C-problem attachments unavailable")
class MappingSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_q3_data()

    def test_linear_first_hour_weights(self) -> None:
        i = self.data.date_index("2025-02-01")
        mapped = map_issue_forecast(self.data, i, 6, PV_MAPPING_LINEAR)
        anchor = self.data.pv[i, 35] / DELTA_H
        first = self.data.hourly_forecast_kw[6][i, 0]
        expected_610 = (5.0 / 6.0 * anchor + 1.0 / 6.0 * first) * DELTA_H
        self.assertAlmostEqual(mapped.today_kwh[36], expected_610, places=6)
        self.assertAlmostEqual(mapped.today_kwh[41], first * DELTA_H, places=6)

    def test_step_first_hour_is_forecast_hour_one(self) -> None:
        i = self.data.date_index("2025-02-01")
        mapped = map_issue_forecast(self.data, i, 6, PV_MAPPING_STEP)
        first = self.data.hourly_forecast_kw[6][i, 0] * DELTA_H
        for t in range(36, 42):
            self.assertAlmostEqual(mapped.today_kwh[t], first, places=6)
            self.assertEqual(int(mapped.today_source_k[t]), 1)
        self.assertEqual(mapped.first_mutable_index, 36)
        self.assertAlmostEqual(mapped.today_kwh[35], self.data.pv[i, 35])

    def test_neither_mapping_reads_future_actual_pv(self) -> None:
        i = self.data.date_index("2025-06-21")
        original = self.data.pv[i].copy()
        befores = {
            mode: map_issue_forecast(self.data, i, 6, mode)
            for mode in (PV_MAPPING_LINEAR, PV_MAPPING_STEP)
        }
        try:
            self.data.pv[i, 36:] += 9999.0
            afters = {
                mode: map_issue_forecast(self.data, i, 6, mode)
                for mode in (PV_MAPPING_LINEAR, PV_MAPPING_STEP)
            }
        finally:
            self.data.pv[i] = original
        for mode in (PV_MAPPING_LINEAR, PV_MAPPING_STEP):
            np.testing.assert_allclose(befores[mode].today_kwh[36:], afters[mode].today_kwh[36:])
            np.testing.assert_allclose(befores[mode].next_day_kwh, afters[mode].next_day_kwh)


class YearEndSocHelperTests(unittest.TestCase):
    def test_make_run_id_without_year_end_unchanged(self) -> None:
        old = make_run_id(
            "2025-02-01",
            "M1_M6",
            LOAD_INFORMATION_MAIN,
            PV_MAPPING_LINEAR,
            SETTLEMENT_MAIN,
            True,
        )
        self.assertEqual(
            old,
            "2025-02-01__M1_M6__causal_load_main__linear_anchor_main__anchor_final_main__48h",
        )
        self.assertEqual(
            dispatch_stem(
                "2025-02-01",
                "M1_M6",
                LOAD_INFORMATION_MAIN,
                PV_MAPPING_LINEAR,
                SETTLEMENT_MAIN,
                True,
            ),
            "q3_dispatch_2025-02-01_M1_M6_causal_load_main_linear_anchor_main_anchor_final_main",
        )

    def test_make_run_id_appends_year_end_tag(self) -> None:
        run_id = make_run_id(
            "2025-12-31",
            "M0",
            LOAD_INFORMATION_MAIN,
            PV_MAPPING_LINEAR,
            SETTLEMENT_MAIN,
            True,
            1200.0,
        )
        self.assertTrue(run_id.endswith("__ye1200"))
        stem = dispatch_stem(
            "2025-12-31",
            "M0",
            LOAD_INFORMATION_MAIN,
            PV_MAPPING_LINEAR,
            SETTLEMENT_MAIN,
            True,
            1200.0,
        )
        self.assertTrue(stem.endswith("_ye1200"))

    def test_year_end_constraint_days(self) -> None:
        self.assertEqual(YEAR_N_DAYS, 365)
        self.assertEqual(today_year_end_soc(364, 365, 1200.0), 1200.0)
        self.assertIsNone(today_year_end_soc(363, 365, 1200.0))
        self.assertEqual(next_day_year_end_soc(363, 365, 6000.0), 6000.0)
        self.assertIsNone(next_day_year_end_soc(362, 365, 6000.0))
        self.assertIsNone(today_year_end_soc(364, 365, None))

    def test_value_cut_cache_key_splits_dec30_boundaries(self) -> None:
        from q3.pilot import _value_cut_cache_key

        shared = _value_cut_cache_key(333, 0, PV_MAPPING_LINEAR, None)
        a = _value_cut_cache_key(363, 0, PV_MAPPING_LINEAR, 1200.0)
        b = _value_cut_cache_key(363, 0, PV_MAPPING_LINEAR, 6000.0)
        self.assertEqual(shared[-1], "")
        self.assertNotEqual(a, b)
        self.assertEqual(shared, _value_cut_cache_key(333, 0, PV_MAPPING_LINEAR))

    def test_solve_horizon_hits_hard_terminal_soc(self) -> None:
        n = 12
        price = np.full(n, 0.4)
        load = np.full(n, 80.0)
        pv = np.zeros(n)
        target = 5000.0
        result = solve_horizon(
            price,
            load,
            pv,
            E_INITIAL_KWH,
            bill_as_day_ahead=True,
            terminal_soc=target,
        )
        self.assertAlmostEqual(float(result.soc[-1]), target, places=5)
        self.assertLessEqual(float(result.max_cd), 1e-4)


@unittest.skipUnless(ATTACH1.exists() and ATTACH3.exists(), "C-problem attachments unavailable")
class YearEndSocAttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_q3_data()

    def test_december_indices_match_year_end_rules(self) -> None:
        self.assertEqual(len(self.data.dates), YEAR_N_DAYS)
        self.assertEqual(self.data.date_index("2025-12-31"), YEAR_N_DAYS - 1)
        self.assertEqual(self.data.date_index("2025-12-30"), YEAR_N_DAYS - 2)
        self.assertEqual(self.data.date_index("2025-12-29"), YEAR_N_DAYS - 3)
        self.assertEqual(self.data.date_index("2025-12-01"), 334)

    def test_dec31_virtual_next_day_from_dec30_hits_target(self) -> None:
        from q3.forecast import causal_load_forecast, next_day_pv_forecast

        dec30 = self.data.date_index("2025-12-30")
        load = causal_load_forecast(self.data, dec30 + 1, dec30)
        pv = next_day_pv_forecast(self.data, dec30, 0, PV_MAPPING_LINEAR)
        result = solve_horizon(
            self.data.price,
            load,
            pv,
            7000.0,
            bill_as_day_ahead=True,
            terminal_soc=1200.0,
        )
        self.assertAlmostEqual(float(result.soc[-1]), 1200.0, places=5)

    def test_dec31_m0_run_day_hits_1200(self) -> None:
        from q3.pilot import run_day

        i = self.data.date_index("2025-12-31")
        run = run_day(
            self.data,
            i,
            "M0",
            E_INITIAL_KWH,
            with_terminal_value=True,
            load_information_case=LOAD_INFORMATION_MAIN,
            pv_mapping_mode=PV_MAPPING_LINEAR,
            settlement_mode=SETTLEMENT_MAIN,
            year_end_soc_kwh=1200.0,
        )
        self.assertAlmostEqual(float(run.summary["soc_end_kwh"]), 1200.0, places=5)
        self.assertIn("ye1200", run.run_id)
        self.assertLess(float(run.summary["max_balance_residual_kwh"]), 1e-5)
        self.assertEqual(int(run.summary["locked_period_violations"]), 0)


class FullAnnualHelperTests(unittest.TestCase):
    def test_parse_boundaries_a_b_both(self) -> None:
        from q3.config import YEAR_END_BOUNDARY_A, YEAR_END_BOUNDARY_B, YEAR_END_SOC_A_KWH, YEAR_END_SOC_B_KWH
        from q3.full_annual import parse_boundaries

        both = parse_boundaries("both")
        self.assertEqual(len(both), 2)
        self.assertEqual(both[0], (YEAR_END_BOUNDARY_A, YEAR_END_SOC_A_KWH))
        self.assertEqual(both[1], (YEAR_END_BOUNDARY_B, YEAR_END_SOC_B_KWH))
        self.assertEqual(parse_boundaries("A"), ((YEAR_END_BOUNDARY_A, YEAR_END_SOC_A_KWH),))
        self.assertEqual(parse_boundaries("B"), ((YEAR_END_BOUNDARY_B, YEAR_END_SOC_B_KWH),))

    def test_continuity_audit_requires_365_independent_paths(self) -> None:
        import pandas as pd

        from q3.full_annual import continuity_audit

        dates = pd.date_range("2025-01-01", "2025-12-31", freq="D").strftime("%Y-%m-%d")
        rows = []
        soc = 6000.0
        for date in dates:
            end = 1200.0 if date == "2025-12-31" else soc + 1.0
            rows.append(
                {
                    "date": date,
                    "strategy": "M0",
                    "year_end_boundary": "A_q2_aligned",
                    "year_end_soc_kwh": 1200.0,
                    "soc_start_kwh": soc,
                    "soc_end_kwh": end,
                }
            )
            soc = end
        audit = continuity_audit(pd.DataFrame(rows))
        self.assertTrue(audit["all_pass"])
        self.assertEqual(audit["paths"][0]["n_days"], 365)


@unittest.skipUnless(ATTACH1.exists() and ATTACH3.exists(), "C-problem attachments unavailable")
class FullAnnualAttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_q3_data()

    def test_annual_calendar_and_jan1_fallback(self) -> None:
        from q3.full_annual import annual_dates, write_annual_forecast_audit

        dates = annual_dates(self.data)
        self.assertEqual(len(dates), 365)
        self.assertEqual(dates[0], "2025-01-01")
        self.assertEqual(dates[-1], "2025-12-31")
        audit = write_annual_forecast_audit(self.data, Path("/tmp/q3_annual_forecast_audit_test.csv"))
        self.assertTrue(bool(audit.loc[0, "used_attachment1_fallback"]))
        self.assertTrue(bool(audit["source_cutoff_ok"].all()))
        self.assertTrue((audit["max_source_index"] < audit["day_index"]).all())


if __name__ == "__main__":
    unittest.main()
