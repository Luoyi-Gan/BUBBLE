#!/usr/bin/env python3
"""Generate daily sign-off PDFs: 队长 / Codex / Cursor / FIN / ACCT."""

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

OUT_DIR = Path("/Users/louis/Desktop")
MARGIN = 14 * mm
NAVY = colors.HexColor("#1B2A4A")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#4B5563")
LINE = colors.HexColor("#D1D5DB")
BAND = colors.HexColor("#F3F4F6")
ACCENT = colors.HexColor("#1D4ED8")
WARN = colors.HexColor("#B45309")


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="CoverTitle", fontName="HeitiBold", fontSize=18, textColor=NAVY, alignment=TA_CENTER, leading=24, spaceAfter=6))
    s.add(ParagraphStyle(name="CoverSub", fontName="Heiti", fontSize=10, textColor=MUTED, alignment=TA_CENTER, leading=14, spaceAfter=12))
    s.add(ParagraphStyle(name="H1", fontName="HeitiBold", fontSize=12, textColor=NAVY, spaceBefore=10, spaceAfter=6, leading=16))
    s.add(ParagraphStyle(name="H2", fontName="HeitiBold", fontSize=10, textColor=ACCENT, spaceBefore=8, spaceAfter=4, leading=14))
    s.add(ParagraphStyle(name="Body", fontName="Heiti", fontSize=8.5, textColor=INK, leading=13, alignment=TA_LEFT, spaceAfter=2))
    s.add(ParagraphStyle(name="Small", fontName="Heiti", fontSize=7.5, textColor=MUTED, leading=11, spaceAfter=2))
    s.add(ParagraphStyle(name="Footer", fontName="Heiti", fontSize=7, textColor=MUTED, alignment=TA_CENTER))
    return s


S = styles()


def P(text, style="Body"):
    return Paragraph(str(text), S[style])


def section_block(day_title, period_title, tasks, deliverable, sign_note=""):
    rows = []
    for t in tasks:
        rows.append([P(f"☐ {t}", "Body")])
    task_table = Table(rows, colWidths=[170 * mm])
    task_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    sign = f"产出：{deliverable}　　签收时间：________　　签名：________"
    if sign_note:
        sign += f"　　{sign_note}"
    return [
        P(day_title, "H1"),
        P(period_title, "H2"),
        task_table,
        Spacer(1, 4),
        P(sign, "Small"),
        Spacer(1, 8),
    ]


