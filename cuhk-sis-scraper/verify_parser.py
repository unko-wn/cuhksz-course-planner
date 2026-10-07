"""Verify the section parser: counts, container alignment, multi-pattern rows."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sis_scraper import Scraper, TERMS

sc = Scraper()
sc.get()
subs = {c: (n, l) for c, n, l in sc.select_letter("C")}
_, link = subs["CSC"]
courses = sc.expand_subject(link)

N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
tot_rows = tot_multi = 0
for nbr, title, clink in courses[:N]:
    sc.action(clink)
    ok = sc.show_sections()
    if not ok:
        print(f"CSC {nbr}: no schedule panel")
        sc._resync("CSC", link)
        continue
    avail = sc.available_terms()
    for tc, tn in TERMS.items():
        if tc not in avail:
            continue
        sc.select_term(tc)
        sc.view_all()
        s = sc.soup
        nsec = len(s.find_all(id=re.compile(r"^win0divCLASS_SECTION\$\d+$")))
        conts = s.find_all(id=re.compile(r"^win0divCLASS_MTGPAT\$\d+$"))
        rows = sc.parse_sections(tn)
        multi = []
        for c in conts:
            k = len(c.find_all(id=re.compile(r"^MTGPAT_DAYS\$\d+$")))
            if k != 1:
                multi.append(k)
        tot_rows += len(rows)
        tot_multi += len(multi)
        flag = f"  MULTI={multi}" if multi else ""
        print(f"CSC {nbr:>5} {tn:<16} sections={nsec} containers={len(conts)} "
              f"rows={len(rows)}{flag}")
    sc._resync("CSC", link)

print(f"\ntotal rows={tot_rows}, containers with !=1 meeting pattern: {tot_multi}")
