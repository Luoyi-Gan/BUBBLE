#!/usr/bin/env python3
"""C 题 Q1：按 docs/handoff/cursor-c-q1-implementation.md 求解并导出。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from q1.config import (  # noqa: E402
    DEFAULT_ATTACH1,
    DEFAULT_RESULT1_TEMPLATE,
    EPS_C,
    OUTPUT_DIR,
    SIMUL_CD_TOL,
)
from q1.export_results import (  # noqa: E402
    write_comparison_csv,
    write_figures,
    write_model_selection_md,
    write_plan_csv,
    write_result1_xlsx,
    write_summary_csv,
    write_validation_md,
)
from q1.load_data import load_attachment1, load_template_labels  # noqa: E402
from q1.optimize import SolveResult, solve_lexico, solve_stage  # noqa: E402


def _require(res: SolveResult, context: str) -> None:
    if not res.passed:
        raise SystemExit(f"{context} failed: status={res.status}; {res.notes}")
    if res.max_cd > SIMUL_CD_TOL:
        raise SystemExit(
            f"{context}: max(c_t d_t)={res.max_cd:.6e} exceeds {SIMUL_CD_TOL}; stop per handoff."
        )


def main() -> None:
    attach = DEFAULT_ATTACH1
    template = DEFAULT_RESULT1_TEMPLATE
    data = load_attachment1(attach)
    labels = load_template_labels(template)
    price = data["price"].to_numpy()
    load = data["load_kwh"].to_numpy()
    pv = data["pv_kwh"].to_numpy()

    m1 = solve_stage("M1", price, load, pv, exclusive=False, cost_cap=None)
    _m1s, m2 = solve_lexico("M2", price, load, pv, exclusive=False)
    m3 = solve_stage("M3", price, load, pv, exclusive=True, cost_cap=None)
    _m3s, m4 = solve_lexico("M4", price, load, pv, exclusive=True)

    results = {"M1": m1, "M2": m2, "M3": m3, "M4": m4}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_comparison_csv(OUTPUT_DIR / "q1_model_comparison.csv", [m1, m2, m3, m4])
    write_model_selection_md(OUTPUT_DIR / "q1_model_selection.md", results, official="M2")

    _require(m1, "M1")
    _require(m2, "M2")
    if m2.purchase_cost > m1.purchase_cost + EPS_C + 1e-8:
        raise SystemExit("M2 cost exceeded M1 C* + eps_C")

    official = m2
    write_plan_csv(OUTPUT_DIR / "q1_plan.csv", labels, data, official)
    write_summary_csv(OUTPUT_DIR / "q1_summary.csv", official)
    write_validation_md(
        OUTPUT_DIR / "q1_validation.md",
        data,
        labels,
        official,
        attach,
        template,
    )
    write_result1_xlsx(template, OUTPUT_DIR / "result1.xlsx", official)
    write_figures(data, official)

    print("Q1 official = M2")
    print(f"  cost={official.purchase_cost:.6f} yuan")
    print(f"  G={official.grid_purchase:.6f} kWh")
    print(f"  S={official.curtailment:.6f} kWh")
    print(f"  Q={official.throughput:.6f} kWh")
    print(f"  max(c d)={official.max_cd:.3e}")
    print(f"  residual={official.max_balance_residual:.3e}")
    print("wrote output/q1_*.csv, output/q1_*.md, output/result1.xlsx, fig/fig1_*.png")


if __name__ == "__main__":
    main()
