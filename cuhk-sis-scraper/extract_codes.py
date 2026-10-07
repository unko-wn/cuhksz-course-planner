"""Extract course codes from the two study-scheme PDFs."""
import re
import sys
import os
import json
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_extract import extract_pages

# PDF 路径：默认在脚本所在目录查找；可用环境变量 STUDY_PDF_DIR 指向实际目录。
PDF_DIR = os.environ.get("STUDY_PDF_DIR", os.path.dirname(os.path.abspath(__file__)))
PDFS = {
    'AI': os.path.join(PDF_DIR, 'Study scheme - AI_2025-26 and thereafter_Senate20251008-13-16.pdf'),
    'CSE': os.path.join(PDF_DIR, 'Study Scheme - CSE_2024-25 and thereafter_3rd(2025)_20250714_0-7-9.pdf'),
}

CODE = re.compile(r"\b([A-Z]{2,6})(\d{3,4}[A-Z]?)\b")

out = {}
for tag, path in PDFS.items():
    pages = extract_pages(path)
    text = "".join("".join(runs) for _, runs in pages)
    text = re.sub(r"\s+", " ", text)
    codes = []
    for m in CODE.finditer(text):
        codes.append(m.group(1) + m.group(2))
    codes = list(dict.fromkeys(codes))
    out[tag] = codes
    print("=" * 88)
    print(f"{tag}: {len(pages)} pages, {len(text)} chars, {len(codes)} distinct codes")
    bysub = collections.defaultdict(list)
    for c in codes:
        bysub[re.match(r"([A-Z]+)", c).group(1)].append(c)
    for s in sorted(bysub):
        print(f"  {s:8s} ({len(bysub[s]):2d}): {', '.join(bysub[s])}")

with open("_pdf_codes.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("\nsaved _pdf_codes.json")
