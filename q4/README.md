# 小问 4

实现依据：`docs/specs/q4.md`。代码放本目录；运行结果写入 `../output/q4` 与 `../fig`。

当前只实现因果价格预测模块（P1）。不要在本阶段启动 Q4-2 / Q4-3 全年储能计算，也不要生成 `result4-2.xlsx` / `result4-3.xlsx`。

```bash
.venv/bin/python -m unittest q4.test_q4_price_forecast -v
.venv/bin/python q4/run_price_forecast_audit.py
```
