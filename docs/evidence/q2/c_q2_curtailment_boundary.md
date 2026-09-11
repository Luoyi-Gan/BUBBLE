# C 题 Q2：无外送收益条件下的弃光边界（FQ2-3）

## 文献通用认识

当某时段可用光伏超过负荷、储能与外部系统可接纳能力时，为维持供需平衡，需要降低光伏实际利用量，即发生弃光。储能可以吸收一部分剩余光伏，但受功率、容量与 SOC 约束，不能保证消除全部弃光。

上述仅是一般物理/调度认识；**“本题不售电”不是文献结论，而是题面未给售电收益时采用的本文边界。**

## 证据卡 1：系统不能吸收或外送时的弃光

**来源定位：** Jorgenson、Hale 和 Cowiestoll（2020），执行摘要第 vii 页；正文第 1 节第 4 页。

**能支持：** 报告说明，当系统无法进一步下调其他资源或通过区域间传输吸收/外送多余功率时，名义可用的光伏会被削减。该定义支持“可用出力未被系统接纳即为弃光”。

**不能支持：** 研究对象是美国西部大电网，不能证明本小区存在相同的输电约束，也不能提供本题售电价、外送上限、弃光惩罚或储能参数。

## 证据卡 2：出口约束、弃光与储能的关系

**来源定位：** Case 等（2018），第 3.1 节“Mitigation Strategies”，PDF 第 7 页，策略 3–5。

**能支持：** 报告将“超过出口约束的光伏发电被削减”作为一种缓解策略，并将电池储能作为吸收光伏、满足出口约束的另一种策略。这支持在负荷、储能和外送均受限时显式建模弃光。

**不能支持：** 报告采用纽约市建筑、Con Edison 费率和特定出口测试，不能把其费率、出口容量、成本或“完美预见”移植到本题。

## 本题边界：只定义可用量，不虚构市场规则

若队长确认主模型采用“只购不售”，令 $P_{d,t}$ 为附件/预测给出的光伏**可用电量**，$w_{d,t}$ 为弃光量，则

\[
0\le w_{d,t}\le P_{d,t},\qquad
P^{\mathrm{use}}_{d,t}=P_{d,t}-w_{d,t}.
\]

一种清晰的公共母线能量平衡是

\[
g_{d,t}+u_{d,t}+P_{d,t}-w_{d,t}+d_{d,t}
=L_{d,t}+c_{d,t},
\]

其中 $g$ 为正常计划购电，$u$ 为实际紧急补购，$c,d$ 为公共母线侧充、放电。此式只表达电量守恒；它不追踪“哪一度光伏先给负荷还是先充电”的物理标签。

### 不应擅自加入

- 售电变量、售电价、净计量补贴或反向潮流收益；
- 题面未给的 PCC 外送上限；
- 题面未给的弃光惩罚系数；
- “光伏必须优先满足负荷”的可观测能流顺序。

如团队日后决定允许外送，应另设外送变量和价格/容量规则，并将其作为新情形，不能与当前不售电结果直接混报。

## 结果复核

- 检查每个时段 $w_{d,t}\ge0$、$w_{d,t}\le P_{d,t}$ 及母线平衡残差。
- 同时报弃光电量 $\sum w$ 与弃光率 $\sum w/\sum P$，并注明分母为可用光伏总量。
- 对高弃光时段核查负荷、SOC 上限、充电功率上限是否共同造成剩余；不要只凭相关性给出单一因果。
- 比较无储能基准时，保持相同的不售电边界和相同数据，才能把弃光差异归因于储能调度。

## 参考文献（GB/T 7714）

[1] JORGENSON J, HALE E, COWIESTOLL B. *Managing solar photovoltaic integration in the Western United States: Power system flexibility requirements and supply*[R]. Golden, CO: National Renewable Energy Laboratory, 2020. NREL/TP-6A20-72471. [NREL 官方 PDF](https://www.nrel.gov/docs/fy21osti/72471.pdf)。

[2] CASE T, LIBURD S, REILLY L, et al. *Grid Ready: Strategies for interconnecting large-scale PV in New York City*[R]. Golden, CO: National Renewable Energy Laboratory, 2018. NREL/TP-7A40-71344. [NREL 官方 PDF](https://www.nrel.gov/docs/fy19osti/71344.pdf)。
