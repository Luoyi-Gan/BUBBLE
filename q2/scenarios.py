from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from q2.config import RESIDUAL_POOL_DAYS
from q2.data import Q2Data
from q2.forecast import ForecastArchive


@dataclass(frozen=True)
class ScenarioSet:
    target_index: int
    pool_indices: np.ndarray
    medoid_indices: np.ndarray
    cluster_labels: np.ndarray
    probabilities: np.ndarray
    scale_load: float
    scale_pv: float
    stress_index: int


def robust_scale(values: np.ndarray) -> float:
    flat = np.asarray(values, dtype=float).ravel()
    med = np.median(flat)
    mad = 1.4826 * np.median(np.abs(flat - med))
    if mad > 1e-12:
        return float(mad)
    std = np.std(flat)
    return float(std if std > 1e-12 else 1.0)


def residual_distance_matrix(
    load_residual: np.ndarray, pv_residual: np.ndarray, price: np.ndarray
) -> tuple[np.ndarray, float, float]:
    sl = robust_scale(load_residual)
    sp = robust_scale(pv_residual)
    weight = price / np.mean(price)
    dl = (load_residual[:, None, :] - load_residual[None, :, :]) / sl
    dp = (pv_residual[:, None, :] - pv_residual[None, :, :]) / sp
    d2 = np.mean(weight[None, None, :] * (dl * dl + dp * dp), axis=2)
    return np.sqrt(np.maximum(d2, 0.0)), sl, sp


def pam(distance: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Small deterministic PAM implementation over a <=28-day pool."""
    n = distance.shape[0]
    if not 1 <= k <= n:
        raise ValueError(f"k={k} is invalid for pool size {n}")
    medoids = [int(np.argmin(distance.sum(axis=1)))]
    while len(medoids) < k:
        nearest = distance[:, medoids].min(axis=1)
        nearest[medoids] = -np.inf
        medoids.append(int(np.argmax(nearest)))
    medoids = np.array(sorted(medoids), dtype=int)

    def cost(ms: np.ndarray) -> float:
        return float(distance[:, ms].min(axis=1).sum())

    current = cost(medoids)
    while True:
        best_cost, best = current, medoids
        outside = np.setdiff1d(np.arange(n), medoids)
        for pos in range(k):
            for candidate in outside:
                trial = medoids.copy()
                trial[pos] = candidate
                trial.sort()
                trial_cost = cost(trial)
                if trial_cost < best_cost - 1e-12:
                    best_cost, best = trial_cost, trial
        if best_cost >= current - 1e-12:
            break
        medoids, current = best, best_cost
    labels = np.argmin(distance[:, medoids], axis=1)
    return medoids, labels


def build_scenarios(
    target_index: int,
    data: Q2Data,
    archive: ForecastArchive,
    k: int,
) -> ScenarioSet:
    if target_index <= 0:
        raise ValueError("No historical residual exists for the first date")
    pool = np.arange(max(0, target_index - RESIDUAL_POOL_DAYS), target_index)
    lr = archive.load_residual[pool]
    pr = archive.pv_residual[pool]
    distance, sl, sp = residual_distance_matrix(lr, pr, data.price)
    local_medoids, labels = pam(distance, min(k, len(pool)))
    counts = np.bincount(labels, minlength=len(local_medoids))
    probabilities = counts.astype(float) / len(pool)
    if not np.isclose(probabilities.sum(), 1.0, atol=1e-12):
        raise AssertionError("scenario probabilities do not sum to one")
    high = data.price >= np.quantile(data.price, 0.75)
    net_positive = np.maximum(lr - pr, 0.0)
    stress_local = int(np.argmax((net_positive[:, high] * data.price[high]).sum(axis=1)))
    return ScenarioSet(
        target_index=target_index,
        pool_indices=pool,
        medoid_indices=pool[local_medoids],
        cluster_labels=labels,
        probabilities=probabilities,
        scale_load=sl,
        scale_pv=sp,
        stress_index=int(pool[stress_local]),
    )


def scenario_trajectories(
    scenarios: ScenarioSet, archive: ForecastArchive
) -> tuple[np.ndarray, np.ndarray]:
    i = scenarios.target_index
    m = scenarios.medoid_indices
    load = np.maximum(0.0, archive.load_hat[i][None, :] + archive.load_residual[m])
    pv = np.maximum(0.0, archive.pv_hat[i][None, :] + archive.pv_residual[m])
    return load, pv


def write_scenarios_csv(
    path: Path, data: Q2Data, scenarios: ScenarioSet
) -> None:
    rows = []
    for cluster, medoid in enumerate(scenarios.medoid_indices):
        rows.append(
            {
                "calibration_date": data.dates[scenarios.target_index].strftime("%Y-%m-%d"),
                "medoid_date": data.dates[medoid].strftime("%Y-%m-%d"),
                "cluster_size": int(np.sum(scenarios.cluster_labels == cluster)),
                "probability": scenarios.probabilities[cluster],
                "stress_test_date": data.dates[scenarios.stress_index].strftime("%Y-%m-%d"),
                "medoid_is_stress_day": bool(medoid == scenarios.stress_index),
                "pool_start": data.dates[scenarios.pool_indices[0]].strftime("%Y-%m-%d"),
                "pool_end": data.dates[scenarios.pool_indices[-1]].strftime("%Y-%m-%d"),
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def posterior_weights(
    scenarios: ScenarioSet,
    archive: ForecastArchive,
    observed_load_residual_prefix: np.ndarray,
    observed_pv_residual_prefix: np.ndarray,
) -> tuple[np.ndarray, float]:
    m = scenarios.medoid_indices
    t = len(observed_load_residual_prefix)
    lr = archive.load_residual[m, :t]
    pr = archive.pv_residual[m, :t]
    delta = np.mean(
        ((lr - observed_load_residual_prefix) / scenarios.scale_load) ** 2
        + ((pr - observed_pv_residual_prefix) / scenarios.scale_pv) ** 2,
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

