from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import cvxpy as cp
import numpy as np

from q3.config import (
    ADJUST_ABS_COEFF,
    EMERGENCY_PRICE_MULTIPLIER,
    E_MAX_KWH,
    E_MIN_KWH,
    ETA_C,
    ETA_D,
    MPC_COST_TOL,
    POWER_LIMIT_KWH,
    SETTLEMENT_ALT,
    SETTLEMENT_MAIN,
    SIMULTANEOUS_CD_TOL,
    SOLVER,
)


ValueCut = tuple[float, float, float]  # reference SOC, value, subgradient


def settlement_cost(price: np.ndarray, g0: np.ndarray, g_final: np.ndarray) -> np.ndarray:
    """Main phi_t = p g^F + 0.5 p |g^F - g^0|. Vectorised and used in tests and audits."""
    price = np.asarray(price, dtype=float).ravel()
    g0 = np.asarray(g0, dtype=float).ravel()
    g_final = np.asarray(g_final, dtype=float).ravel()
    return price * g_final + ADJUST_ABS_COEFF * price * np.abs(g_final - g0)


def adjacent_adjustment_cost(price: np.ndarray, g_prev: np.ndarray, g_new: np.ndarray) -> np.ndarray:
    """1.5 p (up)_+ + 0.5 p (down)_+ between two adjacent commitment versions."""
    price = np.asarray(price, dtype=float).ravel()
    g_prev = np.asarray(g_prev, dtype=float).ravel()
    g_new = np.asarray(g_new, dtype=float).ravel()
    up = np.maximum(g_new - g_prev, 0.0)
    down = np.maximum(g_prev - g_new, 0.0)
    return 1.5 * price * up + 0.5 * price * down


def realized_settlement(
    price: np.ndarray,
    versions: list[np.ndarray] | tuple[np.ndarray, ...],
    settlement_mode: str,
) -> np.ndarray:
    """Period-wise ordinary+adjustment bill for a full version path (no emergency)."""
    price = np.asarray(price, dtype=float).ravel()
    path = [np.asarray(v, dtype=float).ravel() for v in versions]
    if not path:
        raise ValueError("need at least the 0:00 plan")
    if settlement_mode == SETTLEMENT_MAIN:
        return settlement_cost(price, path[0], path[-1])
    if settlement_mode == SETTLEMENT_ALT:
        phi = price * path[0]
        for prev, cur in zip(path[:-1], path[1:]):
            phi = phi + adjacent_adjustment_cost(price, prev, cur)
        return phi
    raise ValueError(f"unknown settlement_mode: {settlement_mode}")


