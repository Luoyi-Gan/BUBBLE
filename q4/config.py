"""Q4 configuration. Price-forecast constants stay aligned with the accepted P1 module."""

from __future__ import annotations

from q3.config import ATTACH4, PILOT_DATES, ROOT, T

OUTPUT_DIR = ROOT / "output" / "q4"
AUDIT_CSV = OUTPUT_DIR / "q4_price_forecast_audit.csv"
TWODAY_JSON = OUTPUT_DIR / "q4_price_forecast_twoday.json"
CAUSALITY_JSON = OUTPUT_DIR / "q4_price_forecast_causality.json"

Q4_2_DISPATCH_DIR = OUTPUT_DIR / "q4_2_dispatch_daily"
Q4_3_DISPATCH_DIR = OUTPUT_DIR / "q4_3_dispatch_daily"
RESULT4_2_XLSX = ROOT / "output" / "result4-2.xlsx"
RESULT4_3_XLSX = ROOT / "output" / "result4-3.xlsx"

RESIDUAL_POOL_DAYS = 28
FIXED_SCENARIO_K = 8
K_REVIEW_CANDIDATES = (4, 8, 12)
K_REVIEW_REFERENCE_ALPHA = 0.60
K_REVIEW_COST_TOLERANCE = 0.01
RISK_ALPHA_CANDIDATES = (0.60, 0.70, 0.80, 0.90)
RISK_CALIBRATION_DAYS = 14
RISK_WARMUP_DAYS = 28
ALPHA_POLICY_LOOP = "day_ahead_joint_q+locked_q+causal_mpc+next_day_value_cuts"
PAM_SEED = 0
PRICE_MONTHLY_CSV = OUTPUT_DIR / "q4_price_forecast_monthly.csv"
PRICE_MONTHLY_JSON = OUTPUT_DIR / "q4_price_forecast_monthly.json"
LOAD_INFORMATION_CASE = "causal_load_main"
Q4_2_YEAR_END_RULE = "q2_accepted_no_hard_terminal"
Q4_3_YEAR_END_BOUNDARY = "A_q2_aligned"
Q4_3_YEAR_END_SOC_KWH = 1200.0
Q4_3_STRATEGY = "M1_M6"
SETTLEMENT_RULE = "delivery_time_actual_price"
Q4_3_ORACLE_DISPATCH_DIR = OUTPUT_DIR / "q4_3_oracle_dispatch_daily"
Q4_3_SETTLEMENT_SENSITIVITY_CSV = OUTPUT_DIR / "q4_3_settlement_sensitivity.csv"
Q4_3_SETTLEMENT_SENSITIVITY_JSON = OUTPUT_DIR / "q4_3_settlement_sensitivity.json"
Q4_3_ORACLE_DAILY_CSV = OUTPUT_DIR / "q4_3_oracle_warmup_daily.csv"
Q4_3_SENSITIVITY_SUMMARY_JSON = OUTPUT_DIR / "q4_3_sensitivity_summary.json"

FIG_DIR = ROOT / "fig" / "q4_final"
Q4_2_DAILY_CSV = OUTPUT_DIR / "q4_2_warmup_daily.csv"
Q4_3_DAILY_CSV = OUTPUT_DIR / "q4_3_warmup_daily.csv"
Q4_2_ALPHA_SELECTION_CSV = OUTPUT_DIR / "q4_2_alpha_selection.csv"
Q4_2_SCENARIO_AUDIT_CSV = OUTPUT_DIR / "q4_2_scenario_audit.csv"
Q2_K8_DAILY_CSV = ROOT / "output/q2_full_k8_risk/daily_summary.csv"
Q3_ANNUAL_DAILY_CSV = ROOT / "output/q3_full_annual/q3_annual_daily_summary.csv"
TAIL_STATS_JSON = OUTPUT_DIR / "q4_tail_stats.json"
TAIL_STATS_CSV = OUTPUT_DIR / "q4_tail_stats.csv"
FAIR_COMPARISON_JSON = OUTPUT_DIR / "q4_fair_comparison.json"
FAIR_COMPARISON_CSV = OUTPUT_DIR / "q4_fair_comparison.csv"
PHYSICAL_YEAR_AUDIT_JSON = OUTPUT_DIR / "q4_physical_audit.json"
SCENARIO_CORR_JSON = OUTPUT_DIR / "q4_2_scenario_correlation.json"

EXPORT_START = "2025-02-01"
EXPORT_END = "2025-12-31"
EXPORT_N_DAYS = 334
YEAR_N_DAYS = 365

# Signed-off workbook / annual totals. Comparisons must not mix 1-12 with 2-12.
EXPECTED_Q4_2_ANNUAL_YUAN = 17_681_029.10
EXPECTED_Q4_2_EXPORT_YUAN = 15_257_873.75
EXPECTED_Q4_3_ANNUAL_YUAN = 17_489_808.24
EXPECTED_Q4_3_EXPORT_YUAN = 15_346_418.14
EXPECTED_Q2_K8_EXPORT_YUAN = 14_456_670.55
EXPECTED_Q3_ANNUAL_YUAN = 16_373_508.75
EXPECTED_Q4_2_ALPHA070_START = "2025-03-12"
EXPECTED_Q4_2_ALPHA070_END = "2025-03-25"

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
