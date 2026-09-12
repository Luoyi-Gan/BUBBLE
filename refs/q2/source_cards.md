# Q2 外部来源证据卡

等级说明：`A` 为高度相关的同行评议来源，`B` 为权威教材/机构报告，`C` 为领域相近但市场或对象不同的类比来源，`X` 为只可写在扩展或局限中的来源。

## 一、两阶段随机规划与信息结构

### Q2-R01　Birge & Louveaux (2011) — 两阶段补救与信息价值【B】

- 文献：*Introduction to Stochastic Programming*, 2nd ed., Springer.
- DOI：<https://doi.org/10.1007/978-1-4614-0237-4>。
- 精确落点：“The Value of Information and the Stochastic Solution”, pp.163–177；“Two-Stage Recourse Problems”, pp.181–263；“Multistage Stochastic Programs”, pp.265–287。
- 支持：不确定量实现前决定一阶段变量，实现后允许情景相关补救；可解释完全信息基准与随机解价值。
- 不支持：不规定本题计划购电、5 倍价格、场景数或风险参数。

### Q2-R02　Shapiro, Dentcheva & Ruszczyński (2021) — 非预见性与风险建模【B】

- 文献：*Lectures on Stochastic Programming: Modeling and Theory*, 3rd ed., SIAM.
- DOI：<https://doi.org/10.1137/1.9781611976595>。
- 支持：随机规划的一阶段/多阶段决策、非预见性、补救、风险度量和近似理论。
- 本题落点：说明所有场景共享日前 `q_t`，而 `x,e,c,d,w,E` 可随场景变化。
- 不支持：不能把书中的某种风险度量写成当前模型实际用了它。

### Q2-R03　Rockafellar & Uryasev (2000) — CVaR 的标准定义【A/X】

- 文献：*Optimization of Conditional Value-at-Risk*, Journal of Risk, 2(3), 21–41.
- DOI：<https://doi.org/10.21314/JOR.2000.038>。
- 用途：只用于明确“CVaR 是另一种尾部风险目标，可作扩展”。
- 重要边界：当前 Q2 没有 CVaR 目标或辅助变量，不能引用此文把经验分位下限称为 CVaR。

## 二、预测、回测和不确定性表达

### Q2-R04　Hong & Fan (2016) — 概率负荷预测【A】

- 文献：*Probabilistic Electric Load Forecasting: A Tutorial Review*, International Journal of Forecasting, 32(3), 914–938.
- DOI：<https://doi.org/10.1016/j.ijforecast.2015.11.011>。
- 精确落点：§1 对负荷预测业务用途和预测区间/分位的定义；§5 对概率预测生成、评价与价值的综述。
- 支持：负荷预测应量化不确定性并服务运营决策；可用分位/区间表达风险。
- 不支持：不证明“最近 4 个同星期日均值”是最优方法，也不规定风险分位 `α`。

### Q2-R05　Antonanzas et al. (2016) — PV 功率预测综述【A】

- 文献：*Review of Photovoltaic Power Forecasting*, Solar Energy, 136, 78–111.
- DOI：<https://doi.org/10.1016/j.solener.2016.06.069>。
- 支持：PV 波动使预测对电网运行和经济调度重要；不同预测时域、输入来源和评价方法应明确。
- 不支持：不证明 7 日历史均值或本项目误差分布最优。

### Q2-R06　Sengupta et al. (2024) — 太阳资源与 PV 预测最佳实践【B】

- 文献：*Best Practices Handbook for the Collection and Use of Solar Resource Data for Solar Energy Applications*, 4th ed.
- DOI：<https://doi.org/10.2172/2448063>；开放记录：<https://elib.dlr.de/208148/>；NREL PDF：<https://www.nrel.gov/docs/fy24osti/88300.pdf>。
- 精确落点：第 12 章，尤其 §12.4（solar radiation and power forecasting）。
- 支持：历史与亚小时太阳资源数据、预测和质量控制对于 PV 性能与并网运行至关重要。
- 不支持：不提供本题 PV 序列或模型参数。

### Q2-R07　Tashman (2000) — rolling-origin 样本外评价【A】

- 文献：*Out-of-Sample Tests of Forecasting Accuracy: An Analysis and Review*, International Journal of Forecasting, 16(4), 437–450.
- DOI：<https://doi.org/10.1016/S0169-2070(00)00065-0>。
- 精确落点：§2–4；§3 比较 fixed-origin 与 rolling-origin。
- 支持：逐个预测起点、只用当时可得样本并跨多个测试期评价，可提高时间序列回测的可复核性。
- 不支持：不规定项目的训练窗口、模型结构或 MAE 阈值。

