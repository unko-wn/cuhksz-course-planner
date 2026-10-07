"""Data-quality audit of the scraped CSC JSON."""
import json, re, collections

d = json.load(open("data/CSC.json", encoding="utf-8"))
courses = d["courses"]
ug = [c for c in courses if c.get("career") == "Undergraduate"]
print(f"courses={len(courses)}  UG={len(ug)}  errors={sum(1 for c in courses if c.get('error'))}")

sess = [s for c in ug for s in (c.get("sections") or [])]
print(f"UG section rows (all terms) = {len(sess)}")
print("by term:", collections.Counter(s["term"] for s in sess))
print("session_no values:", collections.Counter(s["session_no"] for s in sess))
print("component types:", collections.Counter(re.sub(r"^[A-Z]+\d+-", "", s["session_code"])[:4]
                                              for s in sess))
print("status values:", collections.Counter(s["status"] for s in sess))
print("date formats:", collections.Counter(
    re.sub(r"\d", "#", s["dates"]) for s in sess).most_common(5))
print("time formats:", collections.Counter(
    re.sub(r"\d", "#", f"{s['start']}-{s['end']}") for s in sess).most_common(5))

noprereq = [c["course"] for c in ug if not (c.get("enrollment") or {}).get("prerequisite")]
noexcl = [c["course"] for c in ug if not (c.get("enrollment") or {}).get("exclusion")]
print(f"\nUG courses WITHOUT prerequisite: {len(noprereq)}")
print(f"UG courses WITHOUT exclusion   : {len(noexcl)}")
print(f"UG courses with neither        : "
      f"{len([c for c in ug if not (c.get('enrollment') or {}).get('prerequisite') and not (c.get('enrollment') or {}).get('exclusion')])}")
print("\nUG courses with 0 sections in the 3 target terms:")
zs = [c["course"] for c in ug if not c.get("sections")]
print("  ", zs)
print("\nUG courses missing career:", [c["course"] for c in courses if not c.get("career")])
multi = [c["course"] for c in ug if c.get("has_schedule") is False]
print("UG courses with no schedule panel:", multi)
