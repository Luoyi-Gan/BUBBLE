# 小问 4

实现依据：`docs/specs/q4.md`。代码放本目录；运行结果写入 `../output/q4` 与 `../fig`。

当前阶段：已完成全年闭环回测与最终导出。Q4-2 已通过 RQ4-C1 的政策一致校准，Q4-3 固定 Q3 的 `M1_M6`；正式工作簿为 `../output/result4-2.xlsx` 与 `../output/result4-3.xlsx`。1 月用于预测历史与 SOC 预热，题设输出区间为 2025-02-01 至 2025-12-31（334 日）。

```bash
python -m unittest q4.test_q4_price_forecast q4.test_q4_dispatch q4.test_q4_closeout -v
python q4/report_q4_closeout.py
python scripts/reconcile_paper_numbers.py
```

如需完整复现，依次执行 `run_q4_twoday.py`、两套 `run_q4_full.py` 和 `export_result4.py`；全年运行耗时较长，且会重写正式产物，因此仅在需要复现或修复时执行。两日回归覆盖 `2025-02-01` 与 `2025-06-21`，全年调度明细、物理审计、价格因果审计与成本台账均在 `../output/q4/`。不改 `result3.xlsx` 或已验收价格预测模块。
