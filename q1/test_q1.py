from __future__ import annotations

import unittest

import numpy as np

from q1.config import DEFAULT_ATTACH1, DEFAULT_RESULT1_TEMPLATE, DELTA_H, T
from q1.load_data import inspect_template, load_attachment1, normalize_attach_time
from q1.optimize import ModelParams, default_params, solve_stage


class TestLoadOrder(unittest.TestCase):
    def test_raw_row_order_and_times(self) -> None:
        if not DEFAULT_ATTACH1.exists():
            self.skipTest("附件1 missing")
        df = load_attachment1(DEFAULT_ATTACH1)
        self.assertEqual(len(df), T)
        self.assertEqual(list(df["t"]), list(range(1, T + 1)))
        self.assertEqual(df["attach_time"].iloc[0], "00:10:00")
        self.assertEqual(df["attach_time"].iloc[-1], "0:00+1")
        self.assertEqual(df.attrs["row_order_policy"], "attachment_raw_order")
        self.assertGreaterEqual(df["price"].min(), 0.0)

    def test_template_labels(self) -> None:
        if not DEFAULT_RESULT1_TEMPLATE.exists():
            self.skipTest("template missing")
        labels, blocks = inspect_template(DEFAULT_RESULT1_TEMPLATE)
        self.assertEqual(len(labels), T)
        self.assertEqual(labels[0], "0:10-0:20")
        self.assertEqual(labels[-1], "0:00+1-0:10+1")
        self.assertEqual(blocks[0], "0:00-4:00")
        self.assertEqual(blocks[-1], "20:00-24:00")

    def test_normalize_time(self) -> None:
        self.assertEqual(normalize_attach_time("0:00+1"), "0:00+1")


class TestParamsAndBounds(unittest.TestCase):
    def _attach_arrays(self):
        if not DEFAULT_ATTACH1.exists():
            self.skipTest("附件1 missing")
        df = load_attachment1(DEFAULT_ATTACH1)
        return df["price"].to_numpy(), df["load_kwh"].to_numpy(), df["pv_kwh"].to_numpy()

    def test_grid_limit_is_kw(self) -> None:
        price, load, pv = self._attach_arrays()
        p = ModelParams(grid_limit_kw=4000.0)
        r = solve_stage("gmax", price, load, pv, params=p)
        self.assertTrue(r.passed, r.notes)
        self.assertLessEqual(np.max(r.g), p.g_max_kwh + 1e-6)
        self.assertAlmostEqual(p.g_max_kwh, 4000.0 * DELTA_H)

    def test_s_le_pv(self) -> None:
        price, load, pv = self._attach_arrays()
        r = solve_stage("sbound", price, load, pv, params=default_params())
        self.assertTrue(r.passed, r.notes)
        self.assertTrue(np.all(r.s <= pv + 1e-8))

    def test_eta_changes_cost(self) -> None:
        price, load, pv = self._attach_arrays()
        a = solve_stage("A", price, load, pv, params=default_params())
        b = solve_stage("B", price, load, pv, params=ModelParams(eta_c=0.9, eta_d=0.9))
        self.assertTrue(a.passed and b.passed)
        self.assertGreater(abs(a.purchase_cost - b.purchase_cost), 1.0)


if __name__ == "__main__":
    unittest.main()
