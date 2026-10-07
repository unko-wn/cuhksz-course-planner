#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract the CUHK-SZ course-offering table from the PDF offering documents.

Pure standard library (re / zlib / json / argparse / collections / statistics).

The PDFs draw every table cell as its own text run positioned with *relative*
``Td`` / ``TD`` / ``T*`` offsets inside a long text object, in a text space that
is scaled by the ``Tm`` matrix (font size 12).  Offsets therefore have to be
accumulated **through the matrix** (``e += tx*a + ty*c``, ``f += tx*b + ty*d``);
accumulating them as plain numbers puts the header row and the body rows in two
different coordinate spaces.  With the matrix-correct accumulation the whole
page lands in one space (header ``y=1887``, body rows below it), which is what
this script relies on.

Usage:
    python build/pdf_rows.py --pdf p1 --out build/_pdf_p1.json --report build/_pdf_p1_report.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import zlib

# PDF 输入路径。默认在当前目录查找下面两个文件名；可以用环境变量覆盖
# （PDF_P1 / PDF_P2）或把 PDF 放在本目录下同名文件。
PDF_DIR = os.environ.get("PDF_DIR", os.path.dirname(os.path.abspath(__file__)))
PDF_NAMES = {
    "p1": "Formal Course Registration_Course Offering Information_AY2025-26 Term 2 (Updated on Dec. 19).pdf",
    "p2": "AddDrop_Course Offering Information_AY2026-27 Term 1( Updated on September 4).pdf",
}
PDFS = {k: os.environ.get("PDF_" + k.upper(), os.path.join(PDF_DIR, v))
        for k, v in PDF_NAMES.items()}

COLUMNS = ["Department", "Course Code", "Course Title", "Units", "Instructors",
           "Language of Instruction", "Quota", "Activity Counts", "Prerequisite",
           "Corequisite", "Exclusion", "Target Students", "Reserved Quota",
           "Co-listed Course", "Remark"]

CODE_RE = re.compile(r"^[A-Z]{2,4}\d{4}[A-Z]?$")
# PDF2 renames some headers and omits others while keeping the column in the body
ALIASES = {
    "Target Student": "Target Students",
    "Waiting List": "Activity Counts",
    "Activity Count": "Activity Counts",
    "Language": "Language of Instruction",
}
NUM_RE = re.compile(rb"[-+]?(?:\d+\.?\d*|\.\d+)$")
TOK_RE = re.compile(rb"\((?:[^()\\]|\\.)*\)|\[[^\]]*\]|[-+]?[\d.]+|[A-Za-z'\"*]+")
ESC = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "(": "(", ")": ")", "\\": "\\"}


def decode_literal(raw: bytes) -> str:
    out, i = bytearray(), 0
    while i < len(raw):
        c = raw[i]
        if c == 0x5C and i + 1 < len(raw):
            n = raw[i + 1]
            if n in b"nrtbf()\\":
                out += ESC[chr(n)].encode("latin-1"); i += 2; continue
            m = re.match(rb"[0-7]{1,3}", raw[i + 1:i + 4])
            if m:
                out.append(int(m.group(0), 8) & 0xFF); i += 1 + len(m.group(0)); continue
            i += 2; continue
        out.append(c); i += 1
    return out.decode("latin-1")