### Q2-R08　Hyndman & Koehler (2006) — 预测误差指标【A/C】

- 文献：*Another Look at Measures of Forecast Accuracy*, International Journal of Forecasting, 22(4), 679–688.
- DOI：<https://doi.org/10.1016/j.ijforecast.2006.03.001>。
- 支持：选择误差指标时应考虑尺度、零值和跨序列可比性；适合在预测审计中解释为何同时报告绝对误差与尺度化指标。
- 不支持：本项目的费用目标不能被纯预测误差指标替代。

### Q2-R09　Pinson et al. (2009) — 保留时序依赖的轨迹场景【A/C】

- 文献：*From Probabilistic Forecasts to Statistical Scenarios of Short-Term Wind Power Production*, Wind Energy, 12(1), 51–62.
- DOI：<https://doi.org/10.1002/we.284>。
- 支持：多时段决策需要能够保留跨预测步相关性的统计轨迹，而不只是逐时独立边际分布。
- 不支持：对象是风电，不证明负荷–PV 联合残差服从同一模型；本题使用的是历史轨迹经验法。

## 三、场景缩减、medoid 与稳健尺度

### Q2-R10　Dupačová, Gröwe-Kuska & Römisch (2003) — 场景缩减【A】

- 文献：*Scenario Reduction in Stochastic Programming*, Mathematical Programming, 95, 493–511.
- DOI：<https://doi.org/10.1007/s10107-002-0331-0>。
- 支持：在规定场景数下选取原分布的代表子集，并重新分配概率，以控制与原离散分布的距离；文中含电力负荷场景树实例。
- 不支持：不证明 PAM、欧氏距离、价格权重或 `K=8` 是本题唯一正确的缩减法。

### Q2-R11　Kaufman & Rousseeuw (1990) — PAM / k-medoids【B】

- 文献：*Partitioning Around Medoids (Program PAM)*, in *Finding Groups in Data*, pp.68–125.
- DOI：<https://doi.org/10.1002/9780470316801.ch2>。
- 支持：PAM 用簇内真实对象作为 medoid，因此选出的代表场景是可解释、可追溯的历史轨迹，而非人工均值曲线。
- 不支持：PAM 本身不保证随机规划成本近似误差，也不选择 `K=8`。

### Q2-R12　Rousseeuw & Croux (1993) — MAD 稳健尺度【A】

- 文献：*Alternatives to the Median Absolute Deviation*, Journal of the American Statistical Association, 88(424), 1273–1283.
- DOI：<https://doi.org/10.1080/01621459.1993.10476408>；开放全文：<https://wis.kuleuven.be/stat/robust/papers/publications-1993/rousseeuwcroux-alternativestomedianad-jasa-1993.pdf>。
- 精确落点：文首给出 `1.4826×median|x_i-median(x)|` 及其稳健性讨论。
- 支持：MAD 可作抗异常值的尺度标准化，使负荷和 PV 残差不因量纲/极端点直接支配距离。
- 不支持：价格加权和多变量欧氏距离属于本项目设计。

## 四、概率风险与储备

### Q2-R13　Matos & Bessa (2011) — 概率预测驱动的储备决策【A/C】

- 文献：*Setting the Operating Reserve Using Probabilistic Wind Power Forecasts*, IEEE Transactions on Power Systems, 26(2), 594–603.
- DOI：<https://doi.org/10.1109/TPWRS.2010.2065818>；开放稿：<https://www.tse-fr.eu/sites/default/files/medias/stories/SEMIN_11_12/STATISTICS/bessa4.pdf>。
- 支持：概率预测可以通过风险指标映射为日前/日内储备水平，并在经济性与失负荷风险之间权衡。
- 不支持：对象是系统运行备用与风电，不规定本题的 `α`、候选集合或计划购电分位下限。

## 五、滚动时域、跨日状态和末端效应

### Q2-R14　Silvente et al. (2015) — 微网滚动时域更新【A/C】

- 文献：*A Rolling Horizon Optimization Framework for the Simultaneous Energy Supply and Demand Planning in Microgrids*, Applied Energy, 155, 485–501.
- DOI：<https://doi.org/10.1016/j.apenergy.2015.05.090>。
- 支持：在微网中周期更新不确定的生产/消费输入并反复重优化，可响应实际偏差。
- 不支持：其柔性负荷和 MILP 设备逻辑不是本题结构。

