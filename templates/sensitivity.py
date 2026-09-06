"""One-at-a-time sensitivity. Write a table ACCT can paste."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def sensitivity(base: dict[str, float], deltas: dict[str, list[float]], evaluate) -> pd.DataFrame:
    rows = []
    for name, values in deltas.items():
        for v in values:
            params = dict(base)
            params[name] = v
            y = evaluate(params)
            rel = (v - base[name]) / base[name] if base[name] else float("nan")
            rows.append(
                {
                    "parameter": name,
                    "param_value": v,
                    "param_change_pct": rel,
                    "objective": y,
                    "objective_vs_base": y - evaluate(base),
                }
            )
    return pd.DataFrame(rows)


def _demo_eval(p: dict[str, float]) -> float:
    return p["a"] * 2 + p["b"]


if __name__ == "__main__":
    OUTPUT.mkdir(exist_ok=True)
    base = {"a": 1.0, "b": 3.0}
    df = sensitivity(base, {"a": [0.8, 1.0, 1.2], "b": [2.5, 3.0, 3.5]}, _demo_eval)
    path = OUTPUT / "template_sensitivity.csv"
    df.to_csv(path, index=False)
    print(df)
    print("wrote", path)
