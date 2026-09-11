"""Central configuration for the Q3 two-day rolling-adjustment pilot."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def resolve_attach_dir() -> Path:
    candidates = []
    env = os.environ.get("CUMCM_C_ATTACH_DIR")
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            Path("/Users/louis/Desktop/CUMCM2026Problems/C题/附件"),
            ROOT / "data" / "raw",
            ROOT / "data" / "raw" / "附件",
        ]
    )
    for path in candidates:
        if (path / "附件1.xlsx").exists() and (path / "附件3.xlsx").exists():
            return path
    return candidates[0]


ATTACH_DIR = resolve_attach_dir()
ATTACH1 = ATTACH_DIR / "附件1.xlsx"
ATTACH2 = ATTACH_DIR / "附件2.xlsx"
ATTACH3 = ATTACH_DIR / "附件3.xlsx"
OUTPUT_DIR = ROOT / "output" / "q3_pilot"
FIG_DIR = ROOT / "fig" / "q3_pilot"

T = 144
DELTA_H = 1.0 / 6.0
ETA_C = float(np.sqrt(0.9))
ETA_D = float(np.sqrt(0.9))
E_MIN_KWH = 1200.0
E_MAX_KWH = 10800.0
E_INITIAL_KWH = 6000.0
POWER_LIMIT_KW = 5000.0
POWER_LIMIT_KWH = POWER_LIMIT_KW * DELTA_H

EMERGENCY_PRICE_MULTIPLIER = 5.0
ADJUST_ABS_COEFF = 0.5
VOI_EPS_YUAN = 0.01
LOAD_TREATMENT = "deterministic_actual_proxy"
LOAD_HISTORY_SAME_WEEKDAY = 4
NEXT_DAY_PV_HISTORY_DAYS = 7
NEXT_DAY_VALUE_GAP_TOL_YUAN = 1.0
NEXT_DAY_VALUE_MAX_SAMPLES = 25
MPC_COST_TOL = 1e-7
NUMERIC_TOL = 1e-6
SIMULTANEOUS_CD_TOL = 1e-4
SOLVER = "HIGHS"
PILOT_DATES = ("2025-02-01", "2025-06-21")

# Update clock hours and the first 10-minute index that may change.
# Index t corresponds to the period ending at (t+1)*10 minutes after 0:00.
UPDATE_SPECS = (
    (0, 0),    # 0:00 plan; first mutable period is 00:10 (index 0)
    (6, 36),   # 6:00 update; first mutable period is 06:10
    (12, 72),  # 12:00 update; first mutable period is 12:10
    (18, 108),  # 18:00 update; first mutable period is 18:10
)
UPDATE_HOURS = tuple(hour for hour, _index in UPDATE_SPECS)
HOUR_TO_FIRST_MUTABLE = {hour: index for hour, index in UPDATE_SPECS}

STRATEGIES = ("M0", "M1_M6", "M6_only", "M12_only", "M18_only")
STRATEGY_ALLOWED_UPDATES = {
    "M0": (),
    "M1_M6": (6, 12, 18),
    "M6_only": (6,),
    "M12_only": (12,),
    "M18_only": (18,),
}
