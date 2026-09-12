# 论文本地备份

正式写作源已同步至 `overleaf/`，可将该目录完整上传至 Overleaf，并以 `main.tex` 作为主文件。此处放：

- `outline.md` 章节大纲
- `COMPLETION_PLAN.md`：当前缺口、分工、验收门与交稿清单
- 导出的 PDF 备份（可选，注意体积）
- `manuscript/`：**仅含 `.tex` 的论文正文组成**（`sections/` 与 `tables/`），不含流程说明、图表或编译入口
- `reconciliation.md`：ACCT 数字对账单（`reconcile_paper_numbers.py`；Q1–Q4 共 50/50）
- 导出：`scripts/export_paper_q2_q3.py`（Q2/Q3 表图）、`scripts/export_paper_q4_2.py`（Q4-2 表图）、`scripts/export_paper_q4_3.py`（Q4-3 表图）
- `overleaf/`：可独立编译的 LaTeX 工程（入口、样式、图表、数据、审核稿及当前 PDF 快照）；正文 `.tex` 通过 `preamble.tex` 中的 `\def\input@path` 引用 `../manuscript/`
- `submission/`：提交用 PDF 快照（`main.pdf`）与清单

不提交可由 XeLaTeX 重建的 `.aux`、`.log`、`.out` 缓存；`overleaf/main.pdf` 与 `submission/main.pdf` 为可审阅/提交快照。
