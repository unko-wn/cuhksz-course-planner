"""Cross-check: does every targeted code map to the course the PDF names?"""
import json
import os
import re
import sys
import difflib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_extract import extract_pages

# PDF 路径：默认在脚本所在目录查找；可用环境变量 STUDY_PDF_DIR 指向实际目录。
PDF_DIR = os.environ.get("STUDY_PDF_DIR", os.path.dirname(os.path.abspath(__file__)))
PDFS = {
    'AI': os.path.join(PDF_DIR, 'Study scheme - AI_2025-26 and thereafter_Senate20251008-13-16.pdf'),
    'CSE': os.path.join(PDF_DIR, 'Study Scheme - CSE_2024-25 and thereafter_3rd(2025)_20250714_0-7-9.pdf'),
}
CODE = re.compile(r"\b([A-Z]{2,6})(\d{3,4}[A-Z]?)\b")

idx = json.load(open("catalog_index.json", encoding="utf-8"))
targets = json.load(open("targets.json", encoding="utf-8"))

# ---- pull (code, english title) pairs out of the PDFs ----
pairs = {}
for tag, path in PDFS.items():
    text = re.sub(r"\s+", " ", "".join("".join(r) for _, r in extract_pages(path)))
    for m in CODE.finditer(text):
        code = m.group(1) + m.group(2)
        tail = text[m.end(): m.end() + 120]
        tm = re.match(r"\s*([A-Za-z][A-Za-z0-9 ,:;()\-/'&+.]{2,95})", tail)
        if tm:
            title = re.sub(r"\s+", " ", tm.group(1)).strip(" .,:;-")
            pairs.setdefault(code, set()).add(title)

print("codes with a PDF title:", len(pairs))
bad = []
for subj, nbrs in sorted(targets.items()):
    cat = {c[0]: c[1] for c in idx.get(subj, {}).get("courses", [])}
    for nbr in nbrs:
        code = subj + nbr
        sut = cat.get(nbr)
        want = pairs.get(code)
        if sut is None:
            continue
        if not want:
            continue
        best = max((difflib.SequenceMatcher(None, sut.lower(), w.lower()).ratio()
                    for w in want), default=0)
        if best < 0.62:
            bad.append((code, sut, sorted(want)[:2], round(best, 2)))

print(f"\ncodes where the SIS title looks DIFFERENT from the PDF title: {len(bad)}")
for code, sut, want, r in bad:
    print(f"  {code:10s} sim={r}")
    print(f"      SIS    : {sut}")
    print(f"      PDF    : {want}")
if not bad:
    print("  (none - every targeted code matches its study-scheme title)")
