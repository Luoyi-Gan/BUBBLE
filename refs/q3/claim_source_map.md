# Q3 Claim–Source Map（FIN 证据链审计版）

## 1. 版本与可用性登记

| 对象 | 版本/位置 | 审计事实 | 论文权限 |
|---|---|---|---|
| 当前 FIN 任务基线 | `codex/fin-evidence-chain-audit@9400e887e510d88a91db516e755fdeccb60eeca1` | 当前工作树仅有 `output/q3_pilot/`，没有 `output/q3_full_annual/` 或 `output/result3.xlsx` | 不得把当前工作树描述为含全年结果文件 |
| Q3 年度归档 | `cursor/c-q3-full-annual-ab-730d@6e16b3a4276ae880eb65f5dc61214ff9932aaf5d` | `run_meta.json` 记录代码基线 `233d13f7270525574c784129bf594793f3193787`、3650 个 day-runs、HiGHS/Python/cvxpy 版本；`validation.json` 为 all-pass | 可按 `docs/reviews/q3-annual-result-acceptance.md` 已验收范围引用，必须同时写远端归档 commit |
| 年度验收结论 | `docs/reviews/q3-annual-result-acceptance.md` | 验收主路径、边界与指定结果；同时记录四组合敏感性和 `result3.xlsx` 尚未在被审归档闭合 | 只释放文档明确验收的年度主结果，不释放缺口 |
| 后续候选文件 | 远端候选 `08b0c5d657cc061337396f686984b3ce76df1af6` | 含 `output/result3.xlsx` 等后续文件，但不在本任务基线，亦非上述验收所审版本 | FIN 本轮不升级为正式证据；待独立验收/合并 |

## 2. 高影响主张逐条审计

