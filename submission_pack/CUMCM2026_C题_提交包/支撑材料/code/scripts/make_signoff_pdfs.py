#!/usr/bin/env python3
"""Generate daily sign-off PDFs aligned with TEAM.md (四小问 Q1–Q4)."""

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

HARD_NODES = [
    ["选题 + 四问拆解", "9.10 20:30"],
    ["q1.md 已确认", "9.10 23:00"],
    ["Q1 可跑", "9.11 02:00"],
    ["Q1 签收；q2.md 确认", "9.11 10:00"],
    ["Q2 可跑；q3+q4 确认", "9.11 15:30"],
    ["队长离场交接", "9.11 16:00"],
    ["Q3 可跑（目标）", "9.11 24:00"],
    ["Q4 可跑（目标）", "9.12 02:00"],
    ["四问 CSV 齐", "9.12 12:00"],
    ["冻结模型", "9.12 16:00"],
    ["完整初稿", "9.12 24:00"],
    ["正式提交", "9.13 13:00"],
]


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="CoverTitle", fontName="HeitiBold", fontSize=18, textColor=NAVY, alignment=TA_CENTER, leading=24, spaceAfter=6))
    s.add(ParagraphStyle(name="CoverSub", fontName="Heiti", fontSize=9.5, textColor=MUTED, alignment=TA_CENTER, leading=13, spaceAfter=10))
    s.add(ParagraphStyle(name="H1", fontName="HeitiBold", fontSize=12, textColor=NAVY, spaceBefore=10, spaceAfter=5, leading=16))
    s.add(ParagraphStyle(name="H2", fontName="HeitiBold", fontSize=10, textColor=ACCENT, spaceBefore=7, spaceAfter=4, leading=14))
    s.add(ParagraphStyle(name="Body", fontName="Heiti", fontSize=8.5, textColor=INK, leading=13, alignment=TA_LEFT, spaceAfter=2))
    s.add(ParagraphStyle(name="Small", fontName="Heiti", fontSize=7.5, textColor=MUTED, leading=11, spaceAfter=2))
    s.add(ParagraphStyle(name="Th", fontName="HeitiBold", fontSize=7.5, textColor=colors.white, leading=11))
    return s


S = styles()


def P(text, style="Body"):
    return Paragraph(str(text), S[style])


def section_block(day_title, period_title, tasks, deliverable, sign_note=""):
    rows = [[P(f"☐ {t}", "Body")] for t in tasks]
    task_table = Table(rows, colWidths=[170 * mm])
    task_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    sign = f"产出：{deliverable}　　签收：________　　时间：________"
    if sign_note:
        sign += f"　　{sign_note}"
    return [P(day_title, "H1"), P(period_title, "H2"), task_table, Spacer(1, 3), P(sign, "Small"), Spacer(1, 7)]


