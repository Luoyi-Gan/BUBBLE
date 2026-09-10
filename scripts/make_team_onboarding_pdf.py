#!/usr/bin/env python3
"""Generate team onboarding PDF: repo map, AI workflow, Git/PR for FIN & ACCT."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

pdfmetrics.registerFont(TTFont("Heiti", "/System/Library/Fonts/STHeiti Light.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("HeitiBold", "/System/Library/Fonts/STHeiti Medium.ttc", subfontIndex=0))

OUT = Path("/Users/louis/Desktop/国赛队员协作与Git入门指南.pdf")
REPO = "https://github.com/Luoyi-Gan/cumcm-2026"
MARGIN = 14 * mm
NAVY = colors.HexColor("#1B2A4A")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#4B5563")
LINE = colors.HexColor("#D1D5DB")
BAND = colors.HexColor("#F3F4F6")
ACCENT = colors.HexColor("#1D4ED8")
WARN_BG = colors.HexColor("#FEF3C7")


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="CoverTitle", fontName="HeitiBold", fontSize=20, textColor=NAVY, alignment=TA_CENTER, leading=28, spaceAfter=8))
    s.add(ParagraphStyle(name="CoverSub", fontName="Heiti", fontSize=10, textColor=MUTED, alignment=TA_CENTER, leading=14, spaceAfter=14))
    s.add(ParagraphStyle(name="H1", fontName="HeitiBold", fontSize=13, textColor=NAVY, spaceBefore=12, spaceAfter=6, leading=18))
    s.add(ParagraphStyle(name="H2", fontName="HeitiBold", fontSize=10.5, textColor=ACCENT, spaceBefore=8, spaceAfter=4, leading=14))
    s.add(ParagraphStyle(name="Body", fontName="Heiti", fontSize=9, textColor=INK, leading=14, alignment=TA_LEFT, spaceAfter=3))
    s.add(ParagraphStyle(name="CodeBlock", fontName="Heiti", fontSize=8, textColor=INK, leading=12, leftIndent=8, spaceAfter=2))
    s.add(ParagraphStyle(name="Small", fontName="Heiti", fontSize=7.5, textColor=MUTED, leading=11, spaceAfter=2))
    s.add(ParagraphStyle(name="Cell", fontName="Heiti", fontSize=8, textColor=INK, leading=11.5))
    s.add(ParagraphStyle(name="CellB", fontName="HeitiBold", fontSize=8, textColor=NAVY, leading=11.5))
    s.add(ParagraphStyle(name="Th", fontName="HeitiBold", fontSize=8, textColor=colors.white, leading=11.5))
    return s


S = styles()


def P(text, style="Body"):
    return Paragraph(str(text).replace("\n", "<br/>"), S[style])


def cell(t, bold=False):
    return Paragraph(str(t), S["CellB" if bold else "Cell"])


def th(t):
    return Paragraph(str(t), S["Th"])


def table(headers, rows, widths=None):
    data = [[th(h) for h in headers]] + [[cell(c) for c in r] for r in rows]
    if not widths:
        w = (170 * mm) / len(headers)
        widths = [w] * len(headers)
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def callout(text):
    t = Table([[P(text, "Body")]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN_BG), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def build():
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN)
    story = [
        P("CUMCM 2026 队员协作与 Git 入门指南", "CoverTitle"),
        P("给 FIN · ACCT · 新加入队友 | 仓库：cumcm-2026", "CoverSub"),
        P(f"GitHub：{REPO}", "CoverSub"),
        callout("一句话：代码和数字在 Git 仓库里；论文主稿在 Overleaf；本仓是「唯一可对账的版本」。不懂就先 pull，只改自己负责的文件夹，改完 push 分支并开 PR，等队长合并。"),
        Spacer(1, 8),
    ]

    # --- 1. 五人是谁 ---
    story += [
        P("一、五个人 / 工具分别干什么", "H1"),
        table(
            ["角色", "是谁", "主要负责", "不要做什么"],
            [
                ["AI 队长", "技术同学（人）", "选题、定模型、签收数字、合并 PR、提交", "不绕过对账直接采信未核数字"],
                ["Codex", "建模 AI（对话）", "写建模规格、审逻辑；在 docs/specs/", "不写代码、不替队长拍板"],
                ["Cursor", "编程 AI（IDE）", "写 q1/q2/q3 代码，产出 output/ 和 fig/", "不改已确认规格和论文终稿"],
                ["FIN（你可能是）", "金融同学", "refs/ 文献、结果解读、模型评价", "不改代码、不写未签收数字"],
                ["ACCT（你可能是）", "会计同学", "paper/、Overleaf、对账、排版提交", "不擅自改模型、不估算数字"],
            ],
            [22 * mm, 18 * mm, 68 * mm, 62 * mm],
        ),
        Spacer(1, 6),
        P("数据怎么流动（必记）：", "H2"),
        P("Cursor 算出数字 → 放进 output/ → 队长确认后写入 results_summary.md → FIN/ACCT 只引用已确认数字写论文。", "Body"),
        Spacer(1, 8),
    ]

    # --- 2. 东西放哪里 ---
    story += [
        P("二、仓库里东西放哪里（找数据看这张表）", "H1"),
        table(
            ["路径", "里面有什么", "谁维护", "你要怎么用"],
            [
                ["output/", "CSV 结果表（对账用）", "Cursor", "ACCT 对账；FIN 读关键列写分析"],
                ["fig/", "论文插图 fig1.png …", "Cursor", "ACCT 插入 Overleaf"],
                ["results_summary.md", "队长签收后的关键数字摘要", "队长确认", "写论文前先看这个"],
                ["docs/specs/q1.md 等", "建模规格（公式、列名）", "Codex 起草、队长确认", "理解模型口径，不擅自改"],
                ["q1/ q2/ q3/", "各小问 Python 代码", "Cursor", "FIN/ACCT 一般不改"],
                ["data/raw/", "赛题原始附件（本地）", "队长/Cursor", "大文件可能不入库，问队长路径"],
                ["data/processed/", "清洗后的小表", "Cursor", "需要时查阅"],
                ["paper/", "论文大纲、本地备份", "ACCT", "与 Overleaf 同步备份"],
                ["refs/", "文献笔记、bib 线索", "FIN", "FIN 主笔维护"],
                ["prompts/fin.md acct.md", "你和 AI 对话的提示词模板", "各自", "复制到 Cursor 新对话"],
                ["TEAM.md", "排班与签收单", "全员", "按时段勾选任务"],
                ["docs/daily-signoff.md", "早中晚签收细则", "全员", "对照执行"],
                ["docs/ai-compliance.md", "2026 AI 工具申报说明", "队长/ACCT", "提交支撑材料用"],
                ["docs/skills-catalog.md", "可选 AI Skills 清单", "队长", "了解即可"],
                ["templates/", "赛前模板代码", "Cursor", "一般不用动"],
            ],
            [32 * mm, 48 * mm, 28 * mm, 62 * mm],
        ),
        Spacer(1, 6),
        callout("Overleaf 是论文「正式稿」；Git 仓库是「可对账的代码和数字」。两边数字必须一致，以 output/ + results_summary.md 为准。"),
        PageBreak(),
    ]

    # --- 3. FIN / ACCT 日常 ---
    story += [
        P("三、FIN 和 ACCT 每天怎么做", "H1"),
        P("FIN 每日", "H2"),
        P("1. 打开 results_summary.md，只看「已确认」的数字。", "Body"),
        P("2. 在 refs/ 记文献；用 prompts/fin.md 让 AI 帮你写「结果分析」草稿（禁止 AI 改数字）。", "Body"),
        P("3. 演示会（约 18:00）：问至少 2 个「决策/风险」问题。", "Body"),
        P("4. 只改 refs/ 和自己 Overleaf 文稿；要进仓库的笔记可放在 refs/ 下新建 .md。", "Body"),
        Spacer(1, 6),
        P("ACCT 每日", "H2"),
        P("1. 用 output/ 的 CSV 与 results_summary.md 对账；不一致标红，等队长。", "Body"),
        P("2. 维护 paper/ 备份；正式排版在 Overleaf。", "Body"),
        P("3. 用 prompts/acct.md 润色；数字一律从已确认结果复制，不手敲。", "Body"),
        P("4. 插图从 fig/ 取；图注与正文引用要齐全。", "Body"),
        Spacer(1, 8),
        P("9.11 16:00–24:00 队长不在时", "H2"),
        P("FIN 牵头写作，ACCT 牵头对账。禁止：改模型、改口径、把新 CSV 数字直接写进论文（标「待队长签收」）。", "Body"),
        Spacer(1, 8),
    ]

    # --- 4. Git 概念 ---
    story += [
        P("四、Git 是什么（给零基础）", "H1"),
        P("Git = 带时间线的网盘 + 改稿记录。大家在同一仓库协作，不会互相覆盖到看不见。", "Body"),
        table(
            ["词", "通俗理解"],
            [
                ["仓库 repo", f"项目文件夹，线上地址：{REPO}"],
                ["clone", "第一次把仓库下载到电脑"],
                ["pull", "把别人已合并的最新改动拉下来"],
                ["branch 分支", "在副本上改，不影响主线的 main"],
                ["commit", "保存一次改动快照（附说明）"],
                ["push", "把本地分支上传到 GitHub"],
                ["PR（Pull Request）", "请队长审核并合并你的改动"],
                ["merge", "队长同意后，你的改动进入 main"],
            ],
            [35 * mm, 135 * mm],
        ),
        Spacer(1, 8),
        callout("铁律：不要直接在 main 上改大赛关键文件。先建分支 → 改完 → push → 开 PR → 队长合并。"),
        PageBreak(),
    ]

    # --- 5. 第一次配置 ---
    story += [
        P("五、第一次：装软件 + 克隆仓库", "H1"),
        P("需要安装（队长可帮装一次）：", "H2"),
        P("· Git：https://git-scm.com/downloads", "Body"),
        P("· Cursor IDE（可选，用 AI 写/refs 润色）：https://cursor.com", "Body"),
        P("· GitHub 账号，并让队长把你加为仓库协作者（Collaborator）", "Body"),
        Spacer(1, 6),
        P("克隆仓库（只需做一次）：", "H2"),
        P("git clone https://github.com/Luoyi-Gan/cumcm-2026.git", "CodeBlock"),
        P("cd cumcm-2026", "CodeBlock"),
        Spacer(1, 6),
        P("之后每次开工前先更新：", "H2"),
        P("git checkout main", "CodeBlock"),
        P("git pull", "CodeBlock"),
        Spacer(1, 8),
    ]

    # --- 6. 改文件 workflow ---
    story += [
        P("六、改完文件怎么提交（FIN / ACCT 常用流程）", "H1"),
        P("例：你在 refs/ 加了文献笔记，或 paper/ 更新了 outline。", "Body"),
        Spacer(1, 4),
        P("1. 确保在最新 main 上", "H2"),
        P("git checkout main && git pull", "CodeBlock"),
        Spacer(1, 4),
        P("2. 新建分支（名字要有含义）", "H2"),
        P("git checkout -b fin/refs-day1", "CodeBlock"),
        P("（ACCT 可用 acct/paper-outline 等；队长常用 cursor/xxx）", "Small"),
        Spacer(1, 4),
        P("3. 用 Cursor 或记事本改文件，只动自己负责的目录", "H2"),
        Spacer(1, 4),
        P("4. 查看改了什么", "H2"),
        P("git status", "CodeBlock"),
        P("git diff", "CodeBlock"),
        Spacer(1, 4),
        P("5. 暂存并提交", "H2"),
        P("git add refs/notes.md", "CodeBlock"),
        P('git commit -m "docs: add refs notes for Q1 background"', "CodeBlock"),
        Spacer(1, 4),
        P("6. 推送到 GitHub", "H2"),
        P("git push -u origin fin/refs-day1", "CodeBlock"),
        Spacer(1, 4),
        P("7. 在网页开 Pull Request", "H2"),
        P(f"打开 {REPO} → 点 “Compare & pull request” → 写清楚改了什么 → Create PR → 群里 @队长", "Body"),
        Spacer(1, 4),
        P("8. 队长合并后，你本地同步", "H2"),
        P("git checkout main && git pull", "CodeBlock"),
        PageBreak(),
    ]

    # --- 7. PR 怎么写 ---
    story += [
        P("七、PR 写什么（队长看得懂就行）", "H1"),
        table(
            ["项", "示例"],
            [
                ["标题", "docs: FIN 补充 Q1 背景文献笔记"],
                ["改了什么", "refs/q1-background.md 新增 5 篇文献摘要"],
                ["没动什么", "未改 output/、q*/、results_summary.md"],
                ["需要队长做什么", "合并即可 / 请确认某段表述"],
            ],
            [35 * mm, 135 * mm],
        ),
        Spacer(1, 8),
        P("八、什么情况必须 @队长（不要自己 merge）", "H1"),
        P("· 动了 output/、results_summary.md、docs/specs/", "Body"),
        P("· 论文数字和 CSV 对不上", "Body"),
        P("· 想改模型假设或结论", "Body"),
        P("· push 报错（权限、冲突）", "Body"),
        Spacer(1, 8),
        P("九、冲突了怎么办", "H1"),
        P("pull 时提示 conflict：先截图发群，不要强行覆盖。队长或 Cursor 帮解决。", "Body"),
        Spacer(1, 8),
        P("十、和 AI 协作时注意", "H1"),
        P("· 新对话用 prompts/ 里对应角色的 md，不要 @ 整个仓库。", "Body"),
        P("· 让 AI 写分析可以；让 AI 「编一个结果数字」不行。", "Body"),
        P("· 2026 国赛要在支撑材料里交 AI 使用说明，见 docs/ai-compliance.md。", "Body"),
        Spacer(1, 12),
        P("有问题：群里 @队长 | 仓库 README.md 和 TEAM.md | 本队 GitHub Issues", "Small"),
    ]

    doc.build(story)
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)
