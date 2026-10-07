"""Report the live SIS browser state: are we logged in, and what's on screen?"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp  # noqa: E402
from browser_launch import PORT, SIS_URL  # noqa: E402


def connect():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
        targets = json.load(r)
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        raise RuntimeError("no page target")
    # prefer a SIS tab
    p = next((t for t in pages if "sis.cuhk.edu.cn" in t.get("url", "")), pages[0])
    import websocket
    ws = websocket.create_connection(p["webSocketDebuggerUrl"], timeout=60,
                                     max_size=200 * 1024 * 1024)
    return ws, p


class Conn:
    def __init__(self):
        self.ws, self.target = connect()
        self._id = 0

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
            return f"<JSERR {r['exceptionDetails'].get('text')}>"
        return r.get("result", {}).get("value")

    def frames(self):
        """Return the frame tree as a flat list of (frameId, url)."""
        def walk(node, out):
            f = node.get("frame", {})
            out.append((f.get("id"), f.get("url", ""), f.get("name", "")))
            for c in node.get("childFrames", []) or []:
                walk(c, out)
            return out
        tree = self.send("Page.getFrameTree")
        return walk(tree.get("frameTree", {}), [])


if __name__ == "__main__":
    c = Conn()
    print("target url :", c.target.get("url", "")[:130])
    print("title      :", c.ev("document.title"))
    print("location   :", c.ev("location.href")[:150])
    body = c.ev("document.body ? document.body.innerText.slice(0,600) : ''")
    print("--- visible text ---")
    print(body)
    print("--- frames ---")
    for fid, url, name in c.frames():
        print(f"   name={name!r:20s} {url[:110]}")
