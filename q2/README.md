# 小问 2 · 分阶段试算

实现依据：`docs/specs/q2.md` 与
`docs/handoff/cursor-c-q2-pilot-implementation.md`。

## 运行

在仓库根目录执行：

```bash
source .venv/bin/activate
python -m unittest q2.test_q2 -v
python q2/run_q2_pilot.py
python q2/validate_q2_pilot.py
```

输入路径可通过 `CUMCM_C_ATTACH_DIR` 指向包含附件 1、附件 2 的目录。

## 试算输出

- `output/q2_pilot/input_audit.json`
- `output/q2_pilot/perfect_information_daily.csv`
- `output/q2_pilot/forecast_archive.csv`、`forecast_audit.md`
- `output/q2_pilot/scenario_selection.csv`、`scenarios_YYYY-MM-DD.csv`
- `output/q2_pilot/k_selection_validation.md`、`k_freeze_calendar.csv`
- `output/q2_pilot/linked_warmup_daily.csv`
- `output/q2_pilot/next_day_value_audit.csv`、`next_day_value_comparison.csv`
- `output/q2_pilot/q2_pilot_dispatch_YYYY-MM-DD.csv`
- `output/q2_pilot/pilot_day_summary.csv`
- `output/q2_pilot/validation.json`、`validation.md`
- `fig/q2_pilot/`

本流程只验证 P0–P4/R1–R4，不创建或修改 `result2.xlsx`。48 小时价值采用带弦线—切面
误差证书的自适应次日随机 LP 对偶切面，并单列有/无该价值的两日试算对比。P1 当前是跨日
SOC 连续的逐日完美信息比较器；由于它和待定的 48 小时主方案视域不同，
暂不将其宣称为严格的全局下界。

## 全年联动计算

日前普通购电采用预购额度 \(q\)：当前时段实际取用满足 \(x\le q\)，未用额度仍按 \(q\)
计费。低价时段的提前准备只能表现为“普通购电—充电—SOC—后续放电”；未来额度不能倒借。
紧急购电只补足当前实际缺口，按 \(5p\) 计费。

```bash
python q2/run_q2_full.py
python q2/run_q2_comparators.py
python q2/run_q2_k8_risk.py
```

`run_q2_full.py` 每 14 日仅用此前主策略已执行的 SOC 轨迹评分并冻结 K，顺序运行全年的
日前计划与日内 MPC。它输出到 `output/q2_full_linked/`，仍不会生成 `result2.xlsx`。
`run_q2_comparators.py` 随后计算无储能联动基线和逐日完美信息比较器。完整年度结果的解释和
物理审计见 `docs/reviews/q2-full-linked-audit.md`。

`run_q2_k8_risk.py` 保留旧方案不覆盖，输出固定 K=8 与滚动风险分位候选方案到
`output/q2_full_k8_risk/`。K=8 的验证依据、早期 K=1 回退和成本复核见
`docs/reviews/q2-k8-risk-recalculation.md`。
