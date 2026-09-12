# C-Q1 论文支撑与证据边界审计

## 1. 审计结论

- 审计对象：Q1 中拟写入论文的效率、系统边界、终端 SOC、成本与“节省”表述。
- 仓库基线：`codex/fin-evidence-chain-audit@9400e887e510d88a91db516e755fdeccb60eeca1`。
- 结论：Q1 的模型定义、附件事实与项目结果可以形成闭合证据链，但必须把“事实（F）”“数学关系（M）”“建模假设（A）”“项目结果（E）”和“外部一般性知识（L）”分开。论文只能证明一般方法或定义，不能把无售电、无限并网点功率、固定效率、固定终端 SOC 等项目选择改写成客观事实。
- 使用规则：只有 L 类主张引用外部文献；F 类回到赛题正文/附件，M 类给出公式与条件，A 类写明假设及敏感性，E 类绑定输出、版本与样本范围。

## 2. 高影响主张逐条审计

| 编号 | 论文拟写主张 | 类别 | 证据位置或推导条件 | 外部来源与定位 | 不支持什么 | 处理建议 | 状态 |
|---|---|---|---|---|---|---|---|
| Q1-00 | 附件 1 `Sheet1` 以原始行序给出 144 个 10 分钟时段的“时间、电价、小区负载、光伏发电预测功率”。 | F | 附件 1；字段/行数审计见 `q1/load_data.py` 与 `output/q1_validation.md`。 | — | 不支持重排时序、补充未给市场规则或把功率直接当能量。 | 按原始 144 行顺序；功率乘 `1/6 h` 后进入能量模型。 | 可直接使用 |
| Q1-01 | 项目采用“放出电量/充入电量”定义储能往返效率。 | M | `docs/specs/q1.md` 的效率口径；须同时写明测量点与时间范围。 | Q1-L1，PDF p.2，Eq.(2)；Q1-L2，“Round-Trip Efficiency”。 | 不证明赛题附件已经给出同一测量边界。 | 正文先给项目定义，再引一般定义。 | 可直接使用（补边界） |
| Q1-02 | 本文把题给 90% 解释为公共母线侧往返效率，并在对称条件下取单向效率为其平方根。 | A+M | `refs/c_q1_efficiency.md`、`docs/specs/q1.md` 的队长确认；条件为 `eta_ch=eta_dis` 且两者乘积等于 RTE。 | Q1-L1，PDF p.9，§3.2.2，Eq.(12)–(13)。 | 不证明公共母线是题面唯一测点、真实设备两方向效率相等或 90% 只有这一种解释。 | 明写“本文解释 + 对称拆分假设”；并保留充/放各 90%（RTE=81%）敏感性。 | 可直接使用（须带条件） |
| Q1-03 | 往返效率数值随 AC/DC 测量边界和所含变换环节变化。 | L | 一般性系统边界说明。 | Q1-L3，Battery Cell and System > Battery Round Trip Efficiency。 | 不支持反推出本项目附件效率的实际测点。 | 用于解释为什么必须声明边界。 | 可直接使用 |
| Q1-04 | Q1 不允许储能向电网售电。 | A | 项目模型中并网功率非负/不设置售电收益；需回指模型规范。 | — | 论文不能证明该规则来自通用电力系统规律。 | 写成“本文基准模型假设不售电”。 | 需改写 |
| Q1-05 | Q1 未设置有限 PCC 功率上限。 | A | 项目规范及变量约束中无有限并网点容量。 | — | 不能写成实际园区不存在并网容量约束。 | 在局限性中说明可能低估受限并网场景成本。 | 需改写 |
| Q1-06 | 全期采用固定效率，并未计自放电、退化、辅机、温度、网损、需量费与停电风险。 | A | `docs/specs/q1.md` 及跨题复核；均是因题面缺少数据而采用的封闭边界。 | Q1-L1，PDF p.2，Eq.(2) 后仅说明效率会受工况和环境影响。 | 文献不支持恒效，也不能为本题凭空补退化、网损或费率参数。 | 加入局限；效率做敏感性；结论限定为短期能量与购电费调度。 | 需改写 |
| Q1-07 | 日末约束 `E_144=E_0` 用于同起点公平比较并减弱有限时域末端透支。 | A+L | `docs/specs/q1.md` 的终端等式；效果需由有/无约束或终端价值对照确认。 | Q1-L4，正式 PDF pp.19–20 §3.3.2、p.34 §4.3.1。 | 不证明该等式是题目自动要求，也不证明 `6000 kWh` 是唯一终值或消除全部边界效应。 | 写“公平比较/控制末端效应的项目选择”，并报告终端规则敏感性。 | 需改写 |
| Q1-08 | Q1 输出是给定附件、参数、模型边界下的项目结果。 | E | `output/result1.xlsx`、`output/q1_summary.csv`、`output/q1_validation.md`、`results_summary.md`；以仓库归档版本为准。 | — | 不支持对其他园区、年份或电价机制外推。 | 结果句附样本范围、模型版本和边界。 | 可直接使用 |
| Q1-09 | 储能方案相对“同一模型中的无储能基线”降低购电成本。 | E | 有储能与无储能输出必须共享负荷、PV、电价及计费口径。 | — | 不支持称为相对现实世界反事实的绝对经济收益。 | 一律写“相对模型基线节省”。 | 可直接使用（限定基线） |
| Q1-10 | 成本差额由模型内的能量套利、已建约束与边界共同决定。 | M+E | 目标函数分项恒等关系及输出成本分解。 | — | 不能把差额全归因于某一个机制，除非另有消融。 | 给出成本分项或消融再解释机制。 | 需改写 |
| Q1-11 | Q1 的最优性只相对于已实现的确定性优化模型。 | M+A | 目标、变量、约束和求解状态共同限定。 | — | 不支持“现实最优”“行业最优”。 | 使用“模型内最优/求解器报告最优”。 | 需改写 |
| Q1-12 | 终端 SOC、效率与并网约束的改变可能改变节省额。 | A | 属于尚需敏感性验证的方向。 | Q1-L1、Q1-L4 仅提供一般动机。 | 不支持影响方向和幅度已经由项目结果证明。 | 未跑敏感性前写为局限或待验证问题。 | 待补敏感性 |
| Q1-13 | 在正购电价、无售电收益、无强制充放任务且存在等价可行替代时，可用不同时充放电的解替代同时充放电解。 | M+E | 条件性支配论证；`output/q1_validation.md` 另审计 `max(c_t d_t)=0`。 | — | 不支持所有储能系统在任意价格和附加目标下都不同时充放电。 | 数学条件与数值审计同时给出，禁止写成工程定律。 | 可直接使用（保留条件） |

