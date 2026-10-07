#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge the two PDF course-offering tables and the three term spreadsheets into
data/catalog.json (schema v2) plus data/report.md.

Rules (confirmed with the user):
  * course universe  = PDF1 ∪ PDF2 ∪ xlsx catalog
  * sessions/tutorials/teacher/room/time come only from the xlsx, per term
  * Units / Language / Target Students are filled only for courses that the xlsx
    mentions (`attrSource == "xlsx"`); PDF-only courses are tag-only
  * Prerequisite / Exclusion: xlsx first, PDF as the fallback for other courses
  * the college code is deliberately overloaded and carries two independent
    meanings, which callers must not conflate:
      - "college"            = the OFFERING department (PDF Department, else the
                               xlsx Academic Group). Other colleges may still
                               take the course.
      - "collegeRestriction" = the TARGET-STUDENT college list, taken only from
                               the Target Students text. It is what blocks other
                               colleges. It can differ from the offering college
                               (e.g. AIE 4901 is offered by SAI but targets SDS/MED).
  * classification tags: offering college, GE (Target Students contains
    "All UG Students", or the code prefix is a GE series), special student types,
    special majors / tracks -- a course can carry several tags
  * year range and the Target-Students college list are hard filters. Courses
    whose Target Students names only majors/tracks (no year, no college) are
    selectable and carry "majorOnly": true so the UI can warn. The special
    types/majors are otherwise labels only.
  * a course whose prerequisites are ALL themselves college-limited inherits the
    union of those colleges (you cannot satisfy the prerequisites without being
    able to take them), applied to a fixpoint
  * course-level overrides confirmed with the user: PED is Y1-only, CHI/CEC are
    taught in Chinese, PED 1101 has no prerequisite
  * the GEA/GEB/GEC/GED series is Y2-Y4 (per-course PDF wording is overridden),
    needs GFH 1000 or GFN 1000 (a Corequisite in the PDF, modelled as a prereq
    group), and its Y1-only programmes (MSAIN_DMP / JTMSN_JOT) are surfaced as
    "y1Tags" so the UI can tell who may take it in year 1

Usage:
    python build/build_catalog.py [--out data/catalog.json] [--report data/report.md]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from datetime import date

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    print("openpyxl is required (bundled python has it)", file=sys.stderr)
    raise

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "cuhk-sis-scraper", "output")

XLSX_TERMS = [
    ("2025-26-T1", "ALL_UG_SIS_2025-26_Term_1.xlsx", "2025-26", "T1", {"zh": "2025-26 上学期", "en": "2025-26 Term 1"}),
    ("2025-26-T2", "ALL_UG_SIS_2025-26_Term_2.xlsx", "2025-26", "T2", {"zh": "2025-26 下学期", "en": "2025-26 Term 2"}),
    ("2026-27-T1", "ALL_UG_SIS_2026-27_Term_1.xlsx", "2026-27", "T1", {"zh": "2026-27 上学期", "en": "2026-27 Term 1"}),
]
LOCKED_TERM = ("2026-27-T2", "2026-27", "T2", {"zh": "2026-27 下学期", "en": "2026-27 Term 2"},
               {"zh": "该学期课程数据尚未发布，暂不可选。", "en": "Course data for this term has not been released yet."})

COLLEGE_NAMES = {
    "SSE": {"zh": "理工学院", "en": "School of Science and Engineering", "fill": "#e3ecfd", "accent": "#2563eb"},
    "SDS": {"zh": "数据科学学院", "en": "School of Data Science", "fill": "#dbe9fb", "accent": "#1d4ed8"},
    "SAI": {"zh": "人工智能学院", "en": "School of Artificial Intelligence", "fill": "#dcf3dc", "accent": "#16a34a"},
    "MED": {"zh": "医学院", "en": "School of Medicine", "fill": "#fde2e2", "accent": "#dc2626"},
    "MUS": {"zh": "音乐学院", "en": "School of Music", "fill": "#f3e8ff", "accent": "#7c3aed"},
    "HSS": {"zh": "人文社科学院", "en": "School of Humanities and Social Science", "fill": "#fdf6d8", "accent": "#ca8a04"},
    "SME": {"zh": "经管学院", "en": "School of Management and Economics", "fill": "#fde3cf", "accent": "#ea580c"},
}
COLLEGE_ORDER = ["SSE", "SDS", "SAI", "MED", "MUS", "HSS", "SME"]
ACADEMIC_GROUP_MAP = {
    "sch of management and economic": "SME",
    "school of management and economic": "SME",
    "school of management and economics": "SME",
    "sch of artificial intelligence": "SAI",
    "school of artificial intelligence": "SAI",
    "school of medicine": "MED",
    "sch of science and engineering": "SSE",
    "school of science and engineering": "SSE",
    "school of data science": "SDS",
    "school of humanities and social science": "HSS",
    "sch of humanities and soc sci": "HSS",
    "school of humanities and soc sci": "HSS",
    "school of music": "MUS",
    "course offered by cuhk": "HSS",            # 与中大合办的语文体验课
    "cetr for innov desig entrepre": "SSE",     # IDE 创新设计课程
    "registry": "HSS",                          # 占位课程另行剔除
}
# Registry 名下的 Dummy / Exemption 记录不是真实课程，直接从目录里去掉
PLACEHOLDER_PREFIXES = {"DUM", "EXGBE", "EXGBI", "EXME", "EXNE", "EXSE", "EXSS"}
# 无数据课程表：整表删除（用户确认范围为该表全部课号；此处保留 7 门硬编码兜底）
NO_DATA_FILE = "NO_DATA_courses.xlsx"
DELETE_CODES_FALLBACK = {"BIM 3011", "ECE 4006", "MSE 4650", "PHY 4221", "STA 4503", "STA 4504", "HSS 2001"}


