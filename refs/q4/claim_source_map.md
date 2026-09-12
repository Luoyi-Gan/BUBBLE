# Q4 Claim–Source Map（FIN 证据链审计版）

## 1. 当前状态与版本门

- 讨论基线：`docs/discussion/q4-quant-finance-discussion.md`。
- 当前决策：D1–D4 均仍待队长确认。讨论稿建议限制预测只使用决策时点可得信息，并建议以交付时段价格 `p_t` 为主、调整时点价格 `p_tau` 为敏感性；两项建议均不是已签收题意。
- 实施权限：Q4 尚未获实现授权；当前 FIN 基线 `9400e887...` 没有正式 Q4 调度结果，也没有 `output/q4/`。
- 候选审计：远端候选 commit `08b0c5d657cc061337396f686984b3ce76df1af6` 含 `output/q4/q4_price_forecast_audit.csv`、`q4_price_forecast_causality.json`、`q4_price_forecast_twoday.json`。这些文件不在当前基线，且未由本任务升级为正式结果，只能作为“待验收候选证据”登记。

## 2. 高影响主张逐条审计

| 编号 | 论文拟写主张 | 类别 | 证据位置或推导条件 | 外部来源与定位 | 不支持什么 | 处理建议 | 状态 |
|---|---|---|---|---|---|---|---|
| Q4-00 | 附件 4 为 2025-01-01 至 12-31 的 365 日 × 144 个 10 分钟实现价格，首格为“日期\\时间”。 | F | `docs/discussion/q4-quant-finance-discussion.md` §2；候选解析器 `08b0c5d.../q4/data.py` 校验 366×145（含表头）、连续日期与时间标签。 | — | 不支持这些未来实现价格在 0:00 已知，也不提供独立日前预测。 | 实现值只用于发生后结算/回测或 oracle；决策使用因果预测。 | 可直接使用（因果边界） |
| Q4-01 | 讨论稿建议 Q4 的价格预测在每个决策时点只使用当时已知信息。 | A+L | D1 的候选信息集解释。 | Q4-L1，pp.438–440，§2、§3.2。 | 文献不证明项目特征工程实际无泄漏，也不替队长确认具体预测器。 | 队长先签收 D1，再由因果性审计文件逐字段验证。 | 待队长决策 D1 |
| Q4-02 | 滚动控制每次只实施首个动作，再随新状态/信息更新求解。 | L | 一般 MPC 机制。 | Q4-L2，pp.1819–1820，§III-D，Eq.(17) 及 §III-E。 | 不支持 Q4 的价格预测器、更新间隔、结算公式或目标函数。 | 方法原则与项目选项分句写。 | 可直接使用（一般方法） |
| Q4-03 | 价格、负荷和可再生出力可能存在联合依赖，联合建模具有方法学动机。 | L | 一般依赖建模说明。 | Q4-L3，Introduction、§3、§4.1。 | 不证明本附件存在同样依赖，也不证明 D4 必须采用某一种联合残差生成器。 | 先做附件联合诊断；D4 决策后再写项目方法。 | 可直接使用（一般动机） |
| Q4-04 | 完整情景轨迹应保留预测时段之间的相关结构。 | L | 时序情景的一般动机。 | Q4-L4，PDF p.5（正式 p.4）与 p.7（正式 p.6）。 | 不支持 Q4 的经验联合残差路径、场景数或概率权重已经合理。 | 项目方法须另给校准和敏感性。 | 可直接使用（一般方法） |
| Q4-05 | 讨论稿建议以交付时段价格 `p_t` 作为 Q4 主结算解释。 | A | D2 的候选结算解释。 | — | 不是由外部文献或附件自动推出的唯一解释。 | 队长先签收 D2；正文再明确“主解释”，并报告 `p_tau` 敏感性。 | 待队长决策 D2 |
| Q4-06 | 调整时点价格 `p_tau` 是 D2 下的替代结算敏感性候选。 | A | D2 的候选结算解释。 | — | 不支持称为次要且必然不影响结论。 | D2 签收后，两种解释并列表达并比较关键输出。 | 待队长决策 D2 |
| Q4-07 | CVaR 可描述尾部损失，并可借助辅助函数形成可优化表示。 | L | 风险度量的一般定义与数学形式。 | Q4-L5，PDF p.2；p.5，Eq.(4)、Theorem 1、Eq.(5)。 | 不支持风险置信度、权重或“必须纳入目标”的项目选择。 | D3 未决前只解释指标，不写已进入目标。 | 可直接使用（一般方法） |
| Q4-08 | 日成本 90%/95% 分位数、CVaR、最大日成本及相对价格 oracle 的 regret 可作为展示指标；它们是否进入主目标属于另一项决策。 | A | `docs/discussion/q4-quant-finance-discussion.md` 的风险指标表；当前尚无正式计算结果。 | Q4-L5 只支撑 CVaR 定义与表示。 | 不支持这些指标已经改善，也不支持用 regret 把 oracle 称为严格下界。 | 可预先列报告框架；D3 未确认前不得把 CVaR 或任意 lambda 写入主目标。 | 展示框架可用，结果待运行 |
| Q4-08a | 主目标采用期望成本、CVaR 仅展示或敏感性。 | A | Q4 讨论项 D3，尚未签字。 | Q4-L5 不能替代队长选择。 | 不证明风险中性更优，也不支持当前已采用该目标。 | 保持待决；若引入风险厌恶，滚动验证选择 alpha/lambda 并报敏感性。 | 待队长决策 D3 |
| Q4-09 | Q4 采用价格-负荷-PV 联合残差路径。 | A | Q4 讨论项 D4，尚未签字。 | Q4-L3、Q4-L4 只提供一般动机。 | 不证明这种实现优于独立价格情景或适合本附件样本量。 | 保持候选，补依赖诊断和方案敏感性。 | 待队长决策 D4 |
| Q4-10 | 候选价格审计可复核附件 4 的 2025 全年统计与两个审计日预测。 | E | 仅远端候选 `08b0c5d...` 的 3 个 `output/q4/` 文件。 | — | 不支持当前分支已经验收，不支持调度效果、其他年份或外部泛化。 | 合并/验收前只能写“候选审计显示”，并附 commit 和附件范围。 | 待验收候选 |
| Q4-11 | 使用全期实际价格的 oracle 结果可作为严格理论下界。 | A+M | 只有在目标方向、约束、可行域、结算和除信息外全部相同且可证明集合包含关系时才可能成立。 | — | 当前证据没有给出该可行域证明。 | 统一称“oracle/完美信息敏感性”，不得称严格下界。 | 禁止现写法 |
| Q4-12 | Q4 已得到正式年度经济性与风险改进结果。 | E | 当前基线无授权实现、无正式 Q4 调度输出。 | — | 候选预测审计不等于调度或经济性结果。 | 删除；等待 D3/D4、实现授权、运行与验收。 | 禁止使用 |

