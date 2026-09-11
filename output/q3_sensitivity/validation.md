# Q3 映射/结算敏感性两日审计（RQ3-2、RQ3-4、RQ3-5）

主负荷口径仍为 `causal_load_main`。本目录与已验收的 `output/q3_pilot/` 隔离。
**不**生成 `result3.xlsx`，**不**实现 M5，**不**宣布全年策略排序。

## 运行

```bash
.venv/bin/python -m unittest q3.test_q3 -v
.venv/bin/python q3/run_q3_sensitivity.py
.venv/bin/python q3/validate_q3_sensitivity.py
```

- 物理审计全部通过：True
- git：6a67759c7af207be9439fe25b43fd4c03b33f25c
- 求解器：HIGHS；依赖：{'python': '3.12.3', 'numpy': '2.4.4', 'pandas': '3.0.5', 'cvxpy': '1.9.2', 'matplotlib': '3.11.1'}
- 运行键数：40（2 日 × 5 策略 × 2 映射 × 2 结算）
- 日初 SOC：{'2025-02-01': 8687.551655739135, '2025-06-21': 6000.0}

## 相对 baseline（linear_anchor_main + anchor_final_main）的总成本差

pv_mapping_mode               linear_anchor_main                        step_hourly_sensitivity                  
settlement_mode     adjacent_literal_sensitivity anchor_final_main adjacent_literal_sensitivity anchor_final_main
date       strategy                                                                                              
2025-02-01 M0                       0.000000e+00               0.0                  6730.327940       6730.327940
           M12_only                 3.711418e+02               0.0                  5165.803096       5165.803096
           M18_only                 2.723964e+01               0.0                  6757.567579       6726.554650
           M1_M6                    1.054852e+03               0.0                  4908.120290       4578.988981
           M6_only                  2.190361e+02               0.0                  4465.369732       5263.748906
2025-06-21 M0                       1.527951e-10               0.0                    84.630033         84.630033
           M12_only                 9.909490e-08               0.0                  2273.640782       2273.640782
           M18_only                -8.640195e+01               0.0                    -1.806217         -1.067582
           M1_M6                   -2.370022e+02               0.0                  1847.055730       1511.715387
           M6_only                  1.565030e+02               0.0                  1410.370329       1269.310894

## 对照全表

      date strategy         pv_mapping_mode              settlement_mode  total_cost_yuan  settlement_cost_yuan  emergency_cost_yuan  emergency_kwh  curtailment_kwh  soc_start_kwh  soc_end_kwh  adjustment_count  delta_total_vs_baseline_yuan
