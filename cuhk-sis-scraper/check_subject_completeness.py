"""Are the 18 study-scheme subjects now complete vs the SIS catalog?"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
idx = json.load(open(os.path.join(HERE, "catalog_index.json"), encoding="utf-8"))

merged = {}
for d in ("data", "data_supplement"):
    for p in glob.glob(os.path.join(HERE, d, "*.json")):
        b = json.load(open(p, encoding="utf-8"))
        merged.setdefault(b["subject"], set()).update(
            c.get("catalog_nbr", "") for c in b.get("courses", []))

targets = json.load(open(os.path.join(HERE, "targets.json"), encoding="utf-8"))
subs = sorted(targets)

print(f"{'subject':8s} {'catalog':>8s} {'we have':>8s} {'missing':>8s}")
tot_cat = tot_have = tot_miss = 0
missing_all = {}
for s in subs:
    cat = {c[0] for c in idx.get(s, {}).get("courses", [])}
    have = merged.get(s, set())
    miss = sorted(cat - have)
    # numeric-aware sort
    miss.sort(key=lambda x: (len(x), x))
    tot_cat += len(cat)
    tot_have += len(have & cat)
    tot_miss += len(miss)
    if miss:
        missing_all[s] = miss
    flag = "  <-- incomplete" if miss else ""
    print(f"{s:8s} {len(cat):8d} {len(have & cat):8d} {len(miss):8d}{flag}")

print(f"\n{'TOTAL':8s} {tot_cat:8d} {tot_have:8d} {tot_miss:8d}")
json.dump(missing_all, open(os.path.join(HERE, "_still_missing.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)

print("\n=== still-missing courses (first 40) ===")
n = 0
for s, v in missing_all.items():
    print(f"  {s:6s} ({len(v):3d}): {', '.join(v[:18])}{' ...' if len(v) > 18 else ''}")
    n += len(v)
print(f"total still missing: {n}")
