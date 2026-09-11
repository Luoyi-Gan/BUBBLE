# Q2 主张—证据映射

本表以当前已签收的 **固定 `K=8` 滚动风险分位方案**为准。`output/q2_full_linked/` 中的动态 K 结果只作旧对照，不与正式方案混写。

## 信息结构、预测与场景

| 可写主张 | 项目内直接证据 | 外部依据 | 建议措辞与边界 |
|---|---|---|---|
| 每日 0:00 先确定 144 时段正常购电计划，实际不足再紧急补购 | `docs/specs/q2.md`；`q2/optimization.py`；`q2/pilot.py` | Birge & Louveaux (2011), pp.181–263；Shapiro et al. (2021), Ch.2 | 用“两阶段、先验决策—事后补救”解释。5 倍价格是题给事实，不需外部文献。 |
| 各场景共享日前计划 `q_t`，场景内才有 `x,e,c,d,w,E` | `q2/optimization.py`；`docs/specs/q2.md` | Birge & Louveaux (2011)；Shapiro et al. (2021) | 共享 `q`体现非预见性；不得给每个场景各自重选计划。 |
| 日前计划支付 `p_t q_t`，实际使用 `x_t≤q_t`，未用额度为沉没成本 | `docs/specs/q2.md`；`q2/optimization.py`；`q2/pilot.py` | 主要为题意映射，无直接外部来源 | 这是本项目对“计划购电”的可执行解释，不应称为普遍市场规则。 |
| 紧急购电只补当前短缺，不能借未来计划额度 | `q2/pilot.py`；`docs/reviews/q2-final-delivery-audit.md` | 主要为项目决策 | 若允许跨时段挪用，信息结构和成本含义会改变。 |
| 负荷预测最多取最近 4 个同星期日，PV 预测取最近 7 天 | `q2/forecast.py`；`output/q2_full_k8_risk/forecast_audit.md` | Hong & Fan (2016)；Antonanzas et al. (2016)；Sengupta et al. (2024) | 外部文献支持负荷/PV 预测的必要性和日历/历史信息使用；具体 4/7 窗口是项目经验选择。 |
| 预测严格只用目标日 0:00 前历史 | `q2/forecast.py`；`forecast_audit.md`；相关测试 | Tashman (2000) | 可称为 rolling-origin/逐日起点回测；不得把当日实测曲线输入日前模型。 |
| 用历史联合负荷–PV 残差轨迹构造场景，保留时序及二者相关性 | `q2/scenarios.py`；`q2/pilot.py` | Pinson et al. (2009)；Dupačová et al. (2003) | 引用支持“轨迹情景”和“场景缩减”原则；不证明本残差分布完全校准。 |
| 场景距离按价格加权，并用 MAD 尺度标准化 | `q2/scenarios.py` | Rousseeuw & Croux (1993) | MAD 支持稳健尺度；价格权重是问题导向的本文设计，不是该统计文献的结论。 |
| 用 PAM/k-medoids 从真实历史轨迹中选 8 个代表场景，概率为簇占比 | `q2/scenarios.py`；`output/q2_pilot/scenario_selection.csv` | Kaufman & Rousseeuw (1990), Ch.2；Dupačová et al. (2003) | medoid 是实际样本代表；`K=8` 来自本项目旧动态 K 审计后的固定选择，不是文献定理。 |
| 高价权重下最大正净残差日作为压力日，但默认不加入期望 | `q2/scenarios.py`；`docs/specs/q2.md` | 无直接外部来源 | 这是经验压力测试；若未被 PAM 选中，不得修改场景概率或目标函数。 |

## 风险控制、滚动执行与终端价值

| 可写主张 | 项目内直接证据 | 外部依据 | 建议措辞与边界 |
|---|---|---|---|
| 从 1 月 29 日起固定 `K=8`，此前样本不足用 `K=1` 且不设储备 | `q2/run_q2_k8_risk.py`；`output/q2_full_k8_risk/risk_calibration.csv` | 无需外部来源 | 属于本项目样本可用性与正式口径。 |
| 每 14 天用已结束日期在 `α∈{0.60,0.70,0.80,0.90}` 中重新选风险分位 | `q2/run_q2_k8_risk.py`；`q2/pilot.py`；`risk_calibration.csv` | Hong & Fan (2016)；Matos & Bessa (2011) | 外部文献支持用概率/分位信息制定储备；候选集合、14 天频率和选择准则均是项目设计。 |
| 当前方案是经验加权分位下限，不是 CVaR | `docs/specs/q2.md`；`q2/optimization.py` | Rockafellar & Uryasev (2000) 仅作反例/扩展 | 正文应叫“风险分位储备/计划下限”；不能称 CVaR 优化。 |
| 实际运行按已观测残差前缀更新场景权重，并重求余下时段，只执行第一步 | `q2/pilot.py` | Parisio et al. (2014a, 2014b)；Silvente et al. (2018) | 文献支持滚动 MPC/周期更新；本项目的指数前缀距离权重是自定义经验更新，不应宣称严格贝叶斯后验。 |
| SOC 全年连续，只在 1 月 1 日注入一次 6000 kWh | `q2/pilot.py`；`output/q2_full_k8_risk/daily_summary.csv`；validation | La Tona et al. (2021)；Luo et al. (2019) | 跨日状态连续；不能每天重置或照搬 Q1 的日末相等约束。 |
| 48 h 下一日 cost-to-go 缓解有限视界末端效应 | `q2/pilot.py`；`next_day_value_audit.csv` | Cao et al. (2019)；Luo et al. (2019)；Silvente et al. (2018) | 文献支持末端效应与滚动衔接；具体 48 h 是项目选择。 |
| 价值函数以初始 SOC 的对偶斜率生成支持割，并用 chord-vs-cut 间隙验证 | `q2/pilot.py`；`next_day_value_audit.csv`；validation | Boyd & Vandenberghe (2004), §5.6；Benders (1962)；Pereira & Pinto (1991) | 支持割/对偶斜率是分解与动态规划思想；本项目 `≤1 元`阈值是数值验收标准。 |
| 下一日价值只影响当前决策，不并入实际账单 | `q2/pilot.py`；`validation.json` | Birge & Louveaux (2011), value-function/recourse chapters | 账单只含正常计划费与紧急购电费；不要把 terminal value 重复计费。 |

