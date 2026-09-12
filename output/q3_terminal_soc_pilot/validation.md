# Q3 年末 SOC 边界 12 月试验审计

主口径固定 `causal_load_main` + `linear_anchor_main` + `anchor_final_main`。
12 月 1 日 00:00 孤立起点 6000 kWh，不是全年真实 12 月 1 日 SOC。
**不**生成 `result3.xlsx`，**不**实现 M5，**不**自动选择 A/B。

## 运行

```bash
.venv/bin/python -m unittest q3.test_q3 -v
.venv/bin/python q3/run_q3_terminal_soc_pilot.py
.venv/bin/python q3/validate_q3_terminal_soc_pilot.py
```

- 物理/连续审计全部通过：True
- git：bee4f4d711a7b79f5e9a765c0d821a4cc59a57ad
- 求解器：HIGHS；依赖：{'python': '3.12.3', 'numpy': '2.4.4', 'pandas': '3.0.5', 'cvxpy': '1.9.2', 'matplotlib': '3.11.1'}
- 日运行数：310（2 边界 × 5 策略 × 31 日）

## 策略 × 边界汇总

strategy year_end_boundary  year_end_soc_kwh load_information_case    pv_mapping_mode   settlement_mode  with_terminal_value  n_days  total_cost_yuan  settlement_cost_yuan  emergency_cost_yuan  emergency_kwh  curtailment_kwh    charge_kwh  discharge_kwh  adjustment_count  up_adjust_kwh  down_adjust_kwh  soc_start_dec01_kwh  soc_end_dec31_kwh  max_balance_residual_kwh  max_soc_residual_kwh  max_simultaneous_cd_kwh2  locked_period_violations  runtime_seconds  cost_rank_within_boundary
      M0      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.879051e+06          1.421247e+06        457804.238226  139977.069511       485.785379 745012.334406  675064.780796                 0       0.000000         0.000000               6000.0             1200.0              4.773642e-08          5.031870e-08                       0.0                         0       124.826066                        4.0
M12_only      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.841058e+06          1.442487e+06        398571.037941  120185.023669       149.249219 744876.259575  674942.313448                31   28713.665647     17638.434640               6000.0             1200.0              3.410605e-12          4.826393e-08                       0.0                         0       123.726646                        2.0
M18_only      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.879157e+06          1.421350e+06        457806.832935  139980.257836       485.785379 744966.242013  675023.297643                 5     103.786841        65.492011               6000.0             1200.0              4.773642e-08          5.031870e-08                       0.0                         0       123.547443                        5.0
   M1_M6      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.830896e+06          1.452045e+06        378850.777399  113576.873705       137.776245 746919.218438  676780.976425                68   43949.888618     32768.458807               6000.0             1200.0              2.933120e-11          4.826393e-08                       0.0                         0       137.075210                        1.0
 M6_only      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.847942e+06          1.451118e+06        396823.383623  119535.531174       476.787196 746363.325170  676280.672484                31   42680.033565     32392.468523               6000.0             1200.0              4.774006e-08          5.032234e-08                       0.0                         0       124.157507                        3.0
      M0  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.881307e+06          1.423352e+06        457954.150281  140020.258779       485.785379 749450.790707  674505.711636                 0       0.000000         0.000000               6000.0             6000.0              2.586376e-11          4.437243e-08                       0.0                         0       122.194429                        4.0
M12_only  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.843313e+06          1.444592e+06        398720.949997  120228.212937       149.249219 749314.715876  674383.244288                31   28713.665647     17638.434640               6000.0             6000.0              3.410605e-12          4.437243e-08                       0.0                         0       123.759377                        2.0
M18_only  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.881412e+06          1.423456e+06        457956.744990  140023.447104       485.785379 749404.698314  674464.228483                 5     103.786841        65.492011               6000.0             6000.0              2.933120e-11          4.437243e-08                       0.0                         0       123.764159                        5.0
   M1_M6  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.833159e+06          1.454156e+06        379002.489892  113620.854712       137.776245 751352.707780  676217.437002                68   43954.358880     32768.458807               6000.0             6000.0              2.933120e-11          4.437243e-08                       0.0                         0       127.699840                        1.0
 M6_only  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True      31     1.850180e+06          1.453224e+06        396956.270377  119574.514639       476.787196 750801.781471  675721.603324                31   42680.033565     32392.468523               6000.0             6000.0              2.586376e-11          4.437243e-08                       0.0                         0       124.514563                        3.0

## ΔC = C(6000) − C(1200)

strategy  delta_cost_B_minus_A_yuan  delta_emergency_cost_B_minus_A_yuan  delta_emergency_kwh_B_minus_A  delta_curtailment_kwh_B_minus_A  delta_charge_kwh_B_minus_A  delta_discharge_kwh_B_minus_A  rank_A  rank_B  rank_changed  soc_end_A_kwh  soc_end_B_kwh
      M0                2255.436197                           149.912055                      43.189268                              0.0                 4438.456301                    -559.069160       4       4         False         1200.0         6000.0
   M1_M6                2262.879895                           151.712493                      43.981007                              0.0                 4433.489342                    -563.539423       1       1         False         1200.0         6000.0
 M6_only                2238.410896                           132.886754                      38.983466                              0.0                 4438.456301                    -559.069160       3       3         False         1200.0         6000.0
M12_only                2255.436197                           149.912055                      43.189268                              0.0                 4438.456301                    -559.069160       2       2         False         1200.0         6000.0
M18_only                2255.436197                           149.912055                      43.189268                              0.0                 4438.456301                    -559.069160       5       5         False         1200.0         6000.0

本试验只为队长选择年末边界提供证据，不得写入论文主结论。
