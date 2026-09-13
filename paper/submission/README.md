# 论文提交快照

> 生成：2026-09-13。与 `paper/overleaf/main.tex` 及 `paper/manuscript/` 同步。

## 文件

| 文件 | 说明 |
| --- | --- |
| `main.pdf` | 全文 PDF（360 页：摘要 1 页、正文 30 页、附录 329 页；XeLaTeX 编译，0 error、0 版面越界警告） |
| `支撑材料/AI 工具使用详情.pdf` | AI 工具使用详情；与正文参考文献前的 AI 工具使用声明对应。 |
| `支撑材料.zip` | 匿名支撑材料压缩包（程序、正式结果、依赖说明、数字对账和 AI 工具使用详情；小于 20 MB）。 |

## 题设结果工作簿（仓库根目录 `output/`）

| 文件 | 小问 |
| --- | --- |
| `output/result1.xlsx` | Q1 |
| `output/result2.xlsx` | Q2（日前风险额度与日内滚动调度，$K=8$） |
| `output/result3.xlsx` | Q3（全时点价值触发调整策略） |
| `output/result4-2.xlsx` | Q4-2 |
| `output/result4-3.xlsx` | Q4-3 |

## 复现

```bash
cd paper/overleaf && xelatex -interaction=nonstopmode main.tex && xelatex -interaction=nonstopmode main.tex
python3 scripts/reconcile_paper_numbers.py   # 期望 50/50
```

数字对账：`paper/reconciliation.md`。最终交付已逐页渲染复核，五个题设结果工作簿均已独立打开验证。
