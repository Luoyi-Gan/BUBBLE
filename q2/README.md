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

本流程只验证 P0–P4/R1–R4，不创建或修改 `result2.xlsx`。合同 `x<=q` 与
`T_max` 仍待签收，配置集中在 `q2/config.py`。48 小时价值采用带弦线—切面
误差证书的自适应次日随机 LP 对偶切面，并单列有/无该价值的两日试算对比。P1 当前是跨日
SOC 连续的逐日完美信息比较器；由于它和待定的 48 小时主方案视域不同，
暂不将其宣称为严格的全局下界。
