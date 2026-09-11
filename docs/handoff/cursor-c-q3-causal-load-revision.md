# Cursor 交接单：C 题 Q3 因果负荷信息修订

**接收人：** Cursor  
**模型负责人：** Codex  
**状态：** 队长已确认，可开始两日重跑；不得提前生成 `output/result3.xlsx`。  
**唯一模型来源：** `docs/specs/q3.md` 第 2、4、7 节；复核依据 `docs/reviews/q3-pilot-review.md` 的 RQ3-1。

## 1. 目的与边界

当前 P0–P3 试算在 `q3/pilot.py` 中直接使用了当天完整 `data.load[day_index]`。该版本不删除，但必须重命名并保留为 `actual_load_proxy` 理想化信息对照。新的主模型必须使用 Q2 的因果日前负荷预测，消除对当天未来真实负荷的读取。

只修改：`q3/`、`output/q3_pilot/`、必要的 `fig/q3_pilot/`。不得修改 `docs/specs/`、`docs/reviews/`、Q1/Q2 代码、附件或 `output/result3.xlsx`。

## 2. 主模型的确定负荷预测

对计划日 \(d\)，构造

\[
\widehat L_{d,t}=\frac1{|\mathcal H_d|}\sum_{j\in\mathcal H_d}L_{j,t},
\]

其中 \(\mathcal H_d\) 是日期严格早于 \(d\) 的最近至多 4 个同星期历史日。历史不足时采用现有、可复核的 Q2 回退预测，但不得用未来日期补齐。

实现要求：

1. 现有 `causal_load_forecast(data, target_index=d, history_end_exclusive=d)` 可作为唯一日前负荷预测入口；不得在主模型路径中直接读取 `data.load[d, t:]`。
2. 0:00 和 6/12/18 的未来规划使用同一日 0:00 形成的 \(\widehat L_{d,t}\)。已执行前缀仅用于真实 SOC/能量状态，不新增未经规格确认的同日负荷后验更新。
3. 每个 10 分钟 MPC 求解中，当前第一个时段可用真实 \(L_{d,t}\)、\(P_{d,t}\)；未来时段必须用 \(\widehat L_{d,\tau}\)、\(\widehat P_{d,\tau}\)，\(\tau>t\)。
4. 下一日终端价值模块继续使用因果负荷预测；核对其历史截止日严格早于目标日。

## 3. 保留的理想化对照

实现显式 `load_information_case`，至少包括：

- `causal_load_main`：上述主模型；
- `actual_load_proxy`：原始完整附件 2 当日负荷路径，仅用于信息价值对照。

两种信息情形均使用相同的价格、PV 预测映射、结算函数、初始 SOC、终端价值和策略集合。文件名、CSV 列、图例和汇总表必须含 `load_information_case`；不得覆盖原有试算文件或把代理结果混入主方案统计。

## 4. 两日重跑与新增审计

重跑 2025-02-01、2025-06-21 的 M0、M1/M6、仅 6/12/18 更新和无 48h 对照。新增：

1. `q3_load_forecast_audit.csv`：日期、时段、预测负荷、实际负荷、预测来源日期、是否当前执行时段、绝对误差；
2. `q3_load_information_comparison.csv`：按日期、策略、信息情形汇总总成本、结算成本、紧急购电、弃光、SOC 首末值及运行时间；
3. `q3_causality_audit.json`：对某日当天尚未发生的真实负荷人为扰动后，断言主模型的日前/更新计划预测不变；同时确认代理对照允许变化；
4. 所有既有物理、结算、锁定时段与同时充放电审计继续通过。

在 `validation.md` 中明确：新的 `causal_load_main` 才是 Q3 主结果候选；`actual_load_proxy` 仅衡量完美负荷信息带来的差异。不得将两者成本混合或宣称代理对照可现实执行。

## 5. 回报

提交代码、运行命令、依赖/求解器版本、两日新增 CSV/JSON、更新后的物理审计，以及主模型相对代理对照的差异解释。完成后停止，等待 Codex 复核；不要运行全年或生成 `result3.xlsx`。

## 6. Cursor 可直接使用的提示词

> 请严格按 `docs/handoff/cursor-c-q3-causal-load-revision.md` 修订 Q3 两日试算。主模型必须使用 Q2 式因果日前负荷预测：最近至多 4 个已结束同星期日均值，未来时段不能读取当天附件 2 真实负荷；每 10 分钟仅当前执行步使用真实负荷和真实光伏。现有完整真实负荷版本必须保留为独立 `actual_load_proxy` 理想化对照，文件名、列名、图例和汇总表都要显式区分。重跑全部两日策略，新增负荷预测、信息情形比较和因果性审计。仅修改 `q3/`、`output/q3_pilot/`、必要的 `fig/q3_pilot/`；不要生成 `result3.xlsx`，不要修改模型规格或其他小问。完成后提交代码、审计结果、依赖/求解器版本和运行命令，等待复核。
