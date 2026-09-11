# C 题 Q2 论文证据与结果分析审计

**用途：** 给队长和 ACCT 提供可直接落到论文段落的证据地图，并明确哪些事项仍需签收。本文不修改模型、代码、输出或团队最终决策。

**复核日期：** 2026-09-11

**题面证据缺口：** 公开仓库 `data/raw` 未包含 `C题.pdf` 和附件 2 原件。下表中的题面事实来自 Q2 任务单与现有规格；在论文标页码前，必须由队长/ACCT 对照原件复核。外部来源均已给出稳定链接及页码或章节。

## 论文段落—主张—证据—局限映射

| 论文段落/可用主张 | 分类 | 证据或题面位置 | 适用局限 | 状态 |
|---|---|---|---|---|
| 每日 0:00 制定当日购电计划 | 题面事实 | `C题.pdf` Q2 题干；待原件补页码 | 只说明决策时点，不等于已知当天实际负荷/PV | 页码待核 |
| 当日电价在日初计划中给定 | 题面事实 | `C题.pdf` Q2 题干；待原件补页码 | 不引入实时电价误差或市场机制 | 页码待核 |
| 附件 2 实际曲线用于事后滚动回测 | 附件数据/评估口径 | 附件 2；`docs/evidence/q2/c_q2_assumption_boundary.md` | 实际曲线不属于 0:00 信息集 | 列名待核 |
| 供能不足按正常电价 5 倍紧急购电 | 题面事实 | `C题.pdf` Q2 题干；待原件补页码 | 倍数不需外部文献；需区分计划与事后补购 | 页码待核 |
| 正常计划购电在实现前锁定，紧急购电在实现后补足 | 本文信息结构 | `docs/specs/q2.md`；`docs/evidence/q2/c_q2_emergency_purchase_note.md` | 若队长改为完全信息模型，紧急购电通常被严格支配 | 待队长确认 |
| 若同母线、正常购电无上限且同时决策，5 倍紧急购电被严格支配 | 数学推导 | 替换论证，见 `docs/evidence/q2/c_q2_emergency_purchase_note.md` | 要求正价格、同一时段/母线、没有锁定或容量差异 | 可直接写方法说明 |
| Q2 不应在每天 0:00 重置 SOC | 状态定义 + 文献通识 | La Tona 等（2021）第 2 节、PDF 第 5 页；Luo 等（2019）第 1、4.2–4.3 节 | 文献不决定本题具体初值或终端值 | 可引用 |
| 有限窗口终端处理会影响末端充放电 | 文献通识 | Cao 等（2019）第 3.3.2、4.3.1 节；Luo 等（2019）第 4.2–4.3 节 | 不等于必须每日首末相等 | 可引用 |
| 6000 kWh 只在 2025-01-01 作为一次性初值 | 题面事实/题意映射 | `C题.pdf` 附录 1；既有 `refs/c_q1_initial_soc.md` | 1 月是否计费、2 月 1 日如何继承须单独说明 | 待队长确认计费口径 |
| 终端条件采用 $E_{D,144}\ge R_D$ | 本文假设 | `docs/specs/q2.md` 当前草案；`docs/evidence/q2/c_q2_crossday_soc.md` | $R_D$ 必须只用日初历史信息生成；文献不给其数值 | 待队长确认 |
| 未消纳光伏可作为弃光 $0\le w\le P$ | 本文假设 + 文献通识 | Jorgenson 等（2020）第 1 节第 4 页；Case 等（2018）第 3.1 节第 7 页 | 文献只解释弃光机制；不证明本题禁止售电 | 可写，但市场边界待签收 |
| 题面未给售电收益，主模型只购不售 | 本文假设 | 题面信息缺口；`docs/evidence/q2/c_q2_curtailment_boundary.md` | “未给”不等于“明确禁止”；不虚构售电价/出口限制 | 待队长确认 |
| 正常购电无功率上限 | 暂不考虑/模型局限 | 题面未给 PCC 容量 | 必须报告计划购电峰值并说明物理局限 | 待队长确认 |
| 延续公共母线侧 $c,d$ 与 $\eta_c=\eta_d=\sqrt{0.9}$ | 题给效率 + 本文计量假设 | 既有 `refs/c_q1_efficiency.md`；Q1 队长签收口径 | Q1 决策是否自动延续到 Q2 仍须确认 | 待队长确认 |
| 年度实际费用等于正常购电费与 5 倍紧急购电费之和 | 题意映射/数学汇总 | Q2 题干；`docs/evidence/q2/c_q2_result_analysis_plan.md` | CVaR 和规划惩罚不应混入实际账单 | 结果到位后核算 |
| 储能节省必须相对同信息结构的无储能基准 | 结果分析规范 | `docs/evidence/q2/c_q2_result_analysis_plan.md` | 不同计费期或完美信息基准不可直接比较 | 结果到位后核算 |
| 月季与典型日分析只在结果后作方向判断 | 结果分析规范 | `docs/evidence/q2/c_q2_result_analysis_plan.md` | 不预写“夏优冬劣”等结论，不以相关性替代因果 | 待结果 |
| 1 月预热、年末 SOC、零紧急购电必须单列审计 | 边界风险 | `docs/evidence/q2/c_q2_result_analysis_plan.md` | 否则可能把免费初值、期末借电或数据泄漏误写成节省 | 必做 |