CAPTAIN = {
    "title": "队长（AI）签收单",
    "subtitle": "CUMCM 2026 · 四小问 · 技术总负责 · 9.11 16:00–24:00 离场",
    "filename": "国赛签收单_队长.pdf",
    "rules": [
        "论文数字以你写入 results_summary.md 的「已确认」条目为准。",
        "9.11 15:30 前必须完成离场前演示会并宣读交接单。",
        "16:00 后 FIN/ACCT 自治写作，24:00 你回归验收。",
    ],
    "sections": [
        ("9.10· 出题日", "晚 18:00–22:00", [
            "行李 17:00 前打好，桌上只留电脑",
            "组织读题：三题各 30min 可行性评估（A 题试推导）",
            "20:30 选题锁定；四小问拆解与分组写入 results_summary.md",
            "23:00 前 Codex 起草 q1.md + q2.md；确认 q1.md",
            "指派 Cursor：Q1 实现 + Q2 骨架",
        ], "选题记录 · Q1 规格已确认 · Cursor 任务清单"),
        ("9.10· 出题日", "深夜 22:00–02:00", [
            "Cursor 跑通 Q1，output/q1_* 可复现",
            "Q2 骨架可跑；Codex 起草 q3.md 草稿",
            "更新 results_summary.md Q1 关键数字（已确认）",
            "git commit：代码 + 规格 + 摘要",
            "02:00 前在群里发：Q1 已签收 / Q2 状态",
        ], "Q1 CSV + 图 · results_summary Q1 已核"),
        ("9.11· 搬家 + 酒店", "早 08:00–10:00 ⚠️ 关键", [
            "验收隔夜 output/：Q1 数字与规格一致",
            "更新 results_summary.md（Q1 已核；Q2 进度）",
            "确认 q2.md；审阅 q3.md 草稿",
            "撰写 docs/handoff/9.11-1600.md 离场交接单",
            "git commit + 网盘/U 盘备份",
            "10:00 前关电脑出门",
        ], "交接单 · 备份完成"),
        ("9.11· 搬家 + 酒店", "中 13:30–16:00 ⚠️ 最后窗口", [
            "13:30 同步：昨晚进度 + 今日 16:00 离场",
            "15:30 前确认 q3.md + q4.md（Q4 可简化）",
            "指挥 Cursor：Q2 跑通；启动 Q3",
            "15:30–16:00 离场前演示会（主持）",
            "　· Cursor 演示 output/ 列含义",
            "　· ACCT 当场对账 · FIN 提问决策含义",
            "　· 宣读交接单，三人确认",
            "16:00 前 git commit + 发群：离场签收",
        ], "Q2 可跑 · Q3+Q4 规格已确认 · 交接单已宣读", "16:00 离场"),
        ("9.11", "晚 16:00–24:00", [
            "本时段离场 — 无队长任务",
        ], "—", "24:00 回归"),
        ("9.11", "深夜 24:00–02:00", [
            "验收 16:00–24:00 产出；更新 results_summary.md",
            "新数字签收或驳回；驳回处标回 ACCT/FIN",
            "指挥 Cursor：Q3 收尾 / Q4 启动 / 检验",
            "git commit",
            "02:00 前发群：夜间签收 + 9.12 晨会待办",
        ], "Q3 可跑（目标）· Q4 已启动"),
        ("9.12· 黄金全日", "早 08:00–12:00", [
            "08:00–08:30 晨会（主持）：缺图、缺数、空白章",
            "确认四小问 output/ 齐全；更新 results_summary.md",
            "Cursor：补图 + 灵敏度 / 检验",
            "Codex：结果逻辑审阅（记入变更记录）",
            "10:00 前 git commit",
        ], "晨会待办清单 · 检验输出"),
        ("9.12· 黄金全日", "中 12:00–18:00", [
            "12:00 前确认：16:00 后不开新模型",
            "Cursor：附录代码整理、支撑材料目录",
            "14:00 短演示会（15min）：全员对账",
            "16:00 冻结模型；之后只修 bug / 润色 / 排版",
            "更新 AI工具使用详情 草稿",
        ], "16:00 模型冻结 · 支撑材料清单"),
        ("9.12· 黄金全日", "晚 18:00–24:00", [
            "18:00 终审演示会",
            "交叉审阅：三人各读一遍，出问题清单",
            "Cursor：按清单修最后一轮（不修模型）",
            "24:00 完整初稿 — 队长宣布封版",
            "git tag 或 commit：draft-v1",
        ], "初稿 PDF · 问题清单已处理", "初稿封版"),
        ("9.13· 提交", "早 08:00–12:00", [
            "08:00–10:00 独立终审，列问题清单",
            "核数：output/ 与论文最终一致",
            "打包支撑材料（代码 + 数据说明 + AI 声明 PDF）",
            "10:00 前把 blocker 清完",
        ], "支撑材料包"),
        ("9.13· 提交", "午后 13:00–15:00", [
            "13:00–14:00 复核提交系统 / 回执",
            "14:00–15:00 收拾、退房",
        ], "回执确认 · 退房", "15:00 退房"),
    ],
    "meetings": [
        ("9.11", "15:30–16:00", "离场前演示会（你主持）"),
        ("9.12", "14:00", "短演示会 / 对账"),
        ("9.12", "18:00", "终审演示会 / 24:00 封版"),
    ],
}

