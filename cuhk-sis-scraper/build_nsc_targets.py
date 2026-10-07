"""Build targets.json for the courses that were never scraped (categories A+B)."""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
cls = json.load(open(os.path.join(HERE, "_nsc_classes.json"), encoding="utf-8"))

need = list(cls.get("A_NOT_SCRAPED_SUBJECT", [])) + list(cls.get("B_NOT_IN_SUBJECT_LIST", []))
targets = collections.defaultdict(list)
for code in need:
    subj, _, nbr = code.partition(" ")
    if nbr:
        targets[subj].append(nbr)

targets = {k: sorted(set(v)) for k, v in sorted(targets.items())}
total = sum(len(v) for v in targets.values())
print(f"subjects to re-scrape: {len(targets)}, courses: {total}")
for s in targets:
    print(f"  {s:6s} ({len(targets[s]):3d}): {', '.join(targets[s])}")

json.dump(targets, open(os.path.join(HERE, "_nsc_targets.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nsaved _nsc_targets.json")
