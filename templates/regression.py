"""Regression / classification template. Export metrics CSV."""

from pathlib import Path

import pandas as pd
from sklearn.datasets import make_regression
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def fit_example() -> pd.DataFrame:
    X, y = make_regression(n_samples=200, n_features=3, noise=8.0, random_state=0)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=0)
    model = LinearRegression().fit(X_train, y_train)
    pred = model.predict(X_test)
    return pd.DataFrame(
        {
            "metric": ["r2", "mse", "intercept"],
            "value": [r2_score(y_test, pred), mean_squared_error(y_test, pred), float(model.intercept_)],
            "meaning": ["测试集拟合优度", "测试集均方误差", "截距"],
        }
    )


if __name__ == "__main__":
    OUTPUT.mkdir(exist_ok=True)
    df = fit_example()
    path = OUTPUT / "template_regression.csv"
    df.to_csv(path, index=False)
    print(df)
    print("wrote", path)