FIN = {
    "title": "FIN 签收单",
    "subtitle": "CUMCM 2026 · 文献与决策解读 · 结果分析 · 模型评价与推广",
    "filename": "国赛签收单_FIN.pdf",
    "rules": [
        "只引用队长已写入 results_summary.md 的已确认数字。",
        "9.11 16:00–24:00 你牵头写作；新 CSV 标「待队长 24:00 签收」。",
        "不硬推公式；用已确认规格理解模型后写成论文语言。",
    ],
    "sections": [
        ("9.10· 出题日", "晚 18:00–22:00", [
            "记录三题「决策/风险/故事线」各 3 条要点",
            "选题会发言：哪题 FIN 最能写出结果分析",
            "选题后搜 3–5 篇文献，笔记进 refs/",
            "起草假设清单（成本/约束/市场背景），发群供 ACCT 引用",
        ], "refs/ 新增笔记 · 假设草稿"),
        ("9.10· 出题日", "深夜 22:00–02:00", [
            "假设草稿写入 Overleaf「模型假设」占位（标待队长确认数字）",
            "问题重述背景段草稿（不填具体数字）",
            "休息；不熬夜改模型相关表述",
        ], "假设 + 背景草稿"),
        ("9.11· 搬家 + 酒店", "早 08:00–10:00", [
            "检查 refs/ 与假设草稿已保存",
            "备份个人笔记与 Overleaf 离线 PDF",
            "10:00 前出门；路上只看文献，不写代码",
        ], "备份确认"),
        ("9.11· 搬家 + 酒店", "中 13:30–16:00", [
            "演示会前：读完 results_summary.md 已确认部分",
            "演示会：提出至少 2 个决策/风险问题",
            "16:00 前：把 Q1（及已确认 Q2）解读要点写入笔记",
        ], "结果解读要点笔记"),
        ("9.11· 搬家 + 酒店", "晚 16:00–24:00 ※ 你牵头", [
            "16:00 宣读交接单中的「禁止事项」",
            "写「模型假设」定稿（基于已确认规格，不新加假设）",
            "写 Q1「结果分析」草稿（只引用 results_summary.md）",
            "Cursor 若有新 CSV：只标记「待队长 24:00 签收」",
            "21:00 在群里发进度：写了哪几段、缺什么数",
        ], "假设定稿 · Q1 结果分析草稿"),
        ("9.11", "深夜 24:00–02:00", [
            "根据队长签收结果，修订结果分析草稿",
            "轮休 4h（若 16:00–24:00 未睡）",
        ], "结果分析修订"),
        ("9.12· 黄金全日", "早 08:00–12:00", [
            "晨会：汇报结果分析 / 评价章进度",
            "写 Q2–Q4 结果分析（已确认数字）",
            "起草灵敏度「决策含义」段",
        ], "结果分析主文"),
        ("9.12· 黄金全日", "中 12:00–18:00", [
            "写「模型评价与推广」",
            "审摘要中结果表述（与 FIN 口径一致）",
            "补充 refs/ 参考文献线索给 ACCT",
        ], "评价与推广章"),
        ("9.12· 黄金全日", "晚 18:00–24:00", [
            "通读全文：结果与评价表述",
            "标注语病/逻辑，不改正文数字",
        ], "终审意见清单"),
        ("9.13· 提交", "早 08:00–12:00", [
            "独立终审：读摘要 + 结果分析 + 评价",
            "10:00 前提交表述修改建议（仅文字，不动数字）",
        ], "表述修改建议"),
        ("9.13· 提交", "午后 14:00–15:00", [
            "收拾行李、退房",
        ], "退房"),
    ],
    "meetings": [
        ("9.11", "15:30–16:00", "离场前演示会：至少 2 个决策问题"),
        ("9.12", "14:00", "短演示会：确认结果分析数字"),
        ("9.12", "18:00", "终审：通读表述"),
    ],
}

