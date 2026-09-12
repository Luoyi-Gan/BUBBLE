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


if __name__ == "__main__":
    unittest.main()
