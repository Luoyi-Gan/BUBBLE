# C 题 Q1：90% 充放电效率的口径与系统边界（F2）

## 题面事实与待解决的歧义

**题给事实。** 附录 1 仅说明“储能设备的充放电效率为 90%”，未说明该数值是完整充放电循环的往返效率，还是充、放两个单程效率各为 90%，也未声明测量点位于电芯、直流侧 PCS 或公共母线交流侧。

因此，90% 的系统边界无法由题面唯一确定；以下主方案是可复核的建模解释，需由队长最终确认。

## 文献证据与适用边界

| 来源 | 可用论断 | 适用边界 | 本题使用方式 |
|---|---|---|---|
| NREL Annual Technology Baseline（2022） | 往返效率定义为“有用输出能量 / 有用输入能量”。 | 公用事业规模电池系统的性能假设；不能代替题目设备的实测值。 | 用于界定 \(\eta_{rt}\) 的能量意义。 |
| Bašić 等（2023），式 (12)–(13)、§3.2.1 | \(\eta_{rt}=\eta_c\eta_d\)；在仅给定往返效率且假定两个单程对称时，可取 \(\eta_c=\eta_d=\sqrt{\eta_{rt}}\)。论文同时提醒单程效率会随功率和温度变化。 | 电芯实验和容量估计；支持数学拆分，不证明社区储能的具体数值。 | 用于写出对称拆分和其局限性。 |
| Pinto 等（2022），式 (24)–(26) | 社区/微网 MILP 用独立的 \(\eta_{ch}\)、\(\eta_{dis}\) 表示充、放电损耗，并使用 \(\eta_{rt}=\eta_{ch}\eta_{dis}\)。 | 住宅能源社区微网；其市场、设备参数不能迁入本题。 | 支持 Q1 SOC 递推中分别设置 \(\eta_c\)、\(\eta_d\)。 |
| NREL SAM Help（2024），`Battery Dispatch FOM` | AC 接入与 DC 接入下的 RTE 由相应双向变换环节的效率乘积计算，测量边界会改变 RTE 的含义。 | SAM 软件的设备/变流器模型。 | 明确论文必须声明 Q1 的效率采用“公共母线侧储能整体”等效边界。 |

## 两种口径的数学后果

本项目定义：\(c_t\) 是公共母线侧输入储能的电量，\(d_t\) 是储能向负荷侧输出的电量，SOC 递推为

\[
E_t=E_{t-1}+\eta_c c_t-\frac{d_t}{\eta_d}.
\]

| 口径 | 参数设定 | 一次完整循环的结果 | 对 Q1 的影响 |
|---|---|---|---|
| **A：推荐待确认** | 将题给 90% 解释为系统/公共母线侧往返效率：\(\eta_{rt}=0.90\)，对称拆分 \(\eta_c=\eta_d=\sqrt{0.9}=0.948683\)。 | 输入 1 kWh，最终可向负荷送出 0.90 kWh。 | 与“充放电效率”作为整体循环效率的常见定义一致，避免把整体 90% 误写成 81%。 |
| **B：敏感性方案** | 将题给文字解释为充、放电单程效率各 90%：\(\eta_c=\eta_d=0.90\)。 | \(\eta_{rt}=0.9\times0.9=0.81\)；输入 1 kWh，最终送出 0.81 kWh。 | 损耗显著更大，应仅在论文敏感性比较中采用，除非队长确认题意明确指向单程效率。 |

## 推荐表述与模型决定

**推荐待队长确认：** 因题面以单个“90%”描述“储能设备的充放电效率”，且未分别给出充、放电两个数值，Q1 将其视为公共母线侧储能整体的往返效率，令 \(\eta_{rt}=0.90\)。在无单程效率数据时，为保持对称简化，取 \(\eta_c=\eta_d=\sqrt{0.90}\)。

可直接写入论文：

> 题面未给出效率的部件级测量边界，本文将 90% 视为储能设备公共母线侧的往返效率。为在 SOC 递推中刻画充、放电损耗，采用对称等效拆分 \(\eta_c=\eta_d=\sqrt{0.90}\)；并以充、放电各 90% 的口径作敏感性检验。

## 结论边界

1. 该解释是针对题目缺失系统边界的**本文假设**，不是由文献证明的设备事实。
2. 不应把电芯测试效率、PCS 直流侧效率和公共母线交流侧 RTE 混在同一公式中。
3. 不引入未给出的自放电、温度、功率相关效率或变流器损耗；这些属于 Q1 的模型简化与 Q2–Q4 的可扩展项。
4. **请队长确认：选择口径 A 作为主方案，口径 B 作为敏感性方案；确认后再修改 `docs/specs/q1.md`。**

## 参考文献（GB/T 7714）

[1] NATIONAL RENEWABLE ENERGY LABORATORY. Utility-Scale Battery Storage: 2022 Annual Technology Baseline[EB/OL]. [2026-09-10]. <https://atb.nrel.gov/electricity/2022/utility-scale_battery_storage>.

[2] BAŠIĆ H, BOBANAC V, PANDŽIĆ H. Determination of lithium-ion battery capacity for practical applications[J]. *Batteries*, 2023, 9(9): 459. DOI: [10.3390/batteries9090459](https://doi.org/10.3390/batteries9090459).

[3] PINTO E S, SERRA L, LÁZARO A P. Energy communities approach applied to optimize polygeneration systems in residential buildings: Case study in Zaragoza, Spain[J]. *Sustainable Cities and Society*, 2022, 82: 103885. DOI: [10.1016/j.scs.2022.103885](https://doi.org/10.1016/j.scs.2022.103885). 开放版本：<https://zaguan.unizar.es/record/151039/files/texto_completo.pdf>。

[4] NATIONAL RENEWABLE ENERGY LABORATORY. *SAM Help: Battery Storage—Battery Dispatch FOM* [EB/OL]. 2024-12-12 [2026-09-10]. <https://sam.nrel.gov/images/web_page_files/sam-help-2024-12-12.pdf>，`Battery Round Trip Efficiency` 与 `Charge Limits and Priority` 节。
