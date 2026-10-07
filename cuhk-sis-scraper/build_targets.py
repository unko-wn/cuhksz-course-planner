"""Build targets.json = {subject: [catalog_nbr, ...]} from the PDF course codes.

Rules from the user:
  * CSC courses are already scraped -> exclude
  * AIE: only AIE1001, AIE1901, AIE1902, AIE1903, AIE2001, AIE2040
"""
import collections
import json
import re

codes = json.load(open("_pdf_codes.json", encoding="utf-8"))

AIE_KEEP = {"AIE1001", "AIE1901", "AIE1902", "AIE1903", "AIE2001", "AIE2040"}

all_codes = set()
for tag, lst in codes.items():
    all_codes.update(lst)

by_subject = collections.defaultdict(set)
skipped = {"csc": [], "aie": []}
for c in sorted(all_codes):
    subj = re.match(r"([A-Z]+)", c).group(1)
    nbr = c[len(subj):]
    if subj == "CSC":
        skipped["csc"].append(c)
        continue
    if subj == "AIE" and c not in AIE_KEEP:
        skipped["aie"].append(c)
        continue
    by_subject[subj].add(nbr)

targets = {s: sorted(v) for s, v in sorted(by_subject.items())}
total = sum(len(v) for v in targets.values())

print(f"subjects: {len(targets)}   courses to scrape: {total}")
for s in targets:
    print(f"  {s:6s} ({len(targets[s]):2d}): {', '.join(targets[s])}")
print(f"\nexcluded CSC ({len(skipped['csc'])}): {', '.join(skipped['csc'])}")
print(f"excluded AIE ({len(skipped['aie'])}): {', '.join(skipped['aie'])}")

with open("targets.json", "w", encoding="utf-8") as f:
    json.dump(targets, f, ensure_ascii=False, indent=1)
print("\nsaved targets.json")
