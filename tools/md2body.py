"""GitBook .md 原文 -> 官網素材（original.md、body.html、meta.json、images/），並把這幾篇併進 index.csv。
用法：python -I -X utf8 tools/md2body.py <專案資料夾> <md資料夾> <slug> [<slug> ...]
- <md資料夾> 裡要有 <slug>.md（GitBook 頁面網址加 .md 抓下來的原文）。
- slug 要在 <專案資料夾>/文章清單.csv，範圍是「搬」；描述欄要跟原文標題下一行一致（沒描述就留空）。
- 已有 body.html 的篇會停下來，不覆蓋（舊篇的 body.html 可能已手改過連結和格式）。
轉換規則照專案的 任務說明.md。轉完接 README「新文章的完整順序」第 0 步。"""
import csv, html, io, json, re, sys, time
from pathlib import Path
import requests
from PIL import Image

if len(sys.argv) < 4:
    sys.exit(__doc__)
ROOT = Path(sys.argv[1])
ART = ROOT / "articles"
MDDIR = Path(sys.argv[2])
SLUGS = sys.argv[3:]
LIMIT = 150 * 1024
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"

TAG = re.compile(r"</?[a-zA-Z][^<>]*>")

# ---------- inline ----------
def inline(s):
    keep = []
    def hold(x):
        keep.append(x); return f"\x00{len(keep)-1}\x00"
    s = re.sub(r"`([^`]+)`", lambda m: hold("<code>" + html.escape(html.unescape(m.group(1)), False) + "</code>"), s)
    def link(m):
        text, url = m.group(1), m.group(2)
        return hold(f'<a href="{html.escape(html.unescape(url))}">') + text + hold("</a>")
    s = re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", link, s)
    s = TAG.sub(lambda m: hold(m.group(0)), s)
    s = html.escape(html.unescape(s), False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"(?<![A-Za-z0-9_])_(?!\s)(.+?)(?<!\s)_(?![A-Za-z0-9_])", r"<em>\1</em>", s)
    while "\x00" in s:
        s = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], s)
    return s

def para(lines):
    out = []
    for i, l in enumerate(lines):
        l = l.strip()
        last = i == len(lines) - 1
        if l.endswith("\\") and not last:
            out.append(inline(l[:-1]) + "<br>")
        else:
            out.append(inline(l.rstrip("\\")) + ("" if last else "\n"))
    return "<p>" + "".join(out) + "</p>"

# ---------- block ----------
class Ctx:
    def __init__(s, slug):
        s.slug, s.imgs, s.hint, s.stepper, s.details = slug, [], 0, 0, 0

def figure(line, ctx):
    src = re.search(r'<img[^>]*src="([^"]+)"', line).group(1)
    alt = re.search(r'<img[^>]*alt="([^"]*)"', line)
    alt = html.unescape(alt.group(1)) if alt else ""
    cap = re.search(r"<figcaption>(.*?)</figcaption>", line, re.S)
    cap = cap.group(1).strip() if cap else ""
    cap = re.sub(r"^<p>(.*)</p>$", r"\1", cap, flags=re.S).strip()
    ctx.imgs.append(html.unescape(src))
    name = f"images/{len(ctx.imgs):02d}.webp"
    alttext = html.unescape(TAG.sub("", cap)).strip() or alt
    out = [f'<img src="{name}" alt="{html.escape(alttext)}">']
    if cap:
        out.append("<p>" + inline(cap) + "</p>")
    return out

def collect(lines, i, end_pat, start_pat=None):
    """回傳 (內部行, 結束後索引)，支援同名巢狀。"""
    depth, j, inner = 1, i, []
    while j < len(lines):
        l = lines[j]
        if start_pat and re.match(start_pat, l.strip()):
            depth += 1
        elif re.match(end_pat, l.strip()):
            depth -= 1
            if depth == 0:
                return inner, j + 1
        inner.append(l); j += 1
    raise ValueError(f"找不到結尾 {end_pat}")

