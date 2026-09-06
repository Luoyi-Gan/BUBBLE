"""Linear / convex optimization template. Export CSV to output/."""

from pathlib import Path

import cvxpy as cp
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def solve_example() -> pd.DataFrame:
    x = cp.Variable(2, nonneg=True)
    objective = cp.Maximize(3 * x[0] + 2 * x[1])
    constraints = [x[0] + x[1] <= 10, 2 * x[0] + x[1] <= 15]
    prob = cp.Problem(objective, constraints)
    prob.solve()
    return pd.DataFrame(
        {
            "variable": ["x1", "x2", "objective"],
            "value": [float(x.value[0]), float(x.value[1]), float(prob.value)],
            "meaning": ["决策变量1", "决策变量2", "目标函数最优值"],
        }
    )


if __name__ == "__main__":
    OUTPUT.mkdir(exist_ok=True)
    df = solve_example()
    path = OUTPUT / "template_optimization.csv"
    df.to_csv(path, index=False)
    print(df)
    print("wrote", path)
