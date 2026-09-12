# Q4 正式交付图

运行命令：

```bash
MPLCONFIGDIR="$PWD/.mplconfig" python3 q4/plot_final_figures.py
python3 q4/report_q4_closeout.py
```

- 中文字体：WenQuanYi Micro Hei
- 所有 PNG 均以 320 dpi 导出，同时提供矢量 PDF。
- 原始时段顺序保持 `00:10` 至 `0:00+1`，未旋转或补造时段。
- 主图不含 Q4-3 价格神谕年与更新时刻重记账。

## F1a `fig_q4_2_closed_loop`

- 数据源：已签收 Q4-2 机制；图形由 matplotlib patches 矢量绘制。
- 核验：当天 q 锁定、因果 MPC、紧急购电只补当期、实际 SOC 跨日传递。

## F1b `fig_q4_3_update_clock`

- 数据源：已签收 Q4-3 M1_M6 0/6/12/18 时钟。
- 核验：6:00 前前缀锁定；结算为交付时点实际电价。

## F2 `fig_q4_cost_comparison`

- 数据源：Q4-2/Q4-3 日汇总、Q2 K=8 日汇总、Q3 官方 A+M1_M6 日汇总。
- 汇总范围：2025-02-01 至 2025-12-31，共 334 日。不要与 1—12 月年合计混用。
- Q4-2：15,257,873.75 元；Q2 K=8：14,456,670.55 元。
- Q4-3：15,346,418.14 元；Q3 M1_M6 同期：14,512,748.53 元。
- 核验：Q4 与 Q2 对照值与签收工作簿差小于 0.01 元。Q2/Q3 用附件1，Q4 用附件4。

## F3a `fig_q4_2_representative_day`

- 可复现选择：2—12 月 `emergency_cost_yuan` 最大日为 2025-06-01。
- 源文件：`output/q4/q4_2_dispatch_daily/dispatch_2025-06-01.csv`；00:10 至 0:00+1。

## F3b `fig_q4_3_representative_day`

- 可复现选择：2—12 月 `emergency_cost_yuan` 最大日为 2025-07-01。
- 源文件：`output/q4/q4_3_dispatch_daily/dispatch_2025-07-01.csv`。

## F4 `fig_q4_2_risk_calibration`

- 共 26 个生效块：预热 28 日，其后 25 块。
- α=0.60 为 323 日，α=0.70 为 14 日（2025-03-12..2025-03-25）。

## 只读保护

- 绘图脚本对日汇总、α 选择表与 result4/result3 工作簿执行前后 SHA-256 校验。
- `output/result4-2.xlsx` SHA-256：`e24f8b9af91c140b3f02905cd979aeb9c6d619eb8430fc33cc0104cee3e7654f`。
- `output/result4-3.xlsx` SHA-256：`9d5ea9b74f2a6c47308be9e8f2a148236fcb531e10373ab88e95fc5cbe7672b4`。