## 3. 外部来源卡片

### Q4-L1 因果样本外评价

- 作者/机构：Leonard J. Tashman。
- 题名与年份：*Out-of-Sample Tests of Forecasting Accuracy: An Analysis and Review*，2000。
- DOI/稳定链接：<https://doi.org/10.1016/S0169-2070(00)00065-0>。
- 精确定位：pp.438–439，§2；pp.439–440，§3.2 “Rolling origin”。
- 可支撑的准确句子：“预测评价应隔离保留样本以避免窥视，滚动起点应按每个预测时点可得的信息更新。”
- 不能支撑：候选 Q4 预测器实际无泄漏、附件 4 的预测精度或任一项目参数。
- GB/T 7714：TASHMAN L J. Out-of-sample tests of forecasting accuracy: an analysis and review[J]. International Journal of Forecasting, 2000, 16(4): 437-450. DOI:10.1016/S0169-2070(00)00065-0.

### Q4-L2 MPC 滚动执行

- 作者/机构：Alessandra Parisio，Evangelos Rikos，Luigi Glielmo。
- 题名与年份：*A Model Predictive Control Approach to Microgrid Operation Optimization*，2014。
- DOI/稳定链接：<https://doi.org/10.1109/TCST.2013.2295737>。
- 精确定位：pp.1819–1820，§III-D，Eq.(17) 后的滚动机制；§III-E 当前状态初始化。
- 可支撑的准确句子：“有限时域优化在每次更新时仅应用首个控制动作，并用最新状态移动时域后重新求解。”
- 不能支撑：Q4 的价格更新时刻、交付/调整结算解释、风险目标、联合残差方案或项目效果。
- GB/T 7714：PARISIO A, RIKOS E, GLIELMO L. A model predictive control approach to microgrid operation optimization[J]. IEEE Transactions on Control Systems Technology, 2014, 22(5): 1813-1827. DOI:10.1109/TCST.2013.2295737.

### Q4-L3 价格-需求-可再生能源的联合依赖

