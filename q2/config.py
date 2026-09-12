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
FULL_K8_RISK_OUTPUT_DIR = ROOT / "output" / "q2_full_k8_risk"
POLICY_CONSISTENT_OUTPUT_DIR = ROOT / "output" / "q2_policy_consistent"
FIG_DIR = ROOT / "fig" / "q2_pilot"
FIG_POLICY_CONSISTENT_DIR = ROOT / "fig" / "q2_policy_consistent"
FIG_Q2_FINAL_DIR = ROOT / "fig" / "q2_final"
SIGNED_OFF_RESULT2 = ROOT / "output" / "result2.xlsx"
SIGNED_OFF_RESULT2_SHA256 = (
    "70a9785c9e2bba66f7694878e4587ad15c57dc090ec6798d07ba6780b4780ef7"
)
RESULT2_TEMPLATE = ATTACH_DIR / "附件5" / "result2.xlsx"
CANDIDATE_RESULT2 = POLICY_CONSISTENT_OUTPUT_DIR / "result2.xlsx"
RESULT2_SIGNED_OFF_BACKUP = POLICY_CONSISTENT_OUTPUT_DIR / "result2_signed_off_backup.xlsx"

T = 144
DELTA_H = 1.0 / 6.0
ETA_C = float(np.sqrt(0.9))
ETA_D = float(np.sqrt(0.9))
E_MIN_KWH = 1200.0
E_MAX_KWH = 10800.0
E_INITIAL_KWH = 6000.0
POWER_LIMIT_KW = 5000.0
POWER_LIMIT_KWH = POWER_LIMIT_KW * DELTA_H

# Signed-off contract semantics; keep all production Q2 assumptions here.
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
FIXED_SCENARIO_K = 8
K_SENSITIVITY_CANDIDATES = (4, 8, 12)
RISK_ALPHA_CANDIDATES = (0.60, 0.70, 0.80, 0.90)
OFFICIAL_OUTPUT_START = "2025-02-01"
RISK_CALIBRATION_DAYS = 14
MPC_COST_TOL = 1e-7
NEXT_DAY_VALUE_GAP_TOL_YUAN = 1.0
NEXT_DAY_VALUE_MAX_SAMPLES = 25
NUMERIC_TOL = 1e-6
SIMULTANEOUS_CD_TOL = 1e-4
SOLVER = "HIGHS"
PILOT_DATES = ("2025-02-01", "2025-06-21")
