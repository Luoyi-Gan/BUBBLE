"""Information-set probes: future actuals must not change day-ahead or α calibration."""

from __future__ import annotations

import numpy as np

from q2.data import Q2Data
from q2.forecast import build_forecast_archive
from q4.bundle import Q4Bundle
from q4.data import Q4PriceData
from q4.price_forecast import fit_causal_price_forecasts
from q4.q4_2 import plan_locked_q, select_risk_alpha
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
    soc_q43 = float(q43_result.summary["soc_start_kwh"])
    r3 = run_q4_3_day(other, day_index, soc_q43)
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


def perturb_future_actuals(
    bundle: Q4Bundle,
    from_day: int,
    *,
    delta_price: float = 3.25,
    load_scale: float = 1.15,
    pv_scale: float = 0.85,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Shift actual price/load/PV on from_day and later; leave completed days intact."""
    prices = np.asarray(bundle.prices.price, dtype=float).copy()
    load = np.asarray(bundle.q2.load, dtype=float).copy()
    pv = np.asarray(bundle.q2.pv, dtype=float).copy()
    prices[from_day:] = np.maximum(prices[from_day:] + delta_price, 0.0)
    load[from_day:] = np.maximum(load[from_day:] * load_scale, 0.0)
    pv[from_day:] = np.maximum(pv[from_day:] * pv_scale, 0.0)
    return prices, load, pv


def bundle_with_future_actuals(
    bundle: Q4Bundle,
    from_day: int,
    *,
    delta_price: float = 3.25,
    load_scale: float = 1.15,
    pv_scale: float = 0.85,
) -> Q4Bundle:
    prices, load, pv = perturb_future_actuals(
        bundle,
        from_day,
        delta_price=delta_price,
        load_scale=load_scale,
        pv_scale=pv_scale,
    )
    q2 = Q2Data(
        dates=bundle.q2.dates,
        time_labels=bundle.q2.time_labels,
        price=bundle.q2.price,
        fallback_load=bundle.q2.fallback_load,
        fallback_pv=bundle.q2.fallback_pv,
        load=load,
        pv=pv,
    )
    archive = fit_causal_price_forecasts(
        prices, bundle.prices.dates, compute_mpc=False
    )
    return Q4Bundle(
        q3=bundle.q3,
        q2=q2,
        q2_forecast=build_forecast_archive(q2),
        prices=Q4PriceData(
            dates=bundle.prices.dates,
            time_labels=bundle.prices.time_labels,
            price=prices,
        ),
        price_archive=archive,
    )


def probe_alpha_calibration_invariance(
    bundle: Q4Bundle,
    policy_start_soc: np.ndarray,
    target_index: int,
    *,
    k_target: int = 8,
    n_validation: int = 1,
    alphas: tuple[float, ...] = (0.60, 0.90),
) -> dict:
    """Perturb actuals of the calibration day and later; α scores must not move."""
    baseline = select_risk_alpha(
        bundle,
        policy_start_soc,
        target_index,
        k_target,
        n_validation=n_validation,
        alphas=alphas,
        log=False,
    )
    other = bundle_with_future_actuals(bundle, target_index)
    perturbed = select_risk_alpha(
        other,
        policy_start_soc,
        target_index,
        k_target,
        n_validation=n_validation,
        alphas=alphas,
        log=False,
    )
    base_costs = {
        float(row["risk_alpha"]): float(row["mean_validation_cost_yuan"])
        for row in baseline.window_records
    }
    other_costs = {
        float(row["risk_alpha"]): float(row["mean_validation_cost_yuan"])
        for row in perturbed.window_records
    }
    cost_gaps = {
        alpha: abs(base_costs[alpha] - other_costs[alpha]) for alpha in base_costs
    }
    max_cost_gap = float(max(cost_gaps.values())) if cost_gaps else 0.0
    alpha_ok = abs(baseline.selected_alpha - perturbed.selected_alpha) < 1e-12
    cost_ok = max_cost_gap < 1e-6
    return {
        "target_index": int(target_index),
        "n_validation": int(n_validation),
        "alphas": [float(a) for a in alphas],
        "baseline_selected_alpha": float(baseline.selected_alpha),
        "perturbed_selected_alpha": float(perturbed.selected_alpha),
        "max_mean_cost_abs_diff_yuan": max_cost_gap,
        "mean_cost_abs_diff_by_alpha": cost_gaps,
        "alpha_invariant": alpha_ok,
        "cost_invariant": cost_ok,
        "no_future_info": True,
        "used_full_day_actual_scheduler": False,
        "pass": alpha_ok and cost_ok,
    }
