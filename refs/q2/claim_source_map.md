# Q2 Claim–Source Map（FIN 证据链审计版）

## 1. 版本隔离结论

Q2 存在两个不可混写的结果口径。论文引用结果前必须先标注 V1 或 V2；任何未标版本的“Q2 结果”均视为证据链不完整。

| 版本 | 方法与定位 | 结果证据 | 当前权限 | 论文处理 |
|---|---|---|---|---|
| V1：既有签字结果 | 固定 `K=8` 的既有风险调度；旧文档使用“全路径情景补救近似 + MPC”等表述 | `output/result2.xlsx` 覆盖 2025-02-01 至 12-31（334 日）；`output/q2_full_k8_risk/` 覆盖含 1 月预热的 365 日；`docs/reviews/q2-final-delivery-audit.md` | 当前已签字的正式结果口径 | 不混用 2–12 月工作簿成本与 1–12 月完整核算，不借 V2 文献重释为严格多阶段随机控制 |
| V2：policy-consistent 候选 | 单一基准预测的日前 LP + `K=8` 风险备用 + 残差匹配 10 min MPC；`m1/m2/m3`、`alpha` 为候选设计 | `docs/specs/q2-policy-consistent-redesign.md`、`output/q2_policy_consistent/validation.md`、`output/q2_policy_consistent/policy_consistency_audit.json` | C2-R2 验证态；`annual_run=false`，`candidate_result2_xlsx=false` | 只能写“候选方法通过 C2-R2 因果/一致性检查”；不得替换 V1，不得写全年正式效果 |

## 2. 高影响主张逐条审计

