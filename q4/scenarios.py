"""Triple residual K-medoids for Q4-2. Residuals are paired by historical date."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from q2.scenarios import pam, robust_scale
from q4.bundle import Q4Bundle
from q4.config import FIXED_SCENARIO_K, RESIDUAL_POOL_DAYS, T


@dataclass(frozen=True)
class TripleScenarioSet:
    target_index: int
    history_end_exclusive: int
    pool_indices: np.ndarray
    medoid_indices: np.ndarray
    cluster_labels: np.ndarray
    probabilities: np.ndarray
    scale_load: float
    scale_pv: float
    scale_price: float
    k_effective: int
    k_target: int


def complete_triple_days(bundle: Q4Bundle, history_end_exclusive: int) -> np.ndarray:
    """Days strictly before the cutoff with archived causal load, PV, and price forecasts."""
    ok = []
    for i in range(max(0, history_end_exclusive)):
        if not np.isfinite(bundle.price_archive.day_ahead[i]).all():
            continue
        if not np.isfinite(bundle.q2_forecast.load_hat[i]).all():
            continue
        if not np.isfinite(bundle.q2_forecast.pv_hat[i]).all():
            continue
        ok.append(i)
    if not ok:
        return np.zeros(0, dtype=int)
    pool = np.asarray(ok, dtype=int)
    return pool[pool >= max(0, history_end_exclusive - RESIDUAL_POOL_DAYS)]


def residual_stack(bundle: Q4Bundle, indices: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    load_r = bundle.q2.load[indices] - bundle.q2_forecast.load_hat[indices]
    pv_r = bundle.q2.pv[indices] - bundle.q2_forecast.pv_hat[indices]
    price_r = bundle.prices.price[indices] - bundle.price_archive.day_ahead[indices]
    return load_r, pv_r, price_r


def triple_distance_matrix(
    load_residual: np.ndarray, pv_residual: np.ndarray, price_residual: np.ndarray
) -> tuple[np.ndarray, float, float, float]:
    sl = robust_scale(load_residual)
    sp = robust_scale(pv_residual)
    spr = robust_scale(price_residual)
    dl = (load_residual[:, None, :] - load_residual[None, :, :]) / sl
    dp = (pv_residual[:, None, :] - pv_residual[None, :, :]) / sp
    dr = (price_residual[:, None, :] - price_residual[None, :, :]) / spr
    d2 = np.mean(dl * dl + dp * dp + dr * dr, axis=2)
    return np.sqrt(np.maximum(d2, 0.0)), sl, sp, spr


def build_triple_scenarios(
    bundle: Q4Bundle,
    target_index: int,
    history_end_exclusive: int | None = None,
    k_target: int = FIXED_SCENARIO_K,
) -> TripleScenarioSet | None:
    history_end = target_index if history_end_exclusive is None else history_end_exclusive
    if history_end <= 0 or history_end > target_index:
        return None
    pool = complete_triple_days(bundle, history_end)
    if len(pool) == 0:
        return None
    load_r, pv_r, price_r = residual_stack(bundle, pool)
    distance, sl, sp, spr = triple_distance_matrix(load_r, pv_r, price_r)
    k_eff = int(min(k_target, len(pool)))
    local_medoids, labels = pam(distance, k_eff)
    counts = np.bincount(labels, minlength=k_eff)
    probabilities = counts.astype(float) / len(pool)
    if not np.isclose(probabilities.sum(), 1.0, atol=1e-12):
        raise AssertionError("Q4-2 scenario probabilities do not sum to one")
    return TripleScenarioSet(
        target_index=target_index,
        history_end_exclusive=history_end,
        pool_indices=pool,
        medoid_indices=pool[local_medoids],
        cluster_labels=labels,
        probabilities=probabilities,
        scale_load=sl,
        scale_pv=sp,
        scale_price=spr,
        k_effective=k_eff,
        k_target=int(k_target),
    )


def scenario_paths(
    bundle: Q4Bundle,
    scenarios: TripleScenarioSet,
    base_load: np.ndarray,
    base_pv: np.ndarray,
    base_price: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    m = scenarios.medoid_indices
    load_r, pv_r, price_r = residual_stack(bundle, m)
    load = np.maximum(0.0, base_load[None, :] + load_r)
    pv = np.maximum(0.0, base_pv[None, :] + pv_r)
    price = np.maximum(0.0, base_price[None, :] + price_r)
    return load, pv, price


def posterior_weights(
    bundle: Q4Bundle,
    scenarios: TripleScenarioSet,
    observed_load_r: np.ndarray,
    observed_pv_r: np.ndarray,
    observed_price_r: np.ndarray,
) -> tuple[np.ndarray, float]:
    t = len(observed_load_r)
    if t == 0:
        return scenarios.probabilities.copy(), np.nan
    m = scenarios.medoid_indices
    load_r, pv_r, price_r = residual_stack(bundle, m)
    lr = load_r[:, :t]
    pr = pv_r[:, :t]
    rr = price_r[:, :t]
    delta = np.mean(
        ((lr - observed_load_r) / scenarios.scale_load) ** 2
        + ((pr - observed_pv_r) / scenarios.scale_pv) ** 2
        + ((rr - observed_price_r) / scenarios.scale_price) ** 2,
        axis=1,
    )
    if len(m) > 1:
        pair = []
        for a in range(len(m)):
            for b in range(a + 1, len(m)):
                pair.append(
                    np.mean(
                        ((lr[a] - lr[b]) / scenarios.scale_load) ** 2
                        + ((pr[a] - pr[b]) / scenarios.scale_pv) ** 2
                        + ((rr[a] - rr[b]) / scenarios.scale_price) ** 2
                    )
                )
        bandwidth = max(float(np.sqrt(np.median(pair))), 1e-6)
    else:
        bandwidth = 1.0
    logw = np.log(np.maximum(scenarios.probabilities, 1e-300)) - delta / (
        2.0 * bandwidth * bandwidth
    )
    logw -= np.max(logw)
    weights = np.exp(logw)
    weights /= weights.sum()
    return weights, bandwidth