ACCT = {
    "title": "ACCT 签收单",
    "subtitle": "CUMCM 2026 · 论文成稿 · 数字对账 · 排版提交",
    "filename": "国赛签收单_ACCT.pdf",
    "rules": [
        "数字必须等于 output/ 与 results_summary.md 已确认项。",
        "9.11 16:00–24:00 你牵头对账与写作；不得估算或擅自改模型表述。",
        "12:00–13:00 正式提交由你操作，全员围观确认回执。",
    ],
    "sections": [
        ("9.10· 出题日", "晚 18:00–22:00", [
            "列出全部小问 + 每问需要的表/图清单",
            "Overleaf 建章：摘要、问题重述、假设、符号表、模型、结果、检验、评价、参考文献",
            "本仓 paper/ 同步大纲",
            "建对账表（论文字段 ↔ output/ 列名）",
        ], "Overleaf 骨架 · 对账表 v0"),
        ("9.10· 出题日", "深夜 22:00–02:00", [
            "问题重述结构写入 Overleaf（小问逐条对应）",
            "符号表框架（符号可先占位）",
            "休息",
        ], "问题重述 v0"),
        ("9.11· 搬家 + 酒店", "早 08:00–10:00", [
            "导出 Overleaf PDF 备份",
            "对账表核对：Q1 若已有数字，标「待队长签收」",
            "10:00 前出门",
        ], "paper 备份"),
        ("9.11· 搬家 + 酒店", "中 13:30–16:00", [
            "13:00–13:30 测 Overleaf / Git / 热点",
            "演示会：完成 Q1 对账，不一致当场标红",
            "16:00 前：Q1 章节写入 Overleaf（仅用已签收数字）",
            "记录下午待办到 results_summary.md「待补图表」",
        ], "Q1 正文 v1 · 对账记录"),
        ("9.11· 搬家 + 酒店", "晚 16:00–24:00 ※ 你牵头", [
            "维护对账表：新 output/ 标「未核」",
            "写问题重述、符号说明（与 docs/specs/ 一致）",
            "插图占位 + 图注草稿（fig/ 已有则插入）",
            "21:00 与 FIN 对齐：哪些段落可合并、哪些数字还缺",
            "禁止自行改模型表述或估算数字",
        ], "论文进度约 30–40% · 对账表更新"),
        ("9.11", "深夜 24:00–02:00", [
            "根据队长签收，修正论文中未核数字",
            "轮休 4h",
        ], "对账修正"),
        ("9.12· 黄金全日", "早 08:00–12:00", [
            "晨会：汇报对账缺口",
            "写「模型建立与求解」文字（与代码/规格一致）",
            "摘要四要素草稿",
        ], "模型章 + 摘要草稿"),
        ("9.12· 黄金全日", "中 12:00–18:00", [
            "全文排版：图表编号、交叉引用",
            "参考文献录入",
            "第二轮对账：论文 ↔ output/ ↔ results_summary.md",
        ], "排版 v1 · 对账无红项或红项清单"),
        ("9.12· 黄金全日", "晚 18:00–24:00", [
            "导出 24:00 版 PDF，备份三份",
            "确认页数、字体、图表清晰度",
        ], "初稿 PDF 备份"),
        ("9.13· 提交", "早 08:00–13:00", [
            "08:00–10:00 独立终审 + 修订 PDF",
            "10:00–12:00 与队长、FIN 并行修最后一版",
            "12:00–13:00 正式提交 + 网盘 + U 盘备份",
            "确认提交回执截图发群",
        ], "已提交 · 双备份", "已提交"),
        ("9.13· 提交", "午后 14:00–15:00", [
            "收拾行李、退房",
        ], "退房"),
    ],
    "meetings": [
        ("9.11", "15:30–16:00", "离场前演示会：Q1 对账签字"),
        ("9.12", "14:00", "短演示会：第二轮对账"),
        ("9.12", "18:00", "终审：导出 24:00 版 PDF"),
    ],
}

