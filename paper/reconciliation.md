# 论文数字对账单（ACCT）

> 生成时间：2026-09-12 14:38 UTC；脚本：`scripts/reconcile_paper_numbers.py`

## 签收摘要

- 核对条目：**32**
- **已核：32**
- **不一致：0**
- **未核：0**

| 小问 | 正式口径 | 台账/工作簿 | ACCT 状态 |
| --- | --- | --- | --- |
| Q1 | M1，表2公共母线侧 | `output/result1.xlsx`、`q1_summary.csv` | 已核 |
| Q2 | **V2 政策一致 K=8** | `output/result2.xlsx`、`q2_policy_consistent/` | 已核 |
| Q3 | A边界 + `M1_M6` | `q3_annual_strategy_comparison.csv`、`result3.xlsx` | 已核 |
| Q4 | 结果未放行 | — | 未核（正文无数字） |

## 口径提醒（写入摘要前必读）

- Q2：2–12 月 **15,166,538.46 元** 为题设输出区间；1 月预热 **1,977,568.32 元** 须分列，不得相加混报。
- Q3：全年 **16,373,508.75 元** 为 1–12 月主结论；**14,512,748.53 元** 仅为 `result3.xlsx` 的 2–12 月核对区间。
- Q4：待 RQ4-C1 与物理审计通过后方可对账。

## 逐条对账

