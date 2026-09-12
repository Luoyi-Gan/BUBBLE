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
    terminal_value: float
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
    expected_terminal_value: float
    initial_soc_marginal: float
    solve_seconds: float
    status: str


ValueCut = tuple[float, float, float]  # reference SOC, value, subgradient


def evaluate_value_cuts(soc: float, cuts: tuple[ValueCut, ...] | None) -> float:
    if not cuts:
        return 0.0
    return max(
        0.0,
        max(
            value + slope * (soc - reference)
            for reference, value, slope in cuts
        ),
    )


def _terminal_value_expression(
    terminal_soc: cp.Expression, cuts: tuple[ValueCut, ...] | None
) -> tuple[cp.Variable | None, list[cp.Constraint]]:
    if not cuts:
        return None, []
    value = cp.Variable(nonneg=True, name="terminal_value")
    constraints = [
        value >= cut_value + slope * (terminal_soc - reference_soc)
        for reference_soc, cut_value, slope in cuts
    ]
    return value, constraints


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
        terminal_value=0.0,
        solve_seconds=elapsed,
        status=str(problem.status),
    )


def solve_stochastic_plan(
    price: np.ndarray,
    scenario_load: np.ndarray,
    scenario_pv: np.ndarray,
    probabilities: np.ndarray,
    initial_soc: float,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    q_floor: np.ndarray | None = None,
) -> PlanResult:
    k, n = scenario_load.shape
    q = cp.Variable(n, nonneg=True)
    expected_emergency = 0
    expected_terminal_value: cp.Expression | float = 0.0
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
        constraints += _contract_constraints(x, q)
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
        terminal_value, terminal_constraints = _terminal_value_expression(
            E[-1], terminal_value_cuts
        )
        constraints += terminal_constraints
        if terminal_value is not None:
            expected_terminal_value += probabilities[omega] * terminal_value
        expected_emergency += (
            probabilities[omega] * EMERGENCY_PRICE_MULTIPLIER * price @ e
        )
    planned_cost = _planned_normal_cost(price, q)
    problem = cp.Problem(
        cp.Minimize(planned_cost + expected_emergency + expected_terminal_value),
        constraints,
    )
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    elapsed = perf_counter() - started
    if q.value is None:
        raise RuntimeError(f"stochastic plan LP failed: {problem.status}")
    qv = np.asarray(q.value).ravel()
    marginal = -float(
        sum(float(np.asarray(constraint.dual_value)) for constraint in initial_constraints)
    )
    terminal_value_result = (
        float(expected_terminal_value.value)
        if isinstance(expected_terminal_value, cp.Expression)
        else float(expected_terminal_value)
    )
    return PlanResult(
        q=qv,
        planned_cost=float(price @ qv),
        expected_emergency_cost=float(problem.value - price @ qv - terminal_value_result),
        expected_terminal_value=terminal_value_result,
        initial_soc_marginal=marginal,
        solve_seconds=elapsed,
        status=str(problem.status),
    )


@dataclass(frozen=True)
class BaselinePlanResult(PlanResult):
    variable_shapes: dict[str, tuple[int, ...]]
    has_scenario_specific_battery: bool


def solve_baseline_plan(
    price: np.ndarray,
    load_hat: np.ndarray,
    pv_hat: np.ndarray,
    initial_soc: float,
    q_floor: np.ndarray | None = None,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
) -> BaselinePlanResult:
    """Day-ahead LP on a single forecast path; q is locked and billed at p@q."""
    n = len(load_hat)
    if load_hat.shape != (n,) or pv_hat.shape != (n,) or price.shape != (n,):
        raise ValueError("baseline plan requires a single forecast trajectory")
    q = cp.Variable(n, nonneg=True, name="q")
    x = cp.Variable(n, nonneg=True, name="x")
    emergency = cp.Variable(n, nonneg=True, name="emergency")
    charge = cp.Variable(n, nonneg=True, name="charge")
    discharge = cp.Variable(n, nonneg=True, name="discharge")
    curtailment = cp.Variable(n, nonneg=True, name="curtailment")
    soc = cp.Variable(n + 1, name="soc")
    constraints = _contract_constraints(x, q)
    if q_floor is not None:
        floor = np.asarray(q_floor, dtype=float).ravel()
        if floor.shape != (n,) or np.any(floor < -1e-9):
            raise ValueError("q_floor must be a nonnegative vector matching the horizon")
        constraints.append(q >= floor)
    physical = _physical_constraints(
        load_hat, pv_hat, initial_soc, x, emergency, charge, discharge, curtailment, soc
    )
    constraints += physical
    terminal_value, terminal_constraints = _terminal_value_expression(
        soc[-1], terminal_value_cuts
    )
    constraints += terminal_constraints
    planned_cost = _planned_normal_cost(price, q)
    expected_emergency = EMERGENCY_PRICE_MULTIPLIER * price @ emergency
    objective = planned_cost + expected_emergency
    if terminal_value is not None:
        objective = objective + terminal_value
    problem = cp.Problem(cp.Minimize(objective), constraints)
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    elapsed = perf_counter() - started
    if q.value is None:
        raise RuntimeError(f"baseline plan LP failed: {problem.status}")
    qv = np.asarray(q.value).ravel()
    shapes = {
        str(variable.name()): tuple(int(dim) for dim in variable.shape)
        for variable in problem.variables()
    }
    has_scenario_battery = any(
        name in {"charge", "discharge", "soc"} and len(shape) == 2
        for name, shape in shapes.items()
    )
    terminal_value_result = (
        float(terminal_value.value) if terminal_value is not None else 0.0
    )
    return BaselinePlanResult(
        q=qv,
        planned_cost=float(price @ qv),
        expected_emergency_cost=float(EMERGENCY_PRICE_MULTIPLIER * price @ emergency.value),
        expected_terminal_value=terminal_value_result,
        initial_soc_marginal=-float(np.asarray(physical[0].dual_value)),
        solve_seconds=elapsed,
        status=str(problem.status),
        variable_shapes=shapes,
        has_scenario_specific_battery=has_scenario_battery,
    )


def solve_fixed_plan_dispatch(
    price: np.ndarray,
    q: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    throughput_tiebreak: bool = True,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
) -> DispatchResult:
    n = len(load)
    x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
    E = cp.Variable(n + 1)
    constraints = _contract_constraints(x, q)
    constraints += _physical_constraints(load, pv, initial_soc, x, e, c, d, w, E)
    emergency_cost = EMERGENCY_PRICE_MULTIPLIER * price @ e
    terminal_value, terminal_constraints = _terminal_value_expression(
        E[-1], terminal_value_cuts
    )
    constraints += terminal_constraints
    primary = emergency_cost + (terminal_value if terminal_value is not None else 0.0)
    first = cp.Problem(cp.Minimize(primary), constraints)
    started = perf_counter()
    first.solve(solver=SOLVER, verbose=False)
    if e.value is None:
        raise RuntimeError(f"fixed-plan execution LP failed: {first.status}")
    primary_opt = float(primary.value)
    status = str(first.status)
    if throughput_tiebreak:
        second = cp.Problem(
            cp.Minimize(cp.sum(c + d)),
            constraints + [primary <= primary_opt + MPC_COST_TOL],
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
        terminal_value=evaluate_value_cuts(float(E.value[-1]), terminal_value_cuts),
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
