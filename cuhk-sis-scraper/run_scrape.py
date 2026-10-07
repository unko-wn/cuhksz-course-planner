"""Scrape subjects from CUHK-SZ SIS into JSON.

Examples
    python run_scrape.py --subjects CSC
    python run_scrape.py --subjects CSC,CSE
    python run_scrape.py --all-subjects
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sis_scraper import Scraper, SessionExpired, TERMS, LETTERS  # noqa: E402
from ps_fast import load_session  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def refresh_cookies():
    """Re-harvest cookies from the still-open, logged-in browser."""
    print("   [refresh] re-harvesting cookies from browser ...", flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "grab_cookies.py")],
                       capture_output=True, text=True)
    ok = "saved" in (r.stdout or "")
    print(f"   [refresh] {'ok' if ok else 'FAILED: ' + (r.stdout or r.stderr)[-300:]}",
          flush=True)
    return ok


def discover_subjects(sc):
    """{code: (name, letter)} for every subject in the catalog."""
    found = {}
    for L in LETTERS:
        try:
            got = sc.select_letter(L)
        except SessionExpired:
            raise
        except Exception as e:
            print(f"   letter {L} failed: {e}", flush=True)
            continue
        for code, name, _link in got:
            found.setdefault(code, (name, L))
        if got:
            print(f"   {L}: {', '.join(c for c, _, _ in got)}", flush=True)
    return found


def resolve_link(sc, code):
    """Freshly resolve a subject's link id in the current panel state."""
    for c, _n, link in sc.select_letter(code[0]):
        if c == code:
            return link
    return None


def scrape_subject(sc, code, terms, only=None, depth=0):
    try:
        sc.get()
        got = sc.select_letter(code[0])
        hit = [(n, l) for c, n, l in got if c == code]
        if not hit:
            print(f"  !! subject {code} not found under letter {code[0]}", flush=True)
            return None
        name, link = hit[0]
        return sc.scrape_subject(code, name, link, terms=terms, only=only)
    except SessionExpired:
        if depth >= 3:
            raise
        print(f"   !! session expired on {code}; refreshing cookies", flush=True)
        if not refresh_cookies():
            raise
        sc.s = load_session()
        return scrape_subject(sc, code, terms, only=only, depth=depth + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", default="CSC")
    ap.add_argument("--all-subjects", action="store_true")
    ap.add_argument("--targets", default=None,
                    help="JSON file {subject: [catalog_nbr, ...]} to scrape selectively")
    ap.add_argument("--terms", default=",".join(TERMS.keys()))
    ap.add_argument("--outdir", default=DATA)
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip subjects whose <SUBJECT>.json already exists (resume)")
    ap.add_argument("--letters", default=None,
                    help="only scrape subjects starting with these letters, e.g. A,B,C")
    ap.add_argument("--dry-run", action="store_true",
                    help="only report which subjects would be scraped, then exit")
    args = ap.parse_args()

    terms = OrderedDict((t, TERMS[t]) for t in args.terms.split(",") if t in TERMS)
    if not terms:
        print("no valid terms")
        return
    os.makedirs(args.outdir, exist_ok=True)

    targets = None
    if args.targets:
        with open(args.targets, encoding="utf-8-sig") as f:
            targets = json.load(f)

    t0 = time.time()
    sc = Scraper()
    sc.get()
    print("connected to SIS catalog", flush=True)

    catalog = discover_subjects(sc)
    print(f"\ncatalog has {len(catalog)} subjects", flush=True)

    if targets is not None:
        wanted = sorted(targets)
    elif args.all_subjects:
        wanted = sorted(catalog)
    else:
        wanted = [s.strip().upper() for s in args.subjects.split(",") if s.strip()]

    if args.letters:
        keep = {c.strip().upper() for c in args.letters.split(",") if c.strip()}
        wanted = [c for c in wanted if c[0].upper() in keep]
        print(f"letter filter {sorted(keep)} -> {len(wanted)} subjects", flush=True)

    if args.skip_existing:
        before = len(wanted)
        wanted = [c for c in wanted
                  if not os.path.exists(os.path.join(args.outdir, f"{c}.json"))]
        print(f"skip-existing: {before - len(wanted)} already done, {len(wanted)} to go",
              flush=True)

    print(f"terms      : {list(terms.values())}", flush=True)
    print(f"subjects   : {len(wanted)} -> {wanted}", flush=True)

    if args.dry_run:
        todo = [c for c in wanted if c in catalog]
        print(f"\n[dry-run] would scrape {len(todo)} subjects:", flush=True)
        for c in todo:
            print(f"    {c:8s} {catalog[c][0]}", flush=True)
        print("[dry-run] nothing was scraped.", flush=True)
        return

    all_missing = {}
    done = failed = 0
    for code in wanted:
        if code not in catalog:
            print(f"\n!! {code} not in catalog", flush=True)
            continue
        only = targets.get(code) if targets else None
        print(f"\n=== {code} ({catalog[code][0]})"
              f"{' - ' + str(len(only)) + ' requested' if only else ''} ===", flush=True)
        try:
            rows = scrape_subject(sc, code, terms, only=only)
        except Exception:
            traceback.print_exc()
            failed += 1
            continue
        if rows is None:
            failed += 1
            continue
        out = os.path.join(args.outdir, f"{code}.json")
        tmp = out + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"subject": code, "subject_name": catalog[code][0],
                       "terms": dict(terms),
                       "requested": only,
                       "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "courses": rows}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, out)          # atomic: a crash never leaves a half file
        done += 1
        ug = sum(1 for r in rows if r.get("career") == "Undergraduate")
        secs = sum(len(r.get("sections") or []) for r in rows)
        errs = sum(1 for r in rows if r.get("error"))
        miss = (sc.missing or {}).get(code) or []
        if miss:
            all_missing[code] = miss
        print(f"  -> {len(rows)} courses ({ug} UG), {secs} sections, {errs} errors, "
              f"{len(miss)} not-in-catalog | saved {os.path.basename(out)}", flush=True)

    print(f"\nsubjects done this run: {done}, failed: {failed}", flush=True)

    if all_missing:
        print("\n=== requested but NOT FOUND in the SIS catalog ===", flush=True)
        for k, v in all_missing.items():
            print(f"  {k}: {', '.join(v)}", flush=True)

    print(f"\nDONE in {time.time() - t0:.0f}s, postbacks={sc.posts}", flush=True)


if __name__ == "__main__":
    main()
