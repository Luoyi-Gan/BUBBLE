from __future__ import annotations

from dataclasses import dataclass
import time

import cvxpy as cp
import numpy as np

from q1.config import (
    BALANCE_TOL,
    DELTA_H,
    E0_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    EPS_C,
    ETA_C,
    ETA_D,
    NOMINAL_CAPACITY_KWH,
    P_MAX_KW,
    S_BOUND_TOL,
    SIMUL_CD_TOL,
    SOC_END_TOL,
    SOLVER,
    T,
)


@dataclass
class ModelParams:
    eta_c: float = ETA_C
    eta_d: float = ETA_D
    e_min_kwh: float = E_MIN_KWH
    e_max_kwh: float = E_MAX_KWH
    e0_kwh: float = E0_KWH
    power_limit_kw: float = P_MAX_KW
    grid_limit_kw: float | None = None
    nominal_capacity_kwh: float = NOMINAL_CAPACITY_KWH

    @property
    def c_max_kwh(self) -> float:
        return self.power_limit_kw * DELTA_H

    @property
    def d_max_kwh(self) -> float:
        return self.power_limit_kw * DELTA_H

    @property
    def g_max_kwh(self) -> float | None:
        if self.grid_limit_kw is None:
            return None
        return self.grid_limit_kw * DELTA_H


def default_params() -> ModelParams:
    return ModelParams()


def soc_window(nominal_capacity_kwh: float) -> tuple[float, float]:
    return 0.10 * nominal_capacity_kwh, 0.90 * nominal_capacity_kwh


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
    E: np.ndarray
    purchase_cost: float
    grid_purchase: float
    curtailment: float
    throughput: float
    max_cd: float
    soc_min: float
    soc_max: float
    max_balance_residual: float
    peak_grid_kw: float
    max_s_minus_pv: float
    solve_seconds: float
    passed: bool
    params: ModelParams
    notes: str = ""


def _build_problem(
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    exclusive: bool,
    cost_cap: float | None,
    params: ModelParams,
    peak_var: bool,
):
    g = cp.Variable(T, nonneg=True)
    c = cp.Variable(T, nonneg=True)
    d = cp.Variable(T, nonneg=True)
    s = cp.Variable(T, nonneg=True)
    E = cp.Variable(T + 1)
    c_max = params.c_max_kwh
    d_max = params.d_max_kwh
    cons = [
        E[0] == params.e0_kwh,
        E[T] == params.e0_kwh,
        E[1:] >= params.e_min_kwh,
        E[1:] <= params.e_max_kwh,
        c <= c_max,
        d <= d_max,
        s <= pv,
        g + pv + d == load + c + s,
        E[1:] == E[:-1] + params.eta_c * c - d / params.eta_d,
    ]
    if params.g_max_kwh is not None:
        cons.append(g <= params.g_max_kwh)
    z = None
    if exclusive:
        z = cp.Variable(T, boolean=True)
        cons += [c <= c_max * z, d <= d_max * (1 - z)]
    peak = None
    if peak_var:
        peak = cp.Variable(nonneg=True)
        cons.append(g <= peak)
        objective = cp.Minimize(peak)
    elif cost_cap is not None:
        cons.append(price @ g <= cost_cap)
        objective = cp.Minimize(cp.sum(c + d))
    else:
        objective = cp.Minimize(price @ g)
    return cp.Problem(objective, cons), g, c, d, s, E, z, peak


def _metrics(price, load, pv, g, c, d, s, E, params: ModelParams) -> dict:
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
        "e_end_gap": float(abs(E[-1] - params.e0_kwh)),
        "c_over": float(np.max(c - params.c_max_kwh)),
        "d_over": float(np.max(d - params.d_max_kwh)),
        "peak_grid_kw": float(np.max(g) / DELTA_H),
        "max_s_minus_pv": float(np.max(s - pv)),
        "g_over": float(np.max(g - (params.g_max_kwh if params.g_max_kwh is not None else np.inf))),
    }


def _pass(m: dict, params: ModelParams) -> tuple[bool, str]:
    reasons = []
    if m["max_balance_residual"] >= BALANCE_TOL:
        reasons.append(f"balance {m['max_balance_residual']}")
    if m["e_end_gap"] >= SOC_END_TOL:
        reasons.append(f"E144 {m['e_end_gap']}")
    if m["soc_min"] < params.e_min_kwh - SOC_END_TOL:
        reasons.append(f"soc_min {m['soc_min']}")
    if m["soc_max"] > params.e_max_kwh + SOC_END_TOL:
        reasons.append(f"soc_max {m['soc_max']}")
    if m["c_over"] > BALANCE_TOL or m["d_over"] > BALANCE_TOL:
        reasons.append("power limit")
    if m["max_cd"] > SIMUL_CD_TOL:
        reasons.append(f"max c*d {m['max_cd']}")
    if m["max_s_minus_pv"] > S_BOUND_TOL:
        reasons.append(f"s>P {m['max_s_minus_pv']}")
    if m["g_over"] > BALANCE_TOL:
        reasons.append("grid limit")
    return (len(reasons) == 0, "; ".join(reasons))


def solve_stage(
    name: str,
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    exclusive: bool = False,
    cost_cap: float | None = None,
    params: ModelParams | None = None,
) -> SolveResult:
    params = params or default_params()
    prob, g, c, d, s, E, _z, _peak = _build_problem(
        price, load, pv, exclusive, cost_cap, params, peak_var=False
    )
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
            peak_grid_kw=np.nan,
            max_s_minus_pv=np.nan,
            solve_seconds=elapsed,
            passed=False,
            params=params,
            notes=f"solver status={prob.status}",
        )
    gv = np.asarray(g.value, dtype=float).ravel()
    cv = np.asarray(c.value, dtype=float).ravel()
    dv = np.asarray(d.value, dtype=float).ravel()
    sv = np.asarray(s.value, dtype=float).ravel()
    Ev = np.asarray(E.value, dtype=float).ravel()
    m = _metrics(price, load, pv, gv, cv, dv, sv, Ev, params)
    ok, why = _pass(m, params)
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
        peak_grid_kw=m["peak_grid_kw"],
        max_s_minus_pv=m["max_s_minus_pv"],
        solve_seconds=elapsed,
        passed=ok,
        params=params,
        notes=why,
    )


def solve_lexico(
    name: str,
    price,
    load,
    pv,
    exclusive: bool,
    params: ModelParams | None = None,
) -> tuple[SolveResult, SolveResult]:
    params = params or default_params()
    s1 = solve_stage(name + "_stage1", price, load, pv, exclusive, None, params)
    if not np.isfinite(s1.purchase_cost):
        return s1, s1
    cap = s1.purchase_cost + EPS_C
    s2 = solve_stage(name, price, load, pv, exclusive, cap, params)
    s2.notes = (s2.notes + f"; C*={s1.purchase_cost:.12g}; eps_C={EPS_C}").strip("; ")
    if s2.purchase_cost > s1.purchase_cost + EPS_C + 1e-8:
        s2.passed = False
        s2.notes += "; lexico cost exceeded C*+eps"
    return s1, s2


def min_feasible_peak_kw(price, load, pv, params: ModelParams | None = None) -> float:
    params = params or default_params()
    prob, g, _c, _d, _s, _E, _z, peak = _build_problem(
        price, load, pv, exclusive=False, cost_cap=None, params=params, peak_var=True
    )
    prob.solve(solver=SOLVER, verbose=False)
    if peak is None or peak.value is None:
        raise RuntimeError(f"min peak LP failed: {prob.status}")
    return float(peak.value) / DELTA_H
