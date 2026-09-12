# Q1 数字对账（ACCT）

> 完整四问对账单见 [`reconciliation.md`](reconciliation.md)。本文件保留 handoff 要求的 Q1 专用视图。

**状态：** 2026-09-12 已核（14/14 关键条目；与 `reconcile_paper_numbers.py` 同步）

| 论文位置 | 指标 | 单位 | 展示精度 | 论文值 | 源文件 | 源字段 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sections/q1/05_results.tex` | 全天购电量 | kWh | 4 | 57526.2435 | `output/q1_summary.csv` | grid_purchase_kwh | 已核 |
| `sections/q1/05_results.tex` | 全天购电费 | 元 | 4 | 33801.4955 | `output/q1_summary.csv` | purchase_cost_yuan | 已核 |
| `sections/q1/05_results.tex` | 无储能基准购电费 | 元 | 4 | 48052.0466 | `output/q1_baseline.csv` | baseline_purchase_cost_yuan | 已核 |
| `sections/q1/05_results.tex` | 成本节省 | 元 | 4 | 14250.5510 | `output/q1_baseline.csv` | absolute_cost_saving_yuan | 已核 |
| `sections/q1/05_results.tex` | 节省比例 | 1 | 4 | 0.2966 | `output/q1_baseline.csv` | cost_saving_ratio | 已核 |
| `sections/q1/05_results.tex` | 总充电量 | kWh | 4 | 19842.7105 | `output/q1_plan.csv` | sum(charge_kwh) | 已核 |
| `sections/q1/05_results.tex` | 总放电量 | kWh | 4 | 17858.4394 | `output/q1_plan.csv` | sum(discharge_kwh) | 已核 |
| `sections/q1/05_results.tex` | 峰值购电功率 | kW | 4 | 8458.8273 | `output/q1_summary.csv` | peak_grid_kw | 已核 |
| `tables/q1/purchase.tex` | 六个指定时段购电量 | kWh | 4 | 见主对账单 | `output/q1_plan.csv` | grid_purchase_kwh | 已核 |
| `tables/q1/storage.tex` | 六区间充放电量与首末 SOC | kWh | 4 | 见 `result1.xlsx` | `output/result1.xlsx` | 充放电量 | 已核 |
| `sections/q1/06_validation.tex` | 能量平衡/SOC/同时充放 | — | — | 检验叙述 | `output/q1_validation.md` | 审计项 | 已核 |

**口径：** 表 2 充电量 = 公共母线侧 \(c_t\)，放电量 = \(d_t\)；144 行按附件原始行序；主方案 \(\eta_c=\eta_d=\sqrt{0.9}\)。