CODEX = {
    "title": "Codex 签收单",
    "subtitle": "CUMCM 2026 · 建模参谋 · 规格起草与逻辑审阅（不写代码、不替队长决策）",
    "filename": "国赛签收单_Codex.pdf",
    "rules": [
        "只输出建模规格与审阅意见；代码由 Cursor 在 q*/ 实现。",
        "规格末尾标注「待队长确认」；口径变更须队长批准后才改 docs/specs/。",
        "9.11 16:00–24:00 队长离场时：可审阅 output/，但不得代替队长签收数字。",
        "与 Cursor 分开会话，避免规格与实现混在一起。",
    ],
    "sections": [
        ("9.10· 出题日", "晚 18:00–22:00", [
            "18:00–20:00：三题方案对比（数据/可解性/可写性/翻车点）",
            "给出 B>C>A 排序建议与 A 题放弃条件",
            "20:30 选题后：按 docs/specs/_template.md 起草 q1.md",
            "同步启动 q2.md 草稿（不必当晚确认）",
            "每份规格含：假设、符号、公式、算法、output 列名、验证设计",
            "末尾标注「待队长确认」",
        ], "q1.md 草稿 · q2.md 草稿 · 选题建模备忘录"),
        ("9.10· 出题日", "深夜 22:00–02:00", [
            "若 Cursor 产出 Q1 初版：审阅数字与公式是否自洽",
            "记录量级/约束疑点，供队长 02:00 前决策",
            "不直接改 Cursor 代码文件",
        ], "Q1 逻辑审阅意见（若有产出）"),
        ("9.11· 搬家 + 酒店", "早 08:00–10:00", [
            "响应队长：修订 Q2 规格",
            "起草 q3.md 草稿",
        ], "q2 修订 · q3 草稿"),
        ("9.11· 搬家 + 酒店", "中 13:30–16:00", [
            "15:30 前配合队长确认 q3.md + q4.md",
            "演示会前：对 Q1/Q2 output/ 做快速逻辑审阅",
            "列出 16:00–24:00 风险点（写入交接单「Codex 待办」）",
        ], "四问规格齐 · 离场前审阅摘要"),
        ("9.11· 搬家 + 酒店", "晚 16:00–24:00", [
            "队长离场期间：审阅 Cursor 新 output/ 与 fig/",
            "检查是否违背已确认 specs；问题记入 results_summary 变更记录",
            "不批准口径变更；只标「建议队长 24:00 处理」",
            "21:00 向队长（异步）发审阅摘要：通过项 / 风险项",
        ], "异步审阅摘要 · 风险清单"),
        ("9.11", "深夜 24:00–02:00", [
            "队长回归后：审阅 Q3/Q4 是否与规格一致",
            "确认四问检验是否覆盖规格第 7 节",
        ], "夜间验收意见"),
        ("9.12· 黄金全日", "早 08:00–12:00", [
            "对各小问 output/ 做完整结果逻辑审阅",
            "检查：假设↔公式↔数字↔约束 是否闭环",
            "列出缺什么对比实验 / 灵敏度",
            "修订建议交队长批准后再改规格",
        ], "全日逻辑审阅报告"),
        ("9.12· 黄金全日", "中 12:00–18:00", [
            "16:00 模型冻结后：不再建议新模型",
            "对照 specs 审阅论文「模型建立」草稿逻辑",
            "标出 FIN 可展开的决策点是否遗漏",
        ], "论文逻辑检查清单"),
        ("9.12· 黄金全日", "晚 18:00–24:00", [
            "终审前：通读摘要+结果段，查过度推断",
            "只给修改建议，不改 ACCT 终稿文字",
        ], "终审逻辑意见"),
        ("9.13· 提交", "早 08:00–12:00", [
            "协助队长：支撑材料中模型说明是否与 specs 一致",
            "检查 AI 工具使用记录是否含 Codex 会话摘要",
        ], "提交前一致性确认"),
    ],
    "meetings": [
        ("9.11", "15:30 前", "队长会前粘贴：Q1/Q2 审阅摘要"),
        ("9.12", "08:30 晨会后", "提交全日逻辑审阅报告给队长"),
        ("9.12", "18:00 前", "提交终审逻辑意见"),
    ],
    "extra_title": "规格交付检查（每小问）",
    "extra_items": [
        "目标与成功标准",
        "假设与符号表",
        "LaTeX 公式与约束",
        "推荐算法 + 备选",
        "output/ 列名与 fig/ 命名",
        "验证：基线 / 灵敏度 / 合理性",
        "论文要点与审稿风险",
        "文首状态：待队长确认 → 已确认",
    ],
}