CAPTAIN = {
    "title": "队长（AI）签收单",
    "subtitle": "CUMCM 2026 · 每题四小问 · 技术总负责 · 9.11 16:00–24:00 离场",
    "filename": "国赛签收单_队长.pdf",
    "rules": [
        "数字以 results_summary.md「已确认」为准；FIN/ACCT 不得超前引用。",
        "9.11 15:30 前：Q2 可跑 + q3.md + q4.md 已确认 + 离场演示会。",
        "16:00–24:00 离线；24:00 回归验收 Q3，推进 Q4。",
    ],
    "sections": [
        ("9.10 · 选题起跑", "早", [
            "检查 Python 环境、templates/、提交与 AI 合规规则",
            "明确选题评价维度（能做完 > 可写性 > 看起来高级）",
        ], "环境就绪"),
        ("9.10 · 选题起跑", "中（出题后）", [
            "拆 **四小问**，标依赖与模型复用，写入 results_summary.md 分组表",
            "三题可行性评估（A 题 30min 试推导）",
        ], "四问清单 + 优先级"),
        ("9.10 · 选题起跑", "晚 18:00–22:00", [
            "行李 17:00 前打好",
            "**20:30 选题锁定**",
            "23:00 前 Codex 出 q1.md + q2.md 草稿；**确认 q1.md**",
            "派 Cursor：Q1 实现 + Q2 骨架",
        ], "Q1 规格已确认"),
        ("9.10 · 选题起跑", "深夜 22:00–02:00", [
            "02:00 **签收 Q1**（output/q1_* 可复现）",
            "Q2 骨架可跑；Codex 起草 q3.md 草稿",
            "git commit；群里发 Q1 已签收",
        ], "Q1 已核 · q3 草稿"),
        ("9.11 · 离线交接日", "早 08:00–10:00", [
            "验收 Q1；**确认 q2.md**；审阅 q3.md 草稿",
            "撰写 docs/handoff/9.11-1600.md",
            "git commit + 备份；10:00 出门",
        ], "q2 已确认 · 交接单草稿"),
        ("9.11 · 离线交接日", "中 13:30–16:00", [
            "**15:30 前确认 q3.md + q4.md**（Q4 可简化）",
            "Q2 跑通验收；Cursor 启动 Q3",
            "15:30–16:00 离场演示会（主持）",
            "16:00 前 commit + 离场签收",
        ], "Q2 可跑 · 四问规格齐", "16:00 离场"),
        ("9.11", "晚 16:00–24:00", ["本时段离线 — 无队长任务"], "—", "24:00 回归"),
        ("9.11", "深夜 24:00–02:00", [
            "验收 16:00–24:00 产出；更新 results_summary.md",
            "签收/驳回新数字；指挥 Cursor：Q3 收尾 / Q4 启动",
            "发 9.12 晨会待办",
        ], "Q3 可跑（目标）"),
        ("9.12 · 黄金全日", "早 08:00–12:00", [
            "晨会：**四小问 CSV 是否齐全**",
            "Codex 四问逻辑审阅；Cursor 全问检验",
        ], "四问结果齐或阻塞登记"),
        ("9.12 · 黄金全日", "中 12:00–18:00", [
            "**16:00 冻结模型**",
            "14:00 短演示会；更新 AI 工具使用详情草稿",
        ], "模型冻结"),
        ("9.12 · 黄金全日", "晚 18:00–24:00", [
            "18:00 终审演示会",
            "**24:00 宣布初稿封版**（draft-v1）",
        ], "初稿封版"),
        ("9.13 · 提交", "早–中", [
            "终审；核数 output/ = 论文",
            "**13:00 前确认已提交**；三份备份",
        ], "已提交", "已提交"),
        ("9.13 · 提交", "午后", ["复核回执；15:00 退房"], "退房"),
    ],
    "meetings": [
        ("9.11", "15:30–16:00", "离场前演示会"),
        ("9.12", "14:00", "短演示会"),
        ("9.12", "18:00", "终审 / 24:00 封版"),
    ],
    "extra_title": "9.11 09:30 离场交接单要点",
    "extra_items": [
        "Q1–Q2 已确认数字（文件 + 列值）",
        "Q3 Cursor 待办（已确认 spec）",
        "Q4 是否可启动（q4.md 已确认？）",
        "禁止：改 specs · 新开模型 · 未核数字进论文",
        "24:00：Q3 状态 · Q4 进度 · 对账红项",
    ],
}

CODEX = {
    "title": "Codex 签收单",
    "subtitle": "建模参谋 · 规格 q1–q4 · 逻辑审阅（不写代码、不替队长决策）",
    "filename": "国赛签收单_Codex.pdf",
    "rules": [
        "输出 docs/specs/qN.md；末尾标「待队长确认」。",
        "9.11 16:00–24:00 可审阅 output/，但不代队长签收。",
        "与 Cursor 分开会话。",
    ],
    "sections": [
        ("9.10", "晚", [
            "三题方案对比；B>C>A 建议",
            "按 _template.md 起草 q1.md + q2.md",
        ], "q1/q2 规格草稿"),
        ("9.10", "深夜", [
            "审阅 Q1 产出逻辑",
            "起草 q3.md 草稿",
        ], "Q1 审阅 · q3 草稿"),
        ("9.11", "早", ["修订 q2.md"], "q2 修订稿"),
        ("9.11", "中", [
            "**15:30 前配合确认 q3.md + q4.md**",
            "演示会前审阅 Q1/Q2 output/",
        ], "四问规格齐"),
        ("9.11", "晚※", [
            "审阅新 output/；记入变更记录",
            "21:00 异步发审阅摘要给队长",
        ], "风险清单"),
        ("9.11", "深夜", ["验收 Q3/Q4 与规格一致性"], "夜间意见"),
        ("9.12", "早", ["四问完整逻辑审阅报告"], "审阅报告"),
        ("9.12", "中", ["16:00 后不建议新模型；审论文模型章逻辑"], "逻辑检查"),
        ("9.12", "晚", ["终审：摘要与结果段是否过度推断"], "终审意见"),
        ("9.13", "早", ["specs 与支撑材料一致性"], "提交前确认"),
    ],
    "meetings": [
        ("9.11", "15:30 前", "供队长：Q1/Q2 审阅摘要"),
        ("9.12", "08:30", "提交四问审阅报告"),
        ("9.12", "18:00 前", "提交终审逻辑意见"),
    ],
    "extra_title": "每小问规格检查（q1–q4）",
    "extra_items": [
        "目标与成功标准", "假设与符号", "公式与约束", "算法路线",
        "output/ 列名 · fig/ 命名", "验证设计", "论文要点", "状态：已确认",
    ],
}

