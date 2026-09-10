"""Q1 locked constants. Do not change without a new confirmed spec."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

T = 144
DELTA_H = 1.0 / 6.0
P_MAX_KW = 5000.0
E_MAX_KWH = 10800.0
E_MIN_KWH = 1200.0
E0_KWH = 6000.0
ETA_RT = 0.90
ETA_C = ETA_RT**0.5
ETA_D = ETA_RT**0.5
C_MAX = P_MAX_KW * DELTA_H  # 833.333... kWh
D_MAX = P_MAX_KW * DELTA_H

BALANCE_TOL = 1e-6
SOC_END_TOL = 1e-6
SIMUL_CD_TOL = 1e-4
EPS_C = 1e-6

SOLVER = "HIGHS"

DEFAULT_ATTACH1 = Path(
    os.environ.get(
        "CUMCM_C_ATTACH1",
        "/Users/louis/Desktop/CUMCM2026Problems/C题/附件/附件1.xlsx",
    )
)
DEFAULT_RESULT1_TEMPLATE = Path(
    os.environ.get(
        "CUMCM_C_RESULT1_TEMPLATE",
        "/Users/louis/Desktop/CUMCM2026Problems/C题/附件/附件5/result1.xlsx",
    )
)

OUTPUT_DIR = ROOT / "output"
FIG_DIR = ROOT / "fig"

FOUR_HOUR_BLOCKS = [
    ("0:00-4:00", 0, 24),
    ("4:00-8:00", 24, 48),
    ("8:00-12:00", 48, 72),
    ("12:00-16:00", 72, 96),
    ("16:00-20:00", 96, 120),
    ("20:00-24:00", 120, 144),
]