def read_delete_codes() -> set:
    path = os.path.join(OUT_DIR, NO_DATA_FILE)
    if not os.path.exists(path):
        warn(f"{NO_DATA_FILE} not found -> falling back to the explicit 7-course list")
        return set(DELETE_CODES_FALLBACK)
    wb = load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    codes = {code_fmt(r[0]) for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]}
    return codes | DELETE_CODES_FALLBACK
# 补充课时数据（本次新抓到的 258 门课）
SUPPLEMENT_FILE = "SUPPLEMENT_sessions_tutorials.xlsx"
SUPPLEMENT_SHEETS = {
    "2025-26_Term_1": "2025-26-T1",
    "2025-26_Term_2": "2025-26-T2",
    "2026-27_Term_1": "2026-27-T1",
}
STUDENT_TYPES = ["INDAN", "INDAZ", "ASEIN", "ASEIZ", "MASEN", "MASEZ"]
STOP_TAGS = {"UG", "STUDENTS", "STUDENT", "ALL", "TBA", "N/A", "NA", "AND", "OR", "EXCLUDE", "NON",
             "GRADING", "BASIS", "P/U", "DPF", "THE", "OF", "Y", "S", "LANGUAGE", "SESSION", "SESSIONS",
             "ONLY", "ONLY)", "QUOTA", "WAITING", "LIST", "REMARK", "TOTAL"}
DAY_TOKENS = {"Mo": 1, "Tu": 2, "We": 3, "Th": 4, "Fr": 5, "Sa": 6, "Su": 7}
# 可作为选课节次的类型；IDV/RSC/CLN/EXM/THE 仅展示不可选（用户确认）
SELECTABLE_TYPES = {"LEC", "SUP", "LAB", "PRA", "CLP", "WKS", "UGI"}
# 通识课判定：除了 Target Students 写明 "All UG Students"，这些前缀下的课程
# 一律视为通识（用户确认：PED / GEA / GEB / GEC / GED / CEC 系列全部为通识课）
GE_PREFIXES = {"GEA", "GEB", "GEC", "GED", "PED", "CEC"}
# 用户确认的课程级覆盖（原文数据有误或不完整，按前缀/课号统一修正）
CHINESE_LANGUAGE_PREFIXES = {"CHI", "CEC"}      # 中文授课，覆盖 xlsx 里的 English
PED_YEAR_RESTRICTED_PREFIX = "PED"              # 体育课一律只限 Y1
PED_YEAR_MIN = PED_YEAR_MAX = 1
PED_PREREQ_CLEAR = {"PED 1101"}                 # 体育课不应有 ENG 先修（课号也不在目录里）
# GEA/GEB/GEC/GED 系列（用户确认）：全部 Y2-Y4、先修/共修 GFH1000 或 GFN1000、
# 其中点名了专业的课程（如 GEB 2508/2509）选课时弹专业提示
GE_SERIES = {"GEA", "GEB", "GEC", "GED"}
GE_SERIES_YEAR_MIN = 2
GE_SERIES_YEAR_MAX = 4
GE_SERIES_COREQ = ["GFH 1000", "GFN 1000"]
# GFH/GFN 里 Y1 即可选的专业（用户新增的两个标签），其余学生 Y2 以后才能选
GE_Y1_PROGRAMME_TAGS = ["MSAIN_DMP", "JTMSN_JOT"]
# 目标学生里出现的学院/专业代码 -> 界面展示用的专业名（major_map.json 的 tag 映射）
GE_TAG_LABELS = {
    "FE": "金融工程", "SME": "经管学院", "HSS": "人文社科学院", "MED": "医学院", "CMED": "临床医学",
    "MUS": "音乐学院", "MATH": "数学与应用数学", "ENER": "新能源科学与工程", "CHEM": "化学",
    "PHY": "物理学", "MSEN": "材料科学与工程", "DSBDT": "数据科学与大数据技术", "STAT": "统计学",
    "MSAIN_DMP": "MSAIN_DMP 专业", "JTMSN_JOT": "JTMSN_JOT 专业",
}
# PDF 物理行溢出（单元格文字跨行，被解析器分给相邻两行）的修补：
# 只有括号不平衡时才把下一行的目标学生文字并回来


def to_min(hhmm: str) -> int:
    h, m = str(hhmm).split(":")[:2]
    return int(h) * 60 + int(m)

warnings: list[str] = []
notes: list[str] = []
DROPPED_SLOTS: list[str] = []


def warn(msg: str) -> None:
    warnings.append(msg)


def code_fmt(raw: str) -> str:
    """'ACT2111' / 'ACT 2111' -> 'ACT 2111'"""
    s = re.sub(r"\s+", "", str(raw or "")).upper()
    m = re.match(r"^([A-Z]{2,4})(\d{4}[A-Z]?)$", s)
    return f"{m.group(1)} {m.group(2)}" if m else str(raw or "").strip()