## 3. 外部来源卡片

### Q1-L1 往返效率及对称拆分

- 作者/机构：Hrvoje Bašić，Vanja Bobanac，Hrvoje Pandžić。
- 题名与年份：*Determination of Lithium-Ion Battery Capacity for Practical Applications*，2023。
- DOI/稳定链接：<https://doi.org/10.3390/batteries9090459>。
- 精确定位：PDF p.2，Eq.(2) 及其后段落；PDF p.9，§3.2.2，Eq.(12)–(13)。
- 可支撑的准确句子：“在声明能量测量边界后，往返能量效率可写为放电能量与充电能量之比；若额外采用充放电效率对称假设，则两单向效率可按往返效率的平方根拆分。”
- 不能支撑：附件实际测量点、Q1 的具体数值、真实设备在所有工况下对称或恒效、该拆分是唯一选择。
- GB/T 7714：BAŠIĆ H, BOBANAC V, PANDŽIĆ H. Determination of lithium-ion battery capacity for practical applications[J]. Batteries, 2023, 9(9): 459. DOI:10.3390/batteries9090459.

### Q1-L2 往返效率的一般定义

- 作者/机构：National Renewable Energy Laboratory (NREL)。
- 题名与年份：*2022 Annual Technology Baseline: Utility-Scale Battery Storage*，2022。
- DOI/稳定链接：<https://atb.nrel.gov/electricity/2022/utility-scale_battery_storage>。
- 精确定位：网页节 “Round-Trip Efficiency”。
- 可支撑的准确句子：“往返效率是储能系统可用输出电量与充入电量之比。”
- 不能支撑：Q1 附件采用的测量点、充放电效率拆分、项目特定效率值或成本结果。
- GB/T 7714：NATIONAL RENEWABLE ENERGY LABORATORY. 2022 annual technology baseline: utility-scale battery storage[EB/OL]. (2022)[2026-09-12]. https://atb.nrel.gov/electricity/2022/utility-scale_battery_storage.

### Q1-L3 AC/DC 连接边界

