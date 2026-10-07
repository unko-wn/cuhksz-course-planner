"""After the supplement scrape, classify every no-session course and build the two tables.

Outputs
  output/SUPPLEMENT_sessions_tutorials.xlsx  - newly recovered session/tutorial data
  output/NO_DATA_courses.xlsx                - courses that genuinely have no data, with reasons
  output/csv/*.csv                           - the same data as CSV (planner-friendly)
"""
import collections
import csv
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
CSVDIR = os.path.join(OUT, "csv")
TERM_LABEL = {"2510": "2025-26 Term 1", "2520": "2025-26 Term 2", "2610": "2026-27 Term 1"}
TERMS = set(TERM_LABEL.values())


def load_dir(d):
    out = {}
    for path in glob.glob(os.path.join(HERE, d, "*.json")):
        blob = json.load(open(path, encoding="utf-8"))
        for c in blob.get("courses", []):
            out[f"{blob['subject']} {c.get('catalog_nbr','')}"] = c
    return out


orig = load_dir("data")
supp = load_dir("data_supplement")
merged = dict(orig)
merged.update(supp)          # supplement wins for overlapping codes
print(f"original records: {len(orig)}, supplement records: {len(supp)}, merged: {len(merged)}")

cat = json.load(open(os.path.join(HERE, "_catalog.json"), encoding="utf-8"))
by_code = {c["code"]: c for c in cat["courses"]}

rows = list(csv.DictReader(open(os.path.join(HERE, "_no_session.csv"), encoding="utf-8-sig")))
print(f"no-session list: {len(rows)}")

# ---------------------------------------------------------------- classify
rec = []          # recovered -> supplement table
nod = []          # no data   -> no-data table
for r in rows:
    code = r["Course Code"].strip()
    c = merged.get(code)
    info = {
        "code": code,
        "title": r["Course Title"],
        "college": r.get("College", ""),
        "ge": r.get("GE", ""),
        "units": r.get("Units", ""),
        "tags": r.get("Tags", ""),
    }
    if c is None:
        info["reason"] = "NOT_IN_CATALOG"
        info["note"] = "当前 SIS 课程目录中不存在该课号（已实际尝试抓取）"
        info["terms"] = ""
        nod.append(info)
        continue
    secs = [s for s in (c.get("sections") or []) if s.get("term") in TERMS]
    if secs:
        info["career"] = c.get("career", "")
        info["sections"] = secs
        info["header"] = c.get("header") or r["Course Title"]
        rec.append(info)
    elif c.get("has_schedule") is False:
        info["reason"] = "NOT_SCHEDULED"
        info["note"] = "SIS 课程页显示 *** This course has not been scheduled. ***（从未排课）"
        info["terms"] = ""
        nod.append(info)
    else:
        info["reason"] = "NOT_OFFERED_IN_TERMS"
        to = list((c.get("terms_offered") or {}).values())
        info["note"] = ("该课有排课面板，但三个目标学期均未开设")
        info["terms"] = " / ".join(to)
        nod.append(info)

print(f"\nrecovered (now have sessions): {len(rec)}")
print(f"genuinely no data           : {len(nod)}")
print("  by reason:", dict(collections.Counter(x['reason'] for x in nod)))

json.dump({"recovered": [x['code'] for x in rec],
           "no_data": {x['code']: x['reason'] for x in nod}},
          open(os.path.join(HERE, "_nsc_final.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- outputs
os.makedirs(CSVDIR, exist_ok=True)
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HDR_FILL = PatternFill("solid", fgColor="1F4E79")
HDR_FONT = Font(bold=True, color="FFFFFF")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BAND = PatternFill("solid", fgColor="F2F7FB")

SUPP_COLS = [("课程代码", 11), ("课程名称", 46), ("类型", 9), ("Session序号", 10),
             ("Session编号", 13), ("Class Nbr", 10), ("周几", 8), ("时间段", 13),
             ("地点 (Room)", 26), ("老师 (Instructor)", 30), ("开课状态", 10),
             ("上课日期", 24), ("Career", 14)]
NOD_COLS = [("课程代码", 11), ("课程名称", 46), ("College", 8), ("GE", 5), ("Units", 7),
            ("原因", 22), ("说明", 54), ("历史开课学期", 60), ("Tags", 22)]


def write_sheet(ws, cols, data):
    for i, (name, w) in enumerate(cols, 1):
        cell = ws.cell(row=1, column=i, value=name)
        cell.fill, cell.font, cell.border = HDR_FILL, HDR_FONT, BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 28
    for r, row in enumerate(data, 2):
        for i, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=i, value=v)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=cols[i - 1][1] >= 40)
            if r % 2 == 0:
                cell.fill = BAND
    ws.freeze_panes = "A2"
    if data:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(data) + 1}"