| 编号 | 论文拟写主张 | 类别 | 证据位置或推导条件 | 外部来源与定位 | 不支持什么 | 处理建议 | 状态 |
|---|---|---|---|---|---|---|---|
| Q2-00 | 附件 1 给出单日 144 时段基准字段；附件 2 的“小区负载”“光伏发电实际功率”两表给出 2025-01-01 至 12-31 的 365 日实现序列。 | F | `q2/data.py` 字段/表名校验；`docs/reviews/q2-data-and-forecast-audit.md` 的日期、缺失值与行序审计。 | — | 不支持把附件 2 当作决策时点已知的未来值，也不决定合同语义。 | 附件 2 只按因果历史构造预测或按发生时点用于执行/回测。 | 可直接使用 |
| Q2-01 | 两阶段随机规划区分先验决策与情景揭示后的补救决策。 | L | 一般方法定义。 | Q2-L1，Ch.2 “Two-stage problems”。 | 不证明 V1 是严格两阶段或多阶段模型。 | 仅在变量时序与信息集逐项对应后使用。 | 可直接使用（一般方法） |
| Q2-02 | V1 是固定 `K=8` 的既有签字结果。 | E | `output/result2.xlsx`：2025-02-01 至 12-31、334 日；`output/q2_full_k8_risk/`：2025 全年 365 日（含 1 月预热）；`docs/reviews/q2-final-delivery-audit.md`。 | — | 不证明 `K=8` 最优，不允许混用两种核算范围，也不证明 V2 已替代它。 | 结果句加 V1、明确 2–12 月或 1–12 月口径、输出和模型边界。 | 可直接使用（限定 V1） |
| Q2-03 | V1 的“全路径情景补救近似 + MPC”是项目实现描述。 | A+E | 旧实现与既有审计材料；需按代码变量的信息可见性解释。 | Q2-L1 只能提供概念对照。 | 不支持称为严格多阶段随机规划。 | 保留“近似”，避免升级术语。 | 需改写 |
| Q2-04 | 合同量 `q` 按合同规则支付，执行变量满足 `x<=q`。 | A | `docs/specs/q2-policy-consistent-redesign.md` 的候选合同语义。 | — | 不证明附件或现实合同必然采用该支付/履约规则。 | 写成 V2 建模假设；给出替代合同语义敏感性。 | 待队长确认语义 |
| Q2-05 | V2 的日前层使用单一基准预测并保留风险备用。 | A+E | V2 规范与 C2-R2 审计输出。 | Q2-L1 可解释先验/补救的一般区分。 | 不证明该架构优于 V1 或是唯一政策一致架构。 | 写“候选架构”，等 C2-R3 全年结果后再比较。 | 候选可描述 |
| Q2-06 | 滚动预测评估必须防止未来实际值泄漏。 | L | 因果预测与回测的一般规范。 | Q2-L2，pp.438–440，§2、§3.2。 | 不证明 V2 所有特征均无泄漏。 | 由 `policy_consistency_audit.json` 单独证明项目合规。 | 可直接使用（一般方法） |
| Q2-07 | MPC 每次仅实施当前控制量，再以新状态滚动求解。 | L | 一般 receding-horizon 机制。 | Q2-L3，pp.1819–1820，§III-D，Eq.(17) 及 §III-E。 | 不支持 V2 的 10 min 步长、48 h 窗口或具体目标。 | 文献支撑机制，项目规范支撑参数。 | 可直接使用（一般方法） |
| Q2-08 | 联合轨迹情景应保留预测时段间依赖。 | L | 情景方法的一般动机。 | Q2-L4，PDF p.5（正式 p.4）“Generating scenarios”；PDF p.7（正式 p.6）“Scenario generation”。 | 不证明负荷-PV 残差分布、`K=8` 或 28 日窗口已校准。 | 只写“一般上需保留依赖”；具体生成器由项目审计。 | 可直接使用（一般方法） |
| Q2-09 | PAM/k-medoids 可用真实观测中的 medoid 表示簇。 | L | 聚类算法的一般性质。 | Q2-L5，Ch.2，pp.68–125。 | 不证明 `K=8` 最优、簇频率是真实概率或尾部风险充分。 | 将 `K` 写成预注册设计参数并补敏感性。 | 可直接使用（一般方法） |
| Q2-10 | V2 每 14 日在此前 14 个已结束日上比较 `m1/m2/m3 × alpha∈{.60,.70,.80,.90}` 的 12 个候选组合。 | A+E | 候选和窗口定义见 V2 规范；全部受评分校准块的比较记录见 `output/q2_policy_consistent/validation.md`。 | — | 不支持全年闭环优于 V1；也不支持候选、14 日窗口或入选参数普适最优。 | 写“在该候选集与闭环校准协议下比较/入选”，报告选择频率。 | 可直接使用（限定 C2-R2） |
| Q2-11 | V2 的校准和执行审计排除了未来实际值。 | E | `output/q2_policy_consistent/policy_consistency_audit.json`：校准/执行 future actuals exclusion 为 true。 | Q2-L2 只提供一般原则。 | 不支持预测器具有外部数据集泛化能力。 | 附输出版本和审计字段；不写“完全无泄漏”超出已检项目。 | 可直接使用（限定审计项） |
| Q2-12 | V2 已完成全年正式运行并可导出新 `result2.xlsx`。 | E | 同一审计明确 `annual_run=false`、`candidate_result2_xlsx=false`。 | — | 现有证据直接否定该写法。 | 删除；等待 C2-R3 全年台账、K 与初始 SOC 敏感性。 | 禁止使用 |
| Q2-13 | 终端约束或未来价值项可用于减弱有限时域末端放空偏差。 | L+A | 一般末端效应为 L；Q2 的 48 小时结构、价值切面与跨日 SOC 是项目选择/审计。 | Q2-L6，正式 PDF pp.19–20 §3.3.2、p.34 §4.3.1。 | 不支持 48 小时是最优长度、具体价值函数准确，也不支持把 Q2 数值搬给 Q3。 | 一般作用引文与 Q2 数值审计分开；报告有/无价值项、边界和初始 SOC 敏感性。 | 需限定使用 |

## 3. 外部来源卡片

### Q2-L1 两阶段随机规划

- 作者/机构：Alexander Shapiro，Darinka Dentcheva，Andrzej Ruszczyński。
- 题名与年份：*Lectures on Stochastic Programming: Modeling and Theory*，第 3 版，2021。
- DOI/稳定链接：<https://doi.org/10.1137/1.9781611976595>。
- 精确定位：Chapter 2 “Two-stage problems”，先验决策、随机量实现与 recourse 的定义和标准形式。
- 可支撑的准确句子：“两阶段随机规划把随机信息揭示前的决策与揭示后按情景采取的补救决策分开。”
- 不能支撑：V1/V2 自动构成严格两阶段或多阶段模型、本项目合同语义、场景数、风险权重或效果。
- GB/T 7714：SHAPIRO A, DENTCHEVA D, RUSZCZYŃSKI A. Lectures on stochastic programming: modeling and theory[M]. 3rd ed. Philadelphia: Society for Industrial and Applied Mathematics, 2021. DOI:10.1137/1.9781611976595.