LIST_RE = re.compile(r"^(\s*)([*+-]|\d+\.)\s+(.*)$")
TROW = re.compile(r"^\s*\|")
TSEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")

def split_row(l):
    l = l.strip()
    if l.startswith("|"): l = l[1:]
    if l.endswith("|"): l = l[:-1]
    cells, cur, k = [], "", 0
    while k < len(l):
        if l[k] == "\\" and k + 1 < len(l) and l[k+1] == "|":
            cur += "|"; k += 2; continue
        if l[k] == "|":
            cells.append(cur); cur = ""
        else:
            cur += l[k]
        k += 1
    cells.append(cur)
    return [c.strip() for c in cells]

def blocks(lines, ctx):
    out, i, n = [], 0, len(lines)
    while i < n:
        raw = lines[i]; l = raw.strip()
        if not l:
            i += 1; continue
        if l.startswith("```"):
            j = i + 1; code = []
            while j < n and not lines[j].strip().startswith("```"):
                code.append(lines[j]); j += 1
            out.append("<pre><code>" + html.escape("\n".join(code), False) + "</code></pre>")
            i = j + 1; continue
        m = re.match(r'\{%\s*hint\s+style="(\w+)"\s*%\}', l)
        if m:
            inner, i = collect(lines, i + 1, r"\{%\s*endhint\s*%\}")
            ctx.hint += 1
            label = "注意：" if m.group(1) in ("info", "success") else "警告："
            sub = blocks(inner, ctx)
            if sub and sub[0].startswith("<p>"):
                sub[0] = f"<p><strong>{label}</strong>" + sub[0][3:]
            else:
                sub.insert(0, f"<p><strong>{label}</strong></p>")
            out += sub; continue
        if re.match(r"\{%\s*stepper\s*%\}", l):
            inner, i = collect(lines, i + 1, r"\{%\s*endstepper\s*%\}", r"\{%\s*stepper\s*%\}")
            ctx.stepper += 1; k, num = 0, 0
            while k < len(inner):
                if re.match(r"\{%\s*step\s*%\}", inner[k].strip()):
                    body, k = collect(inner, k + 1, r"\{%\s*endstep\s*%\}", r"\{%\s*step\s*%\}")
                    num += 1
                    h = next((x for x, t in enumerate(body) if re.match(r"^#{1,6}\s", t.strip())), None)
                    if h is None or any(t.strip() for t in body[:h]):
                        out.append(f"<h3>步驟 {num}：</h3>")
                        out += blocks(body, ctx)
                    else:
                        title = re.sub(r"^#{1,6}\s+", "", body[h].strip())
                        out.append(f"<h3>步驟 {num}：{inline(title)}</h3>")
                        out += blocks(body[h+1:], ctx)
                elif inner[k].strip():
                    raise ValueError(f"stepper 內有 step 以外的內容：{inner[k]!r}")
                else:
                    k += 1
            continue
        if l.startswith("<details"):
            inner, i = collect(lines, i + 1, r"</details>", r"<details")
            ctx.details += 1
            text = "\n".join(inner)
            sm = re.search(r"<summary>(.*?)</summary>", text, re.S)
            out.append(f"<h3>{inline(sm.group(1).strip())}</h3>")
            rest = (text[:sm.start()] + text[sm.end():]).split("\n")
            out += blocks(rest, ctx); continue
        if l.startswith("<figure"):
            j = i; buf = l
            while "</figure>" not in buf:
                j += 1; buf += "\n" + lines[j]
            out += figure(buf, ctx); i = j + 1; continue
        if l.startswith("<table"):
            j = i; buf = [raw]
            while "</table>" not in "\n".join(buf):
                j += 1; buf.append(lines[j])
            out.append("\n".join(buf).strip()); i = j + 1; continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", l)
        if m:
            lv, t = len(m.group(1)), inline(m.group(2))
            if lv <= 3: out.append(f"<h2>{t}</h2>")
            elif lv == 4: out.append(f"<h3>{t}</h3>")
            else: out.append(f"<p><strong>{t}</strong></p>")
            i += 1; continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", l):
            out.append("<hr>"); i += 1; continue
        if TROW.match(raw) and i + 1 < n and TSEP.match(lines[i+1]) and "-" in lines[i+1]:
            head = split_row(raw); j = i + 2; rows = []
            while j < n and TROW.match(lines[j]):
                rows.append(split_row(lines[j])); j += 1
            t = ["<table>", "<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead>", "<tbody>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t += ["</tbody>", "</table>"]
            out.append("\n".join(t)); i = j; continue
        if l.startswith(">"):
            j = i; q = []
            while j < n and lines[j].strip().startswith(">"):
                q.append(re.sub(r"^\s*>\s?", "", lines[j])); j += 1
            out.append("<blockquote>" + "".join(blocks(q, ctx)) + "</blockquote>"); i = j; continue
        m = LIST_RE.match(raw)
        if m:
            ordered = m.group(2)[-1] == "."
            start = int(m.group(2)[:-1]) if ordered else 1
            items, j = [], i
            while j < n:
                mm = LIST_RE.match(lines[j])
                if mm and (mm.group(2)[-1] == ".") == ordered:
                    items.append([mm.group(3)]); j += 1
                elif lines[j].strip() and items and not LIST_RE.match(lines[j]) and lines[j].startswith((" ", "\t")):
                    items[-1].append(lines[j].strip()); j += 1
                elif not lines[j].strip():
                    k = j
                    while k < n and not lines[k].strip(): k += 1
                    nm = LIST_RE.match(lines[k]) if k < n else None
                    if nm and (nm.group(2)[-1] == ".") == ordered:
                        j = k
                    else:
                        break
                else:
                    break
            tag = "ol" if ordered else "ul"
            st = f' start="{start}"' if ordered and start != 1 else ""
            lis = "".join("<li>" + "<br>".join(inline(x.rstrip("\\")) for x in it) + "</li>" for it in items)
            out.append(f"<{tag}{st}>{lis}</{tag}>"); i = j; continue
        # paragraph
        j = i; buf = []
        while j < n and lines[j].strip() and not is_block_start(lines, j):
            buf.append(lines[j]); j += 1
        if not buf:
            raise ValueError(f"無法辨識：{raw!r}")
        out.append(para(buf)); i = j
    return out

def is_block_start(lines, j):
    l = lines[j].strip(); raw = lines[j]
    return bool(l.startswith(("```", "{%", "<details", "<figure", "<table", ">", "</details"))
                or re.match(r"^#{1,6}\s", l) or LIST_RE.match(raw)
                or (TROW.match(raw) and j + 1 < len(lines) and TSEP.match(lines[j+1]) and "-" in lines[j+1]))

# ---------- images ----------
def get(url):
    for k in range(4):
        try:
            t0 = time.time(); buf = bytearray()
            with S.get(url, timeout=(10, 20), stream=True) as r:
                r.raise_for_status()
                for chunk in r.iter_content(65536):
                    buf += chunk
                    if time.time() - t0 > 90: raise TimeoutError("超過 90 秒")
            return bytes(buf)
        except Exception as e:
            print("  retry", k, e); time.sleep(2 + k * 2)
    raise RuntimeError(f"下載失敗 {url}")

def to_webp(data, dest):
    im = Image.open(io.BytesIO(data))
    note = im.format
    if getattr(im, "n_frames", 1) > 1:
        note += f" 動畫{im.n_frames}格→取第1格"
    im.seek(0)
    im = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA", "PA") or "transparency" in im.info else im.convert("RGB")
    def enc(img, q):
        b = io.BytesIO(); img.save(b, "WEBP", quality=q, method=6); return b.getvalue()
    for q in (80, 75, 70, 65, 60):
        out = enc(im, q)
        if len(out) <= LIMIT:
            dest.write_bytes(out); return f"{note} {im.size[0]}x{im.size[1]} q{q} {len(out)//1024}KB"
    w = im.size[0]
    if w > 1280:
        im = im.resize((1280, round(im.size[1] * 1280 / w)), Image.LANCZOS)
    out = enc(im, 60)
    dest.write_bytes(out)
    return f"{note} 縮{w}→{im.size[0]} q60 {len(out)//1024}KB" + (" 仍超過" if len(out) > LIMIT else "")

# ---------- main ----------
def main():
    with open(ROOT / "文章清單.csv", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["slug"] in SLUGS]
    miss = set(SLUGS) - {r["slug"] for r in rows}
    assert not miss, f"文章清單.csv 找不到：{', '.join(sorted(miss))}"
    for r in rows:
        assert not (ART / r["slug"] / "body.html").exists(), f"{r['slug']} 已有 body.html，不覆蓋"
    index = []
    for r in rows:
        slug = r["slug"]; d = ART / slug; (d / "images").mkdir(parents=True, exist_ok=True)
        raw = (MDDIR / f"{slug}.md").read_bytes()
        (d / "original.md").write_bytes(raw)
        md = raw.decode("utf-8")
        L = md.split("\n")
        L = [x.rstrip("\r") for x in L]
        k = 0
        if L and L[0].startswith("> For the complete documentation index"): k = 1
        while k < len(L) and (not L[k].strip() or L[k].strip() == "---"): k += 1
        assert re.match(r"^#\s", L[k]), (slug, L[k])
        title = re.sub(r"\\([_*\[\]])", r"\1", re.sub(r"^#\s+", "", L[k]).strip()); k += 1
        while k < len(L) and not L[k].strip(): k += 1
        desc = ""
        if r["描述"].strip() and L[k].strip() == r["描述"].strip():
            desc = L[k].strip(); k += 1
        elif r["描述"].strip():
            raise ValueError(f"{slug} 描述句與清單不符：{L[k]!r}")
        ctx = Ctx(slug)
        body = "\n".join(blocks(L[k:], ctx)) + "\n"
        (d / "body.html").write_text(body, encoding="utf-8")
        for idx, url in enumerate(ctx.imgs, 1):
            dest = d / "images" / f"{idx:02d}.webp"
            if dest.exists(): continue
            print(" ", slug, idx, to_webp(get(url), dest))
        hrefs = re.findall(r'<a[^>]+href="([^"]+)"', body)
        hrefs = [html.unescape(h) for h in hrefs]
        uniq = lambda xs: list(dict.fromkeys(xs))
        gb = uniq(h for h in hrefs if "douzo.gitbook.io" in h or "/douzo-docs/" in h)
        sl = uniq(h for h in hrefs if "link.douzo01.com" in h)
        meta = {"title": title, "description": desc, "gitbook_url": r["GitBook網址"], "folder": r["GitBook資料夾"],
                "slug": slug,
                "h2_count": len(re.findall(r"<h2[\s>]", body)), "h3_count": len(re.findall(r"<h3[\s>]", body)),
                "table_count": len(re.findall(r"<table", body)), "hint_count": ctx.hint,
                "stepper_count": ctx.stepper, "details_count": ctx.details, "image_count": len(ctx.imgs),
                "gitbook_links": gb, "short_links": sl}
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        index.append([slug, title, r["GitBook資料夾"], desc, meta["h2_count"], meta["h3_count"], meta["table_count"],
                      meta["image_count"], ctx.hint, ctx.stepper, ctx.details, len(gb), len(sl)])
        print(slug, "ok", {k2: meta[k2] for k2 in ("h2_count", "h3_count", "table_count", "image_count", "hint_count", "stepper_count", "details_count")})
    with open(ROOT / "index.csv", encoding="utf-8-sig", newline="") as f:
        old = list(csv.reader(f))
    done = {x[0] for x in index}
    keep = [old[0]] + [x for x in old[1:] if x and x[0] not in done]
    with open(ROOT / "index.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerows(keep)
        w.writerows(index)

if __name__ == "__main__":
    main()