def content_streams(path: str):
    data = open(path, "rb").read()
    for raw in re.findall(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            d = zlib.decompress(raw.rstrip(b"\r\n"))
        except Exception:
            continue
        if b"BT" in d and b"Tj" in d or b"TJ" in d:
            yield d


def parse_runs(stream: bytes):
    """Linear PDF text interpreter -> [(x, y, text)] in one device-ish space."""
    tm = [1.0, 0, 0, 1.0, 0.0, 0.0]
    tlm = tm[:]
    leading = 0.0
    stack: list[float] = []
    pending = None
    out = []
    for m in TOK_RE.finditer(stream):
        tok = m.group(0)
        head = tok[:1]
        if head == b"(":
            pending = decode_literal(tok[1:-1]); continue
        if head == b"[":
            pending = "".join(decode_literal(p[1:-1]) for p in re.findall(rb"\((?:[^()\\]|\\.)*\)", tok)); continue
        if NUM_RE.match(tok):
            stack.append(float(tok))
            if len(stack) > 8:
                stack.pop(0)
            continue
        op = tok
        if op == b"BT":
            tm = [1.0, 0, 0, 1.0, 0.0, 0.0]; tlm = tm[:]
        elif op == b"Tm" and len(stack) >= 6:
            tm = list(stack[-6:]); tlm = tm[:]
        elif op in (b"Td", b"TD") and len(stack) >= 2:
            tx, ty = stack[-2], stack[-1]
            tlm = [tlm[0], tlm[1], tlm[2], tlm[3],
                   tlm[4] + tx * tlm[0] + ty * tlm[2],
                   tlm[5] + tx * tlm[1] + ty * tlm[3]]
            tm = tlm[:]
            if op == b"TD":
                leading = -ty
        elif op == b"T*":
            tlm = [tlm[0], tlm[1], tlm[2], tlm[3],
                   tlm[4] - leading * tlm[2], tlm[5] - leading * tlm[3]]
            tm = tlm[:]
        elif op == b"TL" and stack:
            leading = stack[-1]
        elif op in (b"Tj", b"TJ", b"'", b'"') and pending is not None:
            if pending.strip():
                out.append((round(tm[4], 2), round(tm[5], 2), pending))
            pending = None
        stack = []
    return out


def header_positions(runs):
    """Best header row of a page -> {column: x} (the row with most known labels)."""
    by_y = collections.defaultdict(dict)
    for x, y, t in runs:
        key = ALIASES.get(t.strip(), t.strip())
        if key in COLUMNS:
            by_y[round(y)].setdefault(key, []).append(x)
    if not by_y:
        return None, 0
    y, found = max(by_y.items(), key=lambda kv: (len(kv[1]), -abs(kv[0])))
    return ({k: sum(v) / len(v) for k, v in found.items()}, y)


def cluster_centers(values, tol=10.0, min_count=3):
    """Cluster 1-D coordinates into column content positions."""
    if not values:
        return []
    vals = sorted(values)
    out, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] <= tol:
            cur.append(v)
        else:
            if len(cur) >= min_count:
                out.append(sum(cur) / len(cur))
            cur = [v]
    if len(cur) >= min_count:
        out.append(sum(cur) / len(cur))
    return out


