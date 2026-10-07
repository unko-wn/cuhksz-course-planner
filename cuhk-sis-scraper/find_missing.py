"""Locate the study-scheme courses that were not found under their listed subject code."""
import json
import re

idx = json.load(open("catalog_index.json", encoding="utf-8"))

# (listed code, expected title fragment from the PDF)
MISSING = [
    ("BMA3001", "Data Analytics for Business"),
    ("BMA3011", "Introduction to System Analysis and Design"),
    ("ECE4320", "Hardware Acceleration for Efficient AI Computing"),
    ("EIE3280", "Networks: Technology, Economics and Society"),
    ("EIE4512", "Digital Image Processing"),
]

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

for listed, title in MISSING:
    print("=" * 84)
    print(f"{listed}  expected title: {title!r}")
    tnorm = norm(title)
    hits = []
    for subj, blob in idx.items():
        for nbr, ctitle in blob["courses"]:
            if norm(ctitle) == tnorm:
                hits.append((subj, nbr, ctitle, "EXACT"))
    if not hits:
        # looser: significant word overlap
        words = [w for w in tnorm.split() if len(w) > 3]
        for subj, blob in idx.items():
            for nbr, ctitle in blob["courses"]:
                cn = norm(ctitle)
                if words and all(w in cn for w in words):
                    hits.append((subj, nbr, ctitle, "FUZZY"))
    if hits:
        for h in hits:
            print(f"   -> {h[0]} {h[1]:<8} {h[2]}   [{h[3]}]")
    else:
        print("   !! not present anywhere in the SIS catalog")

# How big are the listed subjects?
for s in ("BMA", "EIE", "ECE"):
    print(f"\n{s}: {len(idx.get(s, {}).get('courses', []))} catalog courses")
