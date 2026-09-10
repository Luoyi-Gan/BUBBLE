"""Central configuration for the Q2 pilot only."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ATTACH_DIR = Path(
    os.environ.get("CUMCM_C_ATTACH_DIR", "/Users/louis/Desktop/CUMCM2026Problems/C题/附件")
)
ATTACH1 = ATTACH_DIR / "附件1.xlsx"
ATTACH2 = ATTACH_DIR / "附件2.xlsx"
OUTPUT_DIR = ROOT / "output" / "q2_pilot"
FULL_OUTPUT_DIR = ROOT / "output" / "q2_full_linked"
FIG_DIR = ROOT / "fig" / "q2_pilot"

T = 144
DELTA_H = 1.0 / 6.0
ETA_C = float(np.sqrt(0.9))
ETA_D = float(np.sqrt(0.9))
E_MIN_KWH = 1200.0
E_MAX_KWH = 10800.0
E_INITIAL_KWH = 6000.0
POWER_LIMIT_KW = 5000.0
POWER_LIMIT_KWH = POWER_LIMIT_KW * DELTA_H

# Pending captain sign-off; keep all contract semantics here.
CONTRACT_TAKE_MODE = "x_le_q"
NORMAL_COST_BASIS = "planned_q"
EMERGENCY_PRICE_MULTIPLIER = 5.0

LOAD_HISTORY_SAME_WEEKDAY = 4
PV_HISTORY_DAYS = 7
RESIDUAL_POOL_DAYS = 28
K_CANDIDATES = (2, 4, 6, 8, 10, 12)
K_VALIDATION_DAYS = 14
K_RECALIBRATION_DAYS = 14
# Fixed from the R1--R4 timing audit: a validation-day score must be obtained
# within this budget before its K is eligible under the one-standard-error rule.
T_MAX_SECONDS: float | None = 0.20
MPC_COST_TOL = 1e-7
NEXT_DAY_VALUE_GAP_TOL_YUAN = 1.0
NEXT_DAY_VALUE_MAX_SAMPLES = 25
NUMERIC_TOL = 1e-6
SIMULTANEOUS_CD_TOL = 1e-4
SOLVER = "HIGHS"
PILOT_DATES = ("2025-02-01", "2025-06-21")
