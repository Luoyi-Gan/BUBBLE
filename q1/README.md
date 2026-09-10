# 小问 1 · C 题日前购电 LP

实现依据：`docs/specs/q1.md`、`docs/handoff/cursor-c-q1-second-revision.md`。

## 依赖

项目 `.venv`：`numpy scipy pandas matplotlib cvxpy openpyxl`（求解器用 HiGHS）。

## 数据路径

默认读取本机赛题包（不入库）：

- `CUMCM_C_ATTACH1`，默认 `/Users/louis/Desktop/CUMCM2026Problems/C题/附件/附件1.xlsx`
- `CUMCM_C_RESULT1_TEMPLATE`，默认 `/Users/louis/Desktop/CUMCM2026Problems/C题/附件/附件5/result1.xlsx`

## 运行

在仓库根目录：

```bash
source .venv/bin/activate
python q1/run_q1.py
python -m unittest q1.test_q1
```

## 产出

- `output/q1_plan.csv`、`output/q1_summary.csv`
- `output/q1_baseline.csv`、`output/q1_sensitivity.csv`
- `output/q1_model_comparison.csv`、`output/q1_model_selection.md`
- `output/q1_validation.md`
- `output/result1.xlsx`（复制模板填写，不覆盖附件 5 原件）
- `fig/fig1_dispatch.png`、`fig/fig1_soc_price.png`

正式结果为 **M1**（购电费最小）。M2–M4 仅对照。表 2 暂按公共母线侧 `c_t`/`d_t`，待队长签收。
