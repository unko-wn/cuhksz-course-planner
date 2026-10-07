"""CUHK-SZ SIS (PeopleSoft) course-catalog scraper.

Replays PeopleSoft classic component post-backs over HTTP using the
authenticated browser session harvested by grab_cookies.py.

Extracts, per course:
  * identity   : subject, catalog nbr, title, career, units, components
  * enrollment : prerequisite / exclusion (Enrollment Requirement)
  * sections   : session code, session nbr, status, days, start, end,
                 room, instructor, dates   (per term)
"""
import json
import os
import re
import time
import warnings
from collections import OrderedDict

from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

from ps_fast import load_session, form_payload, COMP_URL  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

TERMS = OrderedDict([
    ("2510", "2025-26 Term 1"),
    ("2520", "2025-26 Term 2"),
    ("2610", "2026-27 Term 1"),
])

LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + list("0123456789")


def norm_time(s):
    """'8:30AM' / '08:30' / '1:30PM' -> 'HH:MM' (24h)."""
    s = (s or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*([AP]M)?$", s, re.I)
    if not m:
        return s
    h, mi, ap = int(m.group(1)), m.group(2), (m.group(3) or "").upper()
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{mi}"


def norm_dates(s):
    """Date ranges -> unambiguous ISO.

    '09/01/2025 - 12/12/2025' (SIS US format)  -> '2025-09-01 - 2025-12-12'
    '2025/09/01 - 2025/12/12' (SIS alt format) -> '2025-09-01 - 2025-12-12'
    """
    s = re.sub(r"\s+", " ", (s or "").strip())
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        a = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        b = f"{m.group(6)}-{int(m.group(4)):02d}-{int(m.group(5)):02d}"
        return f"{a} - {b}"
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})\s*-\s*(\d{4})/(\d{1,2})/(\d{1,2})$", s)
    if m:
        a = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        b = f"{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"
        return f"{a} - {b}"
    return s


class SessionExpired(RuntimeError):
    pass


