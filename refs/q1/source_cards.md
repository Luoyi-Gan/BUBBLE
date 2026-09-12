# Q1 外部来源证据卡

## 核心来源

### Q1-R01　Bašić, Bobanac & Pandžić (2023) — 效率定义与对称拆分【A】

- 文献：*Determination of Lithium-Ion Battery Capacity for Practical Applications*, Batteries, 9(9), 459.
- DOI：<https://doi.org/10.3390/batteries9090459>；全文：<https://www.mdpi.com/2313-0105/9/9/459>。
- 精确落点：式 (2) 定义循环/往返效率；式 (12)–(13) 给出充、放效率乘积及对称平方根拆分；§3.2.1 讨论效率随工况变化。
- 支持：`η_rt=η_cη_d`；只给 RTE 时可在“对称”假设下取平方根。
- 不支持：不能证明本题设备的两个单程效率真实相等，也不能替题面决定 90% 的测量边界。

### Q1-R02　NREL Annual Technology Baseline — RTE 的工程定义【B】

- 来源：NREL, *Utility-Scale Battery Storage: Annual Technology Baseline*。
- 入口：<https://atb.nrel.gov/electricity/2022/utility-scale_battery_storage>；历史版：<https://atb-archive.nrel.gov/electricity/2019/index.html?m=1&s=omcfmdpr&t=st>。
- 支持：往返效率是储能系统有用输出能量与输入能量之比；可用于解释参数物理含义。
- 不支持：ATB 的技术/成本假设不能作为本题具体设备的实测值。

### Q1-R03　Pinto, Serra & Lázaro (2022) — 社区能源系统中的分离效率【A/C】

- 文献：*Energy communities approach applied to optimize polygeneration systems in residential buildings: Case study in Zaragoza, Spain*, Sustainable Cities and Society, 82, 103885.
- DOI：<https://doi.org/10.1016/j.scs.2022.103885>；开放版本：<https://zaguan.unizar.es/record/151039/files/texto_completo.pdf>。
- 精确落点：式 (24)–(26)。
- 支持：社区/微网优化可用独立充电效率、放电效率和 SOC 递推表达损耗。
- 不支持：西班牙案例的设备规模、市场价格、热系统和经济参数不可移植到本题。

### Q1-R04　Hashmi et al. (2019) — 储能套利的线性规划【A】

- 文献：*Optimal Storage Arbitrage under Net Metering using Linear Programming*, IEEE SmartGridComm 2019, 1–7.
- DOI：<https://doi.org/10.1109/SMARTGRIDCOMM.2019.8909753>；预印本：<https://arxiv.org/abs/1905.00418>。
- 支持：含电池容量、爬坡/功率、效率损失、刚性负荷、可再生出力和分时价格的储能套利可写为 LP；文中也把预测嵌入 MPC。
- 不支持：其净计量与售电机制不同于本题，不能据此给 Q1 增加售电。

### Q1-R05　DiOrio, Denholm & Hobbs (2020) — PV+储能价格响应调度【A】

- 文献：*A Model for Evaluating the Configuration and Dispatch of PV Plus Battery Power Plants*, Applied Energy, 262, 114465.
- DOI：<https://doi.org/10.1016/j.apenergy.2019.114465>；NREL 资料入口：<https://sam.nrel.gov/battery-storage/battery-publications.html>。
- 支持：PV+电池可根据预测价格做滚动优化，模型同时考虑配置、变流损耗、容量和可捕获的受限/削减能量。
- 不支持：研究对象为大型电站，收益最大化和本题社区购电费最小化并非同一市场。

### Q1-R06　NREL SAM Help (2025) — SOC、充电来源和计量边界【B】

- 文献：NREL, *SAM Help: Battery Storage—Battery Dispatch FOM*, 2025-04-16。
- 官方 PDF：<https://sam.nrel.gov/images/web_page_files/sam-help-2025-4-16.pdf>；网页镜像：<https://samrepo.nrelcloud.org/help/battery_dispatch_fom.html>。
- 精确落点：PDF 第 334 页附近，“Charge Limits and Priority”“Front-of-meter Storage Dispatch Options”。
- 支持：最小/最大 SOC 限制可用调度能量；初始 SOC 是仿真起点；充电来源、并网限制和变流损耗取决于系统边界。
- 不支持：SAM 默认 SOC 百分比不是本题参数，也不能证明外网无限供电。

### Q1-R07　Watari et al. (2021) — 初始/终端 SOC 与日内边界【A/C】

- 文献：*Multi-time Scale Energy Management Framework for Smart PV Systems Mixing Fast and Slow Dynamics*, Applied Energy, 289, 116671.
- DOI：<https://doi.org/10.1016/j.apenergy.2021.116671>；开放版本：<https://imec-publications.be/bitstreams/c1a60c11-f959-49d3-adb1-75c335266983/download>。
- 精确落点：表 1、式 (28)、§4.3。
- 支持：日内 PV—电池调度将初始 SOC 作为状态输入，并用终端设定防止贪婪放空。
- 不支持：不能为本题指定 6000 kWh；也不意味着全年 Q2 每天应首末相等。

### Q1-R08　Verhagen, Hu & Harmsen (2026) — 日前 BESS 的终端 SOC【A/C】

