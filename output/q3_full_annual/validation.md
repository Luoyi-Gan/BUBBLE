# Q3 全年连续 SOC（A=1200 与 B=6000 分列运行）

主口径固定 `causal_load_main` + `linear_anchor_main` + `anchor_final_main`。
A、B 是两条彼此独立的 365 日路径，各自从 2025-01-01 的 6000 kWh 出发，不共享 SOC。
**不**生成 `result3.xlsx`，**不**实现 M5，**不**把两案平均成一个主结论。

## 运行

```bash
.venv/bin/python -m unittest q3.test_q3 -v
.venv/bin/python q3/run_q3_full_annual.py --boundary both
.venv/bin/python q3/validate_q3_full_annual.py
```

- 物理/连续审计全部通过：True
- git：233d13f7270525574c784129bf594793f3193787
- 求解器：HIGHS；依赖：{'python': '3.12.3', 'numpy': '2.4.4', 'pandas': '3.0.5', 'cvxpy': '1.9.2', 'matplotlib': '3.11.1'}
- 日运行数：3650（2 边界 × 5 策略 × 365 日）

## 策略 × 边界汇总

strategy year_end_boundary  year_end_soc_kwh load_information_case    pv_mapping_mode   settlement_mode  with_terminal_value  n_days  total_cost_yuan  settlement_cost_yuan  emergency_cost_yuan  emergency_kwh  curtailment_kwh   charge_kwh  discharge_kwh  adjustment_count  up_adjust_kwh  down_adjust_kwh  soc_start_jan01_kwh  soc_end_dec31_kwh  max_balance_residual_kwh  max_soc_residual_kwh  max_simultaneous_cd_kwh2  locked_period_violations  runtime_seconds  cost_rank_within_boundary
      M0      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.710957e+07          1.333599e+07         3.773579e+06   1.051775e+06     1.338824e+06 7.009830e+06   6.313400e+06                 0       0.000000         0.000000               6000.0             1200.0              4.773642e-08          6.435152e-08                       0.0                         0      1483.111942                        4.0
M12_only      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.656549e+07          1.353168e+07         3.033806e+06   8.136093e+05     1.284601e+06 7.010919e+06   6.314381e+06               365  324909.346555    356669.798562               6000.0             1200.0              4.945377e-12          6.435221e-08                       0.0                         0      1476.799816                        2.0
M18_only      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.711038e+07          1.334220e+07         3.768181e+06   1.050830e+06     1.338824e+06 7.009610e+06   6.313203e+06               218    5108.473906      4745.129306               6000.0             1200.0              4.773642e-08          6.435289e-08                       0.0                         0      1471.179434                        5.0
   M1_M6      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.637351e+07          1.360247e+07         2.771036e+06   7.423228e+05     1.237691e+06 7.049816e+06   6.349388e+06               947  468477.002882    571193.901493               6000.0             1200.0              4.357048e-08          6.435243e-08                       0.0                         0      1638.887716                        1.0
 M6_only      A_q2_aligned            1200.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.675534e+07          1.364441e+07         3.110929e+06   8.531627e+05     1.279368e+06 7.048654e+06   6.348343e+06               364  512716.030782    581751.695967               6000.0             1200.0              4.774006e-08          6.435266e-08                       0.0                         0      1499.098163                        3.0
      M0  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.711182e+07          1.333810e+07         3.773729e+06   1.051818e+06     1.338824e+06 7.014268e+06   6.312841e+06                 0       0.000000         0.000000               6000.0             6000.0              2.586376e-11          6.435152e-08                       0.0                         0      1455.870104                        4.0
M12_only  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.656775e+07          1.353379e+07         3.033956e+06   8.136525e+05     1.284601e+06 7.015357e+06   6.313822e+06               365  324909.346555    356669.798562               6000.0             6000.0              4.945377e-12          6.435221e-08                       0.0                         0      1469.989664                        2.0
M18_only  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.711264e+07          1.334430e+07         3.768331e+06   1.050873e+06     1.338824e+06 7.014049e+06   6.312644e+06               218    5108.473906      4745.129306               6000.0             6000.0              4.357048e-08          6.435289e-08                       0.0                         0      1468.742590                        5.0
   M1_M6  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.637577e+07          1.360458e+07         2.771187e+06   7.423668e+05     1.237691e+06 7.054249e+06   6.348824e+06               947  468481.473145    571193.901493               6000.0             6000.0              4.357048e-08          6.435243e-08                       0.0                         0      1524.202793                        1.0
 M6_only  B_energy_neutral            6000.0      causal_load_main linear_anchor_main anchor_final_main                 True     365     1.675758e+07          1.364652e+07         3.111062e+06   8.532017e+05     1.279368e+06 7.053093e+06   6.347784e+06               364  512716.030782    581751.695967               6000.0             6000.0              2.586376e-11          6.435266e-08                       0.0                         0      1477.884545                        3.0

## ΔC = C(6000) − C(1200)

strategy  delta_cost_B_minus_A_yuan  delta_emergency_cost_B_minus_A_yuan  delta_emergency_kwh_B_minus_A  delta_curtailment_kwh_B_minus_A  delta_charge_kwh_B_minus_A  delta_discharge_kwh_B_minus_A  rank_A  rank_B  rank_changed  soc_end_A_kwh  soc_end_B_kwh
      M0                2255.436197                           149.912055                      43.189268                              0.0                 4438.456301                    -559.069160       4       4         False         1200.0         6000.0
   M1_M6                2262.879895                           151.712493                      43.981007                              0.0                 4433.489342                    -563.539423       1       1         False         1200.0         6000.0
 M6_only                2238.410896                           132.886754                      38.983466                              0.0                 4438.456301                    -559.069160       3       3         False         1200.0         6000.0
M12_only                2255.436197                           149.912055                      43.189268                              0.0                 4438.456301                    -559.069160       2       2         False         1200.0         6000.0
M18_only                2255.436197                           149.912055                      43.189268                              0.0                 4438.456301                    -559.069160       5       5         False         1200.0         6000.0

两案并存供队长选择；在选定主边界之前不得写入论文正式成本。