## 物理边界与结果

| 可写主张 | 项目内直接证据 | 外部依据 | 建议措辞与边界 |
|---|---|---|---|
| 电池效率、SOC、功率和平衡沿用 Q1 公共母线侧口径 | `q2/config.py`；`q2/optimization.py`；`q2/pilot.py` | Bašić et al. (2023)；Pinto et al. (2022)；SAM Help | 具体数值仍来自题面。 |
| 不售电，未消纳 PV 可弃 | `docs/specs/q2.md`；`q2/optimization.py` | Jorgenson et al. (2020)；Case et al. (2018) | 不售电是本文边界，不是文献或题面明确市场规则。 |
| 2–12 月正式总费用约 1445.667 万元，其中计划费 1252.909 万元、应急费 192.758 万元 | `output/q2_full_k8_risk/validation.json`；`daily_summary.csv`；`output/result2.xlsx` | 无需外部来源 | 数字必须以固定 K8 文件为准。 |
| 2–12 月计划量约 2031.857 万 kWh、实用计划量约 1934.691 万 kWh、未用约 97.166 万 kWh、应急约 53.449 万 kWh | 同上 | 无需外部来源 | 计划量≠实际使用量；费用按购买的 `q` 计算。 |
| 2–12 月弃光约 134.949 万 kWh，应急购电发生在 293/334 天 | `daily_summary.csv`；`validation.json` | Jorgenson et al. (2020) 仅解释弃光 | 发生频率是回测结果，不等同系统失供概率。 |
| 最大应急日为 2025-06-01，应急约 14274.48 kWh、费用约 48353.36 元 | `daily_summary.csv`；`results_summary.md` | 无需外部来源 | 可作压力案例，但不能凭单日归因；需结合当日残差、价格、SOC 和计划检查。 |
| 全年正式总费用约 1634.094 万元，平衡残差、跨日 SOC、`x≤q` 和同时充放均通过审计 | `output/q2_full_k8_risk/validation.json`；`results_summary.md` | 无需外部来源 | “通过数值审计”不是现实可实施性的完整证明，仍受市场/PCC/电池退化简化限制。 |
| 固定 K8 相对旧动态 K 的 2–12 月费用降低约 5.017 万元（0.35%） | `results_summary.md`；`output/q2_full_linked/comparison.json`；K8 validation | 无需外部来源 | 必须注明动态 K 是旧比较器而非最终方案；差额来自计划费与应急费的共同变化。 |

## 论文段落的推荐引用组合

- **两阶段信息结构**：Birge & Louveaux + Shapiro et al.，同时引用 `docs/specs/q2.md` 说明本题 `q,x,e` 定义。
- **预测与无泄漏回测**：Hong & Fan + Antonanzas et al. + Tashman。
- **联合残差与场景缩减**：Pinson et al. + Dupačová et al. + Kaufman & Rousseeuw；MAD 再加 Rousseeuw & Croux。
- **风险分位**：Hong & Fan + Matos & Bessa；明确不使用 CVaR。
- **滚动执行**：Silvente et al. + Parisio et al.。
- **跨日 SOC/终端价值**：La Tona et al. + Luo et al. + Cao et al.；对偶支持割再加 Boyd、Benders、Pereira & Pinto。
- **弃光边界**：Jorgenson et al. + Case et al.。

## 可直接使用的精炼论证

> Q2 将正常购电与紧急补购按信息到达时点分开：日初在未知当天真实负荷与光伏的条件下确定所有场景共享的计划量，场景实现后再通过储能、弃光和紧急购电补救。这一结构对应两阶段随机规划中的先验决策与情景相关补救，并以非预见性约束阻止模型利用未来信息。

> 负荷和光伏分别由截至目标日 0:00 的历史生成基准预测，再从历史联合残差轨迹中抽取真实 medoid 场景，以保留日内相关性。PAM、MAD 与场景缩减文献支持代表轨迹选择和稳健尺度处理，但 `K=8`、价格加权距离、窗口长度及前缀权重更新均是本项目经回测确定的设计，不是文献规定。

> 实际运行采用滚动时域：每获得新的真实观测便更新场景可信度，重求剩余时段并只执行首步。SOC 跨日连续；窗口末端通过下一日 cost-to-go 保留未来储能价值。该价值函数影响控制决策但不进入实际购电账单，从而避免把算法内部终端价值与真实费用重复相加。
