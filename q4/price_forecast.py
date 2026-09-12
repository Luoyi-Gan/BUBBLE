"""Causal day-ahead and intraday price forecasts. History is strictly before day d."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from q4.config import (
    CANDIDATE_MODELS,
    CANDIDATE_NAMES,
    INTRA_HOUR_TAU,
    T,
    VAR_EPS,
)


def construct_candidate(
    prices: np.ndarray,
    weekdays: np.ndarray,
    day_index: int,
    model: int,
) -> np.ndarray | None:
    if model == 1:
        if day_index < 1:
            return None
        return prices[day_index - 1].copy()
    if model not in (2, 4):
        raise ValueError(f"unknown candidate model {model}")
    same = np.flatnonzero((np.arange(day_index) >= 0) & (weekdays[:day_index] == weekdays[day_index]))
    if same.size < model:
        return None
    return prices[same[-model:]].mean(axis=0)


def _mae(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - forecast)))


def _rmse(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - forecast) ** 2)))


def ols_remaining(
    residual_hist: np.ndarray,
    z_hist: np.ndarray,
    z_now: float,
) -> tuple[np.ndarray, bool]:
    """Fit r_t = alpha_t + beta_t z on historical days; return residual forecast for remaining t.

    residual_hist has shape (n_hist, n_future). z_hist has shape (n_hist,).
    """
    n_hist, n_future = residual_hist.shape
    if n_hist < 2:
        if n_hist == 1:
            return residual_hist[0].copy(), True
        return np.zeros(n_future, dtype=float), True
    z_center = z_hist - float(z_hist.mean())
    denom = float(np.dot(z_center, z_center))
    if denom <= VAR_EPS:
        return residual_hist.mean(axis=0).copy(), True
    r_center = residual_hist - residual_hist.mean(axis=0)
    beta = z_center @ r_center / denom
    alpha = residual_hist.mean(axis=0) - beta * float(z_hist.mean())
    return alpha + beta * float(z_now), False


def intraday_price_forecast(
    actual: np.ndarray,
    day_ahead: np.ndarray,
    hist_actual: np.ndarray,
    hist_day_ahead: np.ndarray,
    tau: int,
) -> tuple[np.ndarray, bool]:
    """Return a 144-vector: known actual[:tau], OLS-updated remaining[tau:], clamped at 0."""
    if tau < 0 or tau > T:
        raise ValueError(f"tau out of range: {tau}")
    out = np.empty(T, dtype=float)
    if tau == 0:
        return np.maximum(0.0, day_ahead.copy()), True
    out[:tau] = actual[:tau]
    if tau == T:
        return out, True
    z_now = float(np.mean(actual[:tau] - day_ahead[:tau]))
    if hist_actual.size == 0:
        out[tau:] = np.maximum(0.0, day_ahead[tau:])
        return out, True
    residual_hist = hist_actual[:, tau:] - hist_day_ahead[:, tau:]
    z_hist = (hist_actual[:, :tau] - hist_day_ahead[:, :tau]).mean(axis=1)
    delta, fallback = ols_remaining(residual_hist, z_hist, z_now)
    out[tau:] = np.maximum(0.0, day_ahead[tau:] + delta)
    return out, fallback


@dataclass
class PriceForecastArchive:
    dates: pd.DatetimeIndex
    price: np.ndarray
    day_ahead: np.ndarray
    chosen_model: np.ndarray
    candidate_forecasts: dict[int, np.ndarray]
    candidate_available: dict[int, np.ndarray]
    mae_through_prev: dict[int, np.ndarray]
    n_backtest: dict[int, np.ndarray]
    audit: pd.DataFrame


def fit_causal_price_forecasts(
    prices: np.ndarray,
    dates: pd.DatetimeIndex,
    compute_mpc: bool = True,
) -> PriceForecastArchive:
    n = len(dates)
    if prices.shape != (n, T):
        raise ValueError(f"prices shape {prices.shape} != {(n, T)}")
    weekdays = dates.weekday.to_numpy()
    day_ahead = np.full((n, T), np.nan)
    chosen = np.full(n, -1, dtype=int)
    cand_hat = {a: np.full((n, T), np.nan) for a in CANDIDATE_MODELS}
    cand_ok = {a: np.zeros(n, dtype=bool) for a in CANDIDATE_MODELS}
    mae_prev = {a: np.full(n, np.nan) for a in CANDIDATE_MODELS}
    n_bt = {a: np.zeros(n, dtype=int) for a in CANDIDATE_MODELS}
    abs_sum = {a: 0.0 for a in CANDIDATE_MODELS}
    bt_count = {a: 0 for a in CANDIDATE_MODELS}

    rows = []
    for d in range(n):
        for a in CANDIDATE_MODELS:
            n_bt[a][d] = bt_count[a]
            if bt_count[a] > 0:
                mae_prev[a][d] = abs_sum[a] / (bt_count[a] * T)
            hat = construct_candidate(prices, weekdays, d, a)
            if hat is None:
                continue
            cand_hat[a][d] = hat
            cand_ok[a][d] = True

        available = [a for a in CANDIDATE_MODELS if cand_ok[a][d]]
        fallback = "none"
        if not available:
            fallback = "no_history"
            chosen_a = -1
        else:
            scored = []
            for a in available:
                mae = mae_prev[a][d]
                score = float("inf") if not np.isfinite(mae) else float(mae)
                scored.append((score, a))
            chosen_a = min(scored)[1]
            if not cand_ok[1][d]:
                fallback = "no_previous_day"
            elif not cand_ok[2][d] and not cand_ok[4][d]:
                fallback = "previous_day_only"
        chosen[d] = chosen_a
        if chosen_a > 0:
            day_ahead[d] = cand_hat[chosen_a][d]

        da_mae = np.nan
        da_rmse = np.nan
        if chosen_a > 0:
            da_mae = _mae(prices[d], day_ahead[d])
            da_rmse = _rmse(prices[d], day_ahead[d])

        hist_idx = [i for i in range(d) if chosen[i] > 0]
        hist_actual = prices[hist_idx] if hist_idx else np.zeros((0, T))
        hist_da = day_ahead[hist_idx] if hist_idx else np.zeros((0, T))
        intra = {}
        mpc_mae = []
        n_mpc_fallback = 0
        n_mpc = 0
        if chosen_a > 0:
            for hour, tau in INTRA_HOUR_TAU.items():
                pred, ols_fb = intraday_price_forecast(
                    prices[d], day_ahead[d], hist_actual, hist_da, tau
                )
                intra[hour] = {
                    "mae": _mae(prices[d, tau:], pred[tau:]),
                    "rmse": _rmse(prices[d, tau:], pred[tau:]),
                    "ols_fallback": bool(ols_fb),
                }
            if compute_mpc:
                for tau in range(1, T):
                    pred, ols_fb = intraday_price_forecast(
                        prices[d], day_ahead[d], hist_actual, hist_da, tau
                    )
                    mpc_mae.append(_mae(prices[d, tau:], pred[tau:]))
                    n_mpc += 1
                    n_mpc_fallback += int(ols_fb)

        train_cutoff = dates[d - 1].strftime("%Y-%m-%d") if d else ""
        row = {
            "date": dates[d].strftime("%Y-%m-%d"),
            "day_index": d,
            "train_cutoff_date": train_cutoff,
            "weekday": int(weekdays[d]),
            "mae_prev_day": mae_prev[1][d],
            "mae_weekday2": mae_prev[2][d],
            "mae_weekday4": mae_prev[4][d],
            "n_backtest_prev_day": int(n_bt[1][d]),
            "n_backtest_weekday2": int(n_bt[2][d]),
            "n_backtest_weekday4": int(n_bt[4][d]),
            "candidate_prev_day_available": bool(cand_ok[1][d]),
            "candidate_weekday2_available": bool(cand_ok[2][d]),
            "candidate_weekday4_available": bool(cand_ok[4][d]),
            "chosen_model": chosen_a if chosen_a > 0 else "",
            "chosen_model_name": CANDIDATE_NAMES.get(chosen_a, "none"),
            "day_ahead_fallback": fallback,
            "day_ahead_mae": da_mae,
            "day_ahead_rmse": da_rmse,
            "intraday_06_mae": intra.get(6, {}).get("mae", np.nan),
            "intraday_06_rmse": intra.get(6, {}).get("rmse", np.nan),
            "intraday_06_ols_fallback": intra.get(6, {}).get("ols_fallback", True),
            "intraday_12_mae": intra.get(12, {}).get("mae", np.nan),
            "intraday_12_rmse": intra.get(12, {}).get("rmse", np.nan),
            "intraday_12_ols_fallback": intra.get(12, {}).get("ols_fallback", True),
            "intraday_18_mae": intra.get(18, {}).get("mae", np.nan),
            "intraday_18_rmse": intra.get(18, {}).get("rmse", np.nan),
            "intraday_18_ols_fallback": intra.get(18, {}).get("ols_fallback", True),
            "mpc_remaining_mae_mean": float(np.mean(mpc_mae)) if mpc_mae else np.nan,
            "n_mpc_points": n_mpc,
            "n_mpc_ols_fallback": n_mpc_fallback,
        }
        rows.append(row)

        for a in CANDIDATE_MODELS:
            if cand_ok[a][d]:
                abs_sum[a] += float(np.abs(prices[d] - cand_hat[a][d]).sum())
                bt_count[a] += 1

    audit = pd.DataFrame(rows)
    return PriceForecastArchive(
        dates=dates,
        price=prices,
        day_ahead=day_ahead,
        chosen_model=chosen,
        candidate_forecasts=cand_hat,
        candidate_available=cand_ok,
        mae_through_prev=mae_prev,
        n_backtest=n_bt,
        audit=audit,
    )


def assert_no_future_price_leak(
    prices: np.ndarray,
    dates: pd.DatetimeIndex,
    day_index: int,
    tau: int = 0,
) -> None:
    """Perturb prices at and after (day_index, tau); earlier forecasts/choices must not change."""
    archive = fit_causal_price_forecasts(prices, dates, compute_mpc=False)
    perturbed = prices.copy()
    perturbed[day_index, tau:] += 7.5
    if day_index + 1 < len(prices):
        perturbed[day_index + 1 :] += 3.25
    other = fit_causal_price_forecasts(perturbed, dates, compute_mpc=False)
    if day_index > 0:
        np.testing.assert_allclose(
            archive.day_ahead[:day_index],
            other.day_ahead[:day_index],
            equal_nan=True,
        )
        np.testing.assert_array_equal(archive.chosen_model[:day_index], other.chosen_model[:day_index])
    if tau == 0:
        if np.isfinite(archive.day_ahead[day_index]).all():
            np.testing.assert_allclose(archive.day_ahead[day_index], other.day_ahead[day_index], equal_nan=True)
        np.testing.assert_equal(archive.chosen_model[day_index], other.chosen_model[day_index])
    else:
        if archive.chosen_model[day_index] <= 0:
            return
        hist_idx = [i for i in range(day_index) if archive.chosen_model[i] > 0]
        hist_actual = prices[hist_idx] if hist_idx else np.zeros((0, T))
        hist_da = archive.day_ahead[hist_idx] if hist_idx else np.zeros((0, T))
        before, _ = intraday_price_forecast(
            prices[day_index], archive.day_ahead[day_index], hist_actual, hist_da, tau
        )
        after, _ = intraday_price_forecast(
            perturbed[day_index], other.day_ahead[day_index], hist_actual, hist_da, tau
        )
        np.testing.assert_allclose(before[tau:], after[tau:])


def two_day_regression(archive: PriceForecastArchive, dates: tuple[str, ...]) -> dict:
    payload = {}
    for date in dates:
        loc = archive.dates.get_loc(pd.Timestamp(date))
        i = int(loc)
        row = archive.audit.iloc[i].to_dict()
        payload[date] = {
            **{k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in row.items()},
            "day_ahead_first6": archive.day_ahead[i, :6].tolist()
            if np.isfinite(archive.day_ahead[i, :6]).all()
            else None,
            "actual_first6": archive.price[i, :6].tolist(),
        }
    return payload
