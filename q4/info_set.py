"""Information-set probes: future prices must not change day-ahead decisions."""

from __future__ import annotations

import numpy as np

from q4.bundle import Q4Bundle
from q4.data import Q4PriceData
from q4.price_forecast import fit_causal_price_forecasts
from q4.q4_2 import plan_locked_q
from q4.q4_3 import plan_g0


def perturb_unended_and_future(
    prices: np.ndarray, day_index: int, tau: int, delta: float = 3.25
) -> np.ndarray:
    out = np.asarray(prices, dtype=float).copy()
    out[day_index, tau:] = out[day_index, tau:] + delta
    if day_index + 1 < len(out):
        out[day_index + 1 :] = out[day_index + 1 :] + delta
    return np.maximum(out, 0.0)


def bundle_with_prices(bundle: Q4Bundle, new_prices: np.ndarray) -> Q4Bundle:
    archive = fit_causal_price_forecasts(
        new_prices, bundle.prices.dates, compute_mpc=False
    )
    prices = Q4PriceData(
        dates=bundle.prices.dates,
        time_labels=bundle.prices.time_labels,
        price=np.asarray(new_prices, dtype=float),
    )
    return Q4Bundle(
        q3=bundle.q3,
        q2=bundle.q2,
        q2_forecast=bundle.q2_forecast,
        prices=prices,
        price_archive=archive,
    )


def probe_day_ahead_invariance(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    risk_alpha: float | None,
    tau: int = 40,
    with_value_cuts: bool = False,
) -> dict:
    date = bundle.prices.dates[day_index].strftime("%Y-%m-%d")
    q0 = plan_locked_q(
        bundle, day_index, initial_soc, risk_alpha, with_value_cuts=with_value_cuts
    )
    g0 = plan_g0(bundle, day_index, initial_soc, with_value_cuts=with_value_cuts)
    perturbed = perturb_unended_and_future(bundle.prices.price, day_index, tau)
    other = bundle_with_prices(bundle, perturbed)
    q1 = plan_locked_q(
        other, day_index, initial_soc, risk_alpha, with_value_cuts=with_value_cuts
    )
    g1 = plan_g0(other, day_index, initial_soc, with_value_cuts=with_value_cuts)
    q_ok = bool(np.allclose(q0, q1, atol=1e-6, rtol=0.0))
    g_ok = bool(np.allclose(g0, g1, atol=1e-6, rtol=0.0))
    return {
        "date": date,
        "day_index": int(day_index),
        "tau_perturbed": int(tau),
        "with_value_cuts": with_value_cuts,
        "q_max_abs_diff_kwh": float(np.max(np.abs(q0 - q1))),
        "g0_max_abs_diff_kwh": float(np.max(np.abs(g0 - g1))),
        "q_invariant": q_ok,
        "g0_invariant": g_ok,
        "pass": q_ok and g_ok,
    }


def probe_executed_prefix(
    bundle: Q4Bundle,
    day_index: int,
    initial_soc: float,
    risk_alpha: float | None,
    q42_dispatch,
    q43_result,
    tau: int = 40,
) -> dict:
    """Re-solve the day after perturbing unended/future prices; prefix actions must match."""
    from q4.q4_2 import run_q4_2_day
    from q4.q4_3 import run_q4_3_day

    date = bundle.prices.dates[day_index].strftime("%Y-%m-%d")
    other = bundle_with_prices(
        bundle, perturb_unended_and_future(bundle.prices.price, day_index, tau)
    )
    r2 = run_q4_2_day(other, day_index, initial_soc, risk_alpha)
    r3 = run_q4_3_day(other, day_index, initial_soc)
    cols = ["q_or_g0_kwh", "x_kwh", "charge_kwh", "discharge_kwh", "emergency_kwh"]
    d2 = q42_dispatch.iloc[:tau][cols].to_numpy(float)
    d2p = r2.dispatch.iloc[:tau][cols].to_numpy(float)
    q42_ok = bool(np.allclose(d2, d2p, atol=1e-5, rtol=0.0)) and bool(
        np.allclose(q42_dispatch["q_or_g0_kwh"].to_numpy(), r2.q, atol=1e-6)
    )
    g_cols = ["q_or_g0_kwh", "g_final_kwh", "x_kwh", "charge_kwh", "discharge_kwh"]
    d3 = q43_result.dispatch.iloc[:tau][g_cols].to_numpy(float)
    d3p = r3.dispatch.iloc[:tau][g_cols].to_numpy(float)
    q43_ok = bool(np.allclose(d3, d3p, atol=1e-5, rtol=0.0)) and bool(
        np.allclose(q43_result.g0, r3.g0, atol=1e-6)
    )
    return {
        "date": date,
        "tau_perturbed": int(tau),
        "q42_q_max_abs_diff_kwh": float(
            np.max(np.abs(q42_dispatch["q_or_g0_kwh"].to_numpy() - r2.q))
        ),
        "q42_prefix_max_abs_diff": float(np.max(np.abs(d2 - d2p))),
        "q43_g0_max_abs_diff_kwh": float(np.max(np.abs(q43_result.g0 - r3.g0))),
        "q43_prefix_max_abs_diff": float(np.max(np.abs(d3 - d3p))),
        "q42_pass": q42_ok,
        "q43_pass": q43_ok,
        "pass": q42_ok and q43_ok,
    }
