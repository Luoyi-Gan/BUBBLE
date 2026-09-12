# BUBBLE 完整 Overleaf 项目

此目录是**自包含**的 Overleaf 上传包：正文在 `sections/`，表格在 `tables/`，图片在 `figures/`，主文件为根目录 `main.tex`。项目不依赖仓库外的 `manuscript/` 或任何绝对、上级路径。

## 上传与编译

1. 在 Overleaf 选择 **New Project → Upload Project**，上传 `BUBBLE_Overleaf_complete.zip`；也可以将本目录全部文件拖入一个新项目。
2. 将编译器设为 **XeLaTeX**。
3. 将根目录的 `main.tex` 设为 **Main document**。
4. 点击 **Recompile**；首次编译完成后再编译一次以刷新交叉引用。

本目录已在独立环境用 XeLaTeX 双遍验证，可生成 39 页完整 PDF。

## 内容位置

- 全文入口：`main.tex`
- 共同版式和开关：`preamble.tex`、`assembly.tex`、`paper_layout.sty`
- 摘要、假设、符号、问题分析、评价、参考文献和附录：`sections/`
- Q1--Q4 正文：`sections/q1/`、`sections/q2/`、`sections/q3/`、`sections/q4/`
- 正文表格：`tables/q1/`、`tables/q2/`、`tables/q3/`、`tables/q4/`
- 图片：`figures/q1/` 至 `figures/q4/`

修改正文或表格后，直接编辑对应的 `sections/`、`tables/` 文件；不要将子文件内容复制回 `main.tex`，也不要在子文件添加 `documentclass` 或 `\begin{document}`。

## 说明

- Q1--Q4 均已接入主文档；`assembly.tex` 中的 Ready 开关均为 `true`。
- 题设输出区间统一为 2025-02-01 至 2025-12-31；如出现 1--12 月完整核算，正文会单列说明。
- 若打开旧项目仍报缺少 `sections/`，请新建项目并上传本目录的完整压缩包；不要只上传 `main.tex`、模板文件或旧的结构包。
