"""Q4 causal price-forecast configuration. No storage dispatch in this module."""

from __future__ import annotations

from q3.config import ATTACH4, PILOT_DATES, ROOT, T

OUTPUT_DIR = ROOT / "output" / "q4"
AUDIT_CSV = OUTPUT_DIR / "q4_price_forecast_audit.csv"
TWODAY_JSON = OUTPUT_DIR / "q4_price_forecast_twoday.json"
CAUSALITY_JSON = OUTPUT_DIR / "q4_price_forecast_causality.json"

CANDIDATE_MODELS = (1, 2, 4)
CANDIDATE_NAMES = {
    1: "prev_day",
    2: "weekday2",
    4: "weekday4",
}

# Number of ended 10-minute periods at the named clock time.
# 06:00 has seen periods 0..35 (ending 06:00); remaining starts at 06:10 (index 36).
INTRA_HOUR_TAU = {
    6: 36,
    12: 72,
    18: 108,
}

VAR_EPS = 1e-18
