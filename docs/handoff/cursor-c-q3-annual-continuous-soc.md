# Cursor 交接单：Q3 RQ3-3 全年连续 SOC 与正式结果前审计

**发件人：** Codex（建模与独立复核）  
**执行人：** Cursor（实现、全年计算、图形）  
**前置验收：** `d7244c1` 的 RQ3-2/RQ3-4/RQ3-5 两日敏感性功能通过；详见 `docs/reviews/q3-sensitivity-review.md`。  
**本阶段目标：** 实现每个策略、每种口径各自独立的全年连续 SOC 路径，生成可复核的全年中间结果。**不得**生成 `result3.xlsx`，该文件须待 Codex 完成全年复核后再导出。

## 0. 开始前的交付修正

先在 Cursor 分支提交上一阶段的真实重跑产物：`output/q3_sensitivity/`、`fig/q3_sensitivity/`、其 `run_meta.json` 与 `validation.{md,json}`。不得只提交代码。产物应对应本分支实际 commit，且通过：

```bash
.venv/bin/python -m unittest q3.test_q3 -v
.venv/bin/python q3/run_q3_sensitivity.py
.venv/bin/python q3/validate_q3_sensitivity.py
```

## 1. 年度边界与信息结构（不可变）

1. 年度范围为 2025-01-01 至 2025-12-31，365 日 × 144 个 10 分钟时段。每条路径均从
   \[
   E_{2025-01-01,0}=6000\ \mathrm{kWh}
   \]
   开始。
2. 对每一个 `strategy × pv_mapping_mode × settlement_mode`，SOC 必须自行传递：
   \[
   E_{d+1,0}=E_{d,144}.
   \]
   禁止借用 M0、另一策略或另一敏感性口径的日初 SOC；也禁止将 6 月等日期重新设回 6000 kWh。
3. 年末统一固定为
   \[
   E_{2025-12-31,144}=1200\ \mathrm{kWh}.
   \]
   这是与 Q2 年度比较一致的共同终端边界，而非设备“自然必须耗尽”的物理断言；所有年度策略和敏感性必须使用同一边界并在论文中说明。
4. 主信息口径固定为 `causal_load_main`。负荷和光伏预测必须严格遵守已验收的信息结构：当日 0:00 因果负荷 hat、更新后未来负荷不读同日真实值、当前执行步才使用真实负荷/光伏、未来光伏不读附件 2。
5. 保留 48 小时终端价值。它在年末不能凭空访问 2026 年附件数据；年末共同 SOC 约束优先于虚构的次日预测价值。

## 2. 计算矩阵与分阶段执行

### 2.1 年度主口径（优先完成）

对以下主组合分别运行全部五个策略 `M0, M1_M6, M6_only, M12_only, M18_only`：

`linear_anchor_main + anchor_final_main`

这是唯一可进入正式 Q3 主结论候选的年度结果。

### 2.2 年度敏感性（主口径通过后）

同样对五个策略运行另三种组合：

1. `linear_anchor_main + adjacent_literal_sensitivity`；
2. `step_hourly_sensitivity + anchor_final_main`；
3. `step_hourly_sensitivity + adjacent_literal_sensitivity`。

不得只对 M0/M1_M6 运行敏感性后便声称策略选择稳健；两日试算已显示映射与结算都可能改变策略排序。

## 3. 模型实现要求

1. 0:00、6:00、12:00、18:00 的承诺版本、VoI 判断、锁定时段和实时执行机制保持当前实现。年末共同 SOC 约束须同时进入 0:00 计划、每次更新重优化和实时剩余时域可行性检查，不能只在运行结束后筛选。
2. 终端价值模块应按已有的 `pv_mapping_mode` 使用匹配的光伏映射；`adjacent_literal_sensitivity` 必须继续以相邻版本差额进入优化目标，而不是事后重新计费。
3. 同时维护最小吞吐量二级目标与同时充/放电审计；不因全年运行而放松既有物理边界。
4. 年初历史不足时，负荷预测可按已签收的附件 1 回退逻辑执行；须在预测审计中标出回退日期与来源，不能填入未来日的同星期负荷。

## 4. 年度输出、审计与图形

所有新结果写入 `output/q3_full_annual/`、`fig/q3_full_annual/`，不得覆盖 `q3_pilot/` 或 `q3_sensitivity/`。

### 4.1 需提交的表与审计

1. `q3_annual_strategy_comparison.csv`：每个唯一运行键的总成本、结算成本、紧急成本/电量、弃光、调整次数、上/下调量、年初/年末 SOC、最大残差和运行时间；
2. `q3_annual_daily_summary.csv`：每日期、每个唯一运行键的成本分解、购电、紧急电、弃光、日初/日末 SOC、调整次数及约束残差；
3. `q3_annual_forecast_audit.csv`：至少记录每个决策日负荷来源日期/回退标记，以及两类光伏映射的模式和更新信息；
4. `q3_annual_settlement_ledger.csv`：可从每个运行键、每一天、每个时段的台账逐级加总到汇总成本；
5. `q3_annual_physical_audit.json`、`run_meta.json`、`validation.{md,json}`；
6. 逐日/逐时调度明细可置于 `dispatch_daily/`，但不能以忽略该目录为理由省略上述可复核汇总与台账。

每份记录都必须含：

`date, strategy, load_information_case, pv_mapping_mode, settlement_mode, with_terminal_value, run_id`。

### 4.2 图形（由 Cursor 完成）

至少输出：

1. 五策略年度总成本分解图（主口径）；
2. 五条全年 SOC 路径图（主口径），标明 1200/10800 kWh 边界；
3. 映射 × 结算的年度成本敏感性图，且明确它们不是主口径；
4. 月度紧急购电成本与弃光量对比图（主口径）。

## 5. 验收程序与禁止事项

新增全年测试至少验证：全年无日期缺失/重复、365 日 × 144 时段完整、每条路径跨日 SOC 连续、年初 6000/年末 1200、唯一运行键无重复、预测历史截止日不晚于决策日、各口径不混用。

提交前执行：

```bash
.venv/bin/python -m unittest q3.test_q3 -v
.venv/bin/python q3/run_q3_full_annual.py
.venv/bin/python q3/validate_q3_full_annual.py
```

禁止：生成 `result3.xlsx`、实现 M5、以两日结果替代全年结果、跨路径共享 SOC、读取未来附件 2、或把敏感性组合混入主口径平均值。
