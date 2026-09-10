"""Q1 default constants. Runtime models take ModelParams; do not mutate these for cases."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

T = 144
DELTA_H = 1.0 / 6.0
NOMINAL_CAPACITY_KWH = 12000.0
P_MAX_KW = 5000.0
E_MAX_KWH = 10800.0
E_MIN_KWH = 1200.0
E0_KWH = 6000.0
ETA_RT = 0.90
ETA_C = ETA_RT**0.5
ETA_D = ETA_RT**0.5

BALANCE_TOL = 1e-6
SOC_END_TOL = 1e-6
SIMUL_CD_TOL = 1e-4
EPS_C = 1e-6
S_BOUND_TOL = 1e-8

SOLVER = "HIGHS"
OFFICIAL_MODEL = "M1"
EXPECTED_M1_COST = 33801.495542
EXPECTED_EFF_B_COST = 35126.948589
COST_REPRO_TOL = 1e-5

# Table 2: pending captain sign-off. PCC AC-bus side, not battery-internal.
TABLE2_ENERGY_SIDE = "pcc_ac_bus"
TABLE2_CHARGE_VAR = "c_t"
TABLE2_DISCHARGE_VAR = "d_t"

ROW_ORDER_POLICY = "attachment_raw_order"

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

PURCHASE_SHEET = "计划购电量"
CHARGE_SHEET = "充放电量"
PURCHASE_HEADERS = ("时间段", "购电量")
CHARGE_HEADERS = ("时间段", "充电量", "放电量", "时刻", "储电量")
ALLOWED_PURCHASE_CELLS = {(r, 2) for r in range(2, 2 + T)}
ALLOWED_CHARGE_CELLS = {(r, 2) for r in range(2, 8)} | {(r, 3) for r in range(2, 8)} | {(2, 5), (3, 5)}
