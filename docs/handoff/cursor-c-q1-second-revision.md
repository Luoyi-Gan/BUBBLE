# Cursor 任务单：C 题 Q1 二次修改

**下发日期：** 2026-09-10

**完成状态：** Cursor 已完成实现，Codex 已完成复核；2026-09-11 队长签收表 2 的公共母线侧 \(c_t/d_t\) 口径。本任务单保留为实施记录。

**上游规格：** `docs/specs/q1.md`

**复核依据：** `docs/reviews/q1-second-review.md`

**队长已确认：**

1. 时间以附件 1 原始 144 行顺序为基准，不排序、不旋转。
2. 正式模型与 `result1.xlsx` 改用 M1。

**职责边界：** Cursor 只修改 `q1/`、`output/`、`fig/` 和必要测试，不修改 `docs/specs/`、`refs/`、`paper/` 或 `results_summary.md`。

## 1. Git 操作

从远端复核分支起一条独立实现分支，避免覆盖 Codex 文档工作：

```bash
git fetch origin
git switch -c cursor/c-q1-second-revision origin/codex/c-q1-second-review
```

完成后提交并推送该分支，不直接合并 `main`。

## 2. 必做代码修改

### C1 锁定附件原始行序

- `load_attachment1` 必须保留 Excel 原始行序，不按时间字段重新排序。
- 不把末行 `0:00+1` 旋转到第一行。
- 增加精确检查：144 行、列名、数值有限、负荷和光伏非负、价格有限、首行标准化后为 `00:10:00`、末行标准化后为 `0:00+1`。
- 模板第 \(t\) 行继续对应附件第 \(t\) 行；六个四小时汇总继续使用第 1–24、25–48、…、121–144 行。
- 在 `output/q1_validation.md` 写明“附件原始行序口径（队长确认）”。

### C2 正式结果改用 M1

- `run_q1.py` 中正式方案设为 M1。
- `output/q1_plan.csv`、`output/q1_summary.csv`、`output/result1.xlsx` 和两张正式图全部由 M1 生成。
- M2、M3、M4 只写入模型形式对照文件，不得覆盖正式结果。
- 更新 `output/q1_model_selection.md`：正式选择为 M1；M2 仅是数值择优对照，不能声称降低退化或延长寿命。

### C3 补全弃光边界

在线性约束中增加：

\[
0\le s_t\le P_t.
\]

本次主结果预计不变，因为现有解的弃光量为 0；仍须重新求解和验证。

### C4 参数化模型

`solve_stage`、`solve_lexico` 及底层建模函数不得再只读取全局锁死参数。至少允许显式传入：

- \(\eta_c,\eta_d\)
- \(E_{\min},E_{\max},E_0\)
- 最大充/放电功率
- 可选外网购电功率上限 \(G_{\max}\)

默认参数必须严格复现队长确认的 M1。

若接口中的 \(G_{\max}\) 使用 kW，则约束必须写为 \(g_t\le G_{\max}\Delta\)；若使用 kWh/时段，变量名必须明确包含 `_kwh`，禁止混用。

### C5 增加无储能基准

无储能、无售电基准定义为：

\[
g_t^{base}=\max(L_t-P_t,0),\qquad
s_t^{base}=\max(P_t-L_t,0).
\]

生成 `output/q1_baseline.csv`，至少包含：

- 基准总购电量
- 基准购电费
- 基准弃光量
- M1 总购电量与购电费
- 绝对节省费用和节省比例

复核参考值约为：基准购电量 61789.9354 kWh、基准购电费 48052.046591 元、基准弃光 6247.962967 kWh。最终值以新脚本复算为准。

### C6 增加统一敏感性输出

生成 `output/q1_sensitivity.csv`。每个情形至少包含：

`case, eta_c, eta_d, nominal_capacity_kwh, soc_min_kwh, soc_max_kwh, power_limit_kw, grid_limit_kw, purchase_cost_yuan, grid_purchase_kwh, peak_grid_kw, curtailment_kwh, throughput_kwh, soc_observed_min_kwh, soc_observed_max_kwh, pass`

必须包含：

1. `eff_A`：\(\eta_c=\eta_d=\sqrt{0.9}\)。
2. `eff_B`：\(\eta_c=\eta_d=0.9\)。
3. 容量 -10% / +10%：额定容量分别取 10800 / 13200 kWh，SOC 窗口仍按 10%–90%；\(E_0=E_T=6000\) kWh 保持题给绝对值。
4. 功率 -10% / +10%：最大充放电功率分别取 4500 / 5500 kW。
5. PCC 参数分析：
   - 先建立“最小化峰值购电量”的 LP，求最小可行峰值并乘 \(1/\Delta\) 转为 \(G_{\max}^{min}\)（kW）。
   - 以 \(G_{\max}^{min}\) 到无上限 M1 自然峰值之间的等距点做成本优化。
   - 不把任一 \(G_{\max}\) 写成题给参数。

敏感性结果不得覆盖主方案文件。

### C7 输入、模板与输出检查

- 检查所有输入数值为有限数。
- 对实际附件记录价格最小值；如果未来出现负价，显式报错或走单独机制，不能沿用“无需同时充放电”的结论。
- 核对两个工作表名称、表头、计划购电量 144 个标签和充放电量六个区间标签。
- 校验导出后只修改模板允许填写的单元格。
- `output/q1_summary.csv` 增加 `peak_grid_kw` 和正式方案名称 `official_model=M1`。

## 3. 暂不改变的口径

- 表 2 暂按公共母线侧电量汇总：充电量为 \(c_t\)，放电量为 \(d_t\)。
- 该计量侧已由队长签收。代码中继续集中定义并在验证文件说明，不能在多个导出函数中隐式重复。
- \(E_0=E_{144}=6000\) kWh。
- 不售电、外网无上限仍为主方案；PCC 上限只进入敏感性分析。
- 不新增自放电、辅助用电、退化成本、网损或需量费。

## 4. 验收标准

- M1 正式成本应复现约 33801.495542 元；若偏差超过 \(10^{-5}\) 元，停止并解释。
- M1 与 M3 成本一致，且 M1 的 \(\max_t c_t d_t\) 不超过既定容差。
- \(s_t\le P_t\) 对所有时段成立。
- 能量平衡、SOC 边界、功率边界和首末电量全部通过。
- `result1.xlsx` 保留官方结构、标签和格式；正式数值来自 M1。
- 效率 B 的费用应约为 35126.948589 元；若明显不符，检查参数是否真正传入。
- 基准、敏感性和 PCC 分析均有独立文件且包含单位。
- 运行命令在项目 `.venv` 中可复现，不依赖手工修改全局常量。

## 5. Cursor 可直接使用的 Prompt

> 读取 `docs/specs/q1.md`、`docs/reviews/q1-second-review.md` 和 `docs/handoff/cursor-c-q1-second-revision.md`。从 `origin/codex/c-q1-second-review` 创建独立分支 `cursor/c-q1-second-revision`。严格保留附件 1 原始 144 行顺序，不排序、不旋转；将正式输出从 M2 改为 M1；增加 `0 <= s_t <= P_t`；参数化效率、容量、功率和可选 PCC 上限；生成无储能基准及统一敏感性文件；加强输入、模板和导出校验。表 2 暂保持公共母线侧 `c_t/d_t` 口径。只修改 `q1/`、`output/`、`fig/` 和测试，不改规格、文献、论文或结果摘要。完成后运行全量验证，提交并推送分支，汇报 commit、变更文件、主结果、敏感性结果和未决问题，不要自行合并 main。
