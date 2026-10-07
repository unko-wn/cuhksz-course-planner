"""Verify classification semantics against catalog.json and our raw data."""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
cat = json.load(open(os.path.join(HERE, "_catalog.json"), encoding="utf-8"))

print("=== attrSource distribution in catalog.json ===")
print(dict(collections.Counter(c.get("attrSource") for c in cat["courses"])))

print("\n=== terms key distribution (courses with no sessions) ===")
terms = [t["id"] for t in cat["meta"]["terms"] if t["selectable"]]
print("selectable terms:", terms)


def has_sessions(c):
    return any((c.get("terms", {}).get(t, {}) or {}).get("sessions") for t in terms)


none_sess = [c for c in cat["courses"] if not has_sessions(c)]
print(f"courses with no sessions in selectable terms: {len(none_sess)}")

# what term keys DO they carry?
keys = collections.Counter()
for c in none_sess:
    keys[tuple(sorted(c.get("terms", {}).keys()))] += 1
print("their 'terms' keys:")
for k, v in keys.most_common(10):
    print(f"   {v:4d}  {k}")

# ---- verify category E: what terms ARE offered? ----
print("\n=== category E check: courses with has_schedule but no target-term sections ===")
ours = {}
for path in ["data/CEC.json", "data/CHI.json", "data/GEC.json", "data/MUS.json",
             "data/CSC.json", "data/TRA.json"]:
    p = os.path.join(HERE, path)
    if not os.path.exists(p):
        continue
    b = json.load(open(p, encoding="utf-8"))
    for c in b["courses"]:
        ours[f"{b['subject']} {c.get('catalog_nbr','')}"] = c

for code in ["CEC 1001", "CHI 2001", "GEC 2101", "MUS 1001", "CSC 2003", "CSC 3102", "TRA 1001"]:
    r = ours.get(code)
    if not r:
        print(f"   {code}: not in our data")
        continue
    print(f"   {code}: has_schedule={r.get('has_schedule')} "
          f"sections={len(r.get('sections') or [])} "
          f"terms_offered={list((r.get('terms_offered') or {}).values())}")

# ---- verify category D on MUS ----
print("\n=== category D sample detail (from raw json) ===")
m = json.load(open(os.path.join(HERE, "data/MUS.json"), encoding="utf-8"))
nod = [c for c in m["courses"] if c.get("has_schedule") is False]
print(f"MUS courses with has_schedule=False: {len(nod)}")
for c in nod[:5]:
    print(f"   {c['course']:12s} career={c.get('career')} sections={len(c.get('sections') or [])} "
          f"enroll={(c.get('enrollment') or {}).get('raw','')[:40]!r}")
