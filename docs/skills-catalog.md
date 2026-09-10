# 数学建模 Skills 清单

GitHub 上可安装的 Agent Skills 索引，按本队 **队长 + Codex + Cursor + FIN + ACCT** 分工整理。  
安装位置：项目级 `.cursor/skills/`（可提交到本仓，全队共享）。

**原则：** Skills 辅助流程，不替代队长决策；数字以 `output/` + `results_summary.md` 为准。

---

## 本队推荐安装（勾选清单）

赛前按优先级安装，不要一次装太多（易与分工流程冲突）。

| 安装 | Skill / 包 | 来源仓库 | 主要用途 | 角色 |
|:----:|------------|----------|----------|------|
| [ ] | `cumcm-modeling` | [whyself/cumcm-skills](https://github.com/whyself/cumcm-skills) | 题意拆解、模型路线、假设与公式（64 模型参考） | Codex |
| [ ] | `cumcm-plotting` | [whyself/cumcm-skills](https://github.com/whyself/cumcm-skills) | 数据绘图（100 模板 + 脚本） | Cursor |
| [ ] | `cumcm-result-verification` | [whyself/cumcm-skills](https://github.com/whyself/cumcm-skills) | 结果复算、约束与口径检查 | Codex · ACCT |
| [ ] | `literature-search` | [whyself/cumcm-skills](https://github.com/whyself/cumcm-skills) | 文献检索（OpenAlex / Crossref / arXiv） | FIN |
| [ ] | `cumcm-paper-planning` | [whyself/cumcm-skills](https://github.com/whyself/cumcm-skills) | 章节安排、图表与论证顺序 | ACCT |
| [ ] | `cumcm-language-polish` | [whyself/cumcm-skills](https://github.com/whyself/cumcm-skills) | 中文润色（不动数字） | ACCT |
| [ ] | `cumcm-b-problem` | [liufanshan11/cumcm-b-problem-lfs](https://github.com/liufanshan11/cumcm-b-problem-lfs) | **B 题专精**（建模 + 论文 + LaTeX） | Codex |
| [ ] | `cumcm-live-workflow` | [haoxilin/cumcm-live-workflow-skill](https://github.com/haoxilin/cumcm-live-workflow-skill) | 2026 AI 合规、终审脚本、官方模板 | 队长 |

**备选（按需二选一，勿与上表重复装）：**

| 安装 | Skill / 包 | 来源仓库 | 说明 |
|:----:|------------|----------|------|
| [ ] | `math-modeling-solver` | [Lupynow/math-modeling-skills](https://github.com/Lupynow/math-modeling-skills) | 拆题 + 95 场景矩阵 + 22 个 Python 模板 |
| [ ] | `math-modeling-paper` | [Lupynow/math-modeling-skills](https://github.com/Lupynow/math-modeling-skills) | 论文结构、图表策略、排版检查 |
| [ ] | `cumcm-solver` / `cumcm-paper` / `cumcm-review` | [Jiaobin-1/cumcm-skills](https://github.com/Jiaobin-1/cumcm-skills) | Codex-first 三件套（建模 / 写作 / 审稿） |
| [ ] | `math-hub` 等 14 模块 | [capwitf/My-MathModeling-skills](https://github.com/capwitf/My-MathModeling-skills) | 证据链驱动（题面→代码→图→对账→合规） |

**不建议全装：** [han69611/math-modeling-skills](https://github.com/han69611/math-modeling-skills)（37 个 skill）、[xuec699-sudo/math-modeling-skills](https://github.com/xuec699-sudo/math-modeling-skills)（全自动编排）易覆盖队长确认流程。

---

## 按能力分类

### 数据处理 / 结果核验

| Skill | 仓库 | 能力摘要 |
|-------|------|----------|
| `cumcm-result-verification` | whyself/cumcm-skills | 对照题意、模型、代码、`output/` 独立复算 |
| `math-verifier` · `math-code` | capwitf/My-MathModeling-skills | 公式量纲、数值诊断、结果登记 |
| `verify_xlsx_rows.py` 等 | haoxilin/cumcm-live-workflow-skill | result 模板行映射、PDF 数字体检 |
| `cumcm-solver`（EDA） | Jiaobin-1/cumcm-skills | 探索性数据分析、假设台账 |

### 建模 / 拆题

| Skill | 仓库 | 能力摘要 |
|-------|------|----------|
| `cumcm-modeling` | whyself/cumcm-skills | 模型路线比较、假设与公式、64 算法参考 |
| `math-modeling-solver` | Lupynow/math-modeling-skills | 12 类问题判定、95 场景决策矩阵、8 本算法手册 |
| `cumcm-solver` | Jiaobin-1/cumcm-skills | 精确建模优先；LP 可解禁止硬上 GA/PSO |
| `cumcm-b-problem` | liufanshan11/cumcm-b-problem-lfs | B 题专精：机理 / 几何 / 统计 / 论文节奏 |
| `math-model` · `math-problem-reader` | capwitf/My-MathModeling-skills | 分问建模、变量约束、题面与附件锁定 |

### 画图 / 可视化

| Skill | 仓库 | 能力摘要 |
|-------|------|----------|
| `cumcm-plotting` | whyself/cumcm-skills | 100 图模板、89 预览图、8 辅助脚本 |
| `math-figure` | capwitf/My-MathModeling-skills | 发表级样式、矢量导出、图—结论证据链 |
| `04-coding-visual` · `visualization` | han69611/math-modeling-skills | 编码与可视化一体 |
| `math-modeling-paper`（图表策略） | Lupynow/math-modeling-skills | Figure Contract、matplotlib 发表级配置 |

### 论文 / 对账 / 审稿

| Skill | 仓库 | 能力摘要 |
|-------|------|----------|
| `cumcm-paper-planning` | whyself/cumcm-skills | 章节安排、图表与文献缺口 |
| `cumcm-paper` | Jiaobin-1/cumcm-skills | 证据驱动写作；无证据标 `[EVIDENCE MISSING]` |
| `math-modeling-paper` | Lupynow/math-modeling-skills | 国赛结构、摘要、灵敏度写法、排版检查 |
| `cumcm-review` | Jiaobin-1/cumcm-skills | 评委视角审稿 + 终局 Top 5 修复项 |
| `cumcm-language-polish` | whyself/cumcm-skills | 中文润色，保留数字与结论强度 |
| `math-consistency` · `math-review` | capwitf/My-MathModeling-skills | 全文一致性、评委风险审查 |

### 文献检索

| Skill | 仓库 | 能力摘要 |
|-------|------|----------|
| `literature-search` | whyself/cumcm-skills | OpenAlex / Crossref / arXiv / Semantic Scholar |
| `math-literature` | capwitf/My-MathModeling-skills | 引用核验、claim-to-citation 映射 |

### 全流程 / 合规

| Skill / 包 | 仓库 | 能力摘要 |
|------------|------|----------|
| `cumcm-live-workflow` | haoxilin/cumcm-live-workflow-skill | 读题→建模→论文→AI 自查；**2026 合规模板** |
| `mathmodel-skill` | handsomeZR-netizen/mathmodel-skill | CUMCM/MCM 10 阶段可恢复流程 |
| `MathModelAgent` | jihe520/MathModelAgent | 端到端自动化 + 17 套 Typst 模板（偏重） |
| `math-modeling-skills` | zhnnky329/MathModeling-skills | 28 skill + 数字冻结门禁 + 三审（人做判断） |

---

## 仓库总览

| 仓库 | 定位 | 链接 |
|------|------|------|
| whyself/cumcm-skills | **6 个模块化 skill**，与本队分工最贴合 | https://github.com/whyself/cumcm-skills |
| Jiaobin-1/cumcm-skills | Codex-first：solver / paper / review | https://github.com/Jiaobin-1/cumcm-skills |
| Lupynow/math-modeling-skills | solver + paper，150+ 获奖论文提炼 | https://github.com/Lupynow/math-modeling-skills |
| capwitf/My-MathModeling-skills | 14 模块证据链 | https://github.com/capwitf/My-MathModeling-skills |
| liufanshan11/cumcm-b-problem-lfs | B 题专精 | https://github.com/liufanshan11/cumcm-b-problem-lfs |
| haoxilin/cumcm-live-workflow-skill | 2026 实战 + AI 合规 | https://github.com/haoxilin/cumcm-live-workflow-skill |
| han69611/math-modeling-skills | 37 skill 全流程 | https://github.com/han69611/math-modeling-skills |
| zhnnky329/MathModeling-skills | 28 skill + 硬门禁 | https://github.com/zhnnky329/MathModeling-skills |
| xuec699-sudo/math-modeling-skills | 工业级双模式编排 | https://github.com/xuec699-sudo/math-modeling-skills |
| jihe520/MathModelAgent | Skills 驱动全自动 | https://github.com/jihe520/MathModelAgent |
| 4yeo-1114/cumcm-skill-skill | 模块化全流程 + 子代理 | https://github.com/4yeo-1114/cumcm-skill-skill |
| BZDmathclub/bzd-math-modeling-skills | 论文智能评审（评阅细则蒸馏） | https://github.com/BZDmathclub/bzd-math-modeling-skills |
| JackyST0/awesome-agent-skills | Agent Skills 合集索引 | https://github.com/JackyST0/awesome-agent-skills |

---

## 角色 → Skill 映射

| 角色 | 推荐 Skill |
|------|------------|
| **队长** | `cumcm-live-workflow` · `cumcm-review` · `math-compliance`（capwitf） |
| **Codex** | `cumcm-modeling` · `math-modeling-solver` · `cumcm-b-problem` · `cumcm-result-verification` |
| **Cursor** | `cumcm-plotting` · Lupynow 代码模板 · 本仓 `templates/` |
| **FIN** | `literature-search` · 灵敏度 / 决策解读相关 references |
| **ACCT** | `cumcm-paper-planning` · `cumcm-language-polish` · `cumcm-result-verification` |

---

## 安装命令

### 本队推荐套装（whyself × 6 + B 题 + 合规）

```bash
cd /path/to/cumcm-2026
mkdir -p .cursor/skills

# whyself 六个模块化 skill
git clone --depth 1 https://github.com/whyself/cumcm-skills.git /tmp/cumcm-skills
cp -R /tmp/cumcm-skills/skills/* .cursor/skills/

# B 题专精（首选 B 时）
git clone --depth 1 https://github.com/liufanshan11/cumcm-b-problem-lfs.git /tmp/b-problem
cp -R /tmp/b-problem .cursor/skills/cumcm-b-problem

# 2026 合规与终审
git clone --depth 1 https://github.com/haoxilin/cumcm-live-workflow-skill.git /tmp/live
cp -R /tmp/live/cumcm-live-workflow .cursor/skills/cumcm-live-workflow

rm -rf /tmp/cumcm-skills /tmp/b-problem /tmp/live
```

### CLI 安装（可选）

```bash
npx skills add Jiaobin-1/cumcm-skills
npx skills add Lupynow/math-modeling-skills --skill math-modeling-solver
npx skills add Lupynow/math-modeling-skills --skill math-modeling-paper
```

### 目录结构要求

Cursor 识别路径：`.cursor/skills/<skill-name>/SKILL.md`

```
.cursor/skills/
├── cumcm-modeling/
│   └── SKILL.md
├── cumcm-plotting/
│   └── SKILL.md
└── …
```

安装后在本清单「推荐安装」表打勾，并 `git add .cursor/skills/` 提交（注意各 skill 的 LICENSE）。

---

## 与本仓工作流的关系

| 本仓产物 | 对应 Skill 能力 |
|----------|----------------|
| `docs/specs/q*.md` | Codex + `cumcm-modeling` / `cumcm-b-problem` |
| `q*/` `templates/` | Cursor + `cumcm-plotting` |
| `output/` `fig/` | `cumcm-result-verification` |
| `refs/` | `literature-search` |
| `paper/` | `cumcm-paper-planning` · `cumcm-language-polish` |
| `docs/ai-compliance.md` | `cumcm-live-workflow` |

**冲突时以本仓 README 分工为准：** 队长确认规格 → Cursor 实现 → 队长签收 `results_summary.md`。

---

*清单整理：2026-09-10 · 来源：GitHub 公开仓库检索*
