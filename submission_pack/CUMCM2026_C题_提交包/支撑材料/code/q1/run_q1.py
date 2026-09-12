#!/usr/bin/env python3
"""C 题 Q1：按 docs/handoff/cursor-c-q1-second-revision.md 求解并导出。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q1.config import (  # noqa: E402
    COST_REPRO_TOL,
    DEFAULT_ATTACH1,
    DEFAULT_RESULT1_TEMPLATE,
    EPS_C,
    EXPECTED_EFF_B_COST,
    EXPECTED_M1_COST,
    OFFICIAL_MODEL,
    OUTPUT_DIR,
    SIMUL_CD_TOL,
)
from q1.export_results import (  # noqa: E402
    sensitivity_row,
    write_baseline_csv,
    write_comparison_csv,
    write_figures,
    write_model_selection_md,
    write_plan_csv,
    write_result1_xlsx,
    write_sensitivity_csv,
    write_summary_csv,
    write_validation_md,
)
from q1.load_data import inspect_template, load_attachment1  # noqa: E402
from q1.optimize import (  # noqa: E402
    ModelParams,
    SolveResult,
    default_params,
    min_feasible_peak_kw,
    soc_window,
    solve_lexico,
    solve_stage,
)

N_PCC_POINTS = 5


def _require(res: SolveResult, context: str) -> None:
    if not res.passed:
        raise SystemExit(f"{context} failed: status={res.status}; {res.notes}")
    if res.max_cd > SIMUL_CD_TOL:
        raise SystemExit(
            f"{context}: max(c_t d_t)={res.max_cd:.6e} exceeds {SIMUL_CD_TOL}; stop per handoff."
        )


def no_storage_baseline(load: np.ndarray, pv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    g = np.maximum(load - pv, 0.0)
    s = np.maximum(pv - load, 0.0)
    return g, s


def main() -> None:
    attach = DEFAULT_ATTACH1
    template = DEFAULT_RESULT1_TEMPLATE
    data = load_attachment1(attach)
    labels, _blocks = inspect_template(template)
    price = data["price"].to_numpy()
    load = data["load_kwh"].to_numpy()
    pv = data["pv_kwh"].to_numpy()
    params = default_params()
    price_min = float(np.min(price))

    m1 = solve_stage("M1", price, load, pv, exclusive=False, cost_cap=None, params=params)
    _m1s, m2 = solve_lexico("M2", price, load, pv, exclusive=False, params=params)
    m3 = solve_stage("M3", price, load, pv, exclusive=True, cost_cap=None, params=params)
    _m3s, m4 = solve_lexico("M4", price, load, pv, exclusive=True, params=params)

    results = {"M1": m1, "M2": m2, "M3": m3, "M4": m4}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_comparison_csv(OUTPUT_DIR / "q1_model_comparison.csv", [m1, m2, m3, m4])
    write_model_selection_md(OUTPUT_DIR / "q1_model_selection.md", results, official=OFFICIAL_MODEL)

    _require(m1, "M1")
    _require(m3, "M3")
    if abs(m1.purchase_cost - m3.purchase_cost) > EPS_C:
        raise SystemExit(
            f"M1 vs M3 cost mismatch: {m1.purchase_cost} vs {m3.purchase_cost}"
        )
    if abs(m1.purchase_cost - EXPECTED_M1_COST) > COST_REPRO_TOL:
        raise SystemExit(
            f"M1 cost {m1.purchase_cost:.12f} differs from confirmed {EXPECTED_M1_COST} "
            f"by more than {COST_REPRO_TOL} yuan; stop."
        )
    if m1.max_s_minus_pv > 1e-8:
        raise SystemExit(f"s_t > P_t: {m1.max_s_minus_pv}")

    official = m1
    write_plan_csv(OUTPUT_DIR / "q1_plan.csv", labels, data, official)
    write_summary_csv(OUTPUT_DIR / "q1_summary.csv", official)
    write_result1_xlsx(template, OUTPUT_DIR / "result1.xlsx", official)
    write_figures(data, official)

    g_base, s_base = no_storage_baseline(load, pv)
    write_baseline_csv(OUTPUT_DIR / "q1_baseline.csv", g_base, s_base, price, official)

    sens_rows: list[dict] = []
    sens_rows.append(sensitivity_row("eff_A", m1))

    p_b = ModelParams(eta_c=0.9, eta_d=0.9)
    m_b = solve_stage("eff_B", price, load, pv, params=p_b)
    _require(m_b, "eff_B")
    if abs(m_b.purchase_cost - EXPECTED_EFF_B_COST) > 1e-3:
        raise SystemExit(
            f"eff_B cost {m_b.purchase_cost} != expected {EXPECTED_EFF_B_COST}; "
            "check that eta_c/eta_d are passed into the model."
        )
    sens_rows.append(sensitivity_row("eff_B", m_b))

    for case, nom in (("cap_minus10", 10800.0), ("cap_plus10", 13200.0)):
        e_min, e_max = soc_window(nom)
        p = ModelParams(
            e_min_kwh=e_min,
            e_max_kwh=e_max,
            e0_kwh=6000.0,
            nominal_capacity_kwh=nom,
        )
        r = solve_stage(case, price, load, pv, params=p)
        _require(r, case)
        sens_rows.append(sensitivity_row(case, r))

    for case, pkw in (("power_minus10", 4500.0), ("power_plus10", 5500.0)):
        p = ModelParams(power_limit_kw=pkw)
        r = solve_stage(case, price, load, pv, params=p)
        _require(r, case)
        sens_rows.append(sensitivity_row(case, r))

    gmax_min_kw = min_feasible_peak_kw(price, load, pv, params)
    peak_nat = m1.peak_grid_kw
    if gmax_min_kw > peak_nat + 1e-6:
        raise SystemExit(f"min peak {gmax_min_kw} kW exceeds unconstrained M1 peak {peak_nat}")
    grid_kw_grid = np.linspace(gmax_min_kw, peak_nat, N_PCC_POINTS)
    for i, gkw in enumerate(grid_kw_grid):
        p = ModelParams(grid_limit_kw=float(gkw))
        r = solve_stage(f"pcc_{i}", price, load, pv, params=p)
        _require(r, f"pcc_{i}")
        sens_rows.append(sensitivity_row(f"pcc_gmax_{gkw:.4f}kw", r))

    write_sensitivity_csv(OUTPUT_DIR / "q1_sensitivity.csv", sens_rows)
    write_validation_md(
        OUTPUT_DIR / "q1_validation.md",
        data,
        labels,
        official,
        attach,
        template,
        price_min=price_min,
        gmax_min_kw=gmax_min_kw,
    )

    print(f"Q1 official = {OFFICIAL_MODEL}")
    print(f"  cost={official.purchase_cost:.6f} yuan")
    print(f"  G={official.grid_purchase:.6f} kWh")
    print(f"  peak={official.peak_grid_kw:.6f} kW")
    print(f"  S={official.curtailment:.6f} kWh")
    print(f"  Q={official.throughput:.6f} kWh")
    print(f"  max(c d)={official.max_cd:.3e}")
    print(f"  residual={official.max_balance_residual:.3e}")
    print(f"  price_min={price_min:.6g}")
    print(f"  Gmax_min(analysis)={gmax_min_kw:.6f} kW")
    print("wrote output/q1_*.csv, output/q1_*.md, output/result1.xlsx, fig/fig1_*.png")


if __name__ == "__main__":
    main()