CURSOR = {
    "title": "Cursor 签收单",
    "subtitle": "编码助手 · q1/–q4/ · output/ · fig/（按已确认规格）",
    "filename": "国赛签收单_Cursor.pdf",
    "rules": [
        "只实现已确认 docs/specs/qN.md；每问独立对话，只 @ qN/。",
        "9.11 16:00–24:00 按交接单执行，主攻 Q3。",
        "q4.md 确认后才写 q4/。",
    ],
    "sections": [
        ("9.10", "早", ["跑通 templates/"], "模板可运行"),
        ("9.10", "中", ["数据概览：字段、单位、缺失"], "数据概览"),
        ("9.10", "晚", ["q1 确认后搭 q1/ 骨架"], "q1/ 骨架"),
        ("9.10", "深夜", [
            "**Q1 跑通** output/q1_* + fig/",
            "Q2 骨架可跑",
        ], "Q1 可复现"),
        ("9.11", "早", ["Q1 稳定；修 Q2 bug"], "Q1 交付"),
        ("9.11", "中", [
            "**Q2 跑通** output/q2_*",
            "Q3 启动（q3 已确认）",
            "演示会可复现",
        ], "Q2 CSV"),
        ("9.11", "晚※", [
            "交接单：主攻 **Q3**",
            "q4 确认后才动 q4/",
        ], "Q3 推进"),
        ("9.11", "深夜", ["Q3 收尾；Q4 启动；检验"], "Q3 可跑目标"),
        ("9.12", "早", ["Q4 收尾；四问 output/ 齐；补 fig/"], "四问 CSV"),
        ("9.12", "中", ["灵敏度；附录；16:00 后只修 bug"], "支撑材料"),
        ("9.12", "晚", ["按清单最后一轮修复；draft-v1 commit"], "封版代码"),
        ("9.13", "早", ["打包四问代码 + requirements"], "代码包"),
    ],
    "meetings": [
        ("9.11", "15:30–16:00", "演示可复现 + 列含义"),
        ("9.12", "14:00", "补图与检验"),
        ("9.12", "18:00", "代码与论文数字一致"),
    ],
    "extra_title": "每小问交付前检查",
    "extra_items": [
        "只改 qN/ + 必要 templates/", "CSV 列名 = 规格",
        "figN_*.png", "可复现", "未改已确认 spec", "commit 写明小问",
    ],
}

FIN = {
    "title": "FIN 签收单",
    "subtitle": "文献 refs/ · 结果解读 · 模型评价与推广",
    "filename": "国赛签收单_FIN.pdf",
    "rules": [
        "只引用 results_summary.md 已确认数字。",
        "9.11 16:00–24:00 牵头写作；新 CSV 标待签收。",
    ],
    "sections": [
        ("9.10", "早", ["建立检索关键词与记录方式"], "检索框架"),
        ("9.10", "中", ["背景文献；三题故事线要点"], "refs/ 线索"),
        ("9.10", "晚", [
            "选题会发言：哪题最适合写结果分析",
            "搜 3–5 篇文献进 refs/",
            "假设清单草稿",
        ], "假设草稿"),
        ("9.10", "深夜", ["假设/背景写入 Overleaf 占位（无数字）"], "背景段"),
        ("9.11", "早", ["备份 refs/ 与笔记"], "备份"),
        ("9.11", "中", [
            "演示会 ≥2 个决策/风险问题",
            "Q1（及 Q2 若已确认）解读要点",
        ], "解读笔记"),
        ("9.11", "晚※", [
            "宣读交接单禁止事项",
            "Q1 结果分析草稿（仅已确认数字）",
            "21:00 报写作进度",
        ], "Q1 分析草稿"),
        ("9.11", "深夜", ["按队长签收修订"], "修订"),
        ("9.12", "早", ["Q2–Q4 结果分析；灵敏度决策段"], "结果分析主文"),
        ("9.12", "中", ["模型评价与推广；审摘要表述"], "评价章"),
        ("9.12", "晚", ["通读表述；不改数字"], "终审意见"),
        ("9.13", "早", ["审摘要+结果+评价表述建议"], "表述建议"),
        ("9.13", "午后", ["退房"], "—"),
    ],
    "meetings": [
        ("9.11", "15:30–16:00", "≥2 决策问题"),
        ("9.12", "14:00", "确认分析数字"),
        ("9.12", "18:00", "通读表述"),
    ],
}

