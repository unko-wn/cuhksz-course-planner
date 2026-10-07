"""Dependency-free PDF text extractor for CUHK-SZ study-scheme PDFs.

Supports: PDF 1.5+ xref/object streams, FlateDecode, simple + CID fonts with
ToUnicode CMaps, and nested Form XObjects (where table cells often live).
"""
import re
import sys
import zlib


# ---------------------------------------------------------------- objects
def load(path):
    with open(path, "rb") as f:
        return f.read()


def decompress(header, raw):
    if raw is None:
        return None
    if b"FlateDecode" in header:
        for attempt in (lambda r: zlib.decompress(r),
                        lambda r: zlib.decompressobj().decompress(r)):
            try:
                return attempt(raw)
            except Exception:
                pass
        return None
    return raw


def parse_objstm(header, raw):
    d = decompress(header, raw)
    if not d:
        return {}
    mn = re.search(rb"/N\s+(\d+)", header)
    mf = re.search(rb"/First\s+(\d+)", header)
    if not mn or not mf:
        return {}
    n, first = int(mn.group(1)), int(mf.group(1))
    nums = d[:first].split()
    pairs = []
    for i in range(0, min(2 * n, len(nums) - 1), 2):
        try:
            pairs.append((int(nums[i]), int(nums[i + 1])))
        except ValueError:
            break
    out = {}
    for idx, (num, off) in enumerate(pairs):
        start = first + off
        end = first + pairs[idx + 1][1] if idx + 1 < len(pairs) else len(d)
        out[num] = (d[start:end], None)
    return out


