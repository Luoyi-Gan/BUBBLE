# C 题 Q1：文献线索台账

**用途：** 记录检索到的可复核来源、可支持的论断和使用边界。文献不能替代题目给定的容量、SOC 边界、电价或市场规则；正式引用前由 FIN/ACCT 复核链接、页码和 GB/T 7714 格式。

## A. 已采用：初始/终端 SOC（F3）

| 编号 | 来源与链接 | 可支持的论断 | 精确位置 | 状态 |
|---|---|---|---|---|
| L1 | Watari D, et al. (2021), *Applied Energy*, 289, 116671, DOI [10.1016/j.apenergy.2021.116671](https://doi.org/10.1016/j.apenergy.2021.116671)；[开放版](https://imec-publications.be/server/api/core/bitstreams/c1a60c11-f959-49d3-adb1-75c335266983/content) | 在 PV—储能日内管理中，将初始 SOC 与终端 SOC 同设，并用终端设定避免贪婪地在期末放空。 | 表 1、式 (28)、§4.3。 | 已写入 `c_q1_initial_soc.md`。 |
| L2 | Verhagen P, Hu J, Harmsen R. (2026), *Energy Policy*, 208:114903, DOI [10.1016/j.enpol.2025.114903](https://doi.org/10.1016/j.enpol.2025.114903)；[开放全文](https://research-portal.uu.nl/ws/portalfiles/portal/273724276/1-s2.0-S0301421525004100-main.pdf) | 日前 BESS 模型将初始 SOC 作为状态输入；缺少日末 SOC 约束会倾向于期末过度放电以增加收益。 | §3.5.2，式 (14)–(15)，PDF 第 6 页。 | 已写入 `c_q1_initial_soc.md`。 |
| L3 | Lobos-Cornejo S, et al. (2025), *Sci*, 7(2):73, DOI [10.3390/sci7020073](https://doi.org/10.3390/sci7020073) | 微网算例将初、末 SOC 同设为 0.5，并将其解释为保持能量储备。 | 式 (16)–(18)。 | 备用交叉来源；正式使用前复核作者页码。 |

## B. 已采用：SOC 边界与寿命（F4）

| 编号 | 来源与链接 | 可支持的论断 | 精确位置 | 状态 |
|---|---|---|---|---|
| L4 | NREL. *SAM Help: Battery Storage—Battery Dispatch FOM* (2024) [PDF](https://sam.nrel.gov/images/web_page_files/sam-help-2024-12-12.pdf)，[网页](https://samrepo.nrelcloud.org/help/battery_dispatch_fom.html) | 最低/最高 SOC 同时影响可调度能量和循环深度；深循环和频繁切换会影响寿命/性能。 | “Charge Limits and Priority”，PDF 第 333 页。 | 已写入 `c_q1_soc_bounds.md`。 |
| L5 | Smith K, Shi Y, Wood E, et al. (2016). *Optimizing Battery Usage and Management for Long Life*, NREL/PR-5400-66708. [记录页](https://research-hub.nlr.gov/en/publications/optimizing-battery-usage-and-management-for-long-life-nrel-nation-2/) | SOC 运行窗口属于影响电池老化与寿命管理的设计因素。 | 摘要/报告主题；正式引用前应下载并定位页码。 | 已写入 `c_q1_soc_bounds.md`，作为补充。 |

## C. 已采用：效率口径（F2，待队长确认主口径）

| 编号 | 来源与链接 | 可支持的论断 | 使用限制 |
|---|---|---|---|
| L6 | NREL. [Utility-Scale Battery Storage: 2022 ATB](https://atb.nrel.gov/electricity/2022/utility-scale_battery_storage) | 往返效率是有用输出能量与有用输入能量之比。 | 公用事业系统性能定义，不赋予本题设备具体参数。 |
| L7 | Bašić H, Bobanac V, Pandžić H. (2023). *Batteries*, 9(9):459, DOI [10.3390/batteries9090459](https://doi.org/10.3390/batteries9090459) | \(\eta_{rt}=\eta_{ch}\eta_{dis}\)；若显式采用对称单程效率，则 \(\eta_{ch}=\eta_{dis}=\sqrt{\eta_{rt}}\)。 | 电芯实验；单程效率会随工况变化，不可视为本题实测。 |
| L8 | Pinto E S, Serra L, Lázaro A P. (2022). *Sustainable Cities and Society*, 82:103885, DOI [10.1016/j.scs.2022.103885](https://doi.org/10.1016/j.scs.2022.103885) | 社区微网 MILP 分别使用 \(\eta_{ch}\)、\(\eta_{dis}\)，且 \(\eta_{rt}=\eta_{ch}\eta_{dis}\)。 | 只借鉴 SOC 递推结构，不能移植其市场或设备参数。 |
| L9 | NREL. [SAM Help: Battery Dispatch FOM](https://samrepo.nrelcloud.org/help/battery_dispatch_fom.html) | AC/DC 接入方式会改变 RTE 所涵盖的变流环节，必须声明边界。 | 不能将 SAM 的 AC/DC 细节直接套到本题。 |

## D. 背景与方法线索（暂不作为 Q1 参数来源）

| 编号 | 来源与链接 | 可参考内容 | 禁止外推 |
|---|---|---|---|
| L10 | Watari D, et al. (2021), 同 L1 | 多时间尺度/MPC 下的 PV 预测和储能调度，可为 Q3 的滚动调整思路提供背景。 | 不将其住宅 PV 参数、SOC 上下限或结果数值移入本题。 |
| L11 | NREL SAM Help, 同 L4 | 调度需同时考虑价格、PV 可用功率、SOC 与转换损耗。 | SAM 的电价、市场收益、并网限制均非题给参数。 |
| L12 | Verhagen et al. (2026), 同 L2 | 售电、需量/并网费用、辅助服务和网侧功率限制会改变储能优化。 | 本题未给这些机制；仅用于“模型局限性”说明，不能引入其荷兰市场数值。 |

## 使用规则

1. Q1 硬参数只取自 `C题.pdf` 与附件；文献只用于解释模型结构、术语或局限性。
2. 论文中优先引用 L1、L2、L4、L6–L9；L3、L5、L10–L12 须经 FIN/ACCT 复核后再进入参考文献表。
3. F2 已完成证据包；在队长确认口径 A/B 前，不修改 Q1 规格中的 \(\eta_c\)、\(\eta_d\)。
