# FIN 收口期代码运行单

**状态：** 立即执行 A；B 等待 Q2 C2-R3 通过正式验证并获得明确 commit 后执行。

**职责边界：** FIN 只在独立工作树运行既有代码、记录命令和产物校验；不修改 `q2/`、`q4/` 的求解逻辑，不手工改写 CSV/Excel 数字，不覆盖 Cursor 的工作树。

## 0. 为什么不重复运行 C2-R3

当前 C2-R3 已在主运行环境中执行。对同一版本、同一数据重复跑全年 Q2 不能缩短那条正在运行的任务，反而会占用计算资源并产生难以区分的重复产物。因此 FIN 不启动第二条 C2-R3。

FIN 的并行价值是：先独立复现已提交的 Q4 两日回归；然后在 Q2 口径冻结后，接手耗时的 Q4-2 全年重跑，使 Cursor 可继续处理导出和论文图。

## A. 立即任务：Q4 提交版独立两日复现

### 目标

对 PR #17 的提交 `c7f886e` 做一份独立、可复核的运行记录。此任务不产生新的模型结论，也不覆盖 PR 内的正式 Excel。

### 环境与分支

1. 在自己的独立 worktree 检出 `cursor/c-q4-two-day-p2-730d` 的 `c7f886e`；不得在队长或 Cursor 当前目录运行。
2. 确认附件路径可读、Python 环境包含 `numpy`、`pandas`、`cvxpy`、`scikit-learn`、`openpyxl` 和 HiGHS。
3. 运行：

```text
python -m unittest q4.test_q4_price_forecast q4.test_q4_dispatch -v
python q4/run_q4_twoday.py
```

### 签收条件

- 两条命令均以 0 退出；
- `output/q4/q4_twoday_run_metadata.json` 的 `all_pass=true`；
- `output/q4/q4_2_info_set_audit.json` 和 `q4_3_info_set_audit.json` 的 `all_pass=true`；
- 两个试点日 `2025-02-01`、`2025-06-21` 都出现于审计；
- 不上传、替换或手工编辑 `output/result4-2.xlsx`、`output/result4-3.xlsx`。

### 回报格式

向队长和 Codex 回报：commit、两条命令的退出码、运行时长、`all_pass` 值，以及任何缺失依赖或输出差异。若失败，只附首个可复现的错误，不自行修改算法。

## B. 条件任务：Q2 冻结后的 Q4-2 年度重跑

### 前置条件（缺一不可）

1. Cursor 已提交 Q2 C2-R3 的最终 commit，`validate_q2_policy_consistent.py` 零错误通过，并导出正式 `result2.xlsx`；
2. Cursor 已提供一个 **Q4-2 桥接 commit**：它明确采用最终 Q2 的因果预测、日前承诺、风险储备和日内执行口径，并先通过 Q4-2 两日回归；
3. 队长确认该桥接 commit 是 Q4-2 唯一运行来源。

若前置条件未满足，FIN 不得用旧 Q2 代码重新跑全年，也不得把 PR #17 中 17,680,437.93 元写为最终 Q4-2 结论。

### 运行内容

在桥接 commit 的独立 worktree 执行：

```text
python -m unittest q2.test_q2 q4.test_q4_price_forecast q4.test_q4_dispatch -v
python q4/run_q4_twoday.py
python q4/run_q4_full.py --system q4_2
python q4/export_result4.py
```

仅在全年 Q4-2 通过后导出 `result4-2.xlsx`。Q4-3 不因 Q2 变更重跑；它只在 Cursor 修复列宽、数值格式和紧急购电展示阈值后重新导出。

### 年度签收条件

- `q4_2_run_metadata.json`：365 天、`n_days_pass=365`、SOC 连续通过；
- 逐时段账本重算为 `p*q+5p*e`，年成本等于每日账本之和；
- `q` 日内不变，未来价格扰动不改变已作出的决策；
- `result4-2.xlsx` 覆盖 2025-02-01 至 2025-12-31 的 334 天和 144 时段，日期/数值是 Excel 原生类型，页面没有 `###` 或被截断标题；
- 输出、图、元数据与运行 commit 一同提交。FIN 只提交运行产物和运行记录，不修改算法代码。

## C. Q4-3 导出清洁任务（Cursor 完成代码后）

Cursor 完成导出修复后，FIN 只需运行其给定的导出命令并检查：

- 时间列足以显示数值，建议统一到 2—3 位小数；
- `紧急购电量` 只展示大于明确数值容差的正值；
- 展示层过滤不改变逐时段账本、年度成本或物理审计；
- `result4-3.xlsx` 仍为 334 天、144 时段，计划列为 `g0`、调整列为 `gF`。