class Scraper:
    def __init__(self, verbose=True, delay=0.12, max_retries=3):
        self.s = load_session()
        self.soup = None
        self.verbose = verbose
        self.delay = delay
        self.max_retries = max_retries
        self.posts = 0
        os.makedirs(CACHE, exist_ok=True)

    def log(self, *a):
        if self.verbose:
            print(*a, flush=True)

    # ---------------- plumbing ----------------
    @staticmethod
    def _check(soup):
        if soup.find("input", {"name": "userid"}):
            raise SessionExpired("SIS login form returned - session expired")
        if not soup.find("input", {"name": "ICAction"}):
            title = soup.title.get_text(strip=True) if soup.title else ""
            raise SessionExpired(f"component not returned (title={title!r}) - "
                                 f"re-run grab_cookies.py")

    def get(self):
        r = self.s.get(COMP_URL, timeout=60)
        self.soup = BeautifulSoup(r.content.decode("utf-8", "replace"), "lxml")
        self._check(self.soup)
        return self.soup

    def action(self, ic_action, expect=None):
        last_err = None
        for attempt in range(self.max_retries):
            try:
                data = form_payload(self.soup)
                data["ICAction"] = ic_action
                r = self.s.post(COMP_URL, data=data, timeout=90)
                html = r.content.decode("utf-8", "replace")
                soup = BeautifulSoup(html, "lxml")
                self._check(soup)
                if expect and expect not in html:
                    last_err = f"expected {expect!r} missing after {ic_action}"
                    self.log(f"      ! {last_err} (attempt {attempt + 1})")
                    time.sleep(0.7)
                    continue
                self.soup = soup
                self.posts += 1
                if self.delay:
                    time.sleep(self.delay)
                return soup
            except SessionExpired:
                raise
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                self.log(f"      ! post {ic_action} failed ({last_err}); retrying")
                time.sleep(1.0)
                try:
                    self.get()
                except Exception:
                    pass
        raise RuntimeError(f"action {ic_action} failed: {last_err}")

    def _txt(self, elem_id, soup=None):
        e = (soup or self.soup).find(id=elem_id)
        return e.get_text(" ", strip=True) if e else None

    def set_value(self, elem_id, value):
        """Set a field's value in the current panel so the next POST carries it."""
        e = self.soup.find(id=elem_id)
        if e is None:
            raise RuntimeError(f"element {elem_id!r} not found on this page")
        if e.name == "input":
            e["value"] = value
        elif e.name == "select":
            for o in e.find_all("option"):
                if o.get("value") == value:
                    o["selected"] = "selected"
                elif o.has_attr("selected"):
                    del o["selected"]
        elif e.name == "textarea":
            e.clear()
            e.append(value)
        else:
            raise RuntimeError(f"cannot set value on <{e.name}>")
        return value

    # ---------------- catalog navigation ----------------
    def select_letter(self, letter):
        soup = self.action(f"DERIVED_SSS_BCC_SSR_ALPHANUM_{letter}")
        out, seen = [], set()
        for a in soup.find_all("a"):
            aid = a.get("id") or ""
            if not re.match(r"DERIVED_SSS_BCC_GROUP_BOX_1\$\d+\$\$\d+$", aid):
                continue
            m = re.match(r"^([A-Z0-9]{2,6})\s*-\s*(.+)$", a.get_text(" ", strip=True))
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                out.append((m.group(1), m.group(2).strip(), aid))
        return out

    def expand_subject(self, link_id):
        soup = self.action(link_id)
        out = []
        for a in soup.find_all("a"):
            m = re.match(r"CRSE_NBR\$(\d+)$", a.get("id") or "")
            if not m:
                continue
            t = soup.find(id=f"CRSE_TITLE${m.group(1)}")
            out.append((a.get_text(" ", strip=True),
                        t.get_text(" ", strip=True) if t else "", a["id"]))
        return out

    # ---------------- course detail ----------------
    def open_course(self, link_id):
        soup = self.action(link_id)
        d = {}
        hdr = soup.find(id="DERIVED_CRSECAT_DESCR200")
        d["header"] = hdr.get_text(" ", strip=True) if hdr else ""
        for label, key in [("Career", "career"), ("Units", "units"),
                           ("Grading Basis", "grading"), ("Campus", "campus"),
                           ("Academic Group", "academic_group"),
                           ("Academic Organization", "academic_org")]:
            v = self._value_after_label(soup, label)
            if v:
                d[key] = v
        d["enrollment"] = self._enrollment(soup)
        d["attributes"] = self._attr(soup, "Course Attribute")
        d["description"] = self._attr(soup, "Description")
        return d

    def _value_after_label(self, soup, label):
        for lab in soup.find_all(string=re.compile(rf"^{re.escape(label)}\s*$")):
            node = lab.parent
            for _ in range(6):
                if node is None:
                    break
                nxt = node.find_next("span", class_=re.compile("DISPLAYONLY|DISPONLY|LONGEDITBOX"))
                if nxt:
                    t = nxt.get_text(" ", strip=True)
                    if t and t != label:
                        return t
                node = node.parent
        return None

    def _enrollment(self, soup):
        vals = []
        for e in soup.find_all(id=re.compile(r"DERIVED_CRSECAT_DESCR254A\$\d+")):
            t = re.sub(r"\s+", " ", e.get_text(" ", strip=True))
            if t and t not in vals:
                vals.append(t)
        if not vals:
            t = self._value_after_label(soup, "Enrollment Requirement")
            if t:
                vals.append(re.sub(r"\s+", " ", t))
        raw = " || ".join(vals)

        def grab(kind):
            found = []
            pat = rf"{kind}\s*:\s*(.*?)(?=\s*(?:\d+\.\s*)?(?:Prerequisite[s]?|Exclusion[s]?)\s*:|$)"
            for t in vals:
                for m in re.finditer(pat, t, re.I):
                    v = m.group(1).strip(" ;,|")
                    if v and v not in found:
                        found.append(v)
            return " ; ".join(found)

        return {"raw": raw,
                "prerequisite": grab("Prerequisite[s]?"),
                "exclusion": grab("Exclusion[s]?")}

    def _attr(self, soup, label):
        for lab in soup.find_all(string=re.compile(rf"^{re.escape(label)}\s*$")):
            node = lab.parent
            for _ in range(8):
                if node is None:
                    break
                nxt = node.find_next("span", class_=re.compile("LONGEDITBOX|DISPONLY"))
                if nxt:
                    t = nxt.get_text(" ", strip=True)
                    if t and t != label:
                        return t
                node = node.parent
        return ""

    # ---------------- sections ----------------
    def show_sections(self):
        """Open the Course Schedule panel. Some courses have no schedule panel."""
        soup = self.action("DERIVED_SAA_CRS_SSR_PB_GO")
        return "Course Schedule" in soup.get_text(" ", strip=True)

    def available_terms(self):
        sel = self.soup.find("select", {"id": "DERIVED_SAA_CRS_TERM_ALT"})
        if not sel:
            return OrderedDict()
        return OrderedDict((o.get("value"), o.get_text(strip=True))
                           for o in sel.find_all("option"))

    def select_term(self, term_code):
        sel = self.soup.find("select", {"id": "DERIVED_SAA_CRS_TERM_ALT"})
        if not sel:
            return None
        for o in sel.find_all("option"):
            if o.get("value") == term_code:
                o["selected"] = "selected"
            elif o.has_attr("selected"):
                del o["selected"]
        soup = None
        for act in ("DERIVED_SAA_CRS_SSR_PB_GO$3$", "DERIVED_SAA_CRS_SSR_PB_GO"):
            soup = self.action(act)
            if "sections for" in soup.get_text(" ", strip=True):
                return soup
        return soup

    def view_all(self):
        """Expand every paged grid once.

        NB: clicking 'View All' again re-posts the action and resets the grid
        back to its default page size, so each control is used exactly once.
        """
        ids = []
        for a in self.soup.find_all("a"):
            aid = a.get("id") or ""
            if aid.endswith("$fviewall$0") and aid not in ids:
                ids.append(aid)
        for aid in ids:
            self.action(aid)
        return self.soup

    def parse_sections(self, term_label):
        """One row per meeting pattern, paired with its class section by DOM order.

        Structure: each class row (win0divCLASS_SECTION$k) is followed by its own
        meeting-pattern container (win0divCLASS_MTGPAT$k), which may hold several
        rows (a section can meet on more than one day/time).
        """
        soup = self.soup
        sec_nodes = soup.find_all(id=re.compile(r"^win0divCLASS_SECTION\$\d+$"))
        cont_nodes = soup.find_all(id=re.compile(r"^win0divCLASS_MTGPAT\$\d+$"))
        rows = []
        for k, sdiv in enumerate(sec_nodes):
            a = sdiv.find("a")
            code = a.get_text(" ", strip=True) if a else sdiv.get_text(" ", strip=True)
            tr = sdiv.find_parent("tr")
            session_no = status = ""
            if tr is not None:
                sn = tr.find(id=re.compile(r"^CLASS_SESSION\$\d+$"))
                if sn is not None:
                    session_no = sn.get_text(" ", strip=True)
                sd = tr.find(id=re.compile(r"^win0divCLASS_STATUS\$\d+$"))
                if sd is not None:
                    img = sd.find("img")
                    status = (img.get("alt") if img and img.get("alt")
                              else sd.get_text(" ", strip=True))
            mm = re.match(r"^(.*?)\s*\((\d+)\)\s*$", code)
            session_code = mm.group(1).strip() if mm else code
            class_nbr = mm.group(2) if mm else ""

            patterns = []
            if k < len(cont_nodes):
                cont = cont_nodes[k]
                for dnode in cont.find_all(id=re.compile(r"^MTGPAT_DAYS\$\d+$")):
                    j = dnode["id"].rsplit("$", 1)[1]

                    def g(f, j=j, cont=cont):
                        e = cont.find(id=f"MTGPAT_{f}${j}")
                        return e.get_text(" ", strip=True) if e else ""
                    patterns.append({"days": g("DAYS"), "start": norm_time(g("START")),
                                     "end": norm_time(g("END")), "room": g("ROOM"),
                                     "instructor": g("INSTR"),
                                     "dates": norm_dates(g("DATES"))})
            if not patterns:
                patterns = [{"days": "", "start": "", "end": "", "room": "",
                             "instructor": "", "dates": ""}]
            for p in patterns:
                rows.append({"term": term_label, "session_code": session_code,
                             "class_nbr": class_nbr, "session_no": session_no,
                             "status": status, **p})
        if len(cont_nodes) != len(sec_nodes):
            self.log(f"      ~ {len(sec_nodes)} class rows vs {len(cont_nodes)} meeting containers")
        return rows

    def return_to_catalog(self):
        return self.action("DERIVED_SAA_CRS_RETURN_PB", expect="Course Nbr")

    def _resync(self, subject_code, link_id):
        """Get back to the course list after a failure; True if usable."""
        try:
            self.return_to_catalog()
            if self.soup.find(id="CRSE_NBR$0"):
                return True
        except Exception:
            pass
        try:
            self.get()
            self.select_letter(subject_code[0])
            self.expand_subject(link_id)
            return bool(self.soup.find(id="CRSE_NBR$0"))
        except Exception:
            return False

    # ---------------- high level ----------------
    def scrape_subject(self, subject_code, subject_name, link_id, terms=None, only=None):
        """Scrape the courses of one subject.

        only: optional set of catalog numbers; when given, only those courses
              are visited (used for the study-scheme batches).
        """
        terms = terms or TERMS
        courses = self.expand_subject(link_id)
        if only is not None:
            want = {str(x).upper() for x in only}
            selected = [c for c in courses if c[0].upper() in want]
            missing = sorted(want - {c[0].upper() for c in courses})
            self.log(f"    {subject_code} ({subject_name}): {len(courses)} in catalog, "
                     f"{len(selected)} requested")
            if missing:
                self.log(f"      ! not in catalog: {', '.join(missing)}")
        else:
            selected = courses
            missing = []
            self.log(f"    {subject_code} ({subject_name}): {len(courses)} courses")
        self.missing = getattr(self, "missing", {})
        self.missing[subject_code] = missing
        results = []
        for n, (nbr, title, clink) in enumerate(selected, 1):
            label = f"{subject_code} {nbr}"
            try:
                d = self.open_course(clink)
                d["subject"] = subject_code
                d["subject_name"] = subject_name
                d["catalog_nbr"] = nbr
                d["list_title"] = title
                d["course"] = f"{subject_code} {nbr}"
                has_sched = self.show_sections()
                d["has_schedule"] = has_sched
                avail = self.available_terms() if has_sched else OrderedDict()
                d["terms_offered"] = dict(avail)
                d["sections"] = []
                for code, tname in terms.items():
                    if code not in avail:
                        continue
                    self.select_term(code)
                    self.view_all()
                    d["sections"].extend(self.parse_sections(tname))
                results.append(d)
                self.log(f"      [{n:>3}/{len(selected)}] {label:<12} "
                         f"career={str(d.get('career')):<14} secs={len(d['sections']):>3} "
                         f"posts={self.posts}")
            except SessionExpired:
                raise
            except Exception as e:
                self.log(f"      !! {label} failed: {type(e).__name__}: {e}")
                results.append({"course": label, "error": str(e), "subject": subject_code,
                                "catalog_nbr": nbr, "list_title": title, "sections": []})
            if not self._resync(subject_code, link_id):
                self.log(f"      !! lost the course list after {label}; stopping subject")
                break
        return results


if __name__ == "__main__":
    sc = Scraper()
    sc.get()
    print("connected. ICStateNum:",
          (sc.soup.find("input", {"name": "ICStateNum"}) or {}).get("value"))
    print("C subjects:", [s[0] for s in sc.select_letter("C")])
    print("time normalisation:", [norm_time(x) for x in
                                  ["8:30AM", "1:30PM", "12:00PM", "12:15AM", "08:30"]])