# ---- supplement workbook ----
wb = Workbook()
wb.remove(wb.active)
csv_rows = collections.defaultdict(list)
for tcode, tlabel in TERM_LABEL.items():
    data = []
    for x in sorted(rec, key=lambda z: z["code"]):
        for s in x["sections"]:
            if s["term"] != tlabel:
                continue
            typ = "Tutorial" if str(s["session_code"]).endswith("TUT") else "Session"
            row = [x["code"], x["header"], typ, s.get("session_no"), s.get("session_code"),
                   s.get("class_nbr"), s.get("days"), f"{s.get('start')}-{s.get('end')}",
                   s.get("room"), s.get("instructor"), s.get("status"), s.get("dates"),
                   x.get("career", "")]
            data.append(row)
            csv_rows[tlabel].append(row)
    write_sheet(wb.create_sheet(tlabel.replace(" ", "_")), SUPP_COLS, data)
    print(f"  {tlabel}: {len(data)} rows")

ws = wb.create_sheet("说明")
info = [("来源", "对 no_session_courses.csv 中「未爬取到」的课程重新抓取的结果"),
        ("恢复课程数", len(rec)),
        ("说明", "仅包含本次新抓到的课程；已排除三个目标学期均未开设的课程"),
        ("学期", " / ".join(TERM_LABEL.values()))]
for i, (k, v) in enumerate(info, 1):
    ws.cell(row=i, column=1, value=k).font = Font(bold=True)
    ws.cell(row=i, column=2, value=v)
ws.column_dimensions["A"].width = 18
ws.column_dimensions["B"].width = 90
os.makedirs(OUT, exist_ok=True)
p1 = os.path.join(OUT, "SUPPLEMENT_sessions_tutorials.xlsx")
wb.save(p1)

# ---- no-data workbook ----
wb2 = Workbook()
wb2.remove(wb2.active)
order = {"NOT_IN_CATALOG": 0, "NOT_SCHEDULED": 1, "NOT_OFFERED_IN_TERMS": 2}
nod_sorted = sorted(nod, key=lambda x: (order.get(x["reason"], 9), x["code"]))
rows_out = [[x["code"], x["title"], x["college"], x["ge"], x["units"], x["reason"],
             x["note"], x["terms"], x["tags"]] for x in nod_sorted]
write_sheet(wb2.create_sheet("无数据课程"), NOD_COLS, rows_out)
ws2 = wb2.create_sheet("说明")
info2 = [("来源", "no_session_courses.csv 中经核实「确实没有数据」的课程"),
         ("总数", len(nod_sorted)),
         ("NOT_IN_CATALOG",
          "该课号在当前 SIS 课程目录中不存在（已实际尝试抓取）。可能已停开或并入其他课号"),
         ("NOT_SCHEDULED",
          "SIS 课程页显示 *** This course has not been scheduled. ***，即从未排课"),
         ("NOT_OFFERED_IN_TERMS",
          "该课有排课面板，但 2025-26 T1 / T2 / 2026-27 T1 均未开设；「历史开课学期」列出它实际开过的学期"),
         ("结论", "以上课程在三个目标学期内确实没有任何课时数据，可视为未开设/已取消")]
for i, (k, v) in enumerate(info2, 1):
    ws2.cell(row=i, column=1, value=k).font = Font(bold=True)
    ws2.cell(row=i, column=2, value=v).alignment = Alignment(wrap_text=True, vertical="top")
ws2.column_dimensions["A"].width = 24
ws2.column_dimensions["B"].width = 100
p2 = os.path.join(OUT, "NO_DATA_courses.xlsx")
wb2.save(p2)

# ---- CSVs ----
for tlabel, data in csv_rows.items():
    fn = os.path.join(CSVDIR, f"supplement_{tlabel.replace(' ', '_')}.csv")
    with open(fn, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([c[0] for c in SUPP_COLS])
        w.writerows(data)
fn = os.path.join(CSVDIR, "no_data_courses_classified.csv")
with open(fn, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow([c[0] for c in NOD_COLS])
    w.writerows(rows_out)

print(f"\nwrote {p1}\nwrote {p2}\nwrote CSVs -> {CSVDIR}")
