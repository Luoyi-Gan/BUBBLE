# 小问 3 · 四时点滚动购电调整（两日试算）

实现依据：`docs/specs/q3.md` 与
`docs/handoff/cursor-c-q3-implementation.md`。

本阶段只完成 P0–P3 两日端到端试算和审计。未经 Codex/队长复核，不生成
`output/result3.xlsx`，不实现 M5 情景树，不跑全年批量。

## 运行

在仓库根目录：

```bash
export CUMCM_C_ATTACH_DIR=/path/to/C题/附件   # 含 附件1.xlsx 附件2.xlsx 附件3.xlsx
python -m unittest q3.test_q3 -v
python q3/run_q3_pilot.py
python q3/validate_q3_pilot.py
```

若未设置环境变量，代码会依次尝试队长本机路径和仓库 `data/raw/`。

## 口径（不可变更）

- 内部时段 0–143，功率乘 `Δt=1/6` 得 kWh；不旋转附件行序。
- 结算只锚定当日 0:00 原计划：`φ=p g^F + 0.5 p |g^F-g^0|`，中间版本不重复计费。
- 6/12/18 只能改未执行时段，首个可改索引分别为 36/72/108。
- 附件 3 逐小时预报用更新时点已观测实际光伏作因果锚点，再与随后整点预报线性插值。
- 负荷按已确认假设作为确定输入（集中配置 `LOAD_TREATMENT`），执行层当前光伏用实际值、未来光伏只用当次已发布预报。
- 终端价值复用 Q2 的 48 小时切面结构，但按 Q3 预报口径重建；同时输出无终端价值对照。

## 试算输出

全部写入 `output/q3_pilot/`：

| 文件 | 说明 |
| --- | --- |
| `input_audit.json` | 附件 1/2/3 行列、缺失、四条预报完整性和时间映射 |
| `q3_forecast_mapping.csv` | 两试算日、四个更新点的 10 分钟预报、插值节点/权重、是否已执行实际值 |
| `q3_dispatch_YYYY-MM-DD_<strategy>.csv` | 逐时段调度。列：`time, planned_g0_kwh, final_g_kwh, normal_x_kwh, load_kwh, actual_pv_kwh, forecast_pv_kwh, charge_kwh, discharge_kwh, curtailment_kwh, emergency_kwh, soc_kwh, balance_residual_kwh, last_update_time` |
| `q3_update_log.csv` | 含 `voi_yuan, implemented, l1_change_kwh, up/down_adjust_kwh, j_fix_yuan, j_free_yuan` |
| `q3_strategy_comparison.csv` | M0、M1/M6、单时点消融、无 48h 对照的成本与物理摘要 |
| `q3_cost_audit.csv` | 逐时段 `g0,gF,p,φ,5pe` |
| `q3_physical_audit.json` | 能量/SOC 残差、越界、锁定篡改、同时充放电 |
| `q3_warmup_daily.csv` | 1 月 M0 预热，供 2025-02-01 日初 SOC |
| `validation.json` / `validation.md` | 试算后自动复核 |

图写入 `fig/q3_pilot/`：`fig3_strategy_cost.png`、`fig3_dispatch_*_M1_M6.png`、`fig3_voi_*.png`。

## 试算日初 SOC

- `2025-02-01`：从 2025-01-01 的 6000 kWh 起用 Q3 的 M0 预热得到。
- `2025-06-21`：孤立试算，日初 6000 kWh。不把 Q2 全年轨迹当作 Q3 状态。

## 策略名

- `M0`：0:00 后不更新
- `M1_M6`：6/12/18 均评估，`VoI>0.01` 元才改承诺
- `M6_only` / `M12_only` / `M18_only`：只开放一个更新点
