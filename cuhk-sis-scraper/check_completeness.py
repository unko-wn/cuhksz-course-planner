"""Completeness check on PDF extraction: look for split/missed course codes."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_extract import extract_pages

# PDF 路径：默认在脚本所在目录查找；可用环境变量 STUDY_PDF_DIR 指向实际目录。
PDF_DIR = os.environ.get("STUDY_PDF_DIR", os.path.dirname(os.path.abspath(__file__)))
PDFS = {
    'AI': os.path.join(PDF_DIR, 'Study scheme - AI_2025-26 and thereafter_Senate20251008-13-16.pdf'),
    'CSE': os.path.join(PDF_DIR, 'Study Scheme - CSE_2024-25 and thereafter_3rd(2025)_20250714_0-7-9.pdf'),
}

STRICT = re.compile(r"\b([A-Z]{2,6})(\d{3,4}[A-Z]?)\b")
LOOSE = re.compile(r"\b([A-Z]{2,6})\s+(\d{3,4}[A-Z]?)\b")

for tag, path in PDFS.items():
    pages = extract_pages(path)
    text = re.sub(r"\s+", " ", "".join("".join(r) for _, r in pages))
    strict = [m.group(0) for m in STRICT.finditer(text)]
    loose = [m.group(1) + m.group(2) for m in LOOSE.finditer(text)]
    ss, sl = set(strict), set(loose)
    print("=" * 84)
    print(f"{tag}: strict={len(ss)} loose={len(sl)}")
    only_loose = sorted(sl - ss)
    print(f"  codes only visible when split by whitespace ({len(only_loose)}): {only_loose}")

    # every course row should be "<CODE> <English title> <Chinese title> <units>"
    rows = re.findall(r"([A-Z]{2,6}\d{3,4}[A-Z]?)\s+([A-Za-z][^0-9]{4,80}?)\s+\S+\s+(\d)", text)
    print(f"  rows matching '<CODE> <title> <cjk> <units>': {len(rows)}")
    print(f"  distinct codes in those rows: {len({r[0] for r in rows})}")

    # look for suspicious tokens: letters immediately followed by 3-4 digits that were
    # rejected (e.g. lowercase mixed in)
    weird = re.findall(r"\b([A-Za-z]{1,8}\d{3,4}[A-Za-z]?)\b", text)
    odd = sorted({w for w in weird if not re.fullmatch(r"[A-Z]{2,6}\d{3,4}[A-Z]?", w)})
    print(f"  odd code-like tokens ({len(odd)}): {odd[:25]}")