| 编号 | 论文拟写主张 | 类别 | 证据位置或推导条件 | 外部来源与定位 | 不支持什么 | 处理建议 | 状态 |
|---|---|---|---|---|---|---|---|
| Q3-01 | Q3 主结果采用仅含当时可得历史信息的 `causal_load_main`。 | A+E | 年度归档 `run_meta.json` 与验收文档的主口径字段。 | Q3-L1，pp.438–440，§2、§3.2，仅支撑因果回测原则。 | 不证明该代理是唯一或最准确的负荷模型。 | 写成项目主路径，并报告其预测审计。 | 可直接使用（限定版本） |
| Q3-02 | `actual_load_proxy` 使用实现后实际负荷，只能作为 oracle/信息上界型敏感性。 | A | 其信息集包含决策时不可得的未来实际值。 | Q3-L1 提供 no-peeking 原则。 | 在未证明同可行域与单调关系时，不支持称“严格性能下界”。 | 统一称 oracle 敏感性，不与因果主结果并列为可实施策略。 | 需改写 |
| Q3-03 | MPC 每次只执行首个动作，并按更新状态滚动求解。 | L | 一般 receding-horizon 机制。 | Q3-L2，pp.1819–1820，§III-D，Eq.(17) 及 §III-E。 | 不支持 Q3 的具体更新时间、预测代理、映射和结算选择。 | 一般方法与项目参数分句写。 | 可直接使用（一般方法） |
| Q3-04 | 题面更新点为 0:00/6:00/12:00/18:00；6:10/12:10/18:10 的首个生效索引、小时到 10 分钟线性锚点映射及相对 0:00 原计划结算属于本文解释。 | F+A | `docs/specs/q3.md` 的信息表、预测映射和结算公式；附件标签决定首个索引。 | — | 不能用 MPC 文献证明线性映射更准确或结算解释唯一。 | 逐索引回链附件；分段常数×线性映射、锚定×相邻版本结算做五策略全年四组合敏感性。 | 待补敏感性 |
| Q3-05 | 年度归档覆盖 2025-01-01 至 2025-12-31、2 个年末 SOC 边界和 5 个策略，共 3650 个 day-runs。 | E | 归档 commit `6e16b3a...` 的 `output/q3_full_annual/run_meta.json`、`validation.json`；验收文档。 | — | 不支持其他年份、园区或未运行策略。 | 结果句附日期、策略数、边界数和 commit。 | 可直接使用 |
| Q3-06 | 归档年度物理与连续性校验全部通过。 | E | 同 commit 的 `validation.json`、`q3_annual_physical_audit.json`；验收记录 27 tests passed。 | — | 不证明模型假设真实或经济结论可外推。 | 写“在已编码校验项上通过”，不得写“模型完全正确”。 | 可直接使用（限定校验项） |
| Q3-07 | 在 A 边界（年末 SOC=1200 kWh）下，M1_M6 相对 M0 的年度总成本变化为 -4.30%。 | E | 验收文档；归档 `q3_annual_strategy_comparison.csv`。 | — | 不支持因果归因于单一控制动作，也不支持普适节省率。 | 同句给出基线、边界、年份、归档版本。 | 可直接使用 |
| Q3-08 | M1_M6 的改善由普通结算增加与应急结算下降共同构成。 | E+M | 验收文档分项：普通结算约 +26.65 万元，应急结算约 -100.25 万元，净额约 -73.61 万元；精确值回链 CSV。 | — | 不证明未来年度仍有相同机制或幅度。 | 称“该年度输出分解显示”，不要写因果定律。 | 可直接使用（限定输出） |
| Q3-09 | 当 M1 允许保持原计划且调整价已入目标时，M1 与 `epsilon=0` 的 M6 经济等价；M6 是 VoI 的实施/解释记录，不是第二个独立改进算法。 | M+A | `docs/specs/q3.md` §5；成立条件包括同一信息集、目标、可行域与零实施阈值。 | — | 不支持把 M1、M6 的“节省”相加，也不支持 epsilon>0 或不同约束时仍等价。 | 主比较写 M0、M1/M6 与单更新时间消融；逐时点 VoI 只作解释台账。 | 可直接使用（保留条件） |
| Q3-10 | M18 在 A 边界下相对 M0 约 +0.005%，未显示成本改善。 | E | 验收文档与年度策略对比 CSV。 | — | 不支持 M18 在所有边界/年份“无效”。 | 写成该基线下的近零且略高结果。 | 可直接使用 |
| Q3-11 | 两个年末 SOC 边界可用于检查末端条件敏感性。 | A+L | A=1200 kWh 为主口径，B=6000 kWh 为敏感性。 | Q3-L3，正式 PDF pp.19–20 §3.3.2、p.34 §4.3.1。 | 不证明这两个值覆盖所有合理终端规则。 | 报双边界结果并说明范围有限。 | 可直接使用（限定设计） |
| Q3-12 | Q3 已有正式 `result3.xlsx` 且四种映射/结算组合完成五策略全年敏感性。 | E | 被审归档/验收文档明确这些项未闭合；当前基线也无相应文件。 | — | 现有证据直接不支持该说法。 | 删除；后续候选 commit 需另行验收。 | 禁止使用 |
| Q3-13 | Q3 使用 48 小时或等价下一日价值项控制日内滚动末端效应，并按 Q3 信息口径单独标定。 | A+E+L | `docs/specs/q3.md` §3；年度验收主结果标注 48 小时终端价值；其数值必须回链 Q3 归档。 | Q3-L3 仅支撑一般末端效应。 | 不支持直接复用 Q2 的数值、48 小时最优或年度影响由文献证明。 | 将 48 小时审计与年末 A/B 边界分开报告；给有/无 48 小时对照及版本。 | 可直接使用（限定 Q3 审计） |

## 3. 外部来源卡片

### Q3-L1 样本外评价与 no-peeking

- 作者/机构：Leonard J. Tashman。
- 题名与年份：*Out-of-Sample Tests of Forecasting Accuracy: An Analysis and Review*，2000。
- DOI/稳定链接：<https://doi.org/10.1016/S0169-2070(00)00065-0>。
- 精确定位：pp.438–439，§2；pp.439–440，§3.2 “Rolling origin”。
- 可支撑的准确句子：“样本外评价应隔离保留样本，避免利用未来观测造成窥视污染；滚动起点只允许使用预测起点已知的信息。”
- 不能支撑：`causal_load_main` 的具体形式、预测精度、实际负荷代理的严格下界性质或任何年度成本数值。
- GB/T 7714：TASHMAN L J. Out-of-sample tests of forecasting accuracy: an analysis and review[J]. International Journal of Forecasting, 2000, 16(4): 437-450. DOI:10.1016/S0169-2070(00)00065-0.

### Q3-L2 MPC 的滚动执行

