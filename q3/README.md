# 小问 3 · 四时点滚动购电调整（两日试算）

实现依据：`docs/specs/q3.md`、`docs/handoff/cursor-c-q3-implementation.md`
与 `docs/handoff/cursor-c-q3-causal-load-revision.md`。

本阶段只完成 P0–P3 两日端到端试算和审计。未经 Codex/队长复核，不生成
`output/result3.xlsx`，不实现 M5 情景树，不跑全年批量。

**主结果候选：`causal_load_main`（Q2 式因果日前负荷预测）。**
`actual_load_proxy` 只是理想化完美负荷信息对照，不得进入全年正式结果。

## 运行

在仓库根目录：

```bash
export CUMCM_C_ATTACH_DIR=/path/to/C题/附件   # 含 附件1.xlsx 附件2.xlsx 附件3.xlsx
python -m unittest q3.test_q3 -v
python q3/run_q3_pilot.py
python q3/validate_q3_pilot.py
```

若未设置环境变量，代码会依次尝试队长本机路径和仓库 `data/raw/`。

求解器：CVXPY + HiGHS。版本写入 `output/q3_pilot/run_meta.json`。

## 口径（不可变更）

- 内部时段 0–143，功率乘 `Δt=1/6` 得 kWh；不旋转附件行序。
- 结算只锚定当日 0:00 原计划：`φ=p g^F + 0.5 p |g^F-g^0|`，中间版本不重复计费。
- 6/12/18 只能改未执行时段，首个可改索引分别为 36/72/108。
- 附件 3 逐小时预报用更新时点已观测实际光伏作因果锚点，再与随后整点预报线性插值。
- **主模型负荷：** 最近至多 4 个已结束同星期日均值；0:00 与 6/12/18 的未来规划使用同一日 hat；不得读取当天未来附件 2 负荷。
- **执行层：** 每 10 分钟仅当前一步使用真实负荷与真实光伏，其余未来时段用 hat / 当次光伏预报。
- `LOAD_TREATMENT = causal_load_main`。`actual_load_proxy` 单独输出，文件名和列都带 `load_information_case`。
- 终端价值复用 Q2 的 48 小时切面结构，但按 Q3 预报口径重建；下一日负荷截止日严格早于目标日。同时输出无终端价值对照。

## 试算输出

全部写入 `output/q3_pilot/`：

| 文件 | 说明 |
| --- | --- |
| `input_audit.json` | 附件 1/2/3 行列、缺失、四条预报完整性和时间映射 |
| `q3_forecast_mapping.csv` | 两试算日、四个更新点的 10 分钟预报、插值节点/权重、是否已执行实际值 |
| `q3_dispatch_YYYY-MM-DD_<strategy>_<case>.csv` | 逐时段调度；`load_kwh` 为真实负荷，`forecast_load_kwh` 为规划 hat。无 48h 对照带 `_no48h` |
| `q3_update_log.csv` | 含信息情形、`voi_yuan, implemented, l1_change_kwh, up/down_adjust_kwh` |
| `q3_strategy_comparison.csv` | 含 `load_information_case` 的策略摘要 |
| `q3_load_information_comparison.csv` | 按日期、策略、信息情形汇总成本/紧急购电/弃光/SOC/运行时间 |
| `q3_load_forecast_audit.csv` | 日前因果负荷 vs 实际负荷、来源日期、绝对误差 |
| `q3_causality_audit.json` | 扰动尚未发生的同日真实负荷后，主模型预测不变、代理对照可变 |
| `q3_cost_audit.csv` | 逐时段 `g0,gF,p,φ,5pe`，含信息情形 |
| `q3_physical_audit.json` | 能量/SOC 残差、越界、锁定篡改、同时充放电 |
| `q3_warmup_daily_causal_load_main.csv` | 1 月 **主模型** M0 预热，供 2025-02-01 日初 SOC |
| `validation.json` / `validation.md` | 试算后自动复核 |

修订前未标注信息情形的 `q3_dispatch_YYYY-MM-DD_<strategy>.csv` 与
`q3_warmup_daily.csv` 保留为历史文件，校验脚本不会把它们当作主结果。

图写入 `fig/q3_pilot/`：策略成本、M1/M6 调度、VoI 只画 `causal_load_main`；
另有 `fig3_load_information_comparison.png`。

## 试算日初 SOC

- `2025-02-01`：从 2025-01-01 的 6000 kWh 起用 **causal_load_main M0** 预热得到。两种信息情形共用该 SOC。
- `2025-06-21`：孤立试算，日初 6000 kWh。不把 Q2 全年轨迹当作 Q3 状态。

## 策略名

- `M0`：0:00 后不更新
- `M1_M6`：6/12/18 均评估，`VoI>0.01` 元才改承诺
- `M6_only` / `M12_only` / `M18_only`：只开放一个更新点
