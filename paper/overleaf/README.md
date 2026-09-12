# BUBBLE 统一 Overleaf 写作项目

本项目合并 Q1_Overleaf.zip 的 Q1 内容、BUBBLE_Overleaf_structure_update.zip 的全文框架，并补入已完成的 Q1—Q4 问题重述。后续只维护这一项目；旧压缩包留作备份。

## 第一次上传（建议新建项目，避免覆盖你在旧项目里自行修改的句子）

1. 在 Overleaf 项目列表选择 **New Project → Upload Project**。
2. 上传 `BUBBLE_Overleaf_unified.zip`，无需提前解压，也不需要再上传旧框架包或 Q1 包。
3. 打开项目设置，在 **Compiler** 中选择 **XeLaTeX**。
4. 在 **Main document** 中选择根目录的 **main.tex**。
5. 点击 **Recompile**；如首次提示引用更新，再编译一次。PDF 中应有具体 Q1 内容、两张正文结果表、两幅图及完整计划附录。
6. 保存当前项目为新的论文工作项目。若旧 Overleaf 项目中有本地压缩包之外的改动，请按对应章节迁移文字，不要用旧 main.tex 覆盖本项目入口。

## 平时改哪个文件

正文 `.tex` 统一放在 **`../manuscript/`**（仅含 `sections/` 与 `tables/` 的论文组成文件）；`preamble.tex` 通过 `\input@path` 引用该目录，因此 `\input{sections/...}` 与 `\input{tables/...}` 路径不变。Overleaf 上传时需保证项目内能访问到 `manuscript/`（建议以 `paper/` 为项目根，主文件选 `overleaf/main.tex`）。

- 全文入口：`main.tex`，一般不用改。
- 章节接入状态：`assembly.tex`，只在相应内容审核完成后切换 Ready 开关。
- 共同版式：`paper_layout.sty`；沿用原类文件和样式，统一 A4 四边25mm、正文12pt、1.35倍行距、2字符首行缩进、一级居中黑体中文编号。
- 问题背景与重述：`../manuscript/sections/restatement/background.tex`、`q1.tex`、`q2.tex`、`q3.tex`、`q4.tex`。
- 假设：`../manuscript/sections/q1/00_assumptions.tex`，全篇入口为 `../manuscript/sections/02_assumptions.tex`。
- 符号：`../manuscript/sections/q1/00_notation.tex`，全篇入口为 `../manuscript/sections/03_notation.tex`。
- Q1 问题分析：`../manuscript/sections/q1/01_analysis.tex`。
- Q1 模型建立：`../manuscript/sections/q1/02_model.tex`。
- Q1 模型求解：`../manuscript/sections/q1/03_solution.tex`。
- Q1 成本下界：`../manuscript/sections/q1/04_bounds.tex`。
- Q1 结果分析：`../manuscript/sections/q1/05_results.tex`。
- Q1 可行性与稳健性：`../manuscript/sections/q1/06_validation.tex`。
- Q2/Q3/Q4：分别进入 `../manuscript/sections/q2/`、`q3/`、`q4/`，同样按分析、模型、求解、结果、检验逐文件填写；Q3 已接入问题分析、假设、模型建立与求解。
- 结果表：`../manuscript/tables/q1/purchase.tex`、`storage.tex`，按题目正文表1/表2；`plan_appendix.tex` 为完整明细。
- 图片：`figures/q1/`；各问分别建文件夹，使用相对路径。
- 摘要：`../manuscript/sections/00_abstract.tex`；全篇评价：`../manuscript/sections/06_evaluation.tex`。
- 参考文献：`../manuscript/sections/07_references.tex`；附录：`../manuscript/sections/08_appendix.tex`；AI使用声明：`../manuscript/sections/09_ai_statement.tex`。

修改某个 tex 中的具体句子后，保存并重新编译。不要把子文件中的内容再复制进 main.tex。不要在内容子文件增加 documentclass 或 begin/end document。

## 分部分审阅怎么操作

1. 在 **Main document** 中临时选择 `review_restatement.tex`、`review_q1.tex` 或 `review_q1_analysis.tex` / `review_q1_model.tex` / `review_q1_solution.tex` / `review_q1_results.tex`。
2. 点击 Recompile，下载该部分 PDF 进行审核；正文与 main.tex 引用同一组内容文件。
3. 修改仍在 `../manuscript/sections/` 或 `../manuscript/tables/` 中进行，不直接编辑 PDF，也不复制一份正文到 review 入口。
4. 看全文时，把 Main document 切回 `main.tex`。
5. Q2—Q4 已预建 `review_q2.tex`、`review_q3.tex`、`review_q4.tex`；当前只是空框架，填入各问文件后使用。

## 如何最终合并

Q1、Q2 和 Q3 的当前正文已接入主文档：Q2 使用政策一致的闭环口径，Q3 使用全年因果主口径。Q4 保持待撰写提示，待其运行、信息一致性复核和结果审计全部完成后再接入。

每部分可以单独写和审，整问确认后在 assembly.tex 将相应的 `QTwoReadyfalse` / `QThreeReadyfalse` / `QFourReadyfalse` 改为 `...Readytrue`。四问及摘要、评价、声明全部完成后，再将 `FinalPartsReadyfalse` 改为 `FinalPartsReadytrue`，将 `DraftNotestrue` 改为 `DraftNotesfalse`。最后编译 main.tex 两次，自动生成完整论文，不需要手工拼接 PDF 或复制合并正文。

## 当前进度与下一步

以本次说明为准：Q1--Q3 已有可核验的模型正文与结果文字；题设格式的 Q2/Q3 结果表、图表及全篇摘要尚待补齐。Q4 当前运行中，任何成本、图表和结论均须等待其因果性与物理审计通过后再写入。具体材料清单、逐步任务和完成条件见 `WRITING_PLAN.md`。

## 字体与表格

正文、数学公式、标题、题注、页码和表格使用黑色；表格为无底色黑色三线表。原有两幅图保留配色。本项目使用 Overleaf 内置的 **Fandol 宋体/黑体**与 TeX Gyre 西文字体，使本地和云端不依赖 Windows 字体。Fandol 宋体与 Windows SimSun 不同，若必须与 SimSun 字形逐字完全一致，需要另行提供可合法使用的字体文件；本包没有把专有字体复制分发。

## 核对与来源

本包 data/q1/ 存放 Q1 原精度结果和对照数据，正文按4位小数显示。整合来源与修复点见 SOURCE_AUDIT.md；编译和逐页检查见 BUILD_REPORT.md。本次未改动两个旧压缩包，未访问或修改你的 Overleaf 项目，未操作 GitHub，也未重新求解模型。
