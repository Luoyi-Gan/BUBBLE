"""Q4 LPs: scenario-priced day-ahead q and remaining-horizon dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import cvxpy as cp
import numpy as np

from q2.config import (
    EMERGENCY_PRICE_MULTIPLIER,
    E_MAX_KWH,
    E_MIN_KWH,
    ETA_C,
    ETA_D,
    MPC_COST_TOL,
    POWER_LIMIT_KWH,
    SOLVER,
)
from q2.optimization import ValueCut, evaluate_value_cuts


@dataclass(frozen=True)
class DispatchResult:
    x: np.ndarray
    emergency: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    curtailment: np.ndarray
    soc: np.ndarray
    emergency_cost: float
    terminal_value: float
    solve_seconds: float
    status: str

    @property
    def max_cd(self) -> float:
        return float(np.max(self.charge * self.discharge))


@dataclass(frozen=True)
class PlanResult:
    q: np.ndarray
    expected_normal_cost: float
    expected_emergency_cost: float
    expected_terminal_value: float
    initial_soc_marginal: float
    solve_seconds: float
    status: str


def _terminal_value_expression(
    terminal_soc: cp.Expression, cuts: tuple[ValueCut, ...] | None
) -> tuple[cp.Variable | None, list[cp.Constraint]]:
    if not cuts:
        return None, []
    value = cp.Variable(nonneg=True)
    constraints = [
        value >= cut_value + slope * (terminal_soc - reference_soc)
        for reference_soc, cut_value, slope in cuts
    ]
    return value, constraints


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


def solve_stochastic_plan_varying_price(
    scenario_price: np.ndarray,
    scenario_load: np.ndarray,
    scenario_pv: np.ndarray,
    probabilities: np.ndarray,
    initial_soc: float,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    q_floor: np.ndarray | None = None,
    terminal_soc: float | None = None,
) -> PlanResult:
    k, n = scenario_load.shape
    if scenario_price.shape != (k, n) or scenario_pv.shape != (k, n):
        raise ValueError("scenario price/load/PV shapes must match")
    q = cp.Variable(n, nonneg=True)
    expected_normal: cp.Expression | float = 0.0
    expected_emergency: cp.Expression | float = 0.0
    expected_terminal: cp.Expression | float = 0.0
    constraints: list[cp.Constraint] = []
    if q_floor is not None:
        floor = np.asarray(q_floor, dtype=float).ravel()
        if floor.shape != (n,) or np.any(floor < -1e-9):
            raise ValueError("q_floor must be a nonnegative vector matching the horizon")
        constraints.append(q >= floor)
    initial_constraints: list[cp.Constraint] = []
    for omega in range(k):
        x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
        E = cp.Variable(n + 1)
        constraints.append(x <= q)
        physical = _physical_constraints(
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
        constraints += physical
        initial_constraints.append(physical[0])
        if terminal_soc is not None:
            constraints.append(E[-1] == float(terminal_soc))
        terminal_value, terminal_constraints = _terminal_value_expression(
            E[-1], terminal_value_cuts
        )
        constraints += terminal_constraints
        price = np.asarray(scenario_price[omega], dtype=float).ravel()
        expected_normal += probabilities[omega] * (price @ q)
        expected_emergency += probabilities[omega] * EMERGENCY_PRICE_MULTIPLIER * (price @ e)
        if terminal_value is not None:
            expected_terminal += probabilities[omega] * terminal_value
    problem = cp.Problem(
        cp.Minimize(expected_normal + expected_emergency + expected_terminal),
        constraints,
    )
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    elapsed = perf_counter() - started
    if q.value is None:
        raise RuntimeError(f"Q4-2 stochastic plan LP failed: {problem.status}")
    qv = np.asarray(q.value).ravel()
    marginal = -float(
        sum(float(np.asarray(constraint.dual_value)) for constraint in initial_constraints)
    )
    terminal_value_result = (
        float(expected_terminal.value)
        if isinstance(expected_terminal, cp.Expression)
        else float(expected_terminal)
    )
    expected_normal_v = float(sum(probabilities[o] * (scenario_price[o] @ qv) for o in range(k)))
    return PlanResult(
        q=qv,
        expected_normal_cost=expected_normal_v,
        expected_emergency_cost=float(problem.value - expected_normal_v - terminal_value_result),
        expected_terminal_value=terminal_value_result,
        initial_soc_marginal=marginal,
        solve_seconds=elapsed,
        status=str(problem.status),
    )


def solve_fixed_q_dispatch(
    price: np.ndarray,
    q: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    throughput_tiebreak: bool = True,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    terminal_soc: float | None = None,
) -> DispatchResult:
    n = len(load)
    x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
    E = cp.Variable(n + 1)
    constraints = [x <= q]
    constraints += _physical_constraints(load, pv, initial_soc, x, e, c, d, w, E)
    if terminal_soc is not None:
        constraints.append(E[-1] == float(terminal_soc))
    emergency_cost = EMERGENCY_PRICE_MULTIPLIER * price @ e
    terminal_value, terminal_constraints = _terminal_value_expression(E[-1], terminal_value_cuts)
    constraints += terminal_constraints
    primary = emergency_cost + (terminal_value if terminal_value is not None else 0.0)
    first = cp.Problem(cp.Minimize(primary), constraints)
    started = perf_counter()
    first.solve(solver=SOLVER, verbose=False)
    if e.value is None:
        raise RuntimeError(f"Q4-2 fixed-q dispatch LP failed: {first.status}")
    primary_opt = float(primary.value)
    status = str(first.status)
    if throughput_tiebreak:
        second = cp.Problem(
            cp.Minimize(cp.sum(c + d)),
            constraints + [primary <= primary_opt + MPC_COST_TOL],
        )
        second.solve(solver=SOLVER, verbose=False)
        if x.value is None:
            raise RuntimeError(f"Q4-2 tiebreak LP failed: {second.status}")
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
        terminal_value=evaluate_value_cuts(float(E.value[-1]), terminal_value_cuts),
        solve_seconds=elapsed,
        status=status,
    )