### Q2-L2 因果回测与滚动起点

- 作者/机构：Leonard J. Tashman。
- 题名与年份：*Out-of-Sample Tests of Forecasting Accuracy: An Analysis and Review*，2000。
- DOI/稳定链接：<https://doi.org/10.1016/S0169-2070(00)00065-0>。
- 精确定位：pp.438–439，§2 “Testing forecast accuracy”；pp.439–440，§3.2 “Rolling origin”。
- 可支撑的准确句子：“样本外评价应隔离保留样本以避免窥视污染；滚动起点评价随时间移动预测起点并只利用当时可得信息。”
- 不能支撑：V2 的特征、14 日校准窗、候选集合或预测精度已经合理。
- GB/T 7714：TASHMAN L J. Out-of-sample tests of forecasting accuracy: an analysis and review[J]. International Journal of Forecasting, 2000, 16(4): 437-450. DOI:10.1016/S0169-2070(00)00065-0.

### Q2-L3 滚动时域控制

- 作者/机构：Alessandra Parisio，Evangelos Rikos，Luigi Glielmo。
- 题名与年份：*A Model Predictive Control Approach to Microgrid Operation Optimization*，2014。
- DOI/稳定链接：<https://doi.org/10.1109/TCST.2013.2295737>。
- 精确定位：pp.1819–1820，§III-D，Eq.(17) 后的 receding-horizon 描述；§III-E 的当前状态初始化。
- 可支撑的准确句子：“MPC 在每个时刻求解有限时域问题，仅应用首个控制动作，再以更新后的状态移动时域并重新求解。”
- 不能支撑：Q2 的具体更新频率、预测长度、损失函数、指数权重或候选模型优越性。
- GB/T 7714：PARISIO A, RIKOS E, GLIELMO L. A model predictive control approach to microgrid operation optimization[J]. IEEE Transactions on Control Systems Technology, 2014, 22(5): 1813-1827. DOI:10.1109/TCST.2013.2295737.

### Q2-L4 时序相关的联合轨迹情景

- 作者/机构：Pierre Pinson，Henrik Madsen，Henrik Aalborg Nielsen，等。
- 题名与年份：*From Probabilistic Forecasts to Statistical Scenarios of Short-Term Wind Power Production*，2009。
- DOI/稳定链接：<https://doi.org/10.1002/we.284>；作者存档 <https://orbit.dtu.dk/files/4900902/pinsonetal_wpfscenarios_fin.pdf>。
- 精确定位：PDF p.5（正式 p.4）“Generating scenarios of wind power production”；PDF p.7（正式 p.6）“Scenario generation”，Eq.(11)–(12)。
- 可支撑的准确句子：“面向决策的完整预测轨迹应刻画多个预测时段之间的依赖，统计情景可由联合随机结构生成。”
- 不能支撑：本项目负荷-PV 残差满足同一分布、经验路径/聚类是唯一方案、`K=8` 或窗口长度最优。
- GB/T 7714：PINSON P, MADSEN H, NIELSEN H A, et al. From probabilistic forecasts to statistical scenarios of short-term wind power production[J]. Wind Energy, 2009, 12(1): 51-62. DOI:10.1002/we.284.

### Q2-L5 k-medoids / PAM

- 作者/机构：Leonard Kaufman，Peter J. Rousseeuw。
- 题名与年份：*Partitioning Around Medoids (Program PAM)*，1990。
- DOI/稳定链接：<https://doi.org/10.1002/9780470316801.ch2>。
- 精确定位：Chapter 2，pp.68–125，medoid 与 PAM 的定义及算法。
- 可支撑的准确句子：“PAM 以样本中的代表对象作为 medoid 来表征各簇。”
- 不能支撑：`K=8` 是最优场景数、簇频率等于真实概率、极端场景得到充分覆盖或项目效果。
- GB/T 7714：KAUFMAN L, ROUSSEEUW P J. Partitioning around medoids (program PAM)[M]//Finding groups in data: an introduction to cluster analysis. Hoboken: John Wiley & Sons, 1990: 68-125. DOI:10.1002/9780470316801.ch2.