def build_objects(data):
    """{objnum: (header_bytes, raw_stream_or_None)} spanning plain + ObjStm."""
    objs, objstms = {}, []
    for m in re.finditer(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b(.*?)(?:\r?\n)?endobj", data, re.S):
        num, body = int(m.group(1)), m.group(3)
        sm = re.search(rb"stream\r?\n", body)
        raw, header = None, body
        if sm:
            start = sm.end()
            end = body.find(b"endstream", start)
            if end == -1:
                end = len(body)
            raw = body[start:end]
            if raw.endswith(b"\r\n"):
                raw = raw[:-2]
            elif raw[-1:] in (b"\n", b"\r"):
                raw = raw[:-1]
            header = body[: sm.start()]
        if b"/ObjStm" in header:
            objstms.append((header, raw))
        else:
            objs.setdefault(num, (header, raw))
    for header, raw in objstms:
        for num, val in parse_objstm(header, raw).items():
            objs.setdefault(num, val)
    return objs


# ---------------------------------------------------------------- cmaps
def _utf16be(hexstr):
    try:
        b = bytes.fromhex(hexstr if len(hexstr) % 2 == 0 else "0" + hexstr)
        return b.decode("utf-16-be", "replace")
    except Exception:
        return ""


def parse_cmap(data):
    mapping = {}
    text = data.decode("latin-1", "replace")
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            mapping[int(src, 16)] = _utf16be(dst)
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for lo, hi, dst in re.findall(
                r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            base = int(dst, 16)
            for k in range(int(lo, 16), min(int(hi, 16), int(lo, 16) + 65535) + 1):
                mapping[k] = _utf16be(f"{base + (k - int(lo, 16)):04X}")
    return mapping


def collect_cmaps(objs):
    cm = {}
    for num, (header, raw) in objs.items():
        blob = raw
        if blob is None and header:
            blob = header
        elif raw is not None and not (b"beginbfchar" in raw or b"beginbfrange" in raw):
            blob = decompress(header, raw)
        if blob and (b"beginbfchar" in blob or b"beginbfrange" in blob):
            cm[num] = parse_cmap(blob)
    return cm


# ---------------------------------------------------------------- resources
def resolve(objs, token):
    m = re.match(rb"\s*(\d+)\s+\d+\s+R", token or b"")
    return objs.get(int(m.group(1))) if m else None


def dict_body(objs, ref):
    """Return the bytes of the dict a name may point to (inline or indirect)."""
    m = re.match(rb"\s*(\d+)\s+\d+\s+R", ref)
    if m:
        o = objs.get(int(m.group(1)))
        return o[0] if o else b""
    return ref


def font_ctx(objs, cmaps, res_body):
    """/Font entries -> {name: (cmap, two_byte)}"""
    out = {}
    fm = re.search(rb"/Font\s*<<(.*?)>>", res_body, re.S)
    if fm:
        pairs = re.findall(rb"/([A-Za-z0-9_.+-]+)\s+(\d+)\s+\d+\s+R", fm.group(1))
    else:
        fr = re.search(rb"/Font\s+(\d+)\s+\d+\s+R", res_body)
        fobj = objs.get(int(fr.group(1)))[0] if fr and objs.get(int(fr.group(1))) else b""
        pairs = re.findall(rb"/([A-Za-z0-9_.+-]+)\s+(\d+)\s+\d+\s+R", fobj)
    for name, ref in pairs:
        fnum = int(ref)
        cmap = cmaps.get(fnum)
        fobj = objs.get(fnum)
        two = False
        if fobj:
            fh = fobj[0]
            two = b"/Type0" in fh or b"Identity-H" in fh
            if cmap is None:
                tu = re.search(rb"/ToUnicode\s+(\d+)\s+\d+\s+R", fh)
                if tu:
                    cmap = cmaps.get(int(tu.group(1)))
        if cmap and max(cmap.keys(), default=0) > 255:
            two = True
        out[name.decode("latin-1")] = (cmap, two)
    return out


def xobject_ctx(objs, res_body):
    out = {}
    xm = re.search(rb"/XObject\s*<<(.*?)>>", res_body, re.S)
    if xm:
        for name, ref in re.findall(rb"/([A-Za-z0-9_.+-]+)\s+(\d+)\s+\d+\s+R", xm.group(1)):
            out[name.decode("latin-1")] = int(ref)
    return out


# ---------------------------------------------------------------- text ops
TOKEN = re.compile(rb"""
    (?P<str>\((?:\\.|[^\\()]|\((?:\\.|[^\\()])*\))*\))
  | (?P<hex><[0-9A-Fa-f\s]*>)
  | (?P<arr>\[|\])
  | (?P<name>/[^\s/\[\]<>()]+)
  | (?P<num>-?\d+\.?\d*)
  | (?P<op>[A-Za-z*'"]+)
""", re.X | re.S)

SIMPLE = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12, 0x28: 40, 0x29: 41, 0x5C: 92}


def unescape(s):
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == 0x5C and i + 1 < len(s):
            n = s[i + 1]
            if n in SIMPLE:
                out.append(SIMPLE[n]); i += 2; continue
            if 0x30 <= n <= 0x37:
                j, dig = i + 1, b""
                while j < len(s) and len(dig) < 3 and 0x30 <= s[j] <= 0x37:
                    dig += bytes([s[j]]); j += 1
                out.append(int(dig, 8) & 0xFF); i = j; continue
            out.append(n); i += 2; continue
        out.append(c); i += 1
    return bytes(out)


def decode_bytes(b, cmap, two):
    if two:
        codes = [int.from_bytes(b[i:i + 2], "big") for i in range(0, len(b) - 1, 2)]
        if cmap:
            return "".join(cmap.get(c, "") for c in codes)
        return "".join(chr(c) if c < 0x110000 else "" for c in codes)
    if cmap:
        return "".join(cmap.get(x, chr(x)) for x in b)
    return b.decode("latin-1", "replace")


def extract_content(content, fmap, xmap, objs, cmaps, depth=0, out=None):
    if out is None:
        out = []
    if depth > 6 or not content:
        return out
    cur = None
    pending = []
    arrstack = []
    for m in TOKEN.finditer(content):
        kind, val = m.lastgroup, m.group()
        if kind in ("name", "num"):
            pending.append(val); continue
        if kind == "arr":
            if val == b"[":
                arrstack.append([])
            elif arrstack:
                segs = arrstack.pop()
                if arrstack:
                    arrstack[-1].extend(segs)
                else:
                    out.append("".join(decode_bytes(s, *fmap.get(cur, (None, False)))
                                       for s in segs))
            continue
        if kind in ("str", "hex"):
            if kind == "str":
                b = unescape(val[1:-1])
            else:
                h = re.sub(rb"\s", b"", val[1:-1])
                if len(h) % 2:
                    h += b"0"
                b = bytes.fromhex(h.decode("latin-1")) if h else b""
            if arrstack:
                arrstack[-1].append(b)
            else:
                pending.append(b)
            continue
        if kind == "op":
            op = val.decode("latin-1")
            if op == "Tf":
                names = [p for p in pending if p.startswith(b"/")]
                if names:
                    cur = names[-1][1:].decode("latin-1")
            elif op in ("Tj", "'", '"'):
                segs = [p for p in pending if isinstance(p, bytes)]
                if segs:
                    out.append(decode_bytes(b"".join(segs), *fmap.get(cur, (None, False))))
            elif op == "TJ":
                pass  # handled by arrstack
            elif op == "Do":
                names = [p for p in pending if p.startswith(b"/")]
                if names:
                    nm = names[-1][1:].decode("latin-1")
                    ref = xmap.get(nm)
                    xo = objs.get(ref) if ref else None
                    if xo:
                        xh, xr = xo
                        if b"/Form" in xh or b"/Subtype/Form" in xh:
                            sub = decompress(xh, xr) or b""
                            res = re.search(rb"/Resources\s*<<(.*?)>>", xh, re.S)
                            res_body = res.group(1) if res else xh
                            rm = re.search(rb"/Resources\s+(\d+)\s+\d+\s+R", xh)
                            if rm and objs.get(int(rm.group(1))):
                                res_body = objs[int(rm.group(1))][0]
                            sf = font_ctx(objs, cmaps, res_body)
                            sx = xobject_ctx(objs, res_body)
                            extract_content(sub, sf or fmap, sx or xmap, objs, cmaps,
                                            depth + 1, out)
            pending = []
            continue
    return out


# ---------------------------------------------------------------- pages
def page_objects(objs):
    pages = []
    for num in sorted(objs):
        header = objs[num][0]
        if re.search(rb"/Type\s*/Page(?![sA-Za-z])", header):
            pages.append(num)
    return pages


def page_content(objs, header):
    cm = re.search(rb"/Contents\s+(\d+)\s+\d+\s+R", header)
    if cm:
        o = objs.get(int(cm.group(1)))
        return decompress(o[0], o[1]) or b"" if o else b""
    cms = re.search(rb"/Contents\s*\[(.*?)\]", header, re.S)
    if cms:
        buf = b""
        for ref in re.findall(rb"(\d+)\s+\d+\s+R", cms.group(1)):
            o = objs.get(int(ref))
            if o:
                buf += decompress(o[0], o[1]) or b""
        return buf
    return b""


def extract_pages(path):
    data = load(path)
    objs = build_objects(data)
    cmaps = collect_cmaps(objs)
    result = []
    for num in page_objects(objs):
        header = objs[num][0]
        res_body = header
        rm = re.search(rb"/Resources\s+(\d+)\s+\d+\s+R", header)
        if rm and objs.get(int(rm.group(1))):
            res_body = objs[int(rm.group(1))][0]
        fmap = font_ctx(objs, cmaps, res_body)
        xmap = xobject_ctx(objs, res_body)
        runs = extract_content(page_content(objs, header), fmap, xmap, objs, cmaps)
        result.append((num, runs))
    return result


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print("=" * 90)
        print(path)
        pages = extract_pages(path)
        print(f"pages: {len(pages)}")
        for num, runs in pages:
            text = "".join(runs)
            print(f"\n--- page obj {num} ({len(text)} chars) ---")
            print(re.sub(r"\s+", " ", text))
