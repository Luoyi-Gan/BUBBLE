# Q3 主张—证据映射

**适用口径：** A / 1200 kWh，`causal_load_main`，`linear_anchor_main`，`anchor_final_main`，策略 `M1_M6`。
**规则：** 题面/附件事实（F）、模型内推导（M）、本文解释（A）、程序回测（E）和外部一般性主张（L）分开书写。外部文献只支持 L，不能将 A 变为题意事实。

## 1. 信息结构、预测与调整

| 可写主张 | 类别 | 项目内证据 | 可复用外部依据 | 正确边界 |
| --- | --- | --- | --- | --- |
| 0:00 制定普通购电计划，6/12/18 点只能改未执行承诺 | F/M | `docs/specs/q3.md`；`q3_update_log.csv`；锁定时段测试 | Q2 映射中的 Parisio et al.、Silvente et al. | 更新首个可变时段是 6:10/12:10/18:10；不能修改历史时段 |
| 主模型的未来负荷只由此前历史日预测，实际负荷只在执行层进入 | A/E | `q3_annual_forecast_audit.csv`；因果负荷测试 | Tashman (2000)；Hong & Fan (2016)，见 `refs/q2/claim_source_map.md` | 4 个同星期日是项目选择，不称为普适最优预测器 |
| 光伏预测在更新时点以已观测实际值锚定，并映射到 10 分钟网格 | A/E | `q3_forecast_mapping.csv`；映射测试；`input_audit.json` | 可不引用；若说明预测误差和滚动更新，可复用 Q2 的 PV/MPC 来源 | `linear_anchor_main` 是本文映射，不是附件唯一规定 |
| M1/M6 在每次更新比较维持与自由调整的预测成本 | M/A | `docs/specs/q3.md`；`q3_update_log.csv` | 无需外部文献 | 当保持原承诺可行且调整费入目标时，M6 是 M1 的 VoI 实施/解释层，不是第二个独立算法 |
| 最终承诺相对 0:00 原计划一次性结算 | A | `docs/specs/q3.md`；结算单元测试；`q3_settlement_ledger.csv` | 无法由文献解决题意歧义 | 这是避免重复收费的主结算解释；相邻版本结算只作敏感性 |

## 2. 跨日 SOC 与物理约束

| 可写主张 | 类别 | 项目内证据 | 可复用外部依据 | 正确边界 |
| --- | --- | --- | --- | --- |
| 公共母线能量平衡、SOC、功率、效率和弃光定义与 Q1/Q2 一致 | F/M/A | `docs/specs/q3.md`；`q3_annual_physical_audit.json` | Bašić et al.；Pinto et al.；见 Q2 映射 | 设备参数来自题面；无售电和无退化仍是本文边界 |
| SOC 全年连续，年初 6000 kWh，主口径年末 1200 kWh | A/E | `q3_annual_physical_audit.json`；`q3_annual_boundary_delta.csv` | La Tona et al.；Luo et al.，见 Q2 映射 | 年末 1200 是统一核算边界，不是社区实际运行规律 |
| 48 小时到达项缓解有限视域的末端透支 | M/E | `q3_next_day_value_audit.csv`；`docs/specs/q3.md` | Cao et al.；Luo et al.；Silvente et al.，见 Q2 映射 | 具体 48 小时与数值证书只由 Q3 审计支持，不能称精确全年价值函数 |
| LP 解没有同时充放电 | M/E | `q3_annual_physical_audit.json` | 无需外部文献 | 仅在正价、无售电收入、存在损耗及无强制循环等模型条件下成立 |

## 3. 结果与不可外推边界

| 可写主张 | 类别 | 直接证据 | 正确边界 |
| --- | --- | --- | --- |
| A + M1/M6 年度总成本为 16,373,508.75 元，较 M0 低 4.30% | E | `q3_annual_strategy_comparison.csv`；`q3_annual_daily_summary.csv` | 仅适用于 2025 附件数据、当前结算解释、因果负荷与线性映射 |
| B=6000 kWh 不改变五策略排序，且每个策略成本高约 2238—2263 元 | E | `q3_annual_boundary_delta.csv` | 仅支持年末 SOC 边界选择，不代表其他年份或容量设置 |
| `M1_M6` 通过更多常规调整换取更少紧急购电 | E | `q3_annual_strategy_comparison.csv`；`q3_update_log.csv` | 是本回测中的成本分解，不能称真实社区必然节省或投资收益 |

## 4. 禁止性表述

- 不写“线性映射更准确”或“调整结算由题意唯一确定”；
- 不写“M1 和 M6 是两个独立的成本改进算法”；
- 不写“1200 kWh 是题设规定的年度末状态”；
- 不写“Q3 已在全部映射和结算解释下完成年度稳健性验证”；
- 不写“年度成本差等于实际社区节省、投资收益或电池寿命收益”。

## 5. 论文引用的最小组合

若正文确实需要外部方法依据，可引用 Q2 证据库中已核定来源：滚动无泄漏预测用 Tashman；滚动 MPC 用 Parisio/Silvente；跨日 SOC 与有限视域终端效应用 La Tona/Luo/Cao。Q3 的具体预测窗口、映射、结算解释、年末 SOC 和所有数值结果必须回指本项目规格与审计文件，而非外部论文。
