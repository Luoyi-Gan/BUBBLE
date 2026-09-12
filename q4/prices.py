"""Causal helpers that call the accepted price module without rewriting it."""

from __future__ import annotations

import numpy as np

from q4.bundle import Q4Bundle
from q4.config import CANDIDATE_MODELS
from q4.price_forecast import intraday_price_forecast


def day_ahead_today(bundle: Q4Bundle, day_index: int) -> tuple[np.ndarray, str, int]:
    hat = bundle.price_archive.day_ahead[day_index]
    chosen = int(bundle.price_archive.chosen_model[day_index])
    if np.isfinite(hat).all() and chosen > 0:
        return hat.copy(), "price_module", chosen
    return bundle.q3.price.copy(), "attachment1_no_history", -1


def day_ahead_as_of(
    bundle: Q4Bundle, target_index: int, history_end_exclusive: int
) -> tuple[np.ndarray, str, int]:
    """Forecast target_index using only prices with index < history_end_exclusive.

    This is required for the 48-hour value of day d+1 at day d 00:00: the
    archived ``day_ahead[d+1]`` is as-of d+1 00:00 and would leak day d actuals.
    """
    if history_end_exclusive <= 0:
        return bundle.q3.price.copy(), "attachment1_no_history", -1
    weekdays = bundle.prices.dates.weekday.to_numpy()
    prices = bundle.prices.price
    hats: dict[int, np.ndarray] = {}
    if target_index >= 1 and (target_index - 1) < history_end_exclusive:
        hats[1] = prices[target_index - 1].copy()
    for model in (2, 4):
        same = np.flatnonzero(
            weekdays[:history_end_exclusive] == weekdays[target_index]
        )
        if same.size < model:
            continue
        hats[model] = prices[same[-model:]].mean(axis=0)
    if not hats:
        return bundle.q3.price.copy(), "attachment1_no_history", -1
    mae_idx = min(history_end_exclusive, target_index, bundle.n_days() - 1)
    scored = []
    for model in CANDIDATE_MODELS:
        if model not in hats:
            continue
        mae = bundle.price_archive.mae_through_prev[model][mae_idx]
        score = float("inf") if not np.isfinite(mae) else float(mae)
        scored.append((score, model))
    chosen = min(scored)[1]
    return hats[chosen], "price_module_as_of", chosen


def remaining_price_forecast(
    bundle: Q4Bundle, day_index: int, tau: int
) -> tuple[np.ndarray, bool]:
    day_ahead, _src, chosen = day_ahead_today(bundle, day_index)
    actual = bundle.prices.price[day_index]
    if chosen <= 0 or tau <= 0:
        out = day_ahead.copy()
        if tau > 0:
            out[:tau] = actual[:tau]
        return np.maximum(0.0, out), True
    hist_idx = [i for i in range(day_index) if bundle.price_archive.chosen_model[i] > 0]
    if hist_idx:
        hist_actual = bundle.prices.price[hist_idx]
        hist_da = bundle.price_archive.day_ahead[hist_idx]
    else:
        hist_actual = np.zeros((0, day_ahead.shape[0]))
        hist_da = np.zeros((0, day_ahead.shape[0]))
    return intraday_price_forecast(actual, day_ahead, hist_actual, hist_da, tau)
