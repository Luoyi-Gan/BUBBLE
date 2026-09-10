# C 题 Q1：初始电量 6000 kWh 的证据与边界（F3）

## 结论

**题给约束。** 附录 1 给定“2025 年 1 月 1 日 0:00 的电量为 6000 kWh”；Q1 另要求储能设备在 0:00 和 24:00 的储电量相同。因此 Q1 取

\[
E_0=E_{24:00}=6000\ \text{kWh}.
\]

这里的 6000 kWh 是储能状态方程的初值，同时在本小问中由日末等式确定为终值；它不是额定容量、每天强制“重置”的控制动作，也不是额外设定的经济目标。

## 可直接写入“模型假设”的段落（101 字）

附录给定 2025 年 1 月 1 日 0:00 储能电量为 6000 kWh，故将其作为状态递推初值。Q1 又要求 24:00 与 0:00 储电量相同，故令 \(E_0=E_{144}=6000\) kWh。该终端约束避免模型通过期末过度放电虚减当日购电费，并使日内调度具有可比性。

## 文献证据

| 来源 | 可用论断 | 适用边界 | 论文落点 |
|---|---|---|---|
| Watari 等（2021），表 1、式 (28) 及第 4.3 节 | 其 PV—储能日内能量管理以初始 SOC 作为状态输入，并将初始和终端 SOC 同设为 0.5；文中说明该终端设定避免贪婪地将电池放空以降低电费。 | 15 min 的社区/建筑 PV—电池调度；支持“状态初值 + 终端条件”的建模含义，不提供本题参数。 | 状态递推与日末约束的解释。 |
| Verhagen 等（2026），第 3.5.2 节、式 (14)–(15) | 日前 BESS 优化将初始 SOC 作为输入状态，并对每日末 SOC 施加固定值；作者明确指出，缺少这一终端约束时，模型倾向于在日末为提高收益而完全放电。 | 多市场大规模 BESS，而非社区负荷侧微网；仅佐证终端 SOC 约束避免跨周期透支。 | 模型评价：解释为何 Q1 必须遵守首末相等。 |

## 参考文献（GB/T 7714）

[1] WATARI D, TANIGUCHI I, GOVERDE H, et al. Multi-time scale energy management framework for smart PV systems mixing fast and slow dynamics[J]. *Applied Energy*, 2021, 289: 116671. DOI: [10.1016/j.apenergy.2021.116671](https://doi.org/10.1016/j.apenergy.2021.116671). 开放版本：<https://imec-publications.be/server/api/core/bitstreams/c1a60c11-f959-49d3-adb1-75c335266983/content>。

[2] VERHAGEN P, HU J, HARMSEN R. Evaluating non-firm grid connections for battery energy storage systems: A co-optimization case study of the Netherlands[J]. *Energy Policy*, 2026, 208: 114903. DOI: [10.1016/j.enpol.2025.114903](https://doi.org/10.1016/j.enpol.2025.114903). 开放全文：<https://research-portal.uu.nl/ws/portalfiles/portal/273724276/1-s2.0-S0301421525004100-main.pdf>。

## 对后续小问的边界

- **Q1：** 以题给日内条件建立代表日模型，采用 \(E_0=E_{144}=6000\) kWh。
- **Q2–Q4：** 6000 kWh 仅是 2025.1.1 0:00 的全年递推起点。后续日期的日初 SOC 必须由前一时段/前一日递推得到，不能机械复制 Q1 的每日首末相等约束；是否施加滚动终端储备应由相应小问的信息结构和风险设定另行说明。

## 结论边界与队长确认

- 文献支持“初值—状态递推—终端约束”的常见建模逻辑，**不能**替代题面对 6000 kWh 的直接规定。
- Q1 使用 6000 kWh 作为首末值为题意要求；Q2–Q4 不自动沿用。
- **请队长确认：是。**