## 论文可直接引用的外部来源

### 跨日 SOC 与终端边界

[1] LA TONA G, DI PIAZZA M C, LUNA M. Effect of daily forecasting frequency on rolling-horizon-based EMS reducing electrical demand uncertainty in microgrids[J]. *Energies*, 2021, 14(6): 1598. DOI: [10.3390/en14061598](https://doi.org/10.3390/en14061598). 开放全文：[CNR 稳定句柄](https://hdl.handle.net/20.500.14243/398566)。定位：第 2 节、PDF 第 5 页。支持跨日状态继承和滚动更新；不支持本题具体终端值。

[2] LUO Z, ZHU Z, ZHANG Z, et al. Multi-time-scale rolling optimal dispatch for grid-connected AC/DC hybrid microgrids[J]. *Processes*, 2019, 7(12): 961. DOI: [10.3390/pr7120961](https://doi.org/10.3390/pr7120961). 定位：第 1、4.2–4.3 节，式 (11)–(13)。支持周期间状态衔接及终端约束的调节权衡；不支持本题 LP/MILP 或参数选择。

[3] CAO K K, VON KRBEK K, WETZEL M, et al. Classification and evaluation of concepts for improving the performance of applied energy system optimization models[J]. *Energies*, 2019, 12(24): 4656. DOI: [10.3390/en12244656](https://doi.org/10.3390/en12244656). 开放版本：[DLR 机构库](https://elib.dlr.de/129439/)。定位：第 3.3.2 节、正式版 PDF 第 19–20 页及第 4.3.1 节。支持有限窗口末端放空效应；不支持固定某一终端约束。

### 弃光边界

[4] JORGENSON J, HALE E, COWIESTOLL B. *Managing solar photovoltaic integration in the Western United States: Power system flexibility requirements and supply*[R]. Golden, CO: National Renewable Energy Laboratory, 2020. NREL/TP-6A20-72471. [NREL 官方 PDF](https://www.nrel.gov/docs/fy21osti/72471.pdf)。定位：执行摘要第 vii 页、正文第 1 节第 4 页。支持系统不能吸收/外送剩余光伏时发生弃光；不支持本题售电或出口参数。

[5] CASE T, LIBURD S, REILLY L, et al. *Grid Ready: Strategies for interconnecting large-scale PV in New York City*[R]. Golden, CO: National Renewable Energy Laboratory, 2018. NREL/TP-7A40-71344. [NREL 官方 PDF](https://www.nrel.gov/docs/fy19osti/71344.pdf)。定位：第 3.1 节、PDF 第 7 页。支持超过出口约束的 PV 可被削减、储能可吸收部分剩余；不支持移植纽约费率、出口容量或完美预见。

## ACCT 不应这样写

- 不写“每日 0:00 已知当天实际负荷与光伏”；如使用，只能称“给定日情景离线评估/完全信息基准”。
- 不写“文献规定本题每日末 SOC 等于日初”或“文献给出 $R_D=6000$ kWh”。
- 不写“题目明确禁止售电”或“题目明确规定电网无限供电”。
- 不从外部案例移植售电价、外送上限、弃光惩罚、储备比例或电池参数。
- 不写“紧急购电为零证明预测准确”；先排除支配性、数据泄漏和事后重选计划。
- 不在结果生成前写“夏季一定最好、冬季最高、储能总能降低弃光”等方向性结论。

## 队长签收事项

- [ ] **Q2-CAP-1 信息结构：** 确认附件 2 当日实际曲线只作时段到达后的回测实现值；若另用实际曲线优化，统一命名为“给定日情景离线评估”，不得称 0:00 已知。
- [ ] **Q2-CAP-2 主模型层级：** 确认以每日滚动可执行策略为主、全年 SOC 连续完全信息优化为下界，或相反；两者必须分表。
- [ ] **Q2-CAP-3 1 月口径：** 确认 1 月 1 日至 2 月 1 日是训练/预热还是计费期，并保证 6000 kWh 初值只注入一次、2 月 1 日继承真实 SOC。
- [ ] **Q2-CAP-4 终端策略：** 在无终端、固定 6000 kWh、历史信息生成的动态 $R_D$ 中确认主口径和对照；另签收年末条件。
- [ ] **Q2-CAP-5 市场边界：** 确认主模型“只购不售”、正常购电无功率上限是本文假设，并批准相应局限性措辞。
- [ ] **Q2-CAP-6 计量与模型：** 确认延续 Q1 公共母线侧 $c,d$、$\eta_c=\eta_d=\sqrt{0.9}$，并确认 LP/MILP 口径。
- [ ] **Q2-CAP-7 报告口径：** 确认“实际电费”不含 CVaR/训练惩罚，节省仅与同信息结构无储能基准比较。
- [ ] **Q2-CAP-8 题面定位：** 由队长/ACCT 在本地 `C题.pdf` 和附件 2 原件补齐页码、工作表名、列名和单位。

## 证据链摘要（80–120 字）

Q2证据链已区分题面事实、附件事后数据、文献通识、本文假设与数学推导。跨日SOC须连续递推，终端条件会改变边界调度，但具体目标必须由队长签收；无售电收益时可将未消纳光伏作为弃光。结果分析按年度、月季、典型日及边界风险逐层复核。