- 作者/机构：Alessandra Parisio，Evangelos Rikos，Luigi Glielmo。
- 题名与年份：*A Model Predictive Control Approach to Microgrid Operation Optimization*，2014。
- DOI/稳定链接：<https://doi.org/10.1109/TCST.2013.2295737>。
- 精确定位：pp.1819–1820，§III-D，Eq.(17) 后；§III-E 当前状态初始化。
- 可支撑的准确句子：“MPC 求解有限时域优化后只应用首个控制动作，并在获得新状态后移动时域、重新求解。”
- 不能支撑：Q3 的 10 min/小时更新时间、负荷代理、日前到日内映射、结算口径、策略标签或成本效果。
- GB/T 7714：PARISIO A, RIKOS E, GLIELMO L. A model predictive control approach to microgrid operation optimization[J]. IEEE Transactions on Control Systems Technology, 2014, 22(5): 1813-1827. DOI:10.1109/TCST.2013.2295737.

### Q3-L3 有限时域末端效应

- 作者/机构：Karl-Kiên Cao，Katharina von Krbek，Manuel Wetzel，等。
- 题名与年份：*Classification and Evaluation of Concepts for Improving the Performance of Applied Energy System Optimization Models*，2019。
- DOI/稳定链接：<https://doi.org/10.3390/en12244656>。
- 精确定位：正式 PDF pp.19–20，§3.3.2；p.34，§4.3.1 “Discharge Effect”。
- 可支撑的准确句子：“滚动或有限时域模型若缺少循环/终端储能平衡，可能在时域末端形成放空偏差。”
- 不能支撑：A/B 两个终值是唯一合理集合、固定终端状态不会引入新偏差、Q3 任一成本变化。
- GB/T 7714：CAO K K, VON KRBEK K, WETZEL M, et al. Classification and evaluation of concepts for improving the performance of applied energy system optimization models[J]. Energies, 2019, 12(24): 4656. DOI:10.3390/en12244656.

## 4. 年度 E 类结果的闭合边界

| 结果 | 附件/样本范围 | 版本与输出 | 可写结论 | 不可写结论 |
|---|---|---|---|---|
| 主策略比较 | 2025 全年；5 策略；A/B 两终值 | 归档 `6e16b3a...`：`q3_annual_strategy_comparison.csv`、`run_meta.json`；验收文档 | 按验收文档报告各策略相对 M0 的模型内年度差异 | 不外推其他年份；不把相关分解写为现实因果 |
| 日级与边界审计 | 同上，共 3650 day-runs | `q3_annual_daily_summary.csv`、`q3_annual_boundary_delta.csv`、`validation.json`、`q3_annual_physical_audit.json` | 报告已编码物理/连续性校验及双边界敏感性 | 不写“模型完全验证”或“终端条件无影响” |
| 预测因果性 | `causal_load_main` 主路径及对照 | `q3_annual_forecast_audit.csv`、`run_meta.json` | 报告主路径信息集和预测审计 | oracle 不可作为可部署结果，不称严格下界 |
| 正式工作簿/四组合敏感性 | 被审归档未提供或未全年完成 | 验收文档的未闭合项；当前基线无 `result3.xlsx` | 只能列为待验收缺口 | 不得引用后续候选文件冒充被审归档结果 |

## 5. A 类假设、局限与敏感性闭环

| A 类事项 | 项目主选择 | 局限 | 处理要求 |
|---|---|---|---|
| 负荷信息集 | `causal_load_main` | 代理误差会传导到调度 | 报预测审计；`actual_load_proxy` 只作 oracle 敏感性 |
| 日前-日内映射 | 验收主口径 | 其他时间聚合/分摊规则可能改变偏差费用 | 完成五策略全年四组合敏感性，未完成前加局限 |
| 结算口径 | 验收主口径 | 映射与结算存在交互 | 映射×结算联合敏感性，不单因素代替 |
| 终端边界 | A=1200 kWh 主，B=6000 kWh 敏感性 | 两点不能覆盖全部终值/惩罚规则 | 同表报告 A/B，并说明有限覆盖 |
| 日内终端价值 | 48 小时或等价下一日价值项，按 Q3 因果信息重新标定 | 长度与切面是项目选择，且不同于年末 A/B 边界 | 单独报告有/无项、价值误差与版本；不得搬用 Q2 数值 |
| 策略解释 | M1_M6 独立求解 | 不能把组合效果拆成简单加和 | 报策略输出与成本分项；因果解释需消融 |

## 6. FIN 签字意见

Q3 年度主结果可以引用，但证据位置必须写成“远端归档 `6e16b3a...` + 代码基线 `233d13f...` + 本仓验收文档”，不能暗示文件已存在于当前 FIN 分支。因果负荷是主路径，`actual_load_proxy` 仅为 oracle 敏感性；MPC 文献只支撑一般滚动机制。正式 `result3.xlsx` 和五策略全年四组合映射/结算敏感性不在被审证据链内，继续保留为待验收项。
