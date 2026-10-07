"""Classify the no-session courses: genuinely unscheduled vs. never scraped."""
import collections
import csv
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TERMS = {"2510", "2520", "2610"}

# ---------- load our raw scrape ----------
ours = {}
for path in glob.glob(os.path.join(HERE, "data", "*.json")):
    blob = json.load(open(path, encoding="utf-8"))
    subj = blob["subject"]
    for c in blob.get("courses", []):
        key = f"{subj} {c.get('catalog_nbr','')}"
        ours[key] = c
print(f"our scrape: {len(ours)} course records")

# ---------- load the user's catalog ----------
cat = json.load(open(os.path.join(HERE, "_catalog.json"), encoding="utf-8"))
by_code = {c["code"]: c for c in cat["courses"]}

# ---------- load the CSV ----------
rows = list(csv.DictReader(open(os.path.join(HERE, "_no_session.csv"), encoding="utf-8-sig")))
print(f"no-session CSV rows: {len(rows)}")

cats = collections.Counter()
detail = collections.defaultdict(list)
attr_by_cat = collections.defaultdict(collections.Counter)

for r in rows:
    code = r["Course Code"].strip()
    subj, _, nbr = code.partition(" ")
    rec = ours.get(code)
    cc = by_code.get(code, {})
    attr = cc.get("attrSource", "?")

    if rec is None:
        if subj not in {k.split(" ")[0] for k in ours}:
            k = "A_NOT_SCRAPED_SUBJECT"
        else:
            k = "B_NOT_IN_SUBJECT_LIST"
    elif rec.get("error"):
        k = "C_SCRAPE_ERROR"
    elif rec.get("has_schedule") is False:
        k = "D_NO_SCHEDULE_PANEL"
    elif not (rec.get("sections") or []):
        k = "E_NO_SECTION_IN_3_TERMS"
    else:
        k = "F_HAS_SECTIONS_CONTRADICTION"

    cats[k] += 1
    attr_by_cat[k][attr] += 1
    detail[k].append((code, r["Course Title"][:52], r.get("College", ""), attr))

print("\n=== classification ===")
for k in sorted(cats):
    print(f"  {k:32s} {cats[k]:4d}   attrSource={dict(attr_by_cat[k])}")

print("\n=== subjects in each category ===")
for k in sorted(detail):
    subs = collections.Counter(c.split()[0] for c, _, _, _ in detail[k])
    print(f"  {k:32s} {dict(sorted(subs.items(), key=lambda x:-x[1]))}")

print("\n=== samples ===")
for k in sorted(detail):
    print(f"\n--- {k} (first 12) ---")
    for code, title, college, attr in detail[k][:12]:
        print(f"   {code:12s} {college:5s} attr={attr:5s} {title}")

json.dump({k: [d[0] for d in v] for k, v in detail.items()},
          open(os.path.join(HERE, "_nsc_classes.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