- 作者/机构：Fabrizio Durante，Angelica Gianfreda，Francesco Ravazzolo，Luca Rossini。
- 题名与年份：*A Multivariate Dependence Analysis for Electricity Prices, Demand and Renewable Energy Sources*，2022。
- DOI/稳定链接：<https://doi.org/10.1016/j.ins.2022.01.003>；开放版本 <https://arxiv.org/abs/2201.01132>。
- 精确定位：Introduction；§3 的多变量 copula 结构；§4.1 对 prices、demand、wind、solar 联合关系的实证分析。
- 可支撑的准确句子：“电价、需求与可再生能源变量可存在值得显式建模的多变量依赖，copula 可将边际建模与依赖结构分离。”
- 不能支撑：本项目附件必然呈现相同依赖、经验联合残差路径优于其他方案、D4 已被批准或模型有经济收益。
- GB/T 7714：DURANTE F, GIANFREDA A, RAVAZZOLO F, et al. A multivariate dependence analysis for electricity prices, demand and renewable energy sources[J]. Information Sciences, 2022, 590: 74-89. DOI:10.1016/j.ins.2022.01.003.

### Q4-L4 时序相关情景轨迹

- 作者/机构：Pierre Pinson，Henrik Madsen，Henrik Aalborg Nielsen，等。
- 题名与年份：*From Probabilistic Forecasts to Statistical Scenarios of Short-Term Wind Power Production*，2009。
- DOI/稳定链接：<https://doi.org/10.1002/we.284>；作者存档 <https://orbit.dtu.dk/files/4900902/pinsonetal_wpfscenarios_fin.pdf>。
- 精确定位：PDF p.5（正式 p.4）“Generating scenarios of wind power production”；PDF p.7（正式 p.6）“Scenario generation”，Eq.(11)–(12)。
- 可支撑的准确句子：“供多时段决策使用的统计情景应保留预测时段之间的依赖，并以完整轨迹输入决策问题。”
- 不能支撑：Q4 的三变量残差路径、场景生成算法、K 值、窗口、权重或对比结果。
- GB/T 7714：PINSON P, MADSEN H, NIELSEN H A, et al. From probabilistic forecasts to statistical scenarios of short-term wind power production[J]. Wind Energy, 2009, 12(1): 51-62. DOI:10.1002/we.284.

### Q4-L5 CVaR 定义与优化表示

- 作者/机构：R. Tyrrell Rockafellar，Stanislav Uryasev。
- 题名与年份：*Optimization of Conditional Value-at-Risk*，2000。
- DOI/稳定链接：<https://doi.org/10.21314/JOR.2000.038>；作者 PDF <https://sites.math.washington.edu/~rtr/papers/rtr179-CVaR1.pdf>。
- 精确定位：PDF p.2 对 β-CVaR 的定义；PDF p.5，Eq.(4)、Theorem 1、Eq.(5) 的辅助函数与最小化表示。
- 可支撑的准确句子：“CVaR 描述超过相应 VaR 阈值的尾部损失均值，并可通过带辅助变量的函数最小化表示嵌入优化。”
- 不能支撑：Q4 必须采用 CVaR、置信水平或风险权重取值、CVaR 只展示或进入目标的队长选择、任何风险改善结果。
- GB/T 7714：ROCKAFELLAR R T, URYASEV S. Optimization of conditional value-at-risk[J]. Journal of Risk, 2000, 2(3): 21-41. DOI:10.21314/JOR.2000.038.

## 4. A 类假设、局限与敏感性闭环

| A 类事项 | 当前口径 | 局限 | 必需处理 |
|---|---|---|---|
| 价格信息集 | D1 候选：仅使用决策时点可得信息 | 特征发布时间、缺失值处理也可能造成隐性泄漏 | 队长签收 D1 后，逐字段记录可用时点并滚动回测；oracle 单列 |
| 结算价格 | D2 候选：`p_t` 主、`p_tau` 敏感性 | 两种解释可能改变调节价值 | 队长签收 D2 后，同模型双口径并报，不只报方向一致时的一个结果 |
| 风险目标 D3 | 未决 | 展示 CVaR 与优化 CVaR 是不同问题 | 队长签字后固定目标；报告置信度/权重敏感性 |
| 情景依赖 D4 | 未决 | 联合模型可能样本不足，独立模型可能漏掉尾部共振 | 先做依赖诊断，再比较联合/简化方案 |
| oracle | 完美信息敏感性 | 信息、可行域或结算改变会破坏严格下界关系 | 未有集合证明前只称 oracle，不称下界 |
| 外推 | 附件 4 与项目期 | 非平稳电价机制和极端事件限制外推 | 结果只绑定附件、日期、版本和模型边界 |

## 5. FIN 签字意见

Q4 当前只能完成“方法证据与决策门”审计，不能形成正式结果证据链。D1 的因果价格口径、D2 的 `p_t/p_tau` 结算解释、D3 风险目标与 D4 情景依赖均仍待队长决策；在签收前只能写为讨论稿候选。远端 `08b0c5d...` 的价格审计只是待验收候选，不能等同于 Q4 已实施，更不能支撑成本或风险改善。所有 oracle 表述在缺少同可行域集合证明时必须删除“严格下界”。