def fill_missing_columns(canonical, body_x):
    """Insert columns whose header label is missing but whose body content exists."""
    known = sorted(((COLUMNS.index(n), x) for n, x in canonical.items() if n in COLUMNS))
    filled = dict(canonical)
    if len(known) < 3:
        return filled, []
    centers = cluster_centers(body_x)
    known_x = [x for _, x in known]
    inserted = []
    for i in range(len(known) - 1):
        r1, x1 = known[i]
        r2, x2 = known[i + 1]
        if r2 - r1 <= 1:
            continue
        mids = sorted(c for c in centers
                      if x1 + 25 < c < x2 - 25 and all(abs(c - kx) > 25 for kx in known_x))
        for k, rank in enumerate(range(r1 + 1, r2)):
            if k < len(mids):
                filled[COLUMNS[rank]] = mids[k]
                inserted.append(COLUMNS[rank])
    return filled, inserted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", choices=sorted(PDFS), required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--dump-page", type=int, default=0)
    args = ap.parse_args()

    path = PDFS[args.pdf]
    streams = list(content_streams(path))

    pages = []
    header_votes = collections.defaultdict(list)
    for si, st in enumerate(streams):
        runs = parse_runs(st)
        if not runs:
            continue
        hdr, hy = header_positions(runs)
        pages.append({"index": si, "runs": runs, "header": hdr, "headerY": hy})
        if hdr and len(hdr) >= 10:
            for k, v in hdr.items():
                header_votes[k].append(v)

    if not header_votes:
        print("FATAL: no page carries the table header", file=sys.stderr)
        return 2
    canonical = {k: sorted(v)[len(v) // 2] for k, v in header_votes.items()}
    body_x = [x for pg in pages for x, y, t in pg["runs"]
              if not (ALIASES.get(t.strip(), t.strip()) in COLUMNS and pg["headerY"] and abs(y - pg["headerY"]) < 4)]
    canonical, inserted_cols = fill_missing_columns(canonical, body_x)
    missing_cols = [c for c in COLUMNS if c not in canonical]
    ordered = [(c, canonical[c]) for c in COLUMNS if c in canonical]
    ordered.sort(key=lambda kv: kv[1])
    # column left edges: a small pad left of the header label
    edges = [(c, x - 4.0) for c, x in ordered]
    bounds = [x for _, x in edges] + [float("inf")]

    def col_of(x):
        for i in range(len(edges)):
            if bounds[i] <= x < bounds[i + 1]:
                return edges[i][0]
        return None

    rows = []
    page_stats = []
    seen_codes = collections.Counter()
    for pg in pages:
        runs = pg["runs"]
        anchors = [r for r in runs if CODE_RE.match(r[2].strip()) and col_of(r[0]) == "Course Code"]
        anchors.sort(key=lambda r: -r[1])
        if not anchors:
            page_stats.append({"page": pg["index"] + 1, "anchors": 0, "headerY": pg["headerY"], "headerCols": len(pg["header"] or {})})
            continue
        ys = [a[1] for a in anchors]
        cells = collections.defaultdict(list)

        def attach(cluster, col):
            """Attach one multi-line cell to the anchor closest to its centre."""
            if not cluster:
                return
            centre = (cluster[0][0] + cluster[-1][0]) / 2.0
            top = cluster[0][0]
            j = min(range(len(anchors)), key=lambda k: (abs(centre - ys[k]), abs(top - ys[k])))
            cells[(j, col)].extend(cluster)

        bycol = collections.defaultdict(list)
        for x, y, t in runs:
            if CODE_RE.match(t.strip()) and col_of(x) == "Course Code":
                continue                                   # anchors handled separately
            if ALIASES.get(t.strip(), t.strip()) in COLUMNS:
                continue                                   # repeated table header, never body content
            col = col_of(x)
            if col is None:
                continue
            bycol[col].append((y, x, t))
        for col, items in bycol.items():
            items.sort(key=lambda z: -z[0])
            cluster = []
            for it in items:
                if cluster and (cluster[-1][0] - it[0]) > 2.0:
                    attach(cluster, col)
                    cluster = []
                cluster.append(it)
            attach(cluster, col)
        for j, a in enumerate(anchors):
            row = {"_page": pg["index"] + 1, "_y": a[1]}
            for c in COLUMNS:
                items = sorted(cells.get((j, c), []), key=lambda z: (-z[0], z[1]))
                text = " ".join(t.strip() for _, _, t in items if t.strip())
                row[c] = re.sub(r"\s{2,}", " ", text).strip()
            row["Course Code"] = a[2].strip()
            rows.append(row)
            seen_codes[row["Course Code"]] += 1
        page_stats.append({"page": pg["index"] + 1, "anchors": len(anchors),
                           "headerY": pg["headerY"], "headerCols": len(pg["header"] or {})})

    bad = [r["Course Code"] for r in rows if not CODE_RE.match(r["Course Code"])]
    dup = {k: v for k, v in seen_codes.items() if v > 1}
    report = {
        "pdf": args.pdf,
        "source": os.path.basename(path),
        "contentStreams": len(streams),
        "pagesWithHeader": sum(1 for p in pages if p["header"] and len(p["header"]) >= 10),
        "headerLabelsMissing": missing_cols,
        "columnsInferredFromBody": inserted_cols,
        "canonicalColumns": {c: canonical.get(c) for c in COLUMNS},
        "rows": len(rows),
        "distinctCodes": len(seen_codes),
        "duplicateCodes": dup,
        "badCodes": bad[:20],
        "pages": page_stats,
        "emptyTargetStudents": sum(1 for r in rows if not r.get("Target Students")),
        "emptyUnits": sum(1 for r in rows if not r.get("Units")),
        "emptyLanguage": sum(1 for r in rows if not r.get("Language of Instruction")),
    }

    if args.dump_page:
        want = args.dump_page
        for r in rows:
            if r["_page"] == want:
                print(json.dumps(r, ensure_ascii=False))

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"pdf": args.pdf, "source": os.path.basename(path), "rows": rows}, f, ensure_ascii=False, indent=1)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k not in ("pages", "canonicalColumns")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