def dedupe_words(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    half = len(s) // 2
    if len(s) % 2 == 1 and s[:half] == s[half + 1:]:
        return s[:half]
    return s


def clean_department(raw: str) -> str | None:
    s = str(raw or "")
    for token in re.findall(r"\b[A-Z]{2,4}\b", s):
        if token in COLLEGE_NAMES:
            return token
    return None


def clean_language(raw: str) -> str:
    s = dedupe_words(raw)
    s = re.sub(r"^Language of Instruction\s*", "", s).strip()
    return dedupe_words(s)


# --------------------------------------------------------------------- target students
def parse_target(s: str):
    """Target Students string -> (isGE, yearMin, yearMax, colleges, tags, unparsed)"""
    text = dedupe_words(s)
    if not text:
        return False, None, None, [], [], True
    low = text.lower()
    is_ge = "all ug student" in low
    years = [int(y) for y in re.findall(r"\bY(\d)\b", text)]
    rng = re.search(r"\bY(\d)\s*[-–]\s*Y?(\d)\b", text)
    ymin = ymax = None
    if rng:
        ymin, ymax = int(rng.group(1)), int(rng.group(2))
    elif years:
        ymin = ymax = max(years)

    # normalise the token stream: brackets become separators, year/quota noise is dropped
    flat = text.replace("[", " ; ").replace("]", " ; ").replace("(", " ; ").replace(")", " ; ")
    flat = re.sub(r"[:：]\s*\d+", " ", flat)
    flat = re.sub(r"\bY\d\s*[-–]\s*Y?\d\b|\bY\d\b", " ", flat, flags=re.I)
    flat = re.sub(r"\bnon\s*[-–]?\s*", "", flat, flags=re.I)
    flat = re.sub(r"\bexclude\s*", " ", flat, flags=re.I)
    colleges, tags = [], []
    for raw_tok in re.split(r"[;,/\s]+", flat):
        tok = raw_tok.strip(" .:-–()[]")
        up = tok.upper()
        if not up or len(up) < 2 or len(up) > 18:
            continue
        if up in COLLEGE_NAMES:
            if up not in colleges:
                colleges.append(up)
            continue
        if up in STOP_TAGS or up.isdigit() or re.fullmatch(r"Y\d(-\d)?", up) or re.fullmatch(r"L\d{1,2}", up):
            continue
        if up not in tags:
            tags.append(up)
    unparsed = not (is_ge or ymin or colleges or tags)
    return is_ge, ymin, ymax, colleges, tags, unparsed


def coreq_prereq_group(*texts: str) -> list[str]:
    """'GFH or GFN' 这类共修/先修要求 -> 一条 OR 先修组 ['GFH 1000', 'GFN 1000']"""
    joined = " ".join(str(t or "") for t in texts)
    if re.search(r"\bGFH\b", joined) and re.search(r"\bGFN\b", joined):
        return list(GE_SERIES_COREQ)
    return []


def merge_ge_target_spill(rows: list[dict]) -> tuple[int, int]:
    """修补 PDF 物理行溢出（只针对 GEA/GEB/GEC/GED）。

    GEB 2508 / GEB 2509 的目标学生整串文字在 PDF 里只排了一次并跨行：
        GEB2508 'Y2-Y4 Students Y2-Y4 (SME; FE; HSS; MED; CMED; MUS;'
        GEB2509 'MATH; ENER; CHEM; PHY; MSEN; DSBDT; STAT)'      <- 其实是 2508 的续行
    两个问题一起修：
      1) 把续行并回上一行，把上一行里多余的 'Y2-Y4 Students' 去掉；
      2) 续行原来的课程（2509）目标学生更正为同一串（其单元格实际是空的）。
    只对相邻两行都是 GE 系列、且下一行的文字以 ')' 结尾时生效；其它课程
    （MUS/AIE 等）的同类截断不在这里处理，避免把下一行自己的内容搬错。

    返回 (并回的行数, 补写的行数)。
    """
    merged = filled = 0
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        ca, cb = code_fmt(a.get("Course Code", "")), code_fmt(b.get("Course Code", ""))
        if ca.split(" ")[0] not in GE_SERIES or cb.split(" ")[0] not in GE_SERIES:
            continue
        if a.get("_page") != b.get("_page"):
            continue
        ta = str(a.get("Target Students") or "")
        tb = str(b.get("Target Students") or "").strip()
        if ta.count("(") <= ta.count(")") or not tb.endswith(")"):
            continue
        # 上一行形如 'Y2-Y4 Students Y2-Y4 (...' -> 丢掉前面那句多余的
        joined = re.sub(r"^(Y\d\s*[-–]\s*Y?\d\s*Students\s+)(?=Y\d)", "", ta).strip()
        full = (joined + " " + tb).strip()
        a["Target Students"] = full
        b["Target Students"] = full
        merged += 1
        filled += 1
    return merged, filled


def parse_exclusion_codes(raw: str) -> list[str]:
    out = []
    for tok in re.findall(r"\b([A-Z]{2,4})\s?(\d{4}[A-Z]?)\b", str(raw or "")):
        c = code_fmt(tok[0] + tok[1])
        if c not in out:
            out.append(c)
    return out


def parse_prereq_groups(raw: str) -> list[list[str]]:
    """'A or B; (C or D)' -> [['A','B'], ['C','D']]"""
    s = str(raw or "").strip()
    if not s:
        return []
    parts = re.split(r";|,(?![^(]*\))", s)
    groups = []
    for part in parts:
        codes = [code_fmt(a + b) for a, b in re.findall(r"\b([A-Z]{2,4})\s?(\d{4}[A-Z]?)\b", part)]
        codes = [c for c in codes if c]
        if codes:
            groups.append(codes)
    return groups


# --------------------------------------------------------------------- xlsx
def read_term(path: str):
    wb = load_workbook(path, data_only=True)
    sheets = wb.worksheets
    sessions_raw = list(sheets[0].iter_rows(min_row=2, values_only=True))
    tutorials_raw = list(sheets[1].iter_rows(min_row=2, values_only=True))
    enroll_raw = list(sheets[2].iter_rows(min_row=2, values_only=True))
    courses_raw = list(sheets[3].iter_rows(min_row=2, values_only=True))

    def parse_rows(rows, has_type):
        out = collections.defaultdict(list)
        for r in rows:
            if not r or not r[0]:
                continue
            code = code_fmt(r[0])
            out[code].append({
                "sessionName": str(r[3] or "").strip(),
                "classNbr": str(r[4] or "").strip(),
                "day": str(r[5] or "").strip(),
                "time": str(r[6] or "").strip(),
                "room": str(r[7] or "").strip(),
                "teacher": str(r[8] or "").strip(),
                "type": str(r[9] or "").strip() if has_type else "TUT",
                "status": str(r[10] if has_type else r[9] or "").strip(),
                "dateRange": str(r[11] if has_type else r[10] or "").strip(),
            })
        return out

    return {
        "sessions": parse_rows(sessions_raw, True),
        "tutorials": parse_rows(tutorials_raw, False),
        "enroll": {code_fmt(r[0]): r for r in enroll_raw if r and r[0]},
        "courses": {code_fmt(r[0]): r for r in courses_raw if r and r[0]},
    }


def build_sessions(rows, type_default, code):
    """Group xlsx rows of one course into session objects."""
    bysession = collections.defaultdict(list)
    for r in rows:
        bysession[r["sessionName"] or r["classNbr"]].append(r)
    out = []
    for name, items in bysession.items():
        sid = name.split("-")[0].strip() or name
        type_raw = (items[0]["type"] or type_default).upper()
        kind = "tutorial" if type_raw == "TUT" else "lecture"
        slots = {}
        time_tba = False
        for it in items:
            days = [DAY_TOKENS[it["day"][i:i + 2]] for i in range(0, len(it["day"]), 2) if it["day"][i:i + 2] in DAY_TOKENS]
            m = re.match(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", it["time"])
            if not days or not m:
                time_tba = True
                continue
            for d in days:
                key = (d, m.group(1), m.group(2))
                room = it["room"] or "TBA"
                slots.setdefault(key, [])
                if room not in slots[key]:
                    slots[key].append(room)
        slot_list = [{"day": k[0], "start": k[1], "end": k[2]} for k in sorted(slots)]
        # 有些课程按日期逐次排课（同一 session 每周时长不同），同一天的重叠时段只保留覆盖最大的一个
        kept = []
        for sl in sorted(slot_list, key=lambda x: (x["day"], to_min(x["start"]), -to_min(x["end"]))):
            if any(k["day"] == sl["day"] and to_min(sl["start"]) < to_min(k["end"]) and to_min(k["start"]) < to_min(sl["end"]) for k in kept):
                DROPPED_SLOTS.append(f"{code}/{sid} {sl['start']}-{sl['end']}")
                continue
            kept.append(sl)
        slot_list = kept
        rooms: list[str] = []
        for k in sorted(slots):
            for room in slots[k]:
                if room not in rooms:
                    rooms.append(room)
        out.append({
            "id": sid,
            "type": kind,
            "typeRaw": type_raw,
            "selectable": (type_raw == "TUT") or (type_raw in SELECTABLE_TYPES),
            "classNbr": items[0]["classNbr"],
            "teacher": items[0]["teacher"],
            "rooms": rooms or ["TBA"],
            "status": items[0]["status"],
            "dateRange": items[0]["dateRange"],
            "timeTBA": time_tba and not slot_list,
            "slots": slot_list,
        })
    out.sort(key=lambda s: (s["type"] != "lecture", s["id"]))
    return out


def read_supplement():
    """补充课时表：列顺序与 ALL_UG 不同（类型在第 3 列），Session/Tutorial 混在同一张表。"""
    path = os.path.join(OUT_DIR, SUPPLEMENT_FILE)
    if not os.path.exists(path):
        warn(f"supplement file not found: {SUPPLEMENT_FILE}")
        return {}
    wb = load_workbook(path, data_only=True)
    out = {}
    for sheet, tid in SUPPLEMENT_SHEETS.items():
        if sheet not in wb.sheetnames:
            warn(f"supplement sheet missing: {sheet}")
            continue
        sess, tuts = collections.defaultdict(list), collections.defaultdict(list)
        for r in wb[sheet].iter_rows(min_row=2, values_only=True):
            if not r or not r[0]:
                continue
            code = code_fmt(r[0])
            kind = str(r[2] or "").strip().lower()
            name = str(r[4] or "").strip()
            rec = {
                "sessionName": name,
                "classNbr": str(r[5] or "").strip(),
                "day": str(r[6] or "").strip(),
                "time": str(r[7] or "").strip(),
                "room": str(r[8] or "").strip(),
                "teacher": str(r[9] or "").strip(),
                "type": "TUT" if kind.startswith("tut") else (name.split("-")[-1].strip().upper() or "LEC"),
                "status": str(r[10] or "").strip(),
                "dateRange": str(r[11] or "").strip(),
            }
            (tuts if kind.startswith("tut") else sess)[code].append(rec)
        out[tid] = {"sessions": dict(sess), "tutorials": dict(tuts)}
    return out


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "catalog.json"))
    ap.add_argument("--report", default=os.path.join(ROOT, "data", "report.md"))
    args = ap.parse_args()

    pdf1 = json.load(open(os.path.join(ROOT, "build", "_pdf_p1.json"), encoding="utf-8"))["rows"]
    pdf2 = json.load(open(os.path.join(ROOT, "build", "_pdf_p2.json"), encoding="utf-8"))["rows"]
    ge_merged, ge_filled = 0, 0
    for _rows in (pdf1, pdf2):
        _m, _f = merge_ge_target_spill(_rows)
        ge_merged += _m
        ge_filled += _f
    notes.append(f"GE Target Students cells that spilled onto the next row: rejoined {ge_merged}, row re-labelled {ge_filled}")

    def index(rows):
        out = {}
        for r in rows:
            code = code_fmt(r["Course Code"])
            if code and code not in out:
                out[code] = r
        return out

    P1, P2 = index(pdf1), index(pdf2)
    DELETE_CODES = read_delete_codes()
    # 按学院-专业筛选用的官方专业表（31 份培养方案 PDF 的专业名 + 对应课程标签）
    MAJORS = json.load(open(os.path.join(ROOT, "build", "major_map.json"), encoding="utf-8"))["majors"]
    notes.append(f"major list: {len(MAJORS)} programmes from build/major_map.json")
    notes.append(f"PDF1 rows={len(pdf1)} distinct codes={len(P1)}; PDF2 rows={len(pdf2)} distinct codes={len(P2)}")

    terms_data = {}
    xlsx_catalog: dict[str, dict] = {}
    for tid, fname, year, term, label in XLSX_TERMS:
        path = os.path.join(OUT_DIR, fname)
        data = read_term(path)
        terms_data[tid] = data
        for code, row in data["courses"].items():
            xlsx_catalog.setdefault(code, row)
        for code, row in data["enroll"].items():
            xlsx_catalog.setdefault(code, row)
        notes.append(f"{tid}: session courses={len(data['sessions'])} tutorial courses={len(data['tutorials'])} catalog={len(data['courses'])}")

    # 补充数据并入（只针对原本没有排课的课程）
    supplement = read_supplement()
    recovered = set()
    for tid, sdata in supplement.items():
        for code, rows in sdata["sessions"].items():
            terms_data[tid]["sessions"].setdefault(code, []).extend(rows)
            recovered.add(code)
        for code, rows in sdata["tutorials"].items():
            terms_data[tid]["tutorials"].setdefault(code, []).extend(rows)
            recovered.add(code)
    notes.append(f"supplement: {len(recovered)} courses merged from {SUPPLEMENT_FILE} (columns: type at index 2)")

    universe = sorted(c for c in (set(P1) | set(P2) | set(xlsx_catalog))
                      if c.split(" ")[0] not in PLACEHOLDER_PREFIXES and c not in DELETE_CODES)
    placeholders = sorted(c for c in set(xlsx_catalog) if c.split(" ")[0] in PLACEHOLDER_PREFIXES)
    notes.append(f"excluded placeholder records (Dummy/Exemption): {len(placeholders)} -> {', '.join(placeholders[:6])} …")
    notes.append(f"deleted no-data courses from {NO_DATA_FILE}: {len(DELETE_CODES)} codes "
                 f"({len(DELETE_CODES & (set(xlsx_catalog) | set(P1) | set(P2)))} of them existed in the catalogue)")
    notes.append(f"course universe = {len(universe)} (PDF1 {len(P1)} + PDF2 {len(P2)} + xlsx-only {len(set(xlsx_catalog) - set(P1) - set(P2))})")

    all_tags = collections.Counter()
    unparsed_targets = collections.Counter()
    courses = []
    for code in universe:
        r1, r2 = P1.get(code), P2.get(code)
        pdf_row = r2 or r1
        name = ""
        for r in (r2, r1):
            if r and r.get("Course Title", "").strip():
                name = dedupe_words(r["Course Title"])
                break
        xr_course = terms_data["2025-26-T1"]["courses"].get(code) or terms_data["2025-26-T2"]["courses"].get(code) or terms_data["2026-27-T1"]["courses"].get(code)
        xr_enroll = terms_data["2025-26-T1"]["enroll"].get(code) or terms_data["2025-26-T2"]["enroll"].get(code) or terms_data["2026-27-T1"]["enroll"].get(code)
        if not name and xr_course:
            name = dedupe_words(str(xr_course[1] or ""))
        title = f"{code} - {name}" if name and not name.startswith(code) else (name or code)

        dept = clean_department((r2 or {}).get("Department", "")) or clean_department((r1 or {}).get("Department", ""))
        group = None
        if xr_course:
            group = ACADEMIC_GROUP_MAP.get(str(xr_course[4] or "").strip().lower())
        college = dept or group
        if not college:
            college = "HSS"
            warn(f"{code}: no department found, defaulted to HSS")

        # target students: the NEWEST PDF that states a Target Students string is
        # authoritative for the year range, the target-student colleges and the
        # major tokens (the two offering tables disagree for 103 courses, e.g.
        # BIO 3901 is "MED (exclude CMED)" in P1 but "BIFC; BIOL; BME; PHAM" in P2).
        # GE stays a union: if either table calls the course open to all UG it is GE.
        all_targets = [r.get("Target Students", "") for r in (r1, r2) if r]
        is_ge = any("all ug student" in str(t).lower() for t in all_targets)
        # 该前缀本身就是通识系列（PED / GEA-GED / CEC），无论有无 PDF 数据
        if code.split(" ")[0] in GE_PREFIXES:
            is_ge = True
        target_text = ""
        for r in (r2, r1):
            if r and str(r.get("Target Students", "")).strip():
                target_text = str(r["Target Students"])
                break
        year_min = year_max = None
        colleges_restriction: list[str] = []
        tags: list[str] = []
        major_only = False
        if target_text:
            ge_i, ymin, ymax, cols, tgs, bad = parse_target(target_text)
            if ymin and ymax and ymax <= 4:
                year_min, year_max = ymin, ymax
            colleges_restriction = list(cols)
            tags = list(tgs)
            # 目标学生点名了专业/方向、却没有点名学院 -> 选课资格按专业判断。
            # 这类课不再默认限本院，改为可自由选课并在界面上弹提示
            # （parse_target 会把 "Y3-Y4 BME" 里的 BME 当作 3-4 年级线索，真正的
            #   年级限制由 yearMin/yearMax 表达，两者互不冲突）
            major_only = bool(tgs and not cols)
            if bad:
                unparsed_targets[dedupe_words(target_text)] += 1

        in_xlsx = code in xlsx_catalog
        # 学院限制只来自 Target Students 原文；不再回退到开设学院
        # （用户确认：仅点名专业的课可自由选课但弹提示，其余开放）
        dept_tags = [college] if college else []
        student_tags = [c for c in colleges_restriction if c in COLLEGE_NAMES]

        others = [t for t in tags if t not in dept_tags and t not in student_tags]

        others = [t for t in tags if t not in dept_tags and t not in student_tags]
        # the same code can legitimately hold both roles (ACT 2121 is an SME course
        # restricted to SME students) -- de-duplicate across the role groups
        tags = list(dict.fromkeys(dept_tags + (["GE"] if is_ge else []) + student_tags + others))
        colleges_restriction = student_tags
        for tg in tags:
            all_tags[tg] += 1

        units = language = None
        if in_xlsx:
            src = xr_enroll if (xr_enroll and xr_enroll[3] is not None) else xr_course
            try:
                units = float(src[3]) if src and src[3] is not None and str(src[3]).strip() != "" else None
            except (TypeError, ValueError):
                units = None
            attrs = str((xr_course[5] if xr_course else "") or "")
            m = re.search(r"Medium of Instruction:\s*([^;]+)", attrs)
            language = (m.group(1).strip() if m else "English")

        # prerequisite / exclusion: xlsx columns first, then the raw requirement text,
        # then the PDF row as the last fallback
        prereq_raw = excl_raw = ""
        if in_xlsx and xr_enroll:
            prereq_raw = str(xr_enroll[4] or "").strip()
            excl_raw = str(xr_enroll[5] or "").strip()
            if not prereq_raw or not excl_raw:
                raw_er = str(xr_enroll[6] or "").strip()
                if raw_er:
                    if not excl_raw:
                        m = re.search(r"exclusion\s*:?\s*(.+)$", raw_er, re.I) or \
                            re.search(r"(?:have\s+)?taken\s+(.+?)\s+cannot take", raw_er, re.I)
                        if m:
                            excl_raw = m.group(1).strip()
                    if not prereq_raw:
                        m = re.search(r"(?:p-req|prerequisite|pre-requisite)\s*:?\s*(.+)$", raw_er, re.I) or \
                            re.search(r"must\s+(?:take|complete)\s+(.+?)\s+first", raw_er, re.I)
                        if m:
                            prereq_raw = m.group(1).strip()
        if not prereq_raw:
            prereq_raw = dedupe_words((pdf_row or {}).get("Prerequisite", ""))
        if not excl_raw:
            excl_raw = dedupe_words((pdf_row or {}).get("Exclusion", ""))

        # ---- user-confirmed course-level overrides ------------------------
        prefix_now = code.split(" ")[0]
        if prefix_now in CHINESE_LANGUAGE_PREFIXES:
            # CHI / CEC 系列为中文授课（xlsx 里常写成 English）
            language = "Chinese"
        if prefix_now == PED_YEAR_RESTRICTED_PREFIX:
            # 体育课一律只限 Y1
            year_min, year_max = PED_YEAR_MIN, PED_YEAR_MAX
        if code in PED_PREREQ_CLEAR:
            # 体育课不应有 ENG 先修，且这些课号并不在目录中
            prereq_raw = ""

        y1_tags: list[str] = []
        target_tag_text: list[str] = []
        if prefix_now in GE_SERIES:
            # 通识系列：PDF 里有的写 All UG Students、有的留空，用户确认统一 Y2-Y4；
            # 目标学生里点名的专业（如 GEB 2508/2509）作为提示保留。
            # 注意 tags 里含开设学院（HSS）与 GE 标记，都不是"目标学生"，展示时要排掉。
            year_min, year_max = GE_SERIES_YEAR_MIN, GE_SERIES_YEAR_MAX
            named = [t for t in tags if t not in (college, "GE")]
            target_text = (f"Y{GE_SERIES_YEAR_MIN}-Y{GE_SERIES_YEAR_MAX} "
                           + (f"({' ; '.join(named)})" if named else "Students"))
            if not prereq_raw:
                prereq_raw = " or ".join(GE_SERIES_COREQ)
        elif prefix_now in ("GFH", "GFN"):
            # 这两门本身是 Y1 桥梁课：点名了的专业 Y1 即可选，其余学生 Y2 以后
            for tg in tags:
                if tg in GE_Y1_PROGRAMME_TAGS and tg not in y1_tags:
                    y1_tags.append(tg)
            named = [t for t in tags if t not in (college, "GE")]
            if y1_tags:
                # yearMin 保持 Y2：Y1 的例外由 y1Tags 在界面上单独判定，
                # 否则会把这门课对全体一年级开放（而不是只对点名的专业）
                year_min, year_max = GE_SERIES_YEAR_MIN, GE_SERIES_YEAR_MAX
                target_text = f"Y1 ({'; '.join(y1_tags)}); Y{GE_SERIES_YEAR_MIN}-Y{GE_SERIES_YEAR_MAX} Students"
            else:
                year_min, year_max = GE_SERIES_YEAR_MIN, GE_SERIES_YEAR_MAX
                target_text = f"Y{GE_SERIES_YEAR_MIN}-Y{GE_SERIES_YEAR_MAX} Students"
            if not prereq_raw:
                prereq_raw = " or ".join(GE_SERIES_COREQ) if prefix_now in GE_SERIES else ""

        # 目标学生点名了专业/方向（不含开设学院与 GE 标记）-> 选课时弹提示
        target_named = [t for t in tags if t not in (college, "GE")]
        major_only = bool(target_named and not colleges_restriction)
        if target_named:
            target_tag_text = [GE_TAG_LABELS.get(t, t) for t in target_named]

        entry = {
            "code": code,
            "name": title,
            # offering department -- NOT a target-student restriction
            "college": college,
            "tags": tags,
            # every tag in "tags" is either the offering college (deptTags),
            # a target-student college limit (studentTags), or a special
            # type/major label
            "deptTags": dept_tags,
            "studentTags": student_tags,
            "isGE": is_ge,
            "majorOnly": major_only,
            # GFH/GFN: which programmes may take the course in year 1
            "y1Tags": y1_tags,
            # 目标学生里点名的专业/方向（界面提示用），如 GEB 2508/2509
            "targetTagText": target_tag_text,
            # official programme names (from build/major_map.json) whose tag this
            # course carries -- drives the college/programme filter
            "majors": [mj["zh"] for mj in MAJORS if mj["tag"] in tags],

            "units": units if in_xlsx else None,
            "language": language if in_xlsx else None,
            # Target Students 原文对 PDF-only 课程同样重要：它是"仅限某专业"提示
            # 与界面展示的唯一依据，因此只要有 PDF 数据就保留
            "targetStudents": dedupe_words(target_text) if target_text else None,
            "attrSource": "xlsx" if in_xlsx else "none",
            "yearMin": year_min,
            "yearMax": year_max,
            "collegeRestriction": colleges_restriction,
            "prereqRaw": prereq_raw,
            "exclusionRaw": excl_raw,
            "prereqGroups": parse_prereq_groups(prereq_raw),
            "exclusionCodes": parse_exclusion_codes(excl_raw),
            "terms": {},
        }
        for tid, data in terms_data.items():
            sess = build_sessions(data["sessions"].get(code, []), "LEC", code)
            tuts = build_sessions(data["tutorials"].get(code, []), "TUT", code)
            if not sess and not tuts:
                continue
            entry["terms"][tid] = {
                "hasSessions": bool(sess),
                "requireTutorial": bool(tuts),
                "sessions": sess + tuts,
            }
        courses.append(entry)

    # ------------------------------------------------------------------ derived rules
    # 先修限制传递：一门课的【每一组】先修若都是学院限定课，则该课也受同样的学院限定
    # （无法选上先修课的学生就不可能满足先修）。取各组的并集，迭代到不动点，因为
    # 上一轮新产生的限定会解锁下一轮。通识课不受学院限制，直接跳过。
    derived_restriction: dict[str, list[str]] = {}
    by_code = {c["code"]: c for c in courses}
    limited_codes = {c["code"] for c in courses if c["collegeRestriction"]}
    rounds = 0
    changed = True
    while changed and rounds < 20:
        rounds += 1
        changed = False
        for c in courses:
            if c["isGE"] or c["collegeRestriction"]:
                continue
            groups = c["prereqGroups"]
            if not groups:
                continue
            inherited: list[str] = []
            for group in groups:
                # 只要有任意一个先修课不是学院限定（或不在目录里），这一组就不成立
                if not group or any(x not in limited_codes for x in group):
                    inherited = []
                    break
                for x in group:
                    for col in by_code[x]["collegeRestriction"]:
                        if col not in inherited:
                            inherited.append(col)
            if inherited:
                c["collegeRestriction"] = inherited
                c["studentTags"] = [t for t in inherited if t in COLLEGE_NAMES]
                tag_pool = c["deptTags"] + (["GE"] if c["isGE"] else []) + c["studentTags"] + \
                    [t for t in c["tags"] if t not in c["deptTags"] and t not in c["studentTags"]]
                c["tags"] = list(dict.fromkeys(tag_pool))
                derived_restriction[c["code"]] = inherited
                limited_codes.add(c["code"])
                changed = True

    # term metadata
    terms_meta = []
    for tid, fname, year, term, label in XLSX_TERMS:
        d = terms_data[tid]
        def count_sessions(mapping):
            return sum(1 for c in mapping if any(True for e in courses if e["code"] == c and tid in e["terms"]))
        terms_meta.append({
            "id": tid, "year": year, "term": term, "label": label, "selectable": True,
            "source": fname,
            "sessionCourses": len(d["sessions"]),
            "tutorialCourses": len(d["tutorials"]),
            "coursesWithData": sum(1 for e in courses if tid in e["terms"]),
        })
    tid, year, term, label, lock = LOCKED_TERM
    terms_meta.append({"id": tid, "year": year, "term": term, "label": label, "selectable": False,
                       "lockReason": lock, "sessionCourses": 0, "tutorialCourses": 0, "coursesWithData": 0})

    tag_groups = {
        "specialStudentTypes": [t for t in STUDENT_TYPES if all_tags.get(t)],
        "specialMajors": sorted([t for t in all_tags
                                 if t not in COLLEGE_NAMES and t != "GE" and t not in STUDENT_TYPES]),
    }
    # 时长白名单 = 数据里实际出现的时长（用户确认），再并入规范值
    durs = set()
    weekend_slots = 0
    display_only = 0
    for e in courses:
        for tv in e["terms"].values():
            for s in tv["sessions"]:
                if not s.get("selectable", True):
                    display_only += 1
                for sl in s["slots"]:
                    durs.add(to_min(sl["end"]) - to_min(sl["start"]))
                    if sl["day"] >= 6:
                        weekend_slots += 1
    allowed_durations = sorted(durs | {50, 80})
    notes.append(f"durations present in data: {sorted(durs)}")
    notes.append(f"selectable=false sessions (IDV/RSC/CLN/EXM/THE): {display_only}")
    notes.append(f"weekend (Sat/Sun) weekly slots: {weekend_slots}")
    if DROPPED_SLOTS:
        notes.append(f"per-date overlapping slots collapsed to the widest one: {len(DROPPED_SLOTS)} -> {', '.join(DROPPED_SLOTS[:6])}")
    max_end = max((to_min(sl["end"]) for e in courses for tv in e["terms"].values()
                   for s in tv["sessions"] for sl in s["slots"]), default=20 * 60 + 50)

    catalog = {
        "meta": {
            "version": "2.1.0",
            "generated": date.today().isoformat(),
            "sources": {
                "pdf": ["Formal Course Registration_Course Offering Information_AY2025-26 Term 2 (Updated on Dec. 19).pdf",
                        "AddDrop_Course Offering Information_AY2026-27 Term 1( Updated on September 4).pdf"],
                "xlsx": [f for _, f, _, _, _ in XLSX_TERMS],
            },
            "rules": {"dayStart": "08:30",
                      "dayEnd": "%02d:%02d" % (max_end // 60, max_end % 60),
                      "closedWindow": ["12:30", "13:30"],
                      "allowedDurations": allowed_durations, "minGapMinutes": 40,
                      "weekdays": [1, 2, 3, 4, 5], "weekendDays": [6, 7]},
            "terms": terms_meta,
            "colleges": {k: COLLEGE_NAMES[k] for k in COLLEGE_ORDER},
            "tagGroups": tag_groups,
            # 学院-专业两级筛选的数据源，与课程上的 "majors" 同名对应
            "majors": [{k: mj[k] for k in ("college", "zh", "en", "tag")} for mj in MAJORS],
        },
        "courses": courses,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1)

    with_sessions = sum(1 for c in courses if c["terms"])
    report = [
        "# 课程目录解析报告 / Catalog build report", "",
        f"- 生成时间: {catalog['meta']['generated']}",
        f"- 课程总数: **{len(courses)}**",
        f"- 有课时数据的课程: {with_sessions} 门（按学期见下表）",
        f"- 三个 xlsx 提及（含 Units/Language/Target Students）的课程: {sum(1 for c in courses if c['attrSource'] == 'xlsx')}",
        f"- 通识课（Target Students = All UG Students，或前缀属于 {'/'.join(sorted(GE_PREFIXES))}）: {sum(1 for c in courses if c['isGE'])}",
        f"- {'/'.join(sorted(GE_SERIES))} 系列: {sum(1 for c in courses if c['code'].split(' ')[0] in GE_SERIES)} 门"
        f"（统一 Y{GE_SERIES_YEAR_MIN}-Y{GE_SERIES_YEAR_MAX} + 共修 {' 或 '.join(GE_SERIES_COREQ)}）；"
        f"GFH/GFN 的 Y1 桥梁专业: {'/'.join(GE_Y1_PROGRAMME_TAGS)}",
        f"- 学院限制来自 Target Students 原文的课程: {sum(1 for c in courses if c['collegeRestriction'])}"
        f"（开设学院与限制学院不同的课程: {sum(1 for c in courses if c['collegeRestriction'] and c['college'] not in c['collegeRestriction'])}）",
        f"- 仅点名专业/方向、可自由选课但需提示的课程（majorOnly）: {sum(1 for c in courses if c.get('majorOnly'))}",
        f"- 先修限制传递（先修全是学院限定课 -> 本课也受限）新增: {len(derived_restriction)} 门"
        f"（迭代 {rounds} 轮）",
        f"- 课程级覆盖: PED 全部限 Y{PED_YEAR_MIN}-Y{PED_YEAR_MAX}、"
        f"{'/'.join(sorted(CHINESE_LANGUAGE_PREFIXES))} 系列改中文授课、"
        f"{'/'.join(sorted(PED_PREREQ_CLEAR))} 清空先修",

        "",
        "## 各学期",
        "",
        "| 学期 | 可选 | xlsx 课时课程 | xlsx 辅导课课程 | 目录中有课时的课程 |",
        "|---|---|---|---|---|",
    ]
    for tm in terms_meta:
        report.append(f"| {tm['id']} | {'是' if tm['selectable'] else '否'} | {tm['sessionCourses']} | {tm['tutorialCourses']} | {tm['coursesWithData']} |")
    report += ["", "## 标签词表", "",
               f"- 特殊学生类型: {', '.join(tag_groups['specialStudentTypes'])}",
               f"- 特殊专业/方向（{len(tag_groups['specialMajors'])} 个）: {', '.join(tag_groups['specialMajors'])}",
               "", "## 数据质量", ""]
    report += [f"- {n}" for n in notes]
    if unparsed_targets:
        report.append(f"- 未能解析的 Target Students 字符串 {len(unparsed_targets)} 种：")
        for s, n in unparsed_targets.most_common(15):
            report.append(f"    - ×{n} `{s}`")
    if warnings:
        report.append("")
        report.append(f"## 警告 ({len(warnings)})")
        report += [f"- {w}" for w in warnings[:60]]
    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    print(json.dumps({
        "courses": len(courses),
        "withSessions": with_sessions,
        "attrFromXlsx": sum(1 for c in courses if c["attrSource"] == "xlsx"),
        "GE": sum(1 for c in courses if c["isGE"]),
        "tags": len(tag_groups["specialMajors"]) + len(tag_groups["specialStudentTypes"]),
        "unparsedTargetStrings": len(unparsed_targets),
        "warnings": len(warnings),
        "perTerm": {tm["id"]: tm["coursesWithData"] for tm in terms_meta},
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
