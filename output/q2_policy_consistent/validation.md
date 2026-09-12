# Q2 政策一致重设计 · C2-R4

- 状态：**PASS**
- 正式主方案固定为：K=8；C2-R2 冻结的 (m, α) 日历；校准、部署与全年路径均启用次日价值割；全年从 2025-01-01 的 6000 kWh 起步，1 月仅预热，2—12 月正式输出继承 1 月末 SOC。
- **K=8 表述为「预注册且对 K=4/12 稳定的简洁主方案」，不得称为成本最优。**
- **旧全路径 K=8 风险方案仅作信息更强的近似对照，不是正式答卷。**
- 1 月预热实际成本 1977568.32 元；2 月 1 日继承 SOC 8390.680830 kWh。
- 2—12 月正式成本 15166538.46 元，紧急购电 924502.93 kWh。
- K∈{4,8,12} 闭环敏感性结论：`retain_k8_stable`。
- 候选附件写入 `output/q2_policy_consistent/result2.xlsx`；旧签收文件 `output/result2.xlsx` 未覆盖，可回退副本 `output/q2_policy_consistent/result2_signed_off_backup.xlsx`。
- 旧 result2.xlsx SHA-256：`70a9785c9e2bba66f7694878e4587ad15c57dc090ec6798d07ba6780b4780ef7`。
- 逐格对账：`result2_cell_audit.json` / `result2_cell_audit.csv`；pass=True。
- 最终图写入 `fig/q2_policy_consistent/`，未改写 `fig/q2_final/`。

## 候选附件对账

- 日期：2 月 1 日至 12 月 31 日，共 334 日。
- 每行 144 时段，按附件原始行序写入，不旋转。
- 计划购电量/全天购电费与台账 `planned_q_kwh` / `planned_cost_yuan` 一致；单位 kWh / 元。
- 紧急购电量按连续正量合并时段，日合计与台账 `emergency_kwh` 一致。
- 充放电量按 4 小时块汇总；00:00 / 24:00 储电量与日初/日末 SOC 一致，且跨日连续。
- 功率上限、能量平衡、x≤q 与全年物理审计一致。

## 论文口径

- 可写：基于历史残差风险储备的日前购电计划，配合逐时段残差匹配 MPC。
- 不可写：K=8 成本最优、严格多阶段随机最优控制、旧全路径方案为正式主方案。
