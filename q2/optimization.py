from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import cvxpy as cp
import numpy as np

from q2.config import (
    CONTRACT_TAKE_MODE,
    EMERGENCY_PRICE_MULTIPLIER,
    E_MAX_KWH,
    E_MIN_KWH,
    ETA_C,
    ETA_D,
    MPC_COST_TOL,
    NORMAL_COST_BASIS,
    POWER_LIMIT_KWH,
    SOLVER,
)


@dataclass(frozen=True)
class DispatchResult:
    x: np.ndarray
    emergency: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    curtailment: np.ndarray
    soc: np.ndarray
    emergency_cost: float
    solve_seconds: float
    status: str

    @property
    def max_cd(self) -> float:
        return float(np.max(self.charge * self.discharge))


@dataclass(frozen=True)
class PlanResult:
    q: np.ndarray
    planned_cost: float
    expected_emergency_cost: float
    solve_seconds: float
    status: str


def _contract_constraints(x: cp.Variable, q: cp.Variable | np.ndarray) -> list[cp.Constraint]:
    if CONTRACT_TAKE_MODE != "x_le_q":
        raise NotImplementedError(f"Unsupported pilot contract mode: {CONTRACT_TAKE_MODE}")
    return [x <= q]


def _planned_normal_cost(price: np.ndarray, q: cp.Expression) -> cp.Expression:
    if NORMAL_COST_BASIS != "planned_q":
        raise NotImplementedError(f"Unsupported normal-cost basis: {NORMAL_COST_BASIS}")
    return price @ q


def _physical_constraints(
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    normal: cp.Variable,
    emergency: cp.Variable,
    charge: cp.Variable,
    discharge: cp.Variable,
    curtailment: cp.Variable,
    soc: cp.Variable,
) -> list[cp.Constraint]:
    n = len(load)
    return [
        soc[0] == initial_soc,
        soc[1:] == soc[:-1] + ETA_C * charge - discharge / ETA_D,
        soc[1:] >= E_MIN_KWH,
        soc[1:] <= E_MAX_KWH,
        charge <= POWER_LIMIT_KWH,
        discharge <= POWER_LIMIT_KWH,
        curtailment <= pv,
        normal + emergency + pv - curtailment + discharge == load + charge,
    ]


def solve_perfect_information_day(
    price: np.ndarray, load: np.ndarray, pv: np.ndarray, initial_soc: float
) -> DispatchResult:
    n = len(load)
    g, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
    E = cp.Variable(n + 1)
    constraints = _physical_constraints(load, pv, initial_soc, g, e, c, d, w, E)
    objective = cp.Minimize(price @ g + EMERGENCY_PRICE_MULTIPLIER * price @ e)
    problem = cp.Problem(objective, constraints)
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    elapsed = perf_counter() - started
    if g.value is None:
        raise RuntimeError(f"perfect-information LP failed: {problem.status}")
    return DispatchResult(
        x=np.asarray(g.value).ravel(),
        emergency=np.asarray(e.value).ravel(),
        charge=np.asarray(c.value).ravel(),
        discharge=np.asarray(d.value).ravel(),
        curtailment=np.asarray(w.value).ravel(),
        soc=np.asarray(E.value).ravel(),
        emergency_cost=float(EMERGENCY_PRICE_MULTIPLIER * price @ e.value),
        solve_seconds=elapsed,
        status=str(problem.status),
    )


def solve_stochastic_plan(
    price: np.ndarray,
    scenario_load: np.ndarray,
    scenario_pv: np.ndarray,
    probabilities: np.ndarray,
    initial_soc: float,
) -> PlanResult:
    k, n = scenario_load.shape
    q = cp.Variable(n, nonneg=True)
    expected_emergency = 0
    constraints: list[cp.Constraint] = []
    for omega in range(k):
        x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
        E = cp.Variable(n + 1)
        constraints += _contract_constraints(x, q)
        constraints += _physical_constraints(
            scenario_load[omega],
            scenario_pv[omega],
            initial_soc,
            x,
            e,
            c,
            d,
            w,
            E,
        )
        expected_emergency += (
            probabilities[omega] * EMERGENCY_PRICE_MULTIPLIER * price @ e
        )
    planned_cost = _planned_normal_cost(price, q)
    problem = cp.Problem(cp.Minimize(planned_cost + expected_emergency), constraints)
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    elapsed = perf_counter() - started
    if q.value is None:
        raise RuntimeError(f"stochastic plan LP failed: {problem.status}")
    qv = np.asarray(q.value).ravel()
    return PlanResult(
        q=qv,
        planned_cost=float(price @ qv),
        expected_emergency_cost=float(problem.value - price @ qv),
        solve_seconds=elapsed,
        status=str(problem.status),
    )


def solve_fixed_plan_dispatch(
    price: np.ndarray,
    q: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    throughput_tiebreak: bool = True,
) -> DispatchResult:
    n = len(load)
    x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
    E = cp.Variable(n + 1)
    constraints = _contract_constraints(x, q)
    constraints += _physical_constraints(load, pv, initial_soc, x, e, c, d, w, E)
    emergency_cost = EMERGENCY_PRICE_MULTIPLIER * price @ e
    first = cp.Problem(cp.Minimize(emergency_cost), constraints)
    started = perf_counter()
    first.solve(solver=SOLVER, verbose=False)
    if e.value is None:
        raise RuntimeError(f"fixed-plan execution LP failed: {first.status}")
    emergency_opt = float(emergency_cost.value)
    status = str(first.status)
    if throughput_tiebreak:
        second = cp.Problem(
            cp.Minimize(cp.sum(c + d)),
            constraints + [emergency_cost <= emergency_opt + MPC_COST_TOL],
        )
        second.solve(solver=SOLVER, verbose=False)
        if x.value is None:
            raise RuntimeError(f"fixed-plan tiebreak LP failed: {second.status}")
        status = str(second.status)
    elapsed = perf_counter() - started
    return DispatchResult(
        x=np.asarray(x.value).ravel(),
        emergency=np.asarray(e.value).ravel(),
        charge=np.asarray(c.value).ravel(),
        discharge=np.asarray(d.value).ravel(),
        curtailment=np.asarray(w.value).ravel(),
        soc=np.asarray(E.value).ravel(),
        emergency_cost=float(EMERGENCY_PRICE_MULTIPLIER * price @ e.value),
        solve_seconds=elapsed,
        status=status,
    )


def dispatch_balance_residual(
    load: np.ndarray, pv: np.ndarray, result: DispatchResult
) -> np.ndarray:
    return (
        result.x
        + result.emergency
        + pv
        - result.curtailment
        + result.discharge
        - load
        - result.charge
    )

