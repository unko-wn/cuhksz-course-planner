"""Cross-validate requests-scraped data against browser-rendered ground truth.

_term2510_CSC1001_viewall.html was produced by the real browser (UI clicks).
Compare its 19 sections with what our HTTP pipeline recorded for CSC 1001 / 2510.
"""
import json, re, sys
from bs4 import BeautifulSoup

html = open("_term2510_CSC1001_viewall.html", encoding="utf-8").read()
soup = BeautifulSoup(html, "lxml")

truth = []
sec_nodes = soup.find_all(id=re.compile(r"^win0divCLASS_SECTION\$\d+$"))
cont_nodes = soup.find_all(id=re.compile(r"^win0divCLASS_MTGPAT\$\d+$"))
for k, sdiv in enumerate(sec_nodes):
    a = sdiv.find("a")
    code = a.get_text(" ", strip=True)
    tr = sdiv.find_parent("tr")
    sn = tr.find(id=re.compile(r"^CLASS_SESSION\$\d+$")).get_text(strip=True)
    for d in cont_nodes[k].find_all(id=re.compile(r"^MTGPAT_DAYS\$\d+$")):
        j = d["id"].rsplit("$", 1)[1]
        g = lambda f: (cont_nodes[k].find(id=f"MTGPAT_{f}${j}") or
                       soup.new_tag("x")).get_text(" ", strip=True)
        truth.append((code, sn, g("DAYS"), g("START"), g("END"), g("ROOM"), g("INSTR")))

print(f"browser ground truth rows: {len(truth)}")

d = json.load(open("data/CSC.json", encoding="utf-8"))
c = next(x for x in d["courses"] if x["course"] == "CSC 1001")
ours = [(f"{s['session_code']} ({s['class_nbr']})", s["session_no"], s["days"],
         s["start"], s["end"], s["room"], s["instructor"])
        for s in c["sections"] if s["term"] == "2025-26 Term 1"]
print(f"our pipeline rows        : {len(ours)}")

def norm(t):
    code, sn, days, st, en, room, instr = t
    return (code, sn, days, st.replace(":", "").lstrip("0") if st else st,
            en, room, instr)

ok = mismatch = 0
for i, (t, o) in enumerate(zip(truth, ours)):
    # browser times are 24h already; normalise both to HH:MM
    def hhmm(x):
        x = x.strip()
        m = re.match(r"^(\d{1,2}):(\d{2})\s*([AP]M)?$", x, re.I)
        if not m:
            return x
        h, mi, ap = int(m.group(1)), m.group(2), (m.group(3) or "").upper()
        if ap == "PM" and h != 12:
            h += 12
        if ap == "AM" and h == 12:
            h = 0
        return f"{h:02d}:{mi}"
    a = (t[0], t[1], t[2], hhmm(t[3]), hhmm(t[4]), t[5], t[6])
    b = (o[0], o[1], o[2], hhmm(o[3]), hhmm(o[4]), o[5], o[6])
    if a == b:
        ok += 1
    else:
        mismatch += 1
        if mismatch <= 5:
            print("  MISMATCH")
            print("    truth:", a)
            print("    ours :", b)

print(f"\nmatched={ok}  mismatched={mismatch}")
print("VERDICT:", "IDENTICAL" if mismatch == 0 and len(truth) == len(ours)
      else "DIFFERENCES FOUND")
