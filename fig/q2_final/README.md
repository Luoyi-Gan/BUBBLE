# Q2 正式交付图

运行命令：

```bash
MPLCONFIGDIR="$PWD/.mplconfig" .venv/bin/python q2/plot_final_figures.py
```

- 中文字体：PingFang SC
- 所有 PNG 均以 320 dpi 导出，同时提供矢量 PDF。
- 原始时段顺序保持 `00:10` 至 `0:00+1`，未旋转或补造时段。

## F1 `fig_q2_closed_loop`

- 数据源：模型机制与已签收固定口径；图形由 matplotlib patches 矢量绘制。
- 核验：明确当天 q 锁定、日内可修正变量、紧急购电作用和实际 SOC 跨日传递。

## F2 `fig_q2_cost_comparison`

- 数据源：`output/q2_full_k8_risk/daily_summary.csv` 与 `output/q2_full_linked/daily_summary.csv`。
- 汇总范围：2025-02-01 至 2025-12-31，共 334 日。
- K=8：计划费 12,529,090.83 元，紧急费 1,927,579.72 元，总成本 14,456,670.55 元，紧急购电 534,490.42 kWh。
- 相对原动态 K：总成本变化 -50,168.90 元，紧急购电量变化 -120,809.11 kWh。
- 核验：与任务单签收值差异均小于 0.01 元 / 0.01 kWh。

## F3 `fig_q2_representative_day`

- 数据源：K=8 日汇总及对应逐时调度 CSV。
- 可复现选择：2—12 月 `emergency_cost_yuan` 最大日为 2025-06-01。
- 源文件：`output/q2_full_k8_risk/dispatch_daily/dispatch_2025-06-01.csv`；共 144 时段，00:10 至 0:00+1。
- 分时电价由允许读取的 365 日锁定计划、紧急购电和日成本按 `planned_cost=p@q`、`emergency_cost=5*p@e` 联立恢复。
- 电价恢复矩阵秩 144；最大成本回代残差 2.037e-10 元。
- 核验：净负荷、q、x、e、d-c、价格、SOC 均直接读取或逐项确定性计算。

## F4 `fig_q2_risk_calibration`

- 数据源：`output/q2_full_k8_risk/risk_calibration.csv`。
- 共 27 个生效块：前 2 块为 K=1 / 无风险储备，随后 25 块为 K=8。
- 日数核验：α=0.60 为 323 日，α=0.70 为 14 日；区间连续且历史截止日均早于校准日。

## 只读保护

- 绘图脚本对所有源 CSV 与 `output/result2.xlsx` 执行前后 SHA-256 校验。
- `output/result2.xlsx` SHA-256：`70a9785c9e2bba66f7694878e4587ad15c57dc090ec6798d07ba6780b4780ef7`。
