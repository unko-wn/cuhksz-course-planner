"""Pre-flight check for a full SIS scrape.

Run this any time something looks wrong; it reports exactly which layer fails.

    python check_ready.py
"""
import os
import socket
import ssl
import sys
import urllib.request
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"
results = []
warnings = []


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{OK if ok else BAD} {name}" + (f"  -> {detail}" if detail else ""), flush=True)


def warn(name, detail=""):
    warnings.append(name)
    print(f"{WARN} {name}" + (f"  -> {detail}" if detail else ""), flush=True)


print("=" * 78)
print("CUHK-SZ SIS 全量抓取 前置检查")
print("=" * 78)

# ---- 1. dependencies ----
try:
    import requests
    import bs4
    import openpyxl
    report("Python 依赖 (requests/bs4/openpyxl)", True,
           f"requests {requests.__version__}, bs4 {bs4.__version__}, "
           f"openpyxl {openpyxl.__version__}")
except Exception as e:
    report("Python 依赖 (requests/bs4/openpyxl)", False, str(e))

try:
    import lxml  # noqa
    report("Python 依赖 (lxml 解析器)", True)
except Exception as e:
    report("Python 依赖 (lxml 解析器)", False, str(e))

# ---- 2. network ----
HOST = "sis.cuhk.edu.cn"
try:
    ip = socket.gethostbyname(HOST)
    report(f"DNS 解析 {HOST}", True, ip)
except Exception as e:
    ip = None
    report(f"DNS 解析 {HOST}", False, f"{e}  (需要校内网/VPN)")

if ip:
    try:
        with socket.create_connection((HOST, 443), timeout=8):
            report("TCP 443 连通", True)
    except Exception as e:
        report("TCP 443 连通", False, str(e))

# ---- 3. TLS (SIS needs static-RSA kx, TLS<=1.2) ----
if ip:
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        with socket.create_connection((HOST, 443), timeout=10) as raw:
            with ctx.wrap_socket(raw, server_hostname=HOST) as ss:
                report("TLS 握手 (legacy RSA)", True, f"{ss.version()} {ss.cipher()[0]}")
    except Exception as e:
        report("TLS 握手 (legacy RSA)", False, str(e))

# ---- 4. browser (only needed to refresh the session) ----
browser_up = False
try:
    from browser_launch import PORT
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=3) as r:
        v = json.load(r)
    report(f"调试浏览器 (CDP {PORT})", True, v.get("Browser", ""))
    browser_up = True
except Exception:
    warn(f"调试浏览器 (CDP {PORT}) 未运行",
         "已有 Cookie 仍可抓取；但长时间运行建议保持浏览器开启以便自动续期 "
         "(python browser_launch.py)")

# ---- 5. login / cookies ----
if browser_up and os.path.exists(os.path.join(HERE, "_cookies.json")):
    try:
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(HERE, "grab_cookies.py")],
                           capture_output=True, text=True)
        report("刷新 Cookie", "saved" in (r.stdout or ""), "")
    except Exception as e:
        report("刷新 Cookie", False, str(e))

if os.path.exists(os.path.join(HERE, "_cookies.json")) and ip:
    try:
        from sis_scraper import Scraper
        sc = Scraper(verbose=False)
        sc.get()
        n = len(sc.expand_subject(sc.select_letter("C")[0][2])) if False else None
        st = (sc.soup.find("input", {"name": "ICStateNum"}) or {}).get("value")
        report("SIS 登录态 / 组件可访问", True, f"ICStateNum={st}")
    except Exception as e:
        report("SIS 登录态 / 组件可访问", False,
               f"{type(e).__name__}: {e}  -> 在浏览器里完成登录后重试")
else:
    report("SIS 登录态 / 组件可访问", False, "缺少 _cookies.json 或网络不通")

print("=" * 78)
if all(results):
    print("核心检查全部通过，可以开始全量抓取：")
    print("    python run_scrape.py --all-subjects --skip-existing")
    if warnings:
        print("\n注意：")
        for w in warnings:
            print("    - " + w)
else:
    print("存在未通过项，请按上面的提示修复后再开始。")
print("=" * 78)
