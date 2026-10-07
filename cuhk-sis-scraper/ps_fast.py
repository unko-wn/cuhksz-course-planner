"""Requests-based PeopleSoft driver using cookies harvested from the browser."""
import json
import os
import re
import sys
import time

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sis_http import new_session, BASE  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
COOKIES = os.path.join(HERE, "_cookies.json")

COMP_URL = (BASE + "/psc/csprd/EMPLOYEE/HRMS/c/ESTABLISH_COURSES.SSS_BROWSE_CATLG.GBL"
            "?PORTALPARAM_PTCNAV=HC_SSS_BROWSE_CATLG_GBL3&EOPP.SCNode=HRMS"
            "&EOPP.SCPortal=EMPLOYEE&EOPP.SCName=HCSR_CURRICULUM_MANAGEMENT"
            "&EOPP.SCLabel=Curriculum%20Management&EOPP.SCPTfname=HCSR_CURRICULUM_MANAGEMENT"
            "&FolderPath=PORTAL_ROOT_OBJECT.HCSR_CURRICULUM_MANAGEMENT.HCSR_COURSE_CATALOG."
            "HC_SSS_BROWSE_CATLG_GBL3&IsFolder=false")


def load_session():
    s = new_session()
    with open(COOKIES, encoding="utf-8") as f:
        for c in json.load(f):
            s.cookies.set(c["name"], c["value"], domain=c["domain"].lstrip("."),
                          path=c.get("path", "/"))
    return s


def form_payload(soup):
    """Serialise a PeopleSoft component form exactly as the browser would."""
    data = {}
    for el in soup.find_all("input"):
        n = el.get("name")
        if not n:
            continue
        t = (el.get("type") or "text").lower()
        if t in ("image", "button", "submit", "reset", "file"):
            continue
        if t in ("checkbox", "radio"):
            if el.has_attr("checked"):
                data[n] = el.get("value", "on")
            continue
        data[n] = el.get("value", "")
    for el in soup.find_all("select"):
        n = el.get("name")
        if not n:
            continue
        opts = el.find_all("option")
        sel = [o for o in opts if o.has_attr("selected")]
        chosen = sel[0] if sel else (opts[0] if opts else None)
        data[n] = chosen.get("value", "") if chosen else ""
    for el in soup.find_all("textarea"):
        n = el.get("name")
        if n:
            data[n] = el.get_text()
    return data


if __name__ == "__main__":
    s = load_session()
    r = s.get(COMP_URL, timeout=40)
    html = r.content.decode("utf-8", "replace")
    soup = BeautifulSoup(html, "lxml")
    print("status:", r.status_code, "len:", len(html))
    print("title:", soup.title.get_text(strip=True) if soup.title else None)
    print("has ICAction:", bool(soup.find("input", {"name": "ICAction"})))
    print("ICSID:", (soup.find("input", {"name": "ICSID"}) or {}).get("value", "")[:40]
          if soup.find("input", {"name": "ICSID"}) else None)
    print("ICStateNum:", (soup.find("input", {"name": "ICStateNum"}) or {}).get("value")
          if soup.find("input", {"name": "ICStateNum"}) else None)
    labels = [e.get_text(" ", strip=True) for e in
              soup.select(".PAPAGETITLE,.PSGROUPBOXLABEL")][:12]
    print("labels:", labels)
    open("_fast_get.html", "w", encoding="utf-8").write(html)
