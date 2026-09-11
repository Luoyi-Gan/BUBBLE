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
LOAD_INFORMATION_MAIN = "causal_load_main"
LOAD_INFORMATION_PROXY = "actual_load_proxy"
LOAD_INFORMATION_CASES = (LOAD_INFORMATION_MAIN, LOAD_INFORMATION_PROXY)
LOAD_TREATMENT = LOAD_INFORMATION_MAIN
WARMUP_CSV_MAIN = "q3_warmup_daily_causal_load_main.csv"
LOAD_HISTORY_SAME_WEEKDAY = 4
NEXT_DAY_PV_HISTORY_DAYS = 7
NEXT_DAY_VALUE_GAP_TOL_YUAN = 1.0
NEXT_DAY_VALUE_MAX_SAMPLES = 25
MPC_COST_TOL = 1e-7
NUMERIC_TOL = 1e-6
SIMULTANEOUS_CD_TOL = 1e-4
SOLVER = "HIGHS"
PILOT_DATES = ("2025-02-01", "2025-06-21")

PV_MAPPING_LINEAR = "linear_anchor_main"
PV_MAPPING_STEP = "step_hourly_sensitivity"
PV_MAPPING_MODES = (PV_MAPPING_LINEAR, PV_MAPPING_STEP)

SETTLEMENT_MAIN = "anchor_final_main"
SETTLEMENT_ALT = "adjacent_literal_sensitivity"
SETTLEMENT_MODES = (SETTLEMENT_MAIN, SETTLEMENT_ALT)

SENSITIVITY_OUTPUT_DIR = ROOT / "output" / "q3_sensitivity"
SENSITIVITY_FIG_DIR = ROOT / "fig" / "q3_sensitivity"

YEAR_N_DAYS = 365
YEAR_END_SOC_A_KWH = 1200.0
YEAR_END_SOC_B_KWH = 6000.0
YEAR_END_BOUNDARY_A = "A_q2_aligned"
YEAR_END_BOUNDARY_B = "B_energy_neutral"
YEAR_END_BOUNDARIES = (
    (YEAR_END_BOUNDARY_A, YEAR_END_SOC_A_KWH),
    (YEAR_END_BOUNDARY_B, YEAR_END_SOC_B_KWH),
)
TERMINAL_SOC_PILOT_START = "2025-12-01"
TERMINAL_SOC_PILOT_END = "2025-12-31"
TERMINAL_SOC_OUTPUT_DIR = ROOT / "output" / "q3_terminal_soc_pilot"
TERMINAL_SOC_FIG_DIR = ROOT / "fig" / "q3_terminal_soc_pilot"


def year_end_tag(year_end_soc_kwh: float | None) -> str:
    if year_end_soc_kwh is None:
        return ""
    return f"ye{int(round(float(year_end_soc_kwh)))}"


def year_end_boundary_label(year_end_soc_kwh: float | None) -> str | None:
    if year_end_soc_kwh is None:
        return None
    value = float(year_end_soc_kwh)
    if abs(value - YEAR_END_SOC_A_KWH) <= 1e-9:
        return YEAR_END_BOUNDARY_A
    if abs(value - YEAR_END_SOC_B_KWH) <= 1e-9:
        return YEAR_END_BOUNDARY_B
    return f"custom_{value:.0f}"


def today_year_end_soc(
    day_index: int, n_days: int, year_end_soc_kwh: float | None
) -> float | None:
    """Hard E_144 target for remaining-horizon LPs on the calendar year's last day."""
    if year_end_soc_kwh is None:
        return None
    if int(day_index) == int(n_days) - 1:
        return float(year_end_soc_kwh)
    return None


def next_day_year_end_soc(
    day_index: int, n_days: int, year_end_soc_kwh: float | None
) -> float | None:
    """Hard E_144 target for the virtual next-day LP on Dec 30 (48h cost-to-go)."""
    if year_end_soc_kwh is None:
        return None
    if int(day_index) == int(n_days) - 2:
        return float(year_end_soc_kwh)
    return None


def make_run_id(
    date: str,
    strategy: str,
    load_information_case: str,
    pv_mapping_mode: str,
    settlement_mode: str,
    with_terminal_value: bool,
    year_end_soc_kwh: float | None = None,
) -> str:
    tv = "48h" if with_terminal_value else "no48h"
    run_id = (
        f"{date}__{strategy}__{load_information_case}__"
        f"{pv_mapping_mode}__{settlement_mode}__{tv}"
    )
    tag = year_end_tag(year_end_soc_kwh)
    if tag:
        run_id += f"__{tag}"
    return run_id


def dispatch_stem(
    date: str,
    strategy: str,
    load_information_case: str,
    pv_mapping_mode: str,
    settlement_mode: str,
    with_terminal_value: bool,
    year_end_soc_kwh: float | None = None,
) -> str:
    suffix = f"{strategy}_{load_information_case}_{pv_mapping_mode}_{settlement_mode}"
    if not with_terminal_value:
        suffix += "_no48h"
    tag = year_end_tag(year_end_soc_kwh)
    if tag:
        suffix += f"_{tag}"
    return f"q3_dispatch_{date}_{suffix}"

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