2025-02-01       M0      linear_anchor_main            anchor_final_main     22523.385091          21612.595340           910.789751     413.043837      1857.761106    8687.551656  9086.850004                 0                  0.000000e+00
2025-02-01    M1_M6      linear_anchor_main            anchor_final_main     21633.924536          21619.260313            14.664223       6.737525      2387.809555    8687.551656  9028.673323                 3                  0.000000e+00
2025-02-01  M6_only      linear_anchor_main            anchor_final_main     21917.775593          21028.366650           889.408943     351.518882      1517.151149    8687.551656  9083.531908                 1                  0.000000e+00
2025-02-01 M12_only      linear_anchor_main            anchor_final_main     21259.696113          21234.644157            25.051956       9.783649      1385.155625    8687.551656  9085.071513                 1                  0.000000e+00
2025-02-01 M18_only      linear_anchor_main            anchor_final_main     22496.145451          21585.355700           910.789751     413.043837      1857.761106    8687.551656  9028.673323                 1                  0.000000e+00
2025-02-01       M0      linear_anchor_main adjacent_literal_sensitivity     22523.385091          21612.595340           910.789751     413.043837      1857.761106    8687.551656  9086.850004                 0                  0.000000e+00
2025-02-01    M1_M6      linear_anchor_main adjacent_literal_sensitivity     22688.776489          22674.112265            14.664223       6.737525      3853.818205    8687.551656  9086.850004                 1                  1.054852e+03
2025-02-01  M6_only      linear_anchor_main adjacent_literal_sensitivity     22136.811653          21612.595340           524.216313     188.399465      2985.034500    8687.551656  9082.169684                 0                  2.190361e+02
2025-02-01 M12_only      linear_anchor_main adjacent_literal_sensitivity     21630.837950          21612.595340            18.242611       8.352321      2079.923000    8687.551656  9086.850004                 0                  3.711418e+02
2025-02-01 M18_only      linear_anchor_main adjacent_literal_sensitivity     22523.385091          21612.595340           910.789751     413.043837      1857.761106    8687.551656  9086.850004                 0                  2.723964e+01
2025-02-01       M0 step_hourly_sensitivity            anchor_final_main     29253.713030          22187.326139          7066.386891    2371.417120      2134.640008    8687.551656  9094.908756                 0                  6.730328e+03
2025-02-01    M1_M6 step_hourly_sensitivity            anchor_final_main     26212.913517          22665.335400          3547.578116     761.751266      1996.913621    8687.551656  9028.673323                 3                  4.578989e+03
2025-02-01  M6_only step_hourly_sensitivity            anchor_final_main     27181.524499          21668.108204          5513.416295    1662.690220      1464.250863    8687.551656  9094.908755                 1                  5.263749e+03
2025-02-01 M12_only step_hourly_sensitivity            anchor_final_main     26425.499209          22437.223360          3988.275849     962.200900      1736.162608    8687.551656  9094.908755                 1                  5.165803e+03
2025-02-01 M18_only step_hourly_sensitivity            anchor_final_main     29222.700101          22156.313209          7066.386891    2371.417120      2134.640008    8687.551656  9028.673323                 1                  6.726555e+03
2025-02-01       M0 step_hourly_sensitivity adjacent_literal_sensitivity     29253.713030          22187.326139          7066.386891    2371.417120      2134.640008    8687.551656  9094.908756                 0                  6.730328e+03
2025-02-01    M1_M6 step_hourly_sensitivity adjacent_literal_sensitivity     26542.044826          23376.196606          3165.848220     589.490483      2769.640895    8687.551656  9094.908756                 1                  4.908120e+03
2025-02-01  M6_only step_hourly_sensitivity adjacent_literal_sensitivity     26383.145326          22187.326139          4195.819187    1066.324937      2172.114783    8687.551656  9094.908756                 0                  4.465370e+03
2025-02-01 M12_only step_hourly_sensitivity adjacent_literal_sensitivity     26425.499209          22437.223361          3988.275849     962.200900      1736.162608    8687.551656  9094.908756                 1                  5.165803e+03
2025-02-01 M18_only step_hourly_sensitivity adjacent_literal_sensitivity     29253.713030          22187.326139          7066.386891    2371.417120      2134.640008    8687.551656  9094.908756                 0                  6.757568e+03
2025-06-21       M0      linear_anchor_main            anchor_final_main     25712.067745          17121.720868          8590.346878    2345.203044     11841.181695    6000.000000  8026.258718                 0                  0.000000e+00
2025-06-21    M1_M6      linear_anchor_main            anchor_final_main     22937.358842          17260.017663          5677.341179    1448.847633     11139.713197    6000.000000  8026.258718                 3                  0.000000e+00
2025-06-21  M6_only      linear_anchor_main            anchor_final_main     23104.959573          17096.060545          6008.899027    1562.903570     10943.267720    6000.000000  8026.258718                 1                  0.000000e+00
2025-06-21 M12_only      linear_anchor_main            anchor_final_main     23088.960058          17571.143115          5517.816943    1420.829145     11404.394617    6000.000000  8026.258718                 1                  0.000000e+00
2025-06-21 M18_only      linear_anchor_main            anchor_final_main     25798.503995          17112.120651          8686.383344    2360.907635     11841.181695    6000.000000  8026.258718                 1                  0.000000e+00
2025-06-21       M0      linear_anchor_main adjacent_literal_sensitivity     25712.067745          17121.720868          8590.346878    2345.203044     11841.181695    6000.000000  8026.258718                 0                  1.527951e-10
2025-06-21    M1_M6      linear_anchor_main adjacent_literal_sensitivity     22700.356682          17569.572058          5130.784625    1333.046257     11336.948406    6000.000000  8026.258718                 2                 -2.370022e+02
2025-06-21  M6_only      linear_anchor_main adjacent_literal_sensitivity     23261.462532          17239.887792          6021.574740    1566.386581     11280.124056    6000.000000  8026.258718                 1                  1.565030e+02
2025-06-21 M12_only      linear_anchor_main adjacent_literal_sensitivity     23088.960058          17571.143115          5517.816943    1420.829145     11404.394617    6000.000000  8026.258718                 1                  9.909490e-08
2025-06-21 M18_only      linear_anchor_main adjacent_literal_sensitivity     25712.102047          17121.720868          8590.381179    2345.203044     11841.181695    6000.000000  8026.258718                 0                 -8.640195e+01
2025-06-21       M0 step_hourly_sensitivity            anchor_final_main     25796.697778          18255.617513          7541.080265    2410.207623     11366.750717    6000.000000  8026.258718                 0                  8.463003e+01
2025-06-21    M1_M6 step_hourly_sensitivity            anchor_final_main     24449.074229          18472.777024          5976.297205    1921.875910     11107.789679    6000.000000  8026.258718                 3                  1.511715e+03
2025-06-21  M6_only step_hourly_sensitivity            anchor_final_main     24374.270467          18253.195435          6121.075032    1959.120027     10856.747237    6000.000000  8026.258718                 1                  1.269311e+03
2025-06-21 M12_only step_hourly_sensitivity            anchor_final_main     25362.600840          19387.824600          5974.776240    1921.484110     11681.298521    6000.000000  8026.258718                 1                  2.273641e+03
2025-06-21 M18_only step_hourly_sensitivity            anchor_final_main     25797.436413          18255.476489          7541.959924    2410.434222     11366.750717    6000.000000  8026.258718                 1                 -1.067582e+00
2025-06-21       M0 step_hourly_sensitivity adjacent_literal_sensitivity     25796.697778          18255.617513          7541.080265    2410.207623     11366.750717    6000.000000  8026.258718                 0                  8.463003e+01
2025-06-21    M1_M6 step_hourly_sensitivity adjacent_literal_sensitivity     24784.414571          18812.206613          5972.207958    1920.912544     11403.494824    6000.000000  8026.258718                 2                  1.847056e+03
2025-06-21  M6_only step_hourly_sensitivity adjacent_literal_sensitivity     24515.329901          18394.254869          6121.075032    1959.120027     11065.697646    6000.000000  8026.258718                 1                  1.410370e+03
2025-06-21 M12_only step_hourly_sensitivity adjacent_literal_sensitivity     25362.600841          19387.824601          5974.776240    1921.484110     11681.298521    6000.000000  8026.258718                 1                  2.273641e+03
2025-06-21 M18_only step_hourly_sensitivity adjacent_literal_sensitivity     25796.697778          18255.617513          7541.080265    2410.207623     11366.750717    6000.000000  8026.258718                 0                 -1.806217e+00

数字待队长签收前不得写入论文主结论。