def decompose_settlement(
    price: np.ndarray,
    versions: list[np.ndarray] | tuple[np.ndarray, ...],
    settlement_mode: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ordinary, up-fee, down-fee arrays that sum to realized_settlement."""
    price = np.asarray(price, dtype=float).ravel()
    path = [np.asarray(v, dtype=float).ravel() for v in versions]
    if settlement_mode == SETTLEMENT_MAIN:
        g0, gf = path[0], path[-1]
        up = np.maximum(gf - g0, 0.0)
        down = np.maximum(g0 - gf, 0.0)
        return price * gf, 0.5 * price * up, 0.5 * price * down
    if settlement_mode == SETTLEMENT_ALT:
        ordinary = price * path[0]
        up_fee = np.zeros_like(price)
        down_fee = np.zeros_like(price)
        for prev, cur in zip(path[:-1], path[1:]):
            up = np.maximum(cur - prev, 0.0)
            down = np.maximum(prev - cur, 0.0)
            up_fee = up_fee + 1.5 * price * up
            down_fee = down_fee + 0.5 * price * down
        return ordinary, up_fee, down_fee
    raise ValueError(f"unknown settlement_mode: {settlement_mode}")


def evaluate_value_cuts(soc: float, cuts: tuple[ValueCut, ...] | None) -> float:
    if not cuts:
        return 0.0
    return max(
        0.0,
        max(value + slope * (soc - reference) for reference, value, slope in cuts),
    )


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


@dataclass(frozen=True)
class HorizonResult:
    g: np.ndarray
    x: np.ndarray
    emergency: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    curtailment: np.ndarray
    soc: np.ndarray
    objective: float
    settlement_cost: float
    emergency_cost: float
    terminal_value: float
    initial_soc_marginal: float
    solve_seconds: float
    status: str

    @property
    def max_cd(self) -> float:
        return float(np.max(self.charge * self.discharge))


def solve_horizon(
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    initial_soc: float,
    g0: np.ndarray | None = None,
    g_fixed: np.ndarray | None = None,
    terminal_value_cuts: tuple[ValueCut, ...] | None = None,
    throughput_tiebreak: bool = True,
    bill_as_day_ahead: bool = False,
    settlement_mode: str = SETTLEMENT_MAIN,
    g_pre: np.ndarray | None = None,
    sunk_settlement: float = 0.0,
) -> HorizonResult:
    """Solve a remaining-horizon LP.

    If bill_as_day_ahead is True, ordinary energy is billed as p@g with no
    adjustment (used for 0:00 and the virtual next day). Otherwise:
    - anchor_final_main: phi(g0, g) = p g + 0.5 p |g-g0|
    - adjacent_literal_sensitivity: sunk p g0 + prior adjacent fees, plus
      1.5 p (g-g_pre)_+ + 0.5 p (g_pre-g)_+ for this update only.
    """
    n = len(load)
    price = np.asarray(price, dtype=float).ravel()
    load = np.asarray(load, dtype=float).ravel()
    pv = np.asarray(pv, dtype=float).ravel()
    g = cp.Variable(n, nonneg=True)
    x, e, c, d, w = (cp.Variable(n, nonneg=True) for _ in range(5))
    E = cp.Variable(n + 1)
    constraints = _physical_constraints(load, pv, initial_soc, x, e, c, d, w, E)
    constraints.append(x <= g)

    if g_fixed is not None:
        fixed = np.asarray(g_fixed, dtype=float).ravel()
        if fixed.shape != (n,):
            raise ValueError("g_fixed must match the remaining horizon")
        constraints.append(g == fixed)

    emergency_cost = EMERGENCY_PRICE_MULTIPLIER * price @ e
    terminal_value, terminal_constraints = _terminal_value_expression(E[-1], terminal_value_cuts)
    constraints += terminal_constraints
    terminal_term: cp.Expression | float = terminal_value if terminal_value is not None else 0.0

    if bill_as_day_ahead:
        settlement = price @ g
    elif settlement_mode == SETTLEMENT_MAIN:
        if g0 is None:
            raise ValueError("g0 is required unless bill_as_day_ahead=True")
        g0 = np.asarray(g0, dtype=float).ravel()
        if g0.shape != (n,):
            raise ValueError("g0 must match the remaining horizon")
        up = cp.Variable(n, nonneg=True)
        down = cp.Variable(n, nonneg=True)
        constraints.append(g - g0 == up - down)
        settlement = price @ g + ADJUST_ABS_COEFF * price @ (up + down)
    elif settlement_mode == SETTLEMENT_ALT:
        if g0 is None or g_pre is None:
            raise ValueError("adjacent settlement requires g0 and g_pre")
        g0 = np.asarray(g0, dtype=float).ravel()
        g_pre_arr = np.asarray(g_pre, dtype=float).ravel()
        if g0.shape != (n,) or g_pre_arr.shape != (n,):
            raise ValueError("g0 and g_pre must match the remaining horizon")
        up = cp.Variable(n, nonneg=True)
        down = cp.Variable(n, nonneg=True)
        constraints.append(g - g_pre_arr == up - down)
        settlement = float(sunk_settlement) + 1.5 * price @ up + 0.5 * price @ down
    else:
        raise ValueError(f"unknown settlement_mode: {settlement_mode}")

    primary = settlement + emergency_cost + terminal_term
    problem = cp.Problem(cp.Minimize(primary), constraints)
    started = perf_counter()
    problem.solve(solver=SOLVER, verbose=False)
    if g.value is None:
        raise RuntimeError(f"Q3 horizon LP failed: {problem.status}")
    status = str(problem.status)
    primary_opt = float(primary.value)
    if throughput_tiebreak:
        second = cp.Problem(
            cp.Minimize(cp.sum(c + d)),
            constraints + [primary <= primary_opt + MPC_COST_TOL],
        )
        second.solve(solver=SOLVER, verbose=False)
        if g.value is None:
            raise RuntimeError(f"Q3 throughput tiebreak failed: {second.status}")
        status = str(second.status)
    elapsed = perf_counter() - started

    gv = np.asarray(g.value).ravel()
    xv = np.asarray(x.value).ravel()
    ev = np.asarray(e.value).ravel()
    cv = np.asarray(c.value).ravel()
    dv = np.asarray(d.value).ravel()
    wv = np.asarray(w.value).ravel()
    Ev = np.asarray(E.value).ravel()
    if bill_as_day_ahead:
        settle = float(price @ gv)
    elif settlement_mode == SETTLEMENT_MAIN:
        settle = float(np.sum(settlement_cost(price, g0, gv)))
    else:
        settle = float(sunk_settlement) + float(np.sum(adjacent_adjustment_cost(price, g_pre_arr, gv)))
    terminal = evaluate_value_cuts(float(Ev[-1]), terminal_value_cuts)
    dual = float(np.asarray(constraints[0].dual_value))
    return HorizonResult(
        g=gv,
        x=xv,
        emergency=ev,
        charge=cv,
        discharge=dv,
        curtailment=wv,
        soc=Ev,
        objective=float(primary_opt),
        settlement_cost=settle,
        emergency_cost=float(EMERGENCY_PRICE_MULTIPLIER * price @ ev),
        terminal_value=terminal,
        initial_soc_marginal=-dual,
        solve_seconds=elapsed,
        status=status,
    )


def dispatch_balance_residual(load: np.ndarray, pv: np.ndarray, result: HorizonResult) -> np.ndarray:
    return (
        result.x
        + result.emergency
        + pv
        - result.curtailment
        + result.discharge
        - load
        - result.charge
    )


def assert_physical(result: HorizonResult, load: np.ndarray, pv: np.ndarray, prefix: str = "") -> None:
    residual = dispatch_balance_residual(load, pv, result)
    soc_residual = result.soc[1:] - (
        result.soc[:-1] + ETA_C * result.charge - result.discharge / ETA_D
    )
    if np.max(np.abs(residual)) > 1e-5:
        raise AssertionError(f"{prefix}energy balance residual {np.max(np.abs(residual)):.3e}")
    if np.max(np.abs(soc_residual)) > 1e-5:
        raise AssertionError(f"{prefix}SOC residual {np.max(np.abs(soc_residual)):.3e}")
    if result.soc.min() < E_MIN_KWH - 1e-6 or result.soc.max() > E_MAX_KWH + 1e-6:
        raise AssertionError(f"{prefix}SOC bound violated")
    if np.any(result.charge < -1e-8) or np.any(result.discharge < -1e-8):
        raise AssertionError(f"{prefix}negative charge/discharge")
    if np.any(result.curtailment < -1e-8) or np.any(result.curtailment - pv > 1e-6):
        raise AssertionError(f"{prefix}curtailment bound violated")
    if np.any(result.x - result.g > 1e-6):
        raise AssertionError(f"{prefix}x exceeds commitment g")
    if result.max_cd > SIMULTANEOUS_CD_TOL:
        raise AssertionError(
            f"{prefix}simultaneous charge/discharge product {result.max_cd:.3e} "
            "exceeds tolerance; stop rather than ignore"
        )
