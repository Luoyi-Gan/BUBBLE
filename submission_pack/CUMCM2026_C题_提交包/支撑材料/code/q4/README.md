# 小问 4

实现依据：`docs/specs/q4.md`。代码放本目录；运行结果写入 `../output/q4` 与 `../fig`。

当前阶段：P2 两日回归（Q4-2 / Q4-3）。不改已验收价格模块，不覆盖 `result3.xlsx`，两日通过前不写 `result4-*.xlsx`。

```bash
python -m unittest q2.test_q2 q3.test_q3 q3.test_q3_result3_export q4.test_q4_price_forecast q4.test_q4_dispatch -v
python q4/run_q4_twoday.py
python q4/run_q4_full.py --system q4_2
python q4/run_q4_full.py --system q4_3
python q4/export_result4.py
```

两日回归只写 `2025-02-01` 与 `2025-06-21` 的 144 行调度明细；1 月 1 日至试点日为因果 SOC 预热。通过后再跑 365 日并导出 `result4-2.xlsx` / `result4-3.xlsx`（2—12 月）。不改 `result3.xlsx` 或价格预测模块。
