# CUMCM 2026 · cumcm-2026

三人队国赛仓库：**技（AI / 队长）+ FIN + ACCT**。

赛程：9.10 出题 → 9.11–9.13 完成。  
酒店：9.11 12:00 入住 · 9.13 15:00 退房 · **9.13 13:00 前提交**。

## 谁写哪里

| 人 | 主目录 | 不要动 |
|----|--------|--------|
| 技 | `q1/` `q2/` `q3/` `templates/` `output/` `fig/` | 不要直接改 Overleaf 终稿逻辑 |
| FIN | `refs/` `prompts/fin.md` 结果分析草稿 | 不要开 Agent 改整仓 |
| ACCT | `paper/` `results_summary.md` 对账 | 数字必须能对上 `output/` |

## 目录

```
q1 q2 q3          按小问的代码
templates/        赛前可复用：优化 / 回归 / 画图 / 灵敏度
output/           CSV，给 ACCT 对账
fig/              图，给论文插入（fig1.png …）
data/raw          原始数据（默认不入库）
data/processed    清洗后的小表
paper/            论文本地备份 / 大纲
refs/             文献笔记与 bib 线索
prompts/          三人 Cursor 提示词
results_summary.md  每日关键数字（技更新）
TEAM.md           分工、酒店节点、额度
```

## 每日节奏

1. 技把数字写入 `output/` 和本文件的 `results_summary.md`
2. 演示会：技展示图 → ACCT 对账 → FIN 问决策含义
3. ACCT 把能写的段落写入 Overleaf，并在本仓 `paper/` 留备份
4. 每 4 小时：`git add` 有用的代码和摘要后提交（队长执行）

## 硬节点

- 9.10 20:30 选题锁定
- 9.11 02:00 小问 1 可跑 + 论文骨架
- 9.12 24:00 完整初稿
- 9.13 13:00 已提交（15:00 退房）

## 环境（技）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install numpy scipy pandas matplotlib scikit-learn cvxpy
```

先跑通 `templates/` 再开赛。
