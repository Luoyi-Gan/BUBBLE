# 论文提交快照

> 生成：2026-09-12。与 `paper/overleaf/main.tex` 及 `paper/manuscript/` 同步。

## 文件

| 文件 | 说明 |
| --- | --- |
| `main.pdf` | 全文 PDF（39 页；XeLaTeX 双遍编译，0 error） |

## 题设结果工作簿（仓库根目录 `output/`）

| 文件 | 小问 |
| --- | --- |
| `output/result1.xlsx` | Q1 |
| `output/result2.xlsx` | Q2（V2 政策一致 K=8） |
| `output/result3.xlsx` | Q3（M1_M6） |
| `output/result4-2.xlsx` | Q4-2 |
| `output/result4-3.xlsx` | Q4-3 |

## 复现

```bash
cd paper/overleaf && xelatex -interaction=nonstopmode main.tex && xelatex -interaction=nonstopmode main.tex
python3 scripts/reconcile_paper_numbers.py   # 期望 50/50
python3 scripts/build_submission_pack.py     # 生成 submission_pack/CUMCM2026_C题_提交包.zip
```

## 竞赛提交（format2026.doc）

| 上传项 | 本仓库对应 | 说明 |
| --- | --- | --- |
| 参赛论文 PDF | 提交包内 `参赛论文.pdf` | 单独文件、不压缩；首页为摘要；≤20MB |
| 支撑材料 | 提交包内 `支撑材料/` | 含代码、题设 result*.xlsx、文件列表 |

打包脚本输出：`submission_pack/CUMCM2026_C题_提交包/` 与 `.zip`（已纳入版本库，可直接下载）。

数字对账：`paper/reconciliation.md`
