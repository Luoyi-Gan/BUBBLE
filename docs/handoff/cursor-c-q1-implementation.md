# Cursor 交接单：C 题 Q1 线性规划实现

> **已被取代：** 2026-09-10 起，以 `docs/handoff/cursor-c-q1-second-revision.md` 为最新实现任务单。本文件只保留第一次实现记录，其中“M2 作为正式结果”的要求不再有效。

**负责人：** Cursor  
**模型负责人：** Codex  
**状态：** 第一次实现已完成；后续修改见二次任务单。

## 1. 唯一规格来源

- 主规格：`docs/specs/q1.md`。
- 题目数据：`/Users/louis/Desktop/CUMCM2026Problems/C题/附件/附件1.xlsx`，`Sheet1`。
- 官方结果模板：`/Users/louis/Desktop/CUMCM2026Problems/C题/附件/附件5/result1.xlsx`。
- 假设证据：`refs/c_q1_efficiency.md`、`refs/c_q1_market_boundary.md`。

只修改 `q1/`、`output/`、`fig/`，及为生成结果所必需的受控脚本；不得修改 `paper/`、`refs/`、`docs/specs/`、`results_summary.md` 或官方模板原件。

## 2. 已锁定模型

时间粒度为 \(\Delta=1/6\) h，\(T=144\)。将附件中的负荷和光伏功率乘 \(\Delta\) 得到 kWh。

决策变量：购电量 \(g_t\)、充电量 \(c_t\)、放电量 \(d_t\)、时段末 SOC \(E_t\)、弃光量 \(s_t\)。

\[
\min\ \sum_{t=1}^{144}p_tg_t
\]

\[
g_t+P_t+d_t=L_t+c_t+s_t,
\]
\[
E_t=E_{t-1}+\sqrt{0.9}\,c_t-\frac{d_t}{\sqrt{0.9}}.
\]

约束：

\[
0\le c_t,d_t\le833.333333\ \text{kWh},\quad
1200\le E_t\le10800,
\]
\[
E_0=E_{144}=6000,\quad g_t,s_t\ge0.
\]

- 主方案效率口径：往返效率 90%，\(\eta_c=\eta_d=\sqrt{0.9}\)。
- 不售电；富余光伏可弃用；不设题目未给的购电上限、需量费、网损或退化成本。
- 不要求二元充放电互斥变量；求解后必须检查 \(c_td_t\) 是否接近 0。
- 优先使用 `scipy.optimize.linprog(method="highs")` 或等价 HiGHS LP 实现。

## 3. 必须交付

1. `q1/` 内可复现的主脚本和简短 README：注明依赖、运行命令、外部数据路径配置方式。
2. `output/q1_plan.csv`：严格使用规格中已列的完整字段，144 行。
3. `output/q1_summary.csv`：至少含总购电量、总购电费、弃光量、SOC 最小/最大值、\(E_0\)、\(E_{144}\)、最大能量平衡残差。
4. `fig/fig1_dispatch.png`、`fig/fig1_soc_price.png`：标明单位、图例和时间轴。
5. 仿照官方模板另存生成的 `output/result1.xlsx`；不得覆盖附件5原件，不得增删/改名工作表、表头或 144 行时间标签。
6. 生成 `output/q1_validation.md`，逐项报告下列验收结果。

## 4. 验收要求

- 144 个时段齐全；输入功率已正确换算为 kWh。
- 每时段能量平衡残差绝对值小于 \(10^{-6}\) kWh。
- 所有 \(c_t,d_t\) 不超过 833.333333 kWh；所有 SOC 在 1200–10800 kWh 内。
- \(|E_{144}-6000|<10^{-6}\) kWh，且 \(E_0=6000\) kWh。
- 报告最大 \(c_td_t\)；若超过数值容差，停止并说明原因。
- 结果工作簿保留官方工作表“计划购电量”“充放电量”、原表头和所有官方时间标签。

## 5. 时间标签处理

附件1的数据时间与 result1 标签存在 10 分钟表述差异。实现中：

- 内部模型用整数索引 \(t=1,\ldots,144\)，SOC 独立使用 \(E_0\) 至 \(E_{144}\)。
- 导出时按**官方模板既有的行序**填写第 \(t\) 个购电结果，绝不自行新增 `0:00-0:10` 或移动模板行。
- 在 `output/q1_validation.md` 中记录“内部索引 \(t\) → 附件1第 \(t\)条数据 → 模板第 \(t\)条时间标签”的映射说明；不要伪造额外时间区间。
- 若该行序映射导致对题意理解的实质冲突，停止导出并报告给 Codex/队长。

## 6. 必做内部模型对照（主结果验收后、正式导出前）

在同一份清洗后的输入数据上运行以下四种情形：

| 编号 | 求解形式 | 目标 |
|---|---|---|
| M1 | LP，不设互斥二元变量 | 最小购电费 |
| M2 | LP，不设互斥二元变量 | 先最小购电费，再在成本容差内最小化 \(Q=\sum_t(c_t+d_t)\) |
| M3 | MILP，设互斥二元变量 | 最小购电费 |
| M4 | MILP，设互斥二元变量 | 先最小购电费，再在成本容差内最小化 \(Q\) |

- M3/M4 加入 \(z_t\in\{0,1\}\)、\(c_t\le833.333333z_t\)、\(d_t\le833.333333(1-z_t)\)。
- M2/M4 必须先保存第一阶段最优成本 \(C^*\)，再加 \(\sum_tp_tg_t\le C^*+\varepsilon_C\) 后最小化 \(Q\)。不得用未经说明的微小加权项替代词典序求解。
- 输出 `output/q1_model_comparison.csv`：`case, solver, purchase_cost_yuan, grid_purchase_kwh, curtailment_kwh, throughput_kwh, max_simultaneous_charge_discharge, soc_min_kwh, soc_max_kwh, max_balance_residual_kwh, solve_seconds, pass`。
- 输出 `output/q1_model_selection.md`：说明成本容差 \(\varepsilon_C\)、四种情形的约束检查、推荐方案和理由。
- 不要让 M1/M3/M4 覆盖正式结果；正式 `output/result1.xlsx` 暂按 M2 生成，交由 Codex 验收后定稿。

## 7. 可选工作（四种模型对照完成后再做）

- 效率敏感性 B：\(\eta_c=\eta_d=0.90\)，对应往返效率 81%。不得覆盖主方案输出。
- SOC 离散动态规划交叉验证；记录 SOC 网格精度及与 LP 的目标差异。
