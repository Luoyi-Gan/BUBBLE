#!/usr/bin/env python3
"""Build CUMCM 2026 submission zip per format2026.doc.

Outputs:
- submission_pack/CUMCM2026_C题_提交包/参赛论文.pdf
- submission_pack/CUMCM2026_C题_提交包/支撑材料/...
- submission_pack/CUMCM2026_C题_提交包.zip
"""

from __future__ import annotations

import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "submission_pack" / "CUMCM2026_C题_提交包"
SUPPORT = PACK_ROOT / "支撑材料"
CODE = SUPPORT / "code"
RESULTS = SUPPORT / "题设结果"
PAPER_SRC = ROOT / "paper" / "submission" / "main.pdf"

CODE_DIRS = ("q1", "q2", "q3", "q4", "scripts")
RESULT_FILES = (
    "result1.xlsx",
    "result2.xlsx",
    "result3.xlsx",
    "result4-2.xlsx",
    "result4-3.xlsx",
)


def copy_code_tree() -> list[str]:
    paths: list[str] = []
    for name in CODE_DIRS:
        src = ROOT / name
        dst = CODE / name
        if not src.exists():
            continue
        for path in src.rglob("*"):
            if path.is_dir():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            rel = path.relative_to(ROOT)
            target = CODE / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            paths.append(str(rel).replace("\\", "/"))
    req = ROOT / "requirements.txt"
    if req.exists():
        shutil.copy2(req, SUPPORT / "requirements.txt")
        paths.append("requirements.txt")
    return sorted(paths)


def copy_results() -> list[str]:
    paths: list[str] = []
    for name in RESULT_FILES:
        src = ROOT / "output" / name
        if not src.exists():
            raise FileNotFoundError(f"missing required workbook: {src}")
        shutil.copy2(src, RESULTS / name)
        paths.append(f"题设结果/{name}")
    return paths


def write_usage() -> None:
    text = """CUMCM 2026 C题 · 支撑材料使用说明

一、环境
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt

二、题设结果（已验收）
  题设结果/result1.xlsx … result4-3.xlsx 与论文数字一致。
  数字对账见仓库 paper/reconciliation.md（本包未重复打包）。

三、复现入口（示例）
  Q1: python3 -m q1.run_q1
  Q2: python3 -m q2.run_q2_policy_consistent_r4   # 政策一致 V2 正式链
  Q3: python3 -m q3.run_q3_full_annual
  Q4: python3 -m q4.run_q4_full                    # Q4-2/Q4-3 全年

四、说明
  - 附件原始数据未随包分发；代码默认读取仓库 data/ 或环境内附件路径。
  - 论文 PDF 单独置于提交包根目录「参赛论文.pdf」，首页为摘要（不含承诺书/编号页）。
  - 规范依据：format2026.doc（2026年修订稿）第九条、第十条。
"""
    (SUPPORT / "使用说明.txt").write_text(text, encoding="utf-8")


def write_file_list(code_paths: list[str], result_paths: list[str]) -> None:
    lines = [
        "CUMCM 2026 C题 · 支撑材料文件列表",
        f"生成时间：{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "【题设结果】",
        *result_paths,
        "",
        "【程序代码】",
        *code_paths,
        "",
        "【说明文档】",
        "使用说明.txt",
        "requirements.txt",
        "文件列表.txt",
    ]
    (SUPPORT / "文件列表.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_zip() -> Path:
    zip_path = ROOT / "submission_pack" / "CUMCM2026_C题_提交包.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in PACK_ROOT.rglob("*"):
            if path.is_file():
                arc = path.relative_to(PACK_ROOT.parent)
                zf.write(path, arc)
    return zip_path


def main() -> None:
    if not PAPER_SRC.exists():
        raise FileNotFoundError(f"missing paper PDF: {PAPER_SRC}")
    if PACK_ROOT.exists():
        shutil.rmtree(PACK_ROOT)
    SUPPORT.mkdir(parents=True)
    CODE.mkdir(parents=True)
    RESULTS.mkdir(parents=True)

    shutil.copy2(PAPER_SRC, PACK_ROOT / "参赛论文.pdf")
    code_paths = copy_code_tree()
    result_paths = copy_results()
    write_usage()
    write_file_list(code_paths, result_paths)

    zip_path = build_zip()
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    paper_mb = (PACK_ROOT / "参赛论文.pdf").stat().st_size / (1024 * 1024)
    print(f"paper: {paper_mb:.2f} MB")
    print(f"zip:   {zip_path} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
