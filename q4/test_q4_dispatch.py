from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from q2.scenarios import pam
from q3.optimization import settlement_cost
from q4.audit import ledger_from_dispatch_q42, ledger_from_dispatch_q43
from q4.config import ATTACH4, T
from q4.price_forecast import assert_no_future_price_leak
from q4.q4_2 import planned_q_hash
from q4.scenarios import triple_distance_matrix


class TripleResidualTests(unittest.TestCase):
    def test_distance_is_symmetric_and_paired(self) -> None:
        rng = np.random.default_rng(0)
        load_r = rng.normal(size=(6, T))
        pv_r = rng.normal(size=(6, T))
        price_r = rng.normal(size=(6, T))
        dist, sl, sp, spr = triple_distance_matrix(load_r, pv_r, price_r)
        self.assertTrue(np.allclose(dist, dist.T))
        np.testing.assert_allclose(np.diag(dist), 0.0, atol=1e-12)
        self.assertGreater(sl, 0.0)
        medoids, labels = pam(dist, 3)
        self.assertEqual(len(medoids), 3)
        self.assertEqual(len(labels), 6)


class LedgerTests(unittest.TestCase):
    def test_q42_ledger_uses_p_times_q_not_x(self) -> None:
        q = np.full(T, 10.0)
        x = np.full(T, 4.0)
        e = np.zeros(T)
        e[3] = 2.0
        p = np.full(T, 0.5)
        frame = pd.DataFrame(
            {
                "q_or_g0_kwh": q,
                "x_kwh": x,
                "emergency_kwh": e,
                "actual_price": p,
            }
        )
        ledger = ledger_from_dispatch_q42(frame)
        self.assertAlmostEqual(float(ledger["normal_cost_yuan"].sum()), 0.5 * 10.0 * T)
        self.assertAlmostEqual(float(ledger["emergency_cost_yuan"].sum()), 5.0 * 0.5 * 2.0)
        self.assertGreater(float(ledger["normal_cost_yuan"].sum()), float((p * x).sum()))

    def test_q43_ledger_matches_phi_plus_emergency(self) -> None:
        g0 = np.full(T, 8.0)
        gf = g0.copy()
        gf[10] = 12.0
        gf[11] = 5.0
        p = np.full(T, 2.0)
        e = np.zeros(T)
        e[20] = 1.0
        frame = pd.DataFrame(
            {
                "q_or_g0_kwh": g0,
                "g_final_kwh": gf,
                "emergency_kwh": e,
                "actual_price": p,
            }
        )
        ledger = ledger_from_dispatch_q43(frame)
        phi = settlement_cost(p, g0, gf)
        self.assertAlmostEqual(float(ledger["total_cost_yuan"].sum()), float(phi.sum() + 5.0 * 2.0 * 1.0))
        cancelled = 3.0
        # Downward adjustment must not charge the cancelled energy twice as ordinary energy.
        self.assertAlmostEqual(float(phi[11]), 2.0 * 5.0 + 0.5 * 2.0 * cancelled)

    def test_update_clock_settlement_rebooks_only_adjustment(self) -> None:
        from q4.q4_3_sensitivity import adjustment_at_update_clock

        n = 6
        labels = ["00:10", "00:20", "00:30", "00:40", "00:50", "06:00"]
        last = ["00:00", "00:00", "06:00", "06:00", "06:00", "06:00"]
        g0 = np.array([10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
        gf = np.array([10.0, 10.0, 12.0, 7.0, 10.0, 10.0])
        p = np.array([1.0, 1.0, 2.0, 2.0, 2.0, 4.0])
        frame = pd.DataFrame(
            {
                "date": ["2025-02-01"] * n,
                "time_label": labels,
                "last_update_time": last,
                "q_or_g0_kwh": g0,
                "g_final_kwh": gf,
                "emergency_kwh": np.zeros(n),
                "actual_price": p,
            }
        )
        alt = adjustment_at_update_clock(frame)
        # Delivery: 0.5*2*|12-10| + 0.5*2*|7-10| = 2 + 3 = 5
        self.assertAlmostEqual(float(alt["adjustment_delivery_yuan"].sum()), 5.0)
        # Update clock uses p at 06:00 = 4: 0.5*4*2 + 0.5*4*3 = 4 + 6 = 10
        self.assertAlmostEqual(float(alt["adjustment_update_clock_yuan"].sum()), 10.0)
        self.assertAlmostEqual(float(alt["normal_cost_yuan"].sum()), float((p * gf).sum()))
        self.assertAlmostEqual(float(alt.loc[0, "total_delivery_yuan"]), float(alt.loc[0, "total_update_clock_yuan"]))


class HashAndBoundsTests(unittest.TestCase):
    def test_q_hash_detects_mutation(self) -> None:
        q = np.arange(T, dtype=float)
        first = planned_q_hash(q)
        q[0] += 1e-6
        self.assertNotEqual(first, planned_q_hash(q))

    def test_emergency_and_soc_bounds(self) -> None:
        from q2.config import E_MAX_KWH, E_MIN_KWH
        from q4.optimization import solve_fixed_q_dispatch

        n = 6
        price = np.ones(n)
        low = solve_fixed_q_dispatch(
            price,
            np.zeros(n),
            np.full(n, 4000.0),
            np.zeros(n),
            E_MIN_KWH,
            throughput_tiebreak=False,
        )
        self.assertGreater(float(low.emergency.sum()), 0.0)
        self.assertGreaterEqual(low.soc[1:].min(), E_MIN_KWH - 1e-6)
        self.assertLessEqual(low.soc[1:].max(), E_MAX_KWH + 1e-6)
        high = solve_fixed_q_dispatch(
            price,
            np.zeros(n),
            np.zeros(n),
            np.full(n, 4000.0),
            E_MAX_KWH,
            throughput_tiebreak=False,
        )
        self.assertGreaterEqual(high.soc[1:].min(), E_MIN_KWH - 1e-6)
        self.assertLessEqual(high.soc[1:].max(), E_MAX_KWH + 1e-6)
        self.assertGreaterEqual(float(high.curtailment.min()), -1e-9)


class PriceLeakageReuseTests(unittest.TestCase):
    def test_price_module_still_ignores_future(self) -> None:
        dates = pd.date_range("2025-01-01", periods=10, freq="D")
        rng = np.random.default_rng(2)
        prices = rng.uniform(0.2, 0.9, size=(10, T))
        assert_no_future_price_leak(prices, dates, day_index=6, tau=0)
        assert_no_future_price_leak(prices, dates, day_index=6, tau=36)

    def test_alpha_calibrator_uses_official_loop_not_full_day_actual(self) -> None:
        import inspect

        import q4.q4_2 as module

        self.assertFalse(hasattr(module, "_validation_cost"))
        source = inspect.getsource(module.select_risk_alpha)
        window_src = inspect.getsource(module.run_candidate_window)
        self.assertIn("run_q4_2_day", window_src)
        self.assertNotIn("solve_fixed_q_dispatch", source)
        self.assertNotIn("solve_fixed_q_dispatch", window_src)
        self.assertIn("used_full_day_actual_scheduler", window_src)

    def test_monthly_price_table_pools_rmse(self) -> None:
        from q4.export_price_monthly import monthly_from_audit

        frame = pd.DataFrame(
            {
                "date": ["2025-01-02", "2025-01-03", "2025-02-01"],
                "day_ahead_mae": [0.2, 0.4, 0.6],
                "day_ahead_rmse": [0.3, 0.5, 0.7],
                "intraday_06_mae": [0.1, 0.3, 0.5],
                "intraday_06_rmse": [0.2, 0.4, 0.6],
                "intraday_12_mae": [0.1, 0.3, 0.5],
                "intraday_12_rmse": [0.2, 0.4, 0.6],
                "intraday_18_mae": [0.1, 0.3, 0.5],
                "intraday_18_rmse": [0.2, 0.4, 0.6],
                "mpc_remaining_mae_mean": [0.2, 0.4, 0.6],
            }
        )
        monthly = monthly_from_audit(frame)
        jan = monthly.loc[monthly["year_month"] == "2025-01"].iloc[0]
        self.assertEqual(int(jan["n_days"]), 2)
        self.assertAlmostEqual(float(jan["day_ahead_mae"]), 0.3)
        self.assertAlmostEqual(float(jan["day_ahead_rmse"]), float(np.sqrt((0.3**2 + 0.5**2) / 2)))
        annual = monthly.loc[monthly["year_month"] == "2025-annual"].iloc[0]
        self.assertEqual(int(annual["n_days"]), 3)

    def test_q2_calibration_calendar_has_25_windows(self) -> None:
        from q4.q4_2 import q2_aligned_calibration_indices
        from q4.run_k_review import decide_keep_k8

        idx = q2_aligned_calibration_indices(365)
        self.assertEqual(idx[0], 28)
        self.assertEqual(idx[-1], 364)
        self.assertEqual(len(idx), 25)
        self.assertEqual(idx, list(range(28, 365, 14)))
        stable = decide_keep_k8(
            {
                4: {"mean_cost_per_day_yuan": 101.0, "mean_elapsed_seconds": 0.5},
                8: {"mean_cost_per_day_yuan": 100.0, "mean_elapsed_seconds": 0.8},
                12: {"mean_cost_per_day_yuan": 99.5, "mean_elapsed_seconds": 1.2},
            }
        )
        self.assertEqual(stable["keep_k"], 8)
        self.assertTrue(stable["k8_stable"])
        self.assertTrue(stable["k8_within_1pct_of_best"])


@unittest.skipUnless(ATTACH4.exists(), "attachments unavailable")
class AttachmentSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from q4.bundle import load_q4_bundle
        from q4.q4_2 import run_q4_2_day
        from q4.q4_3 import run_q4_3_day

        cls.bundle = load_q4_bundle(compute_price_mpc=False)
        cls.q42 = run_q4_2_day(cls.bundle, 0, 6000.0, None)
        cls.q43 = run_q4_3_day(cls.bundle, 0, 6000.0)

    def test_jan1_q_locked_and_physical(self) -> None:
        self.assertTrue(self.q42.summary["pass"])
        self.assertTrue(np.allclose(self.q42.q, self.q42.dispatch["q_or_g0_kwh"]))
        self.assertTrue((self.q42.dispatch["last_update_time"] == "00:00").all())
        self.assertEqual(len(self.q42.dispatch), T)
        self.assertLessEqual(float(self.q42.summary["max_x_minus_q_kwh"]), 1e-6)
        soc = np.concatenate(
            [[self.q42.summary["soc_start_kwh"]], self.q42.dispatch["soc_end_kwh"].to_numpy()]
        )
        self.assertGreaterEqual(soc.min(), 1200.0 - 1e-6)
        self.assertLessEqual(soc.max(), 10800.0 + 1e-6)

    def test_jan1_q43_prefix_and_ledger(self) -> None:
        self.assertTrue(self.q43.summary["pass"])
        self.assertEqual(int(self.q43.summary["locked_period_violations"]), 0)
        self.assertTrue(self.q43.update_log["prefix_lock_ok"].all())
        ledger = ledger_from_dispatch_q43(self.q43.dispatch)
        self.assertAlmostEqual(
            float(ledger["total_cost_yuan"].sum()),
            float(self.q43.summary["total_cost_yuan"]),
            places=6,
        )
        np.testing.assert_allclose(self.q43.g_final[:36], self.q43.g0[:36], atol=1e-8)
        six = self.q43.update_log[self.q43.update_log["update_time"] == "06:00"]
        if not six.empty:
            self.assertEqual(int(six.iloc[0]["first_mutable_index"]), 36)

    def test_price_oracle_uses_actuals_and_does_not_replace_main(self) -> None:
        from q4.q4_3 import run_q4_3_day

        oracle = run_q4_3_day(self.bundle, 0, 6000.0, price_mode="oracle")
        self.assertTrue(oracle.summary["pass"])
        self.assertEqual(oracle.summary["price_mode"], "oracle")
        self.assertEqual(oracle.update_log.iloc[0]["price_source"], "price_oracle")
        np.testing.assert_allclose(
            oracle.dispatch["price_forecast_used"].to_numpy(),
            oracle.dispatch["actual_price"].to_numpy(),
            atol=1e-12,
        )
        self.assertFalse(np.allclose(oracle.g0, self.q43.g0, atol=1e-6))
        self.assertEqual(self.q43.summary.get("price_mode", "causal"), "causal")

    def test_settlement_sensitivity_matches_official_feb1_ledger(self) -> None:
        from pathlib import Path

        from q4.q4_3_sensitivity import summarize_settlement_day

        path = Path("output/q4/q4_3_dispatch_daily/dispatch_2025-02-01.csv")
        if not path.exists():
            self.skipTest("Q4-3 dispatch archive missing")
        row = summarize_settlement_day(pd.read_csv(path))
        self.assertTrue(row["ledger_matches_delivery"])
        self.assertIn("adjustment_update_clock_yuan", row)

    def test_future_price_does_not_change_jan1_q(self) -> None:
        from q4.info_set import probe_day_ahead_invariance

        report = probe_day_ahead_invariance(self.bundle, 0, 6000.0, None, tau=40)
        self.assertTrue(report["pass"], report)

    def test_future_price_does_not_change_day14_decisions(self) -> None:
        from q4.info_set import probe_day_ahead_invariance

        report = probe_day_ahead_invariance(self.bundle, 14, 6000.0, None, tau=40)
        self.assertTrue(report["q_invariant"], report)
        self.assertTrue(report["g0_invariant"], report)

    def test_day_ahead_as_of_ignores_current_day_price(self) -> None:
        from q4.prices import day_ahead_as_of

        hat, src, _chosen = day_ahead_as_of(self.bundle, 15, 14)
        self.assertNotEqual(src, "")
        other_prices = self.bundle.prices.price.copy()
        other_prices[14] += 5.0
        other_prices[15] += 5.0
        from q4.info_set import bundle_with_prices

        other = bundle_with_prices(self.bundle, other_prices)
        hat2, _src2, _ch2 = day_ahead_as_of(other, 15, 14)
        np.testing.assert_allclose(hat, hat2, atol=1e-12)


@unittest.skipUnless(ATTACH4.exists(), "attachments unavailable")
class AlphaCalibrationLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from q4.bundle import load_q4_bundle

        cls.bundle = load_q4_bundle(compute_price_mpc=False)

    def test_candidate_chains_own_soc_from_deployed_start(self) -> None:
        from q4.q4_2 import run_candidate_window, select_risk_alpha

        start = np.full(self.bundle.n_days(), np.nan)
        start[14] = 6000.0
        start[15] = 7000.0
        choice = select_risk_alpha(
            self.bundle,
            start,
            16,
            8,
            n_validation=2,
            alphas=(0.60, 0.90),
            log=False,
        )
        self.assertEqual(len(choice.window_records), 2)
        for row in choice.window_records:
            self.assertFalse(row["used_full_day_actual_scheduler"])
            self.assertTrue(row["no_future_info"])
            self.assertIn("total_planned_fee_yuan", row)
            self.assertIn("total_emergency_fee_yuan", row)
            self.assertIn("total_unused_quota_kwh", row)
            self.assertIn("daily_soc_end_path_kwh", row)
            self.assertTrue(row["all_value_cuts_present"])
            self.assertEqual(int(row["validation_days"]), 2)
        by_alpha = {
            float(row["risk_alpha"]): [
                d for d in choice.daily_records if abs(float(d["risk_alpha"]) - float(row["risk_alpha"])) < 1e-12
            ]
            for row in choice.window_records
        }
        for alpha, days in by_alpha.items():
            self.assertEqual(len(days), 2, alpha)
            self.assertAlmostEqual(days[0]["soc_start_kwh"], 6000.0, places=6)
            self.assertAlmostEqual(days[1]["soc_start_kwh"], days[0]["soc_end_kwh"], places=6)
            self.assertNotAlmostEqual(days[1]["soc_start_kwh"], 7000.0, places=3)
            self.assertTrue(days[0]["has_value_cuts"])
            self.assertGreater(len(days[0]["soc_end_path_kwh"].split(";")), 1)
            self.assertIn("planned_fee_yuan", days[0])
            self.assertIn("emergency_fee_yuan", days[0])
            self.assertIn("unused_quota_kwh", days[0])
            self.assertFalse(days[0]["used_full_day_actual_scheduler"])
        self.assertIn(choice.selected_alpha, (0.60, 0.90))
        ranked = sorted(
            choice.window_records,
            key=lambda row: (row["mean_validation_cost_yuan"], row["risk_alpha"]),
        )
        self.assertTrue(ranked[0]["selected"])
        self.assertEqual(choice.selected_alpha, float(ranked[0]["risk_alpha"]))

        daily, summary = run_candidate_window(
            self.bundle, start, 16, risk_alpha=0.60, k_target=8, n_validation=2
        )
        self.assertEqual(len(daily), 2)
        self.assertAlmostEqual(summary["soc_window_start_kwh"], 6000.0, places=6)

    def test_future_actuals_do_not_change_alpha_calibration(self) -> None:
        from q4.info_set import probe_alpha_calibration_invariance

        start = np.full(self.bundle.n_days(), 6000.0)
        report = probe_alpha_calibration_invariance(
            self.bundle,
            start,
            16,
            k_target=8,
            n_validation=1,
            alphas=(0.60, 0.90),
        )
        self.assertTrue(report["pass"], report)
        self.assertTrue(report["alpha_invariant"], report)
        self.assertTrue(report["cost_invariant"], report)
        self.assertLess(report["max_mean_cost_abs_diff_yuan"], 1e-6)
        from q4.audit import write_json
        from q4.config import OUTPUT_DIR

        write_json(OUTPUT_DIR / "q4_2_alpha_info_set_audit.json", report)


if __name__ == "__main__":
    unittest.main()