### Q2-R15　Silvente et al. (2018) — 随机规划与滚动时域结合【A】

- 文献：*A Rolling Horizon Approach for Optimal Management of Microgrids under Stochastic Uncertainty*, Chemical Engineering Research and Design, 131, 293–317.
- DOI：<https://doi.org/10.1016/j.cherd.2017.09.013>；开放版本：<https://discovery.ucl.ac.uk/id/eprint/1576229/>。
- 支持：两阶段情景随机规划可嵌入滚动时域，通过周期性更新预测来保持计算可行和适应性。
- 不支持：其场景内容、热负荷和柔性任务不能移植。

### Q2-R16　Parisio, Rikos & Glielmo (2014) — 微网 MPC【A】

- 文献：*A Model Predictive Control Approach to Microgrid Operation Optimization*, IEEE Transactions on Control Systems Technology, 22(5), 1813–1827.
- DOI：<https://doi.org/10.1109/TCST.2013.2295737>。
- 支持：微网可在约束下反复求解有限预测时域优化，并执行当前控制动作后向前滚动。
- 不支持：不证明本项目的前缀指数权重是严格贝叶斯后验。

### Q2-R17　Parisio et al. (2014) — MPC 的实验微网验证【A/C】

- 文献：*Use of Model Predictive Control for Experimental Microgrid Optimization*, Applied Energy, 115, 37–46.
- DOI：<https://doi.org/10.1016/j.apenergy.2013.10.027>。
- 支持：MPC 可用于微网经济运行，并在预测变化时更新控制。
- 不支持：实验系统、价格、设备约束不同于本题。

### Q2-R18　La Tona, Di Piazza & Luna (2021) — 跨日 SOC 与滚动预测频率【A】

- 文献：*Effect of Daily Forecasting Frequency on Rolling-Horizon-Based EMS Reducing Electrical Demand Uncertainty in Microgrids*, Energies, 14(6), 1598.
- DOI：<https://doi.org/10.3390/en14061598>；开放全文：<https://hdl.handle.net/20.500.14243/398566>。
- 精确落点：§2，PDF 第 5 页，约束 (6)–(8)。
- 支持：SOC 按相邻时段递推，某日初始 SOC 继承前一日最终 SOC；滚动时使用新测得状态更新。
- 不支持：该案例的日间循环条件不能推出本题每天首末相等。

### Q2-R19　Luo et al. (2019) — 多时间尺度状态衔接【A/C】

- 文献：*Multi-Time-Scale Rolling Optimal Dispatch for Grid-Connected AC/DC Hybrid Microgrids*, Processes, 7(12), 961.
- DOI：<https://doi.org/10.3390/pr7120961>；全文：<https://www.mdpi.com/2227-9717/7/12/961>。
- 精确落点：§1、§4.2–4.3，式 (11)–(13)。
- 支持：上一调度周期终态成为下一周期初态；忽略周期间状态衔接会损害连续调节能力。
- 不支持：不能据此确定本题 LP/MILP、终端储备或参数。

### Q2-R20　Cao et al. (2019) — 滚动窗口的储能末端效应【A】

- 文献：*Classification and Evaluation of Concepts for Improving the Performance of Applied Energy System Optimization Models*, Energies, 12(24), 4656.
- DOI：<https://doi.org/10.3390/en12244656>；开放版本：<https://elib.dlr.de/129439/>。
- 精确落点：§3.3.2，正式版 PDF 第 19–20 页；§4.3.1。
- 支持：有限滚动窗口会对跨时段储能产生边界/放空效应，重叠窗口和终端处理可缓解但不会自动消失。
- 不支持：不规定本题必须采用固定终端 SOC 或 48 h。

## 六、对偶支持割与价值函数近似

### Q2-R21　Boyd & Vandenberghe (2004) — 对偶斜率与支持超平面【B】

- 文献：*Convex Optimization*, Cambridge University Press.
- DOI：<https://doi.org/10.1017/CBO9780511804441>；开放版：<https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf>。
- 精确落点：第 5 章，尤其 §5.6。
- 支持：最优对偶变量给出价值函数对约束扰动的局部下界/灵敏度，可构造凸价值函数的支持线。
- 不支持：不能单独证明本项目割集已全局足够；必须以 gap 审计验证。

### Q2-R22　Benders (1962) — 分解与最优性割【A/B】