CURSOR = {
    "title": "Cursor 签收单",
    "subtitle": "CUMCM 2026 · 编码助手 · 按已确认规格实现 q*/ templates/ output/ fig/",
    "filename": "国赛签收单_Cursor.pdf",
    "rules": [
        "只实现队长已确认的 docs/specs/qN.md；遇歧义停手问队长。",
        "不自行改模型目标、核心假设、指标口径或结论。",
        "每问独立对话，只 @ 当前 qN/ 文件夹；禁止 @ 整个仓库。",
        "9.11 16:00–24:00 仅执行交接单列出的 Cursor 待办。",
    ],
    "sections": [
        ("9.10· 出题日", "晚 20:30–22:00", [
            "等待队长确认 q1.md 后开工",
            "阅读规格：输入/输出/约束/算法/验证设计",
            "在 q1/ 搭建代码骨架",
        ], "q1/ 代码骨架"),
        ("9.10· 出题日", "深夜 22:00–02:00", [
            "跑通 Q1：output/q1_*.csv + fig/fig1_*.png",
            "争取 Q2 骨架可跑（按 q2 草稿或队长口头令）",
            "CSV 列名与规格一致；代码可复现",
            "阻塞点写入 README 或交接口头令",
        ], "Q1 可复现 · Q2 骨架（目标）"),
        ("9.11· 搬家 + 酒店", "早 08:00–10:00", [
            "仅修 overnight bug；不新功能",
            "确保 Q1 输出与 specs 一致",
        ], "Q1 稳定版"),
        ("9.11· 搬家 + 酒店", "中 13:30–16:00", [
            "Q2 跑通优先（output/q2_*）",
            "Q3 启动（q3.md 已确认）；Q4 待 q4.md 确认",
            "演示会：现场可复现运行 + 解释 output/ 列含义",
            "16:00 前 commit；交接单写明未完成任务",
        ], "Q2 可跑 · Q3 已启动"),
        ("9.11· 搬家 + 酒店", "晚 16:00–24:00", [
            "严格按交接单：主攻 Q3",
            "q4.md 已确认后才动 Q4",
            "新 CSV 标「待 24:00 队长签收」",
            "禁止改 docs/specs/ 已确认章节",
        ], "Q3 推进"),
        ("9.11", "深夜 24:00–02:00", [
            "队长验收后：Q3 收尾 / Q4 启动 / 检验",
            "templates/sensitivity.py 复用做灵敏度",
            "git commit",
        ], "检验输出 · 夜间 commit"),
        ("9.12· 黄金全日", "早 08:00–12:00", [
            "补全全部 fig/",
            "跑灵敏度与对比实验",
            "确保四小问 output/ CSV 齐全",
        ], "全量 output/ + fig/"),
        ("9.12· 黄金全日", "中 12:00–18:00", [
            "16:00 后：不开新模型，只修 bug",
            "整理附录代码与支撑材料目录",
            "数据清洗脚本与 data/processed/ 说明",
        ], "附录 + 支撑材料"),
        ("9.12· 黄金全日", "晚 18:00–24:00", [
            "按终审问题清单修最后一轮",
            "不修模型、不改口径",
            "24:00 封版 commit：draft-v1",
        ], "终稿对应代码版本"),
        ("9.13· 提交", "早 08:00–12:00", [
            "配合队长打包支撑材料",
            "代码可解压、requirements.txt 可安装",
            "关键脚本附运行说明",
        ], "支撑材料代码包"),
    ],
    "meetings": [
        ("9.11", "15:30–16:00", "演示会：可复现运行 + 列含义说明"),
        ("9.12", "14:00", "短演示会：补图与检验展示"),
        ("9.12", "18:00", "终审：确认代码与论文数字一致"),
    ],
    "extra_title": "实现检查（每小问交付前）",
    "extra_items": [
        "仅修改 qN/ 与必要 templates/",
        "output/ CSV 列名 = 规格第 6 节",
        "fig/ 命名 figN_*.png",
        "本地可复现运行",
        "未改 specs 已确认章节",
        "commit 信息写明小问与 output 影响",
    ],
}


