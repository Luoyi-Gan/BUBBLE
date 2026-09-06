"""Save figures to fig/ with paper-friendly names."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "fig"


def save_example() -> Path:
    FIG.mkdir(exist_ok=True)
    x = np.linspace(0, 10, 200)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(x, np.sin(x), label="示例曲线")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title("fig0_template")
    ax.legend()
    ax.grid(True, alpha=0.3)
    path = FIG / "fig0_template.png"
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


if __name__ == "__main__":
    print("wrote", save_example())
