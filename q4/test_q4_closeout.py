from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import POWER_LIMIT_KWH, T
from q4.audit import physical_from_dispatch
from q4.closeout import (
    empirical_cvar,
    empirical_var,
    expected_q43_last_update,
    output_interval,
    pearson_corrcoef,
    residual_correlation_report,
    scan_dispatch_year,
)


class WindowFilterTests(unittest.TestCase):
    def test_export_window_keeps_334_days(self) -> None:
        dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
        frame = pd.DataFrame({"date": dates, "total_cost_yuan": np.arange(len(dates), dtype=float)})
        selected = output_interval(frame)
        self.assertEqual(len(selected), 334)
        self.assertEqual(str(selected["date"].iloc[0].date()), "2025-02-01")
        self.assertEqual(str(selected["date"].iloc[-1].date()), "2025-12-31")
        self.assertNotIn(pd.Timestamp("2025-01-31"), pd.to_datetime(selected["date"]).tolist())

    def test_wrong_length_raises(self) -> None:
        frame = pd.DataFrame({"date": ["2025-02-01", "2025-02-02"], "total_cost_yuan": [1.0, 2.0]})
        with self.assertRaises(AssertionError):
            output_interval(frame)


class CVaRTests(unittest.TestCase):
    def test_uniform_ten_points(self) -> None:
        values = np.arange(1, 11, dtype=float)
        self.assertAlmostEqual(empirical_var(values, 0.90), 9.1)
        # worst ceil(0.1 * 10) = 1 observation
        self.assertAlmostEqual(empirical_cvar(values, 0.90), 10.0)
        self.assertAlmostEqual(empirical_cvar(values, 0.80), float(np.mean([9.0, 10.0])))

    def test_cvar_uses_worst_tail_not_body(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 100.0])
        self.assertGreater(empirical_cvar(values, 0.75), empirical_var(values, 0.75))
        self.assertAlmostEqual(empirical_cvar(values, 0.75), 100.0)


class PhysicalAggregationTests(unittest.TestCase):
    def _one_day(self, date: str, q4_3: bool) -> pd.DataFrame:
        t = np.arange(T)
        load = np.full(T, 100.0)
        pv = np.zeros(T)
        x = np.full(T, 100.0)
        q = np.full(T, 120.0)
        g = q.copy()
        if q4_3:
            g[40] = 130.0
        charge = np.zeros(T)
        discharge = np.zeros(T)
        emergency = np.zeros(T)
        residual = x + emergency + pv + discharge - load - charge
        clocks = expected_q43_last_update(t) if q4_3 else np.full(T, "00:00")
        labels = [f"{((i + 1) // 6) % 24:02d}:{((i + 1) % 6) * 10:02d}" for i in range(T)]
        labels[0] = "00:10"
        labels[-1] = "0:00+1"
        soc = np.full(T, 6000.0)
        return pd.DataFrame(
            {
                "date": date,
                "period_index": t,
                "time_label": labels,
                "q_or_g0_kwh": q,
                "g_final_kwh": g if q4_3 else np.nan,
                "x_kwh": x,
                "emergency_kwh": emergency,
                "charge_kwh": charge,
                "discharge_kwh": discharge,
                "curtailment_kwh": 0.0,
                "soc_start_kwh": soc,
                "soc_end_kwh": soc,
                "actual_load_kwh": load,
                "actual_pv_kwh": pv,
                "actual_price": np.full(T, 0.5),
                "last_update_time": clocks,
                "balance_residual_kwh": residual,
            }
        )

    def test_physical_from_dispatch_pass(self) -> None:
        frame = self._one_day("2025-02-01", q4_3=False)
        phys = physical_from_dispatch(frame, q4_3=False)
        self.assertTrue(phys["pass"])
        self.assertLess(phys["max_x_minus_cap_kwh"], 0.0)

    def test_year_scan_on_tiny_calendar_rejected(self) -> None:
        frame = self._one_day("2025-01-01", q4_3=False)
        daily = pd.DataFrame(
            {
                "date": ["2025-01-01"],
                "total_cost_yuan": [0.5 * 120.0 * T],
                "soc_start_kwh": [6000.0],
                "soc_end_kwh": [6000.0],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dispatch_2025-01-01.csv"
            frame.to_csv(path, index=False)
            with self.assertRaises(AssertionError):
                scan_dispatch_year(Path(tmp), daily, q4_3=False)

    def test_q43_clock_by_period(self) -> None:
        clocks = expected_q43_last_update(np.arange(T))
        self.assertEqual(clocks[0], "00:00")
        self.assertEqual(clocks[35], "00:00")
        self.assertEqual(clocks[36], "06:00")
        self.assertEqual(clocks[72], "12:00")
        self.assertEqual(clocks[108], "18:00")
        self.assertLessEqual(POWER_LIMIT_KWH, 833.34)


class ResidualCorrelationTests(unittest.TestCase):
    def test_perfect_and_zero_correlation(self) -> None:
        rng = np.random.default_rng(0)
        load = rng.normal(size=(8, T))
        pv = 2.0 * load
        price = rng.normal(size=(8, T))
        report = residual_correlation_report(
            load, pv, price, [f"2025-01-{i+1:02d}" for i in range(8)]
        )
        self.assertAlmostEqual(report["pearson_flattened_slots"]["load_vs_pv"], 1.0, places=12)
        self.assertEqual(report["n_days"], 8)
        self.assertTrue(np.isnan(pearson_corrcoef(np.ones(5), np.arange(5.0))))
        anti = pearson_corrcoef(np.arange(10.0), -np.arange(10.0))
        self.assertAlmostEqual(anti, -1.0, places=12)


if __name__ == "__main__":
    unittest.main()