### Q2-L6 有限时域末端效应

- 作者/机构：Karl-Kiên Cao，Katharina von Krbek，Manuel Wetzel，等。
- 题名与年份：*Classification and Evaluation of Concepts for Improving the Performance of Applied Energy System Optimization Models*，2019。
- DOI/稳定链接：<https://doi.org/10.3390/en12244656>。
- 精确定位：正式 PDF pp.19–20，§3.3.2；p.34，§4.3.1 “Discharge Effect”。
- 可支撑的准确句子：“有限或滚动时域若忽略储能循环/终端平衡，可能在时域末端人为放空储能；终端条件或跨期处理用于控制这类偏差。”
- 不能支撑：Q2 的 48 小时长度、价值切面数值、跨日边界或成本改善，也不能替代 Q3 的专属标定与审计。
- GB/T 7714：CAO K K, VON KRBEK K, WETZEL M, et al. Classification and evaluation of concepts for improving the performance of applied energy system optimization models[J]. Energies, 2019, 12(24): 4656. DOI:10.3390/en12244656.

## 4. A 类假设、局限与敏感性闭环

| A 类事项 | 假设 | 主要局限 | 必需处理 |
|---|---|---|---|
| 合同语义 | `q` 按合同规则支付，`x<=q` | 附件若是按实际交付或偏差结算，目标与最优策略会变化 | 队长确认主解释；至少比较替代合同语义 |
| 场景数 | 固定 `K=8` | 尾部覆盖和计算量的折中未经普适证明 | C2-R3 报 K 敏感性；此前只称设计参数 |
| 基准预测器 | `m1` 的负荷取最近至多 4 个同星期日，PV 取最近至多 7 日；`m2/m3` 为有限候选 | 结构与回退规则可能受季节/预热期影响 | 报负荷、PV、净负荷诊断和闭环成本；FIN 自适应预测器只作为同政策候选 |
| 残差池 | 最近至多 28 个完整历史日，PAM 压缩为 K=8 | 28 日、距离与簇频率都是估计选择，簇占比不是真实概率 | 比较替代窗口、K=4/8/12 与必要的等权情景；报告尾部覆盖 |
| 校准与风险分位 | 每 14 日用此前 14 个已结束日比较 `alpha∈{.60,.70,.80,.90}` | 候选集合和重选频率可能受非平稳性影响 | 报各 alpha 的选择频率、覆盖率和实现成本；不写行业最优 |
| 计算预算 | 若正文沿用 `T_max=0.20 s` | 这是团队计算预算，不是电力系统要求 | 报硬件/求解器/超时频率，并做预算敏感性或仅列实现限制 |
| 终端/初始 SOC | 每个时域按规范施加边界 | 可能带来起止时段偏差 | 完成 2 月初 SOC 与终端规则敏感性 |
| 近似时序 | V1/V2 对信息阶段作项目化简 | 不等同严格多阶段随机控制 | 方法名称保留“近似/候选”，列明每类变量可见信息 |

## 5. E 类结果写作模板

- V1：`在 V1（固定 K=8、既有签字口径）的附件样本和模型边界下，output/result2.xlsx 与 output/q2_full_k8_risk/ 给出……；该结果不外推至其他年份或合同语义。`
- V2：`在 C2-R2 候选验证中，output/q2_policy_consistent/ 记录了校准/执行的因果一致性检查；该阶段未完成正式全年运行，也未生成候选 result2.xlsx。`
- 禁止把 V1 数值与 V2 方法名拼成同一条结果句；禁止把 `deployed_days=365` 解释为 C2-R3 正式全年闭环运行。

## 6. FIN 签字意见

V1 仍是当前正式 Q2 结果，V2 仅是通过 C2-R2 检查的候选重构。文献只支撑两阶段、滚动起点、MPC、相关轨迹和 medoid 的一般方法，不支撑本项目合同语义、参数最优性或性能。C2-R3 全年台账、K 敏感性、2 月初 SOC 敏感性及候选工作簿未完成前，不得用 V2 替换 V1。
