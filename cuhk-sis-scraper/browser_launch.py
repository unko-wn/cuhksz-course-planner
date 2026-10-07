"""Launch a persistent Edge/Chrome instance with CDP enabled, pointed at SIS.

The profile directory persists, so the ADFS/SSO login survives across runs.

Usage:
    python browser_launch.py            # launch (visible) and navigate to SIS
    python browser_launch.py --headless
    python browser_launch.py --check    # just report what's running
"""
import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "_browser_profile")
PORT = 9333
SIS_URL = ("https://sis.cuhk.edu.cn/psp/csprd/EMPLOYEE/HRMS/c/ESTABLISH_COURSES.SSS_BROWSE_CATLG.GBL"
           "?PORTALPARAM_PTCNAV=HC_SSS_BROWSE_CATLG_GBL3&EOPP.SCNode=HRMS&EOPP.SCPortal=EMPLOYEE"
           "&EOPP.SCName=HCSR_CURRICULUM_MANAGEMENT&EOPP.SCLabel=Curriculum%20Management"
           "&EOPP.SCPTfname=HCSR_CURRICULUM_MANAGEMENT"
           "&FolderPath=PORTAL_ROOT_OBJECT.HCSR_CURRICULUM_MANAGEMENT.HCSR_COURSE_CATALOG."
           "HC_SSS_BROWSE_CATLG_GBL3&IsFolder=false")


def devtools_up(port=PORT):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as r:
            return json.load(r)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", help="run without a visible window")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--url", default=SIS_URL)
    args = ap.parse_args()

    up = devtools_up()
    if args.check:
        print("devtools:", "UP" if up else "DOWN", up.get("Browser") if up else "")
        if up:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
                for t in json.load(r):
                    if t.get("type") == "page":
                        print(f"   page: {t.get('title')!r} {t.get('url')[:110]}")
        return

    if up:
        print(f"browser already running on {PORT}: {up.get('Browser')}")
        return

    exe = cdp.find_browser()
    args_list = [
        exe,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--start-maximized" if not args.headless else "--window-size=1600,1200",
        args.url,
    ]
    if args.headless:
        args_list.insert(1, "--headless=new")

    import subprocess
    proc = subprocess.Popen(args_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    print(f"launched pid={proc.pid} exe={exe}")
    print(f"profile={PROFILE}")

    for i in range(60):
        time.sleep(0.5)
        if devtools_up():
            print(f"devtools ready after {(i + 1) * 0.5:.1f}s")
            break
    else:
        print("!! devtools never came up")
        sys.exit(1)

    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
        for t in json.load(r):
            if t.get("type") == "page":
                print(f"   page: {t.get('title')!r} {t.get('url')[:120]}")


if __name__ == "__main__":
    main()
