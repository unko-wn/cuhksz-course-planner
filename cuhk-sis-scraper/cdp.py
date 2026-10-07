"""Tiny Chrome DevTools Protocol driver (no external deps beyond websocket-client)."""
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request

import websocket

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("no Edge/Chrome found")


def free_port(start=9333):
    for p in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("no free port")


class Browser:
    def __init__(self, profile_dir, headless=True, port=None):
        self.exe = find_browser()
        self.port = port or free_port()
        self.profile = os.path.abspath(profile_dir)
        os.makedirs(self.profile, exist_ok=True)
        args = [
            self.exe,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate,OptimizationHints",
            "--remote-allow-origins=*",
            "about:blank",
        ]
        if headless:
            args.insert(1, "--headless=new")
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        self.ws = None
        self.target_id = None
        self._wait_ready()

    def _wait_ready(self, timeout=40):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=2) as r:
                    self.version = json.load(r)
                return
            except Exception:
                time.sleep(0.4)
        raise RuntimeError("browser devtools did not come up")

    # ---- targets ----
    def list_targets(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=5) as r:
            return json.load(r)

    def new_page(self, url="about:blank"):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json/new?{urllib.parse.quote(url, safe='')}",
                    data=b"", timeout=10) as r:
                t = json.load(r)
        except Exception:
            # older chrome needs PUT
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/json/new?{urllib.parse.quote(url, safe='')}",
                method="PUT")
            with urllib.request.urlopen(req, timeout=10) as r:
                t = json.load(r)
        self.target_id = t["id"]
        self.ws = websocket.create_connection(t["webSocketDebuggerUrl"],
                                              timeout=60, max_size=200 * 1024 * 1024)
        self._id = 0
        return t

    def attach_first_page(self):
        pages = [t for t in self.list_targets() if t["type"] == "page"]
        if not pages:
            return self.new_page()
        t = pages[0]
        self.target_id = t["id"]
        self.ws = websocket.create_connection(t["webSocketDebuggerUrl"],
                                              timeout=60, max_size=200 * 1024 * 1024)
        self._id = 0
        return t

    # ---- protocol ----
    def send(self, method, **params):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def evaluate(self, expr, await_promise=False):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=await_promise)
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS error: {r['exceptionDetails'].get('text')} "
                               f"{r['exceptionDetails'].get('exception', {}).get('description', '')}")
        return r.get("result", {}).get("value")

    def goto(self, url, wait=3.0):
        self.send("Page.enable")
        self.send("Page.navigate", url=url)
        time.sleep(wait)
        return self.html()

    def html(self):
        return self.evaluate("document.documentElement.outerHTML") or ""

    def url(self):
        return self.evaluate("location.href")

    def title(self):
        return self.evaluate("document.title")

    def close(self):
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    b = Browser(profile_dir="_cdp_profile_test", headless=True)
    print("browser:", b.version.get("Browser"))
    b.attach_first_page()
    print("title:", b.title())
    b.goto("https://sis.cuhk.edu.cn/psp/csprd/?cmd=login", wait=5)
    print("after goto ->", b.url())
    print("title:", b.title())
    print("len html:", len(b.html()))
    b.close()