- 文献：*Evaluating Non-Firm Grid Connections for Battery Energy Storage Systems: A Co-Optimization Case Study of the Netherlands*, Energy Policy, 208, 114903.
- DOI：<https://doi.org/10.1016/j.enpol.2025.114903>；开放全文：<https://research-portal.uu.nl/files/273724276/1-s2.0-S0301421525004100-main.pdf>。
- 精确落点：§3.5.2，式 (14)–(15)。
- 支持：初始 SOC 是日前优化输入；缺少终端约束可能使模型在日末为提高目标值而放空。
- 不支持：荷兰非牢固并网市场参数不能迁入本题。

### Q1-R09　Jorgenson, Hale & Cowiestoll (2020) — 弃光的一般机制【B】

- 文献：*Managing Solar Photovoltaic Integration in the Western United States: Power System Flexibility Requirements and Supply*, NREL/TP-6A20-72471.
- 官方全文：<https://www.nrel.gov/docs/fy21osti/72471.pdf>。
- 精确落点：执行摘要第 vii 页；正文 §1 第 4 页。
- 支持：系统不能继续吸收或外送剩余 PV 时会发生削减。
- 不支持：美国西部输电条件不能证明本题存在同样的网络约束。

### Q1-R10　Case et al. (2018) — 出口约束、弃光与储能【B/C】

- 文献：*Grid Ready: Strategies for Interconnecting Large-Scale PV in New York City*, NREL/TP-7A40-71344.
- 官方全文：<https://www.nrel.gov/docs/fy19osti/71344.pdf>。
- 精确落点：§3.1，PDF 第 7 页。
- 支持：超过出口约束的 PV 可削减，储能可吸收部分富余能量。
- 不支持：纽约费率、出口上限和成本不能移植。

### Q1-R11　Boyd & Vandenberghe (2004) — 对偶、KKT 与敏感性【B】

- 文献：*Convex Optimization*, Cambridge University Press.
- DOI：<https://doi.org/10.1017/CBO9780511804441>；作者开放版：<https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf>。
- 精确落点：第 5 章，尤其 §5.5 KKT、§5.6 perturbation and sensitivity analysis。
- 支持：在强对偶等条件成立时，对偶变量可解释为约束右端微小变化的局部边际价值。
- 不支持：影子价格不能跨越基变化或大范围扰动机械外推。

## 物理真实性与局限来源

### Q1-R12　Nazir & Almassalkhi (2023) — 充放互斥约束问题【A/X】

- 文献：*Guaranteeing a Physically Realizable Battery Dispatch Without Charge-Discharge Complementarity Constraints*, IEEE Transactions on Smart Grid, 14(3), 2473–2476.
- DOI：<https://doi.org/10.1109/TSG.2021.3109805>；机构页：<https://www.pnnl.gov/publications/guaranteeing-physically-realizable-battery-dispatch-without-charge-discharge>。
- 支持：同时充放电互斥是电池调度的物理可实现性问题；直接互补约束会增加非凸性，特定线性构造可避免它。
- 不支持：文中的保证依赖其特定模型条件，不能自动证明本项目的更简单 LP 松弛。

### Q1-R13　Joshi et al. (2021) — 非同时充放的充分条件【C/X】

- 文献：*A Sufficient Condition to Guarantee Non-Simultaneous Charging and Discharging of Household Battery Energy Storage*，预印本。
- 链接：<https://arxiv.org/abs/2104.06267>。
- 支持：可用于讨论何时连续优化会自然给出非同时充放。
- 不支持：它是补充理论线索，不能替代对本项目每个时段 `c_t d_t` 的数值审计。

### Q1-R14　Grimaldi et al. (2023) — 效率与老化依赖工况【A/X】

- 文献：*Ageing and Energy Performance Analysis of a Utility-Scale Lithium-Ion Battery for Power Grid Applications through a Data-Driven Empirical Modelling Approach*, Journal of Energy Storage, 65, 107232.
- DOI：<https://doi.org/10.1016/j.est.2023.107232>；开放记录：<https://iris.polito.it/handle/11583/2977810>。
- 支持：实测系统效率会随运行功率/服务类型变化，循环与老化应在更高保真模型中考虑。
- 不支持：该装置的效率与衰减率不能作为本题设备参数。

### Q1-R15　Smith et al. (2016) — SOC 窗口与寿命管理【B/X】

- 文献：*Optimizing Battery Usage and Management for Long Life*, NREL/PR-5400-66708.
- 官方全文：<https://www.nrel.gov/docs/fy16osti/66708.pdf>；机构记录：<https://research-hub.nlr.gov/en/publications/optimizing-battery-usage-and-management-for-long-life-nrel-nation-2/>。
- 支持：SOC 运行窗口、热管理和系统设计会影响老化与寿命。
- 不支持：不能把报告中的经验窗口替换题给 1200–10800 kWh。

### Q1-R16　DeCarolis et al. (2017) — 能源优化模型的可复现与边界披露【B】

- 文献：*Formalizing Best Practice for Energy System Optimization Modelling*, Applied Energy, 194, 184–198.
- DOI：<https://doi.org/10.1016/j.apenergy.2017.03.001>。
- 支持：清楚记录模型边界、假设、敏感性和可复现过程是能源系统优化的规范做法。
- 不支持：不提供本题任何具体参数。

## 最小引用组合

- **模型与效率段**：Q1-R04 + Q1-R01 + Q1-R03。
- **SOC 与终端段**：Q1-R06 + Q1-R07。
- **弃光与市场边界段**：Q1-R09 + Q1-R10，并明确“不售电”为本文假设。
- **灵敏度/影子价值段**：Q1-R11。
- **局限性段**：Q1-R12 + Q1-R14 + Q1-R15。
