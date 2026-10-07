"""Shared HTTP session factory for CUHK-SZ SIS (legacy RSA-kx / TLS1.2 only)."""
import ssl
import requests
from requests.adapters import HTTPAdapter

BASE = "https://sis.cuhk.edu.cn"
CATALOG_URL = (
    BASE + "/psp/csprd/EMPLOYEE/HRMS/c/ESTABLISH_COURSES.SSS_BROWSE_CATLG.GBL"
    "?PORTALPARAM_PTCNAV=HC_SSS_BROWSE_CATLG_GBL3&EOPP.SCNode=HRMS"
    "&EOPP.SCPortal=EMPLOYEE&EOPP.SCName=HCSR_CURRICULUM_MANAGEMENT"
    "&EOPP.SCLabel=Curriculum%20Management&EOPP.SCPTfname=HCSR_CURRICULUM_MANAGEMENT"
    "&FolderPath=PORTAL_ROOT_OBJECT.HCSR_CURRICULUM_MANAGEMENT.HCSR_COURSE_CATALOG.HC_SSS_BROWSE_CATLG_GBL3"
    "&IsFolder=false"
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class LegacyTLSAdapter(HTTPAdapter):
    """SIS only speaks TLS<=1.2 with static-RSA key exchange."""

    def __init__(self, *a, **kw):
        self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE
        self._ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        self._ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(*a, **kw)

    def init_poolmanager(self, *a, **kw):
        kw["ssl_context"] = self._ctx
        return super().init_poolmanager(*a, **kw)

    def proxy_manager_for(self, *a, **kw):
        kw["ssl_context"] = self._ctx
        return super().proxy_manager_for(*a, **kw)


def new_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", LegacyTLSAdapter())
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        "Connection": "keep-alive",
    })
    return s


if __name__ == "__main__":
    s = new_session()
    r = s.get(CATALOG_URL, timeout=30, allow_redirects=True)
    print("STATUS:", r.status_code, "| LEN:", len(r.text))
    print("FINAL:", r.url)
    for h in r.history:
        print("  redirect:", h.status_code, "->", h.headers.get("Location"))
    print("COOKIES:", list(s.cookies.keys()))
    import re
    m = re.search(r"<title>(.*?)</title>", r.text, re.S | re.I)
    print("TITLE:", m.group(1).strip() if m else None)
    open("_probe_catalog.html", "w", encoding="utf-8").write(r.text)
    print("saved _probe_catalog.html")
