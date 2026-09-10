# 队员协作与 Git 入门

> PDF 版：`python3 scripts/make_team_onboarding_pdf.py` → 桌面 `国赛队员协作与Git入门指南.pdf`

**仓库：** https://github.com/Luoyi-Gan/cumcm-2026

一句话：**代码和数字在 Git；论文主稿在 Overleaf；本仓是唯一可对账版本。**

## 五人分工

| 角色 | 负责 | 不要 |
|------|------|------|
| AI 队长 | 选题、定模型、签收数字、合并 PR | 绕过对账 |
| Codex | `docs/specs/` 建模规格、逻辑审阅 | 写代码、替队长决策 |
| Cursor | `q1/`–`q4/` `output/` `fig/` | 改已确认规格 |
| FIN | `refs/`、结果解读 | 改代码、未核数字 |
| ACCT | `paper/`、Overleaf、对账 | 估算数字、改模型 |

**数字链路：** `output/` → 队长确认 → `results_summary.md` → FIN/ACCT 写论文

## 东西放哪里

| 路径 | 内容 | 谁维护 |
|------|------|--------|
| `output/` | CSV 结果 | Cursor |
| `fig/` | 论文图 | Cursor |
| `results_summary.md` | 已签收关键数字 | 队长 |
| `docs/specs/` | 建模规格 | Codex + 队长 |
| `paper/` | 论文备份 | ACCT |
| `refs/` | 文献笔记 | FIN |
| `TEAM.md` | 排班签收 | 全员 |

完整表见 PDF 第二节。

## Git 流程（FIN / ACCT）

```bash
git checkout main && git pull
git checkout -b fin/refs-day1    # 或 acct/paper-outline
# …改 refs/ 或 paper/ …
git add refs/
git commit -m "docs: add refs for Q1"
git push -u origin fin/refs-day1
```

然后在 GitHub 开 **Pull Request**，@队长 合并。

**不要**直接在 `main` 上改；**不要**自己 merge 动过 `output/` 的 PR。

## 更多

- 早中晚任务：`docs/daily-signoff.md`、`TEAM.md`
- AI 合规：`docs/ai-compliance.md`
- 提示词：`prompts/fin.md`、`prompts/acct.md`