ACCT = {
    "title": "ACCT 签收单",
    "subtitle": "paper/ · Overleaf · 对账 · 排版 · 13:00 提交",
    "filename": "国赛签收单_ACCT.pdf",
    "rules": [
        "数字 = output/ = results_summary.md 已确认项。",
        "9.11 16:00–24:00 牵头对账；不估算数字。",
        "12:00–13:00 正式提交。",
    ],
    "sections": [
        ("9.10", "早", ["Overleaf + 论文大纲"], "骨架可编辑"),
        ("9.10", "中", ["四问问题重述结构；对账表框架"], "四问章节框架"),
        ("9.10", "晚", [
            "四问表/图清单",
            "Overleaf 全章骨架；paper/ 同步",
            "对账表（论文字段 ↔ output/ 列）",
        ], "对账表 v0"),
        ("9.10", "深夜", ["问题重述四问写入；符号表占位"], "问题重述 v0"),
        ("9.11", "早", ["导出 Overleaf 备份；Q1 标待签收"], "备份"),
        ("9.11", "中", [
            "13:00–13:30 测网",
            "演示会 Q1 对账",
            "Q1 章节写入 Overleaf",
        ], "Q1 正文 v1"),
        ("9.11", "晚※", [
            "对账表维护；新 output/ 标未核",
            "问题重述/符号说明；插图占位",
            "21:00 与 FIN 对齐缺口",
        ], "进度约 40%"),
        ("9.11", "深夜", ["修正未核数字"], "对账修正"),
        ("9.12", "早", ["模型章文字；摘要四要素草稿"], "模型章+摘要"),
        ("9.12", "中", ["排版；参考文献；二轮对账"], "排版 v1"),
        ("9.12", "晚", ["导出 24:00 PDF 三份备份"], "初稿 PDF"),
        ("9.13", "早–中", [
            "终审修订",
            "**12:00–13:00 提交** + 双备份 + 回执",
        ], "已提交", "已提交"),
        ("9.13", "午后", ["退房"], "退房"),
    ],
    "meetings": [
        ("9.11", "15:30–16:00", "Q1 对账签字"),
        ("9.12", "14:00", "二轮对账"),
        ("9.12", "18:00", "导出 24:00 PDF"),
    ],
}


def build_pdf(person):
    out_path = OUT_DIR / person["filename"]
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN, title=person["title"])
    story = [P(person["title"], "CoverTitle"), P(person["subtitle"], "CoverSub"), Spacer(1, 6), P("铁律", "H2")]
    for r in person["rules"]:
        story.append(P(f"· {r}", "Body"))
    story.append(Spacer(1, 8))

    hard_data = [[P("节点", "Th"), P("时间", "Th")]] + [[P(a, "Body"), P(b, "Body")] for a, b in HARD_NODES]
    ht = Table(hard_data, colWidths=[90 * mm, 80 * mm], repeatRows=1)
    ht.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [P("全队硬节点（四小问）", "H2"), ht, Spacer(1, 8)]

    for day, period, tasks, deliverable, *rest in person["sections"]:
        story += section_block(day, period, tasks, deliverable, rest[0] if rest else "")

    story.append(PageBreak())
    story.append(P("演示会 / 关键节点签收", "H1"))
    for date, time, note in person.get("meetings", []):
        story.append(P(f"☐ {date} {time} — {note}", "Body"))

    if person.get("extra_items"):
        story.append(Spacer(1, 10))
        story.append(P(person["extra_title"], "H1"))
        for item in person["extra_items"]:
            story.append(P(f"☐ {item}", "Body"))

    story.append(Spacer(1, 8))
    story.append(P("每场演示会：Cursor 可复现 · ACCT 对账 · FIN ≥2 问题 · 待办写入 results_summary.md", "Small"))
    doc.build(story)
    return out_path


def main():
    for person in (CAPTAIN, CODEX, CURSOR, FIN, ACCT):
        print(build_pdf(person))


if __name__ == "__main__":
    main()
