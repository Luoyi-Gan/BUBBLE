from __future__ import annotations

from dataclasses import dataclass
import time

import cvxpy as cp
import numpy as np

from q1.config import (
    BALANCE_TOL,
    C_MAX,
    D_MAX,
    E0_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    EPS_C,
    ETA_C,
    ETA_D,
    SIMUL_CD_TOL,
    SOLVER,
    SOC_END_TOL,
    T,
)


@dataclass
class SolveResult:
    name: str
    exclusive: bool
    lexico: bool
    status: str
    g: np.ndarray
    c: np.ndarray
    d: np.ndarray
    s: np.ndarray
    E: np.ndarray  # length T+1, E[0]..E[T]
    purchase_cost: float
    grid_purchase: float
    curtailment: float
    throughput: float
    max_cd: float
    soc_min: float
    soc_max: float
    max_balance_residual: float
    solve_seconds: float
    passed: bool
    notes: str = ""


def _build_problem(price: np.ndarray, load: np.ndarray, pv: np.ndarray, exclusive: bool, cost_cap: float | None):
    g = cp.Variable(T, nonneg=True)
    c = cp.Variable(T, nonneg=True)
    d = cp.Variable(T, nonneg=True)
    s = cp.Variable(T, nonneg=True)
    E = cp.Variable(T + 1)

    cons = [
        E[0] == E0_KWH,
        E[T] == E0_KWH,
        E[1:] >= E_MIN_KWH,
        E[1:] <= E_MAX_KWH,
        c <= C_MAX,
        d <= D_MAX,
        g + pv + d == load + c + s,
        E[1:] == E[:-1] + ETA_C * c - d / ETA_D,
    ]
    z = None
    if exclusive:
        z = cp.Variable(T, boolean=True)
        cons += [c <= C_MAX * z, d <= D_MAX * (1 - z)]
    if cost_cap is not None:
        cons.append(price @ g <= cost_cap)
        objective = cp.Minimize(cp.sum(c + d))
    else:
        objective = cp.Minimize(price @ g)
    return cp.Problem(objective, cons), g, c, d, s, E, z


def _metrics(price, load, pv, g, c, d, s, E) -> dict:
    balance = g + pv + d - load - c - s
    return {
        "purchase_cost": float(price @ g),
        "grid_purchase": float(np.sum(g)),
        "curtailment": float(np.sum(s)),
        "throughput": float(np.sum(c + d)),
        "max_cd": float(np.max(c * d)),
        "soc_min": float(np.min(E)),
        "soc_max": float(np.max(E)),
        "max_balance_residual": float(np.max(np.abs(balance))),
        "e_end_gap": float(abs(E[-1] - E0_KWH)),
        "c_over": float(np.max(c - C_MAX)),
        "d_over": float(np.max(d - D_MAX)),
    }


def _pass(m: dict) -> tuple[bool, str]:
    reasons = []
    if m["max_balance_residual"] >= BALANCE_TOL:
        reasons.append(f"balance {m['max_balance_residual']}")
    if m["e_end_gap"] >= SOC_END_TOL:
        reasons.append(f"E144 {m['e_end_gap']}")
    if m["soc_min"] < E_MIN_KWH - SOC_END_TOL:
        reasons.append(f"soc_min {m['soc_min']}")
    if m["soc_max"] > E_MAX_KWH + SOC_END_TOL:
        reasons.append(f"soc_max {m['soc_max']}")
    if m["c_over"] > BALANCE_TOL or m["d_over"] > BALANCE_TOL:
        reasons.append("power limit")
    if m["max_cd"] > SIMUL_CD_TOL:
        reasons.append(f"max c*d {m['max_cd']}")
    return (len(reasons) == 0, "; ".join(reasons))


def solve_stage(
    name: str,
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    exclusive: bool,
    cost_cap: float | None,
) -> SolveResult:
    prob, g, c, d, s, E, _z = _build_problem(price, load, pv, exclusive, cost_cap)
    t0 = time.perf_counter()
    prob.solve(solver=SOLVER, verbose=False)
    elapsed = time.perf_counter() - t0
    if g.value is None:
        return SolveResult(
            name=name,
            exclusive=exclusive,
            lexico=cost_cap is not None,
            status=str(prob.status),
            g=np.zeros(T),
            c=np.zeros(T),
            d=np.zeros(T),
            s=np.zeros(T),
            E=np.full(T + 1, np.nan),
            purchase_cost=np.nan,
            grid_purchase=np.nan,
            curtailment=np.nan,
            throughput=np.nan,
            max_cd=np.nan,
            soc_min=np.nan,
            soc_max=np.nan,
            max_balance_residual=np.nan,
            solve_seconds=elapsed,
            passed=False,
            notes=f"solver status={prob.status}",
        )
    gv = np.asarray(g.value, dtype=float).ravel()
    cv = np.asarray(c.value, dtype=float).ravel()
    dv = np.asarray(d.value, dtype=float).ravel()
    sv = np.asarray(s.value, dtype=float).ravel()
    Ev = np.asarray(E.value, dtype=float).ravel()
    m = _metrics(price, load, pv, gv, cv, dv, sv, Ev)
    ok, why = _pass(m)
    return SolveResult(
        name=name,
        exclusive=exclusive,
        lexico=cost_cap is not None,
        status=str(prob.status),
        g=gv,
        c=cv,
        d=dv,
        s=sv,
        E=Ev,
        purchase_cost=m["purchase_cost"],
        grid_purchase=m["grid_purchase"],
        curtailment=m["curtailment"],
        throughput=m["throughput"],
        max_cd=m["max_cd"],
        soc_min=m["soc_min"],
        soc_max=m["soc_max"],
        max_balance_residual=m["max_balance_residual"],
        solve_seconds=elapsed,
        passed=ok,
        notes=why,
    )


def solve_lexico(name: str, price, load, pv, exclusive: bool) -> tuple[SolveResult, SolveResult]:
    stage1_name = name + "_stage1"
    s1 = solve_stage(stage1_name, price, load, pv, exclusive, None)
    if not np.isfinite(s1.purchase_cost):
        return s1, s1
    cap = s1.purchase_cost + EPS_C
    s2 = solve_stage(name, price, load, pv, exclusive, cap)
    s2.notes = (s2.notes + f"; C*={s1.purchase_cost:.12g}; eps_C={EPS_C}").strip("; ")
    if s2.purchase_cost > s1.purchase_cost + EPS_C + 1e-8:
        s2.passed = False
        s2.notes += "; lexico cost exceeded C*+eps"
    return s1, s2