| 小问 | 论文位置 | 指标 | 单位 | 展示精度 | 论文值 | 源文件 | 源列/字段 | 源值 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q1 | `sections/q1/05_results.tex` | 无储能基准购电费 | 元 | 4 | 48052.0466 | `output/q1_baseline.csv` | baseline_purchase_cost_yuan | 48052.0465908 | **已核** |  |
| Q1 | `sections/q1/05_results.tex` | 成本节省 | 元 | 4 | 14250.5510 | `output/q1_baseline.csv` | absolute_cost_saving_yuan | 14250.5510486 | **已核** |  |
| Q1 | `sections/q1/05_results.tex` | 节省比例 | 1 | 4 | 0.2966 | `output/q1_baseline.csv` | cost_saving_ratio | 0.296564913665 | **已核** |  |
| Q1 | `sections/q1/05_results.tex` | 全天购电量 | kWh | 4 | 57526.2435 | `output/q1_summary.csv` | grid_purchase_kwh | 57526.2434809 | **已核** |  |
| Q1 | `sections/q1/05_results.tex` | 全天购电费 | 元 | 4 | 33801.4955 | `output/q1_summary.csv` | purchase_cost_yuan | 33801.4955422 | **已核** |  |
| Q1 | `sections/q1/05_results.tex` | 总充电量 | kWh | 4 | 19842.7105 | `output/q1_plan.csv` | sum(charge_kwh) | 19842.7104755 | **已核** |  |
| Q1 | `sections/q1/05_results.tex` | 总放电量 | kWh | 4 | 17858.4394 | `output/q1_plan.csv` | sum(discharge_kwh) | 17858.439428 | **已核** |  |
| Q1 | `sections/q1/05_results.tex` | 峰值购电功率 | kW | 4 | 8458.8273 | `output/q1_summary.csv` | peak_grid_kw | 8458.8273 | **已核** |  |
| Q1 | `tables/q1/purchase.tex` | 购电量 10:00-10:10 | kWh | 4 | 0.0000 | `output/q1_plan.csv` | time=10:00-10:10/grid_purchase_kwh | 0 | **已核** |  |
| Q1 | `tables/q1/purchase.tex` | 购电量 12:00-12:10 | kWh | 4 | 486.4029 | `output/q1_plan.csv` | time=12:00-12:10/grid_purchase_kwh | 486.4029 | **已核** |  |
| Q1 | `tables/q1/purchase.tex` | 购电量 14:00-14:10 | kWh | 4 | 0.0000 | `output/q1_plan.csv` | time=14:00-14:10/grid_purchase_kwh | 0 | **已核** |  |
| Q1 | `tables/q1/purchase.tex` | 购电量 16:00-16:10 | kWh | 4 | 394.9315 | `output/q1_plan.csv` | time=16:00-16:10/grid_purchase_kwh | 394.931483333 | **已核** |  |
| Q1 | `tables/q1/purchase.tex` | 购电量 18:00-18:10 | kWh | 4 | 636.9826 | `output/q1_plan.csv` | time=18:00-18:10/grid_purchase_kwh | 636.982616667 | **已核** |  |
| Q1 | `tables/q1/purchase.tex` | 购电量 20:00-20:10 | kWh | 4 | 0.0000 | `output/q1_plan.csv` | time=20:00-20:10/grid_purchase_kwh | 0 | **已核** |  |
| Q2 | `sections/q2/05_results.tex` | 2-12月总成本 | 元或kWh | 2 | 15166538.46 | `output/q2_policy_consistent/cost_breakdown.csv` | 2-12月总成本 | 15166538.4609 | **已核** | V2 政策一致主方案 |
| Q2 | `sections/q2/05_results.tex` | 2-12月计划成本 | 元或kWh | 2 | 11883687.24 | `output/q2_policy_consistent/cost_breakdown.csv` | 2-12月计划成本 | 11883687.2369 | **已核** | V2 政策一致主方案 |
| Q2 | `sections/q2/05_results.tex` | 2-12月紧急成本 | 元或kWh | 2 | 3282851.22 | `output/q2_policy_consistent/cost_breakdown.csv` | 2-12月紧急成本 | 3282851.22402 | **已核** | V2 政策一致主方案 |
| Q2 | `tables/q2/cost_summary.tex` | 1月预热总成本 | 元或kWh | 2 | 1977568.32 | `output/q2_policy_consistent/cost_breakdown.csv` | 1月预热总成本 | 1977568.32241 | **已核** | V2 政策一致主方案 |
| Q2 | `tables/q2/cost_summary.tex` | 2-12月紧急购电量 | 元或kWh | 2 | 924502.93 | `output/q2_policy_consistent/cost_breakdown.csv` | 2-12月紧急购电量 | 924502.928715 | **已核** | V2 政策一致主方案 |
| Q2 | `tables/q2/cost_summary.tex` | 2月1日继承SOC | 元或kWh | 4 | 8390.6808 | `output/q2_policy_consistent/cost_breakdown.csv` | 2月1日继承SOC | 8390.68083021 | **已核** | V2 政策一致主方案 |
| Q2 | `tables/q2/parameter_selection.tex` | K=8总成本 | 元或kWh | 2 | 15166538.46 | `output/q2_policy_consistent/cost_breakdown.csv` | K=8总成本 | 15166538.4609 | **已核** | V2 政策一致主方案 |
| Q2 | `tables/q2/parameter_selection.tex` | K=8紧急购电量 | 元或kWh | 2 | 924502.93 | `output/q2_policy_consistent/cost_breakdown.csv` | K=8紧急购电量 | 924502.928715 | **已核** | V2 政策一致主方案 |
| Q2 | `output/result2.xlsx` | 逐格对账 | - | - | PASS | `output/q2_policy_consistent/result2_cell_audit.json` | pass | True | **已核** | 334日模板；SHA与台账一致 |
| Q3 | `sections/q3/05_results.tex` | M1_M6全年总成本 | 元/%/次 | 2 | 16373508.75 | `output/q3_full_annual/q3_annual_strategy_comparison.csv` | M1_M6全年总成本 | 16373508.749 | **已核** |  |
| Q3 | `sections/q3/05_results.tex` | M0全年总成本 | 元/%/次 | 2 | 17109568.25 | `output/q3_full_annual/q3_annual_strategy_comparison.csv` | M0全年总成本 | 17109568.2517 | **已核** |  |
| Q3 | `sections/q3/05_results.tex` | 相对M0节省 | 元/%/次 | 2 | 736059.50 | `output/q3_full_annual/q3_annual_strategy_comparison.csv` | 相对M0节省 | 736059.502696 | **已核** |  |
| Q3 | `sections/q3/05_results.tex` | 节省比例 | 元/%/次 | 2 | 4.30 | `output/q3_full_annual/q3_annual_strategy_comparison.csv` | 节省比例 | 4.30203434632 | **已核** |  |
| Q3 | `sections/q3/05_results.tex` | B边界成本增量 | 元/%/次 | 2 | 2262.88 | `output/q3_full_annual/q3_annual_strategy_comparison.csv` | B边界成本增量 | 2262.87989454 | **已核** |  |
| Q3 | `tables/q3/strategy_comparison.tex` | result3输出区间成本 | 元/%/次 | 2 | 14512748.53 | `output/q3_full_annual/q3_annual_strategy_comparison.csv` | result3输出区间成本 | 14512748.528 | **已核** |  |
| Q3 | `tables/q3/strategy_comparison.tex` | M1_M6结算成本 | 元/%/次 | 2 | 13602473.20 | `output/q3_full_annual/q3_annual_strategy_comparison.csv` | M1_M6结算成本 | 13602473.196 | **已核** |  |
| Q3 | `tables/q3/strategy_comparison.tex` | M1_M6紧急购电/kWh | 元/%/次 | 2 | 742322.81 | `output/q3_full_annual/q3_annual_strategy_comparison.csv` | M1_M6紧急购电/kWh | 742322.81341 | **已核** |  |
| Q3 | `tables/q3/strategy_comparison.tex` | 调整次数 | 元/%/次 | 0 | 947 | `output/q3_full_annual/q3_annual_strategy_comparison.csv` | 调整次数 | 947 | **已核** |  |

## 结论

Q1–Q3 正文与表格数字均可在展示精度内回链至正式 `output/` 台账；可进入摘要/评价写作前的数字锁定阶段。

## ACCT 签收清单

- [x] Q1–Q3 逐条对账（本文件 + `reconciliation_audit.json`）
- [x] Q1 专用视图：`paper/q1_reconciliation.md`
- [ ] Q4 待 RQ4-C1 与物理审计后再对账
- [ ] 摘要/评价写作时再次引用本对账单

**复跑：** `python3 scripts/reconcile_paper_numbers.py`（退出码 0 = 全部已核）
