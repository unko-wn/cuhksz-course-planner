"""Extract the authenticated SIS cookies from the live browser and save them."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sisui import SIS

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cookies.json")

if __name__ == "__main__":
    s = SIS()
    res = s.send("Network.getAllCookies")
    cookies = res.get("cookies", [])
    keep = [c for c in cookies if "cuhk.edu.cn" in c.get("domain", "")]
    print(f"total cookies: {len(cookies)}, cuhk.edu.cn cookies: {len(keep)}")
    for c in keep:
        print(f"   {c['name']:60s} domain={c['domain']:20s} len={len(c.get('value',''))} "
              f"httpOnly={c.get('httpOnly')} secure={c.get('secure')}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(keep, f, indent=1)
    print("\nsaved", OUT)