- 文献：*Partitioning Procedures for Solving Mixed-Variables Programming Problems*, Numerische Mathematik, 4, 238–252.
- DOI：<https://doi.org/10.1007/BF01386316>。
- 支持：把连接变量与子问题分开，并由子问题对偶信息向主问题添加割的经典原理。
- 不支持：Q2 代码不是完整 Benders 算法；正文宜说“借鉴对偶支持割思想”。

### Q2-R23　Pereira & Pinto (1991) — 随机对偶动态规划【A/C】

- 文献：*Multi-Stage Stochastic Optimization Applied to Energy Planning*, Mathematical Programming, 52, 359–375.
- DOI：<https://doi.org/10.1007/BF01582895>。
- 支持：在能源规划中用对偶动态规划逐步逼近未来成本函数。
- 不支持：本项目只有短期 48 h 次日价值近似，不应宣称实现了完整 SDDP。

## 七、弃光、电池边界与论文规范

### Q2-R24　Jorgenson, Hale & Cowiestoll (2020) — 弃光机制【B】

- 文献：*Managing Solar Photovoltaic Integration in the Western United States: Power System Flexibility Requirements and Supply*, NREL/TP-6A20-72471.
- 全文：<https://www.nrel.gov/docs/fy21osti/72471.pdf>；定位：执行摘要 vii、§1 p.4。
- 支持：系统无法继续吸收/外送剩余光伏时发生削减。
- 不支持：不证明本题禁止售电或存在美国西部输电条件。

### Q2-R25　Case et al. (2018) — 储能吸收出口受限 PV【B/C】

- 文献：*Grid Ready: Strategies for Interconnecting Large-Scale PV in New York City*, NREL/TP-7A40-71344.
- 全文：<https://www.nrel.gov/docs/fy19osti/71344.pdf>；定位：§3.1，PDF p.7。
- 支持：PV 超过出口限制可被削减，储能可吸收部分剩余。
- 不支持：不移植纽约费率或出口容量。

### Q2-R26　Bašić, Bobanac & Pandžić (2023) — RTE 拆分【A】

- DOI：<https://doi.org/10.3390/batteries9090459>；定位：式 (2)、(12)–(13)、§3.2.1。
- 支持：Q2 沿用 `η_rt=η_cη_d` 及对称等效拆分的数学口径。
- 不支持：真实设备效率随工况变化；不能据此证明常效率模型完全真实。

### Q2-R27　Pinto, Serra & Lázaro (2022) — 社区微网储能状态方程【A/C】

- DOI：<https://doi.org/10.1016/j.scs.2022.103885>；定位：式 (24)–(26)。
- 支持：独立充/放效率和跨时段 SOC 的社区能源系统表达。
- 不支持：案例市场和设备参数不可移植。

### Q2-R28　Hashmi et al. (2019) — 预测+MPC 的储能 LP【A/C】

- DOI：<https://doi.org/10.1109/SMARTGRIDCOMM.2019.8909753>；预印本：<https://arxiv.org/abs/1905.00418>。
- 支持：含价格、负荷、可再生和电池约束的 LP 可结合预测与 MPC。
- 不支持：净计量售电机制不同，不证明本题的计划额度/紧急采购结构。

### Q2-R29　DeCarolis et al. (2017) — 能源优化建模最佳实践【A/B】

- 文献：*Formalizing Best Practice for Energy System Optimization Modelling*, Applied Energy, 194, 184–198.
- DOI：<https://doi.org/10.1016/j.apenergy.2017.03.001>。
- 支持：模型边界、输入、假设、不确定性、敏感性和可复现材料应透明披露。
- 不支持：不提供本题具体数学结构或参数。

## 当前方案中没有“一对一外部出处”的设计

以下内容依靠本项目动机、回测与审计，而非某篇文献直接规定：

- 负荷“最近 4 个同星期日”与 PV“最近 7 天”的预测窗口；
- 历史残差池最多 28 天；
- 价格加权的 MAD 标准化欧氏距离；
- 固定 `K=8`，以及首 28 天 `K=1`；
- 每 14 天在四个 `α` 候选中校准；
- 根据已观测残差前缀作指数距离重加权；
- 48 h 下一日价值和 `chord-vs-cut≤1 元` 的验收阈值；
- 最大正净残差压力日只作诊断、不自动进入期望。

这些可以写成“本文设计/经滚动回测选择”，并用 `output/q2_full_k8_risk/` 下的审计文件支撑；不应写成“依据文献取值”。