- 作者/机构：National Renewable Energy Laboratory (NREL)，System Advisor Model (SAM) 团队。
- 题名与年份：*System Advisor Model Help*，2025。
- DOI/稳定链接：<https://sam.nrel.gov/images/web_page_files/sam-help-2025-4-16.pdf>。
- 精确定位：PDF 约 p.334，“Battery Cell and System > Battery Round Trip Efficiency”；分别给出 DC-connected 与 AC-connected 的效率链。
- 可支撑的准确句子：“系统往返效率的计算会随 AC/DC 连接方式及所计入的变换环节而改变，因此报告效率时必须声明系统边界。”
- 不能支撑：Q1 的系统边界已经由附件明确、某一种连接方式必然适用或某个效率数值真实有效。
- GB/T 7714：NATIONAL RENEWABLE ENERGY LABORATORY. System advisor model help[EB/OL]. (2025-04-16)[2026-09-12]. https://sam.nrel.gov/images/web_page_files/sam-help-2025-4-16.pdf.

### Q1-L4 有限时域末端效应

- 作者/机构：Karl-Kiên Cao，Katharina von Krbek，Manuel Wetzel，等。
- 题名与年份：*Classification and Evaluation of Concepts for Improving the Performance of Applied Energy System Optimization Models*，2019。
- DOI/稳定链接：<https://doi.org/10.3390/en12244656>。
- 精确定位：正式 PDF pp.19–20，§3.3.2；p.34，§4.3.1 “Discharge Effect”。
- 可支撑的准确句子：“有限或滚动优化时域若忽略储能循环/终端平衡，模型可能在时域末端人为放空储能，形成末端效应。”
- 不能支撑：固定终端值 `6000 kWh` 是唯一正确方案、终端等式不会扭曲结果、Q1 的节省幅度。
- GB/T 7714：CAO K K, VON KRBEK K, WETZEL M, et al. Classification and evaluation of concepts for improving the performance of applied energy system optimization models[J]. Energies, 2019, 12(24): 4656. DOI:10.3390/en12244656.

## 4. E 类结果的版本与外推边界

| 结果对象 | 附件/样本范围 | 版本与输出 | 可写范围 | 禁止外推 |
|---|---|---|---|---|
| Q1 正式结果 | 附件 1 单日 144 个 10 分钟时段；结果按附件 5 `result1.xlsx` 模板行序导出 | 审计基线 `9400e887...`；`output/result1.xlsx`、`output/q1_summary.csv`、`output/q1_validation.md` | “在该附件、参数和模型边界下”报告全天成本、调度和校验 | 不外推至其他园区、日期、年份、设备或市场规则 |
| 无储能对照 | 与储能方案完全同口径的项目基线 | 对照输出及成本分解 | 报告“相对模型基线”的差额/比例 | 不称现实世界因果收益，不称普适节省率 |

若论文中的任何数值无法回链至上述输出及其运行元数据，应降为“待核验”，不得用文献补足项目证据。

## 5. Q1 写作红线

- 禁止：“附件证明往返效率就是某测量边界。”改为：“本文在所声明的测量边界下采用该效率定义。”
- 禁止：“充放电效率均为往返效率平方根。”改为：“在对称拆分假设下取平方根。”
- 禁止：“园区不能售电。”改为：“基准模型假设不向电网售电。”
- 禁止：“并网容量无限。”改为：“模型未设置有限 PCC 功率上限。”
- 禁止：“年末 SOC 必须为 6000 kWh。”改为：“本文以固定终端 SOC 控制末端效应，并将其视为可检验假设。”
- 禁止：“储能节省了 X 元。”改为：“相对同口径无储能模型基线，目标值降低 X 元。”
- 禁止：“方案全局/现实最优。”改为：“在给定目标、变量、约束和求解设置下取得模型内最优解。”
- 禁止：“储能系统不会同时充放电。”改为：“在已列价格、市场和任务条件下存在不同时充放电的更优或等价替代，项目输出亦通过互斥审计。”

## 6. FIN 签字意见

Q1 的文献链可支撑效率定义、对称拆分条件、系统边界必要性和有限时域末端效应的一般说明；它不能支撑项目参数、附件解释或项目效果。论文提交前，所有固定效率、不售电、PCC 上限缺失及终端 SOC 均须保留 A 标签和局限说明；所有成本/节省句均须绑定 Q1 输出与同口径基线。