def build_pdf(person):
    out_path = OUT_DIR / person["filename"]
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=person["title"],
    )
    story = [
        P(person["title"], "CoverTitle"),
        P(person["subtitle"], "CoverSub"),
        Spacer(1, 6),
        P("铁律", "H2"),
    ]
    for r in person["rules"]:
        story.append(P(f"· {r}", "Body"))
    story.append(Spacer(1, 10))

    hard = [
        ["节点", "时间"],
        ["选题 + 四问拆解", "9.10 20:30"],
        ["q1.md 已确认", "9.10 23:00"],
        ["Q1 可跑", "9.11 02:00"],
        ["Q2 可跑；q3+q4 确认", "9.11 15:30"],
        ["Q3 可跑（目标）", "9.11 24:00"],
        ["四问 CSV 齐", "9.12 12:00"],
        ["完整初稿", "9.12 24:00"],
        ["正式提交", "9.13 13:00"],
    ]
    ht = Table([[P(h, "H2") for h in hard[0]]] + [[P(c, "Body") for c in row] for row in hard[1:]], colWidths=[85 * mm, 85 * mm])
    ht.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE), ("BACKGROUND", (0, 0), (-1, 0), BAND)]))
    story += [P("硬节点", "H2"), ht, Spacer(1, 10)]

    for day, period, tasks, deliverable, *rest in person["sections"]:
        sign_note = rest[0] if rest else ""
        story += section_block(day, period, tasks, deliverable, sign_note)

    story.append(PageBreak())
    story.append(P("关键节点签收", "H1"))
    for date, time, note in person["meetings"]:
        story.append(P(f"☐ {date} {time} — {note}", "Body"))
    story.append(Spacer(1, 12))

    if person.get("extra_items"):
        story.append(P(person["extra_title"], "H1"))
        for item in person["extra_items"]:
            story.append(P(f"☐ {item}", "Body"))
        story.append(Spacer(1, 12))

    if "队长" in person["title"]:
        story.append(P("演示会（队长主持，Codex 会前供审阅摘要）", "H2"))
        story.append(P("每场：Cursor 可复现 · ACCT 对账 · FIN ≥2 决策问题 · 待办写入 results_summary.md", "Small"))
    elif person["title"].startswith("FIN") or person["title"].startswith("ACCT"):
        story.append(P("演示会到场签收", "H2"))
        story.append(P("每场：Cursor 可复现 · ACCT 对账 · FIN ≥2 决策问题 · 待办写入 results_summary.md", "Small"))

    if "队长" in person["title"]:
        story.append(Spacer(1, 12))
        story.append(P("9.11 离场交接单要点（09:30 写好）", "H1"))
        handoff = [
            "已确认可写入论文的数字（Q1/Q2 文件与列值）",
            "Cursor 待办列表（不得越界改规格）",
            "FIN / ACCT 下午待办",
            "禁止：改 docs/specs/ · 新开模型 · 新 CSV 直接进论文",
            "24:00 检查：output 一致 · fig 齐全 · 对账红项清零",
        ]
        for h in handoff:
            story.append(P(f"☐ {h}", "Body"))

    doc.build(story)
    return out_path


def main():
    paths = []
    for person in (CAPTAIN, CODEX, CURSOR, FIN, ACCT):
        paths.append(build_pdf(person))
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
