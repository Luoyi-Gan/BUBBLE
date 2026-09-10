# C 题 Q1：SOC 边界与最低电量（F4）

## 题给硬约束

**题给约束。** 附录 1 给出储能额定容量 12000 kWh，并明确规定后继充放电过程中的电量必须保持在 1200–10800 kWh。因此 Q1 直接采用：

\[
1200\le E_t\le10800\quad (t=1,\ldots,144).
\]

其对应额定容量的 10%–90% SOC，可调度容量为

\[
10800-1200=9600\ \text{kWh}.
\]

1200 kWh 是本题的最低允许电量，不是由文献估计出的推荐阈值。

## 文献证据

| 来源 | 可用论断 | 适用边界 | 论文落点 |
|---|---|---|---|
| NREL System Advisor Model（SAM）Help，`Battery Dispatch FOM`，"Charge Limits and Priority" | 最低和最高 SOC 既限制可用于调度的能量，也影响充放电深度；深循环和快速循环会影响电池性能/寿命。 | SAM 的通用电池系统调度文档，SOC 取可用容量百分比；不针对本题电池化学体系给出 10% 或 90% 的统一推荐值。 | 模型假设：说明设置 SOC 上下界具有寿命与运行保护含义。 |
| Smith 等（2016），NREL/PR-5400-66708 | 技术报告将 SOC 运行窗口列为影响电池老化和寿命管理的系统设计因素之一。 | 锂离子电池寿命管理的技术报告，不能用于指定本题 SOC 上下界数值。 | 模型评价：未显式计入退化成本的局限性。 |

## 参考文献（GB/T 7714）

[1] NATIONAL RENEWABLE ENERGY LABORATORY. *SAM Help: Battery Storage—Battery Dispatch FOM* [EB/OL]. 2024-12-12 [2026-09-10]. <https://sam.nrel.gov/images/web_page_files/sam-help-2024-12-12.pdf>，第 333 页；网页镜像：<https://samrepo.nrelcloud.org/help/battery_dispatch_fom.html>。

[2] SMITH K, SHI Y, WOOD E, et al. Optimizing battery usage and management for long life[R]. Golden, CO: National Renewable Energy Laboratory, 2016. NREL/PR-5400-66708. <https://research-hub.nlr.gov/en/publications/optimizing-battery-usage-and-management-for-long-life-nrel-nation-2/>。

## 为什么 Q1 不额外加入运行储备

Q1 已给定 10%–90% 的硬边界，且当天电价、负荷和光伏预测均作为已知输入。再人为提高最低 SOC 或降低最高 SOC，会在没有题目参数支撑的情况下缩小可用容量、改变最优成本，属于新增主观假设。因此 Q1 不另设不确定性储备；预测误差、保供需求和额外储备只在 Q2–Q4 的不确定性分析中讨论。

## 结论边界与队长确认

- 文献只支持“SOC 窗口影响调度和寿命”，**不支持**用任何外部推荐值替换题给的 1200/10800 kWh。
- Q1 的硬约束来源为题面附录 1，而非文献。
- **请队长确认：是。**
