"""Build a full catalog index: subject -> [(catalog_nbr, title)] for all 114 subjects.

Each subject's link is re-resolved in the live panel before expanding, because
PeopleSoft link ids are positional and become stale after any post-back.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sis_scraper import Scraper, LETTERS

OUT = "catalog_index.json"


def main():
    sc = Scraper(verbose=False)
    sc.get()
    letters = {}
    for L in LETTERS:
        try:
            letters[L] = [(c, n) for c, n, _ in sc.select_letter(L)]
        except Exception as e:
            print(f"  letter {L} failed: {e}", flush=True)

    index = {}
    t0 = time.time()
    for L, subs in letters.items():
        for code, name in subs:
            try:
                got = sc.select_letter(L)          # fresh ids for this panel
                hit = [l for c, n, l in got if c == code]
                if not hit:
                    print(f"  {code}: link not found", flush=True)
                    continue
                courses = sc.expand_subject(hit[0])
                index[code] = {"name": name,
                               "courses": [[n, t] for n, t, _ in courses]}
                print(f"  {code:8s} {len(courses):4d}  {name}", flush=True)
            except Exception as e:
                print(f"  {code:8s} FAILED {type(e).__name__}: {e}", flush=True)
                try:
                    sc.get()
                    sc.select_letter(L)
                except Exception:
                    pass

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    total = sum(len(v["courses"]) for v in index.values())
    print(f"\n{len(index)} subjects, {total} courses, {time.time()-t0:.0f}s -> {OUT}",
          flush=True)


if __name__ == "__main__":
    main()
