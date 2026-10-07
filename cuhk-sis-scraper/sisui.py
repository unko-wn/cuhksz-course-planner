"""SIS UI automation toolkit over CDP.

Drives the live SIS browser (launched by browser_launch.py) and works inside the
PeopleSoft TargetContent frame.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import websocket  # noqa: E402
from browser_launch import PORT  # noqa: E402

FRAME = "document.getElementById('ptifrmtgtframe').contentDocument"


def _list():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
        return json.load(r)


class SIS:
    def __init__(self, port=PORT):
        self.port = port
        targets = [t for t in _list() if t.get("type") == "page"]
        if not targets:
            raise RuntimeError("no page target; run browser_launch.py first")
        t = next((x for x in targets if "sis.cuhk.edu.cn" in x.get("url", "")), targets[0])
        self.target = t
        self.ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=120,
                                              max_size=300 * 1024 * 1024)
        self._id = 0
        self.send("Page.enable")
        self.send("Runtime.enable")

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

    def ev(self, expr, await_promise=False):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=await_promise)
        if "exceptionDetails" in r:
            ed = r["exceptionDetails"]
            raise RuntimeError("JS error: " + str(ed.get("exception",
                                                         {}).get("description") or ed.get("text")))
        return r.get("result", {}).get("value")

    def evf(self, expr, await_promise=False):
        """Evaluate expr with `d` bound to the TargetContent document."""
        return self.ev(f"(function(){{var d={FRAME}; if(!d) return null; return ({expr});}})()",
                       await_promise=await_promise)

    # ---------- state ----------
    def ic_state(self):
        return self.evf("(d.getElementById('ICStateNum')||{}).value")

    def frame_title(self):
        return self.evf("d.title")

    def frame_text(self):
        return self.evf("d.body.innerText")

    def is_busy(self):
        try:
            return bool(self.ev(
                "!!(document.getElementById('processing') && "
                "document.getElementById('processing').offsetParent)"))
        except Exception:
            return False

    def wait_idle(self, timeout=60, settle=0.6):
        """Wait for a PeopleSoft postback to finish."""
        t0 = time.time()
        last = self.ic_state()
        stable = 0
        while time.time() - t0 < timeout:
            time.sleep(0.25)
            try:
                cur = self.ic_state()
            except Exception:
                continue
            if cur != last:
                last = cur
                stable = 0
                continue
            stable += 0.25
            if stable >= settle and not self.is_busy():
                return True
        return False

    def click(self, elem_id, wait=True):
        before = self.ic_state()
        self.evf(f"(function(){{var e=d.getElementById({elem_id!r});"
                 f"if(!e) throw new Error('no element '+{elem_id!r});e.click();return true;}})()")
        if wait:
            t0 = time.time()
            while time.time() - t0 < 60:
                time.sleep(0.3)
                try:
                    if self.ic_state() != before and not self.is_busy():
                        break
                except Exception:
                    pass
            time.sleep(0.5)

    def set_input(self, elem_id, value):
        self.evf(f"(function(){{var e=d.getElementById({elem_id!r});"
                 f"if(!e) throw new Error('no input '+{elem_id!r});"
                 f"e.value={value!r};e.dispatchEvent(new Event('change',{{bubbles:true}}));"
                 f"return e.value;}})()")

    def goto(self, url, wait=4.0):
        self.send("Page.navigate", url=url)
        time.sleep(wait)

    def dump(self, path, what="html"):
        val = self.evf("d.documentElement.outerHTML") if what == "html" else self.frame_text()
        with open(path, "w", encoding="utf-8") as f:
            f.write(val or "")
        return len(val or "")


if __name__ == "__main__":
    s = SIS()
    print("target:", s.target.get("url", "")[:100])
    print("frame title:", s.frame_title())
    print("ICStateNum:", s.ic_state())
    print("busy:", s.is_busy())
