"""官網指南文章驗收：只讀前台和公開 API，只出報表，不改任何東西。
用法：python -I -X utf8 tools/site_check.py <專案資料夾> [<slug> ...] [--live]
- 不給 slug：檢查 文章清單.csv 裡範圍是「搬」的全部文章。
- --live：把「還沒發布」也算 FAIL（整批上線後用）。不加時，草稿只查第 1 層，第 2 層標「未發布，略過」。
輸出：<專案資料夾>/前台檢查報告.md。有 FAIL 結束碼 1，沒有回 0。
查什麼（對應專案 CLAUDE.md「完成定義」）：
- 第 1 層（後台存的值，讀公開 API /api/articles/<slug>）：文章存在、分類、標題、摘要、SEO 標題與描述（有填、長度、不含破折號）、
  封面（不是預設圖、抓得到）、Alt、只有繁中有內文、內文的小標／清單／連結／圖片數量和圖片網址跟 body_final.html 一致。
- 第 2 層（發布後）：前台網址 200、<title>／description 是不是全站通用版、robots 有沒有 noindex；
  內文每張圖 200 且是圖片；每條連結最後狀態 < 400，連到 /guide/ 的那篇要已發布。
- 機器查不到、要人看的：手機寬 390 看表格圖、列表卡片和分類頁。報表最後列出來。
"""
import csv, html, json, re, sys, time
from html.parser import HTMLParser
from pathlib import Path
import requests

SITE = "https://douzo01.com"
GENERIC_TITLE = "Douzo - web3 智能放貸平台"
UA = {"User-Agent": "Mozilla/5.0 (site_check; read-only)"}
S = requests.Session(); S.headers.update(UA)
DASH = re.compile(r"——|—|－－")


class Counter(HTMLParser):
    def __init__(s):
        super().__init__(); s.n = {"h2": 0, "h3": 0, "li": 0, "a": 0, "img": 0}; s.imgs = []; s.links = []
    def handle_starttag(s, tag, attrs):
        a = dict(attrs)
        if tag in s.n: s.n[tag] += 1
        if tag == "img" and a.get("src"): s.imgs.append(html.unescape(a["src"]))
        if tag == "a" and a.get("href"): s.links.append(html.unescape(a["href"]))


def parse(h):
    c = Counter(); c.feed(h or ""); return c


def get(url, **kw):
    for k in range(3):
        try:
            return S.get(url, timeout=20, **kw)
        except requests.RequestException as e:
            err = e; time.sleep(1 + k)
    raise err


_api_cache = {}
def api(slug):
    if slug not in _api_cache:
        r = get(f"{SITE}/api/articles/{slug}")
        try:
            j = r.json()
        except ValueError:
            j = {}
        _api_cache[slug] = j.get("content") if r.status_code == 200 and j.get("code") == 200 else None
    return _api_cache[slug]


_url_cache = {}
def check_url(url, want_image=False):
    """回傳 (ok, 說明)。"""
    key = (url, want_image)
    if key in _url_cache: return _url_cache[key]
    try:
        r = get(url, allow_redirects=True, stream=True)
        r.close()
        final, code, ctype = r.url, r.status_code, r.headers.get("content-type", "")
        if code >= 400:
            res = (False, f"{code}")
        elif want_image and not ctype.startswith("image/"):
            res = (False, f"{code} 不是圖片（{ctype}）")
        else:
            res = (True, f"{code}" + (f" → {final}" if final.rstrip("/") != url.rstrip("/") else ""))
    except requests.RequestException as e:
        res = (False, f"連不上：{type(e).__name__}")
    _url_cache[key] = res
    return res


def check(row, proj, live):
    slug, cat = row["slug"], row["官網分類Slug(建議)"]
    out = []  # (層, 等級, 項目, 說明)
    add = lambda lvl, layer, item, msg="": out.append((layer, lvl, item, msg))
    c = api(slug)
    if not c:
        add("FAIL", 1, "後台有這篇", "公開 API 查不到，還沒建或 slug 不同")
        return out, False
    pub = bool(c.get("is_published"))
    # ---- 第 1 層 ----
    got_cat = (c.get("category") or {}).get("slug")
    add("OK" if got_cat == cat else "FAIL", 1, "分類", f"{got_cat}（應為 {cat}）")
    t = (c.get("title") or {}).get("zh_TW") or ""
    add("OK" if t.strip() == row["標題"].strip() else "WARN", 1, "標題", t if t.strip() == row["標題"].strip() else f"{t}（清單：{row['標題']}）")
    d = (c.get("description") or {}).get("zh_TW") or ""
    add("OK" if d.strip() else "FAIL", 1, "摘要", d[:40] or "空")
    st = (c.get("seo_title") or {}).get("zh_TW") or ""
    sd = (c.get("seo_description") or {}).get("zh_TW") or ""
    add("FAIL" if not st else ("WARN" if len(st) > 60 or DASH.search(st) else "OK"), 1, "SEO 標題", f"{len(st)} 字 {st}")
    add("FAIL" if not sd else ("WARN" if len(sd) > 160 or DASH.search(sd) else "OK"), 1, "Meta Description", f"{len(sd)} 字")
    img = c.get("img") or ""
    if not img or "default" in img:
        add("FAIL", 1, "封面", img or "空")
    else:
        ok, msg = check_url(SITE + img if img.startswith("/") else img, want_image=True)
        add("OK" if ok else "FAIL", 1, "封面", f"{img} {msg}")
    add("OK" if (c.get("img_alt") or "").strip() else "WARN", 1, "封面 Alt", c.get("img_alt") or "空")
    # 空的編輯器會存成 <p></p>，去掉標籤後沒字、也沒有圖才算空
    others = [k for k, v in (c.get("content") or {}).items()
              if k != "zh_TW" and (re.sub(r"<[^>]+>|&nbsp;|\s", "", v or "") or "<img" in (v or ""))]
    add("FAIL" if others else "OK", 1, "只有繁中有內文", ",".join(others) or "")
    body = (c.get("content") or {}).get("zh_TW") or ""
    local = proj / "articles" / slug / "body_final.html"
    got = parse(body)
    if local.exists():
        want = parse(local.read_text(encoding="utf-8"))
        diff = [f"{k} {got.n[k]}/{want.n[k]}" for k in want.n if got.n[k] != want.n[k]]
        add("FAIL" if diff else "OK", 1, "內文結構（後台/本機）", "；".join(diff) or str(want.n))
        miss = [u for u in want.imgs if u not in got.imgs]
        add("FAIL" if miss else "OK", 1, "內文圖片網址", f"少 {len(miss)} 張：{miss[0]}" if miss else f"{len(want.imgs)} 張")
        lmiss = [u for u in want.links if u not in got.links]
        add("FAIL" if lmiss else "OK", 1, "內文連結網址", f"少 {len(lmiss)} 條：{lmiss[0]}" if lmiss else f"{len(want.links)} 條")
    else:
        add("WARN", 1, "內文結構", "本機沒有 body_final.html，無法比對")
    # ---- 第 2 層 ----
    if not pub:
        add("FAIL" if live else "SKIP", 2, "已發布", "還沒發布" + ("" if live else "，第 2 層略過"))
        return out, pub
    add("OK", 2, "已發布", c.get("published_at") or "")
    if c.get("is_pinned"):
        add("WARN", 2, "置頂", "有開置頂，會進前台熱門文章")
    page = f"{SITE}/guide/{cat}/{slug}"
    r = get(page)
    if r.status_code != 200:
        add("FAIL", 2, "前台網址", f"{r.status_code} {page}")
    else:
        h = r.text
        title = html.unescape((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]).strip()
        m = re.search(r'<meta name="robots" content="([^"]*)"', h)
        robots = m.group(1) if m else ""
        m = re.search(r'<meta name="description" content="([^"]*)"', h)
        desc = html.unescape(m.group(1)) if m else ""
        add("OK" if title and title != GENERIC_TITLE else "FAIL", 2, "前台 <title>", title + ("（全站通用版，工程端）" if title == GENERIC_TITLE else ""))
        add("OK" if desc and (desc == sd or desc == d) else "FAIL", 2, "前台 description", desc[:40] + ("" if desc in (sd, d) else "（不是後台值，工程端）"))
        add("FAIL" if "noindex" in robots else "OK", 2, "前台 robots", robots + ("（工程端）" if "noindex" in robots else ""))
    for u in dict.fromkeys(got.imgs):
        ok, msg = check_url(u, want_image=True)
        if not ok: add("FAIL", 2, "內文圖片", f"{u} {msg}")
    add("OK", 2, "內文圖片狀態", f"{len(set(got.imgs))} 張查過")
    for u in dict.fromkeys(got.links):
        m = re.match(r"https://douzo01\.com/guide/([^/]+)/([^/?#]+)", u)
        if m:
            t2 = api(m.group(2))
            if not t2: add("FAIL", 2, "站內連結", f"{u} 查不到這篇")
            elif not t2.get("is_published"): add("FAIL" if live else "WARN", 2, "站內連結", f"{u} 目標還沒發布")
            elif (t2.get("category") or {}).get("slug") != m.group(1): add("FAIL", 2, "站內連結", f"{u} 分類不對（實際 {t2['category']['slug']}）")
            continue
        ok, msg = check_url(u)
        if not ok: add("FAIL", 2, "連結", f"{u} {msg}")
        elif "gitbook.io" in msg: add("WARN", 2, "連結", f"{u} 最後落在 GitBook：{msg}")
    add("OK", 2, "內文連結狀態", f"{len(set(got.links))} 條查過")
    return out, pub


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args: sys.exit(__doc__)
    live = "--live" in sys.argv
    proj = Path(args[0]); only = set(args[1:])
    rows = [r for r in csv.DictReader(open(proj / "文章清單.csv", encoding="utf-8-sig"))
            if r["範圍"] == "搬" and (not only or r["slug"] in only)]
    if only - {r["slug"] for r in rows}:
        sys.exit(f"文章清單.csv 找不到：{', '.join(sorted(only - {r['slug'] for r in rows}))}")
    lines = [f"# 前台檢查報告（{time.strftime('%Y-%m-%d %H:%M')}{'，--live' if live else ''}）", "",
             "只讀前台和公開 API。FAIL 要處理；WARN 要人看一眼；SKIP 是還沒到那一層。", "",
             "| 文章 | 發布 | 第 1 層 | 第 2 層 |", "|---|---|---|---|"]
    detail, total_fail = [], 0
    for r in rows:
        res, pub = check(r, proj, live)
        f1 = sum(1 for x in res if x[0] == 1 and x[1] == "FAIL"); f2 = sum(1 for x in res if x[0] == 2 and x[1] == "FAIL")
        w = sum(1 for x in res if x[1] == "WARN")
        total_fail += f1 + f2
        cell = lambda f, layer: ("❌ " + str(f) if f else ("略過" if any(x[0] == layer and x[1] == "SKIP" for x in res) else "✅"))
        lines.append(f"| {r['slug']} | {'是' if pub else '否'} | {cell(f1, 1)} | {cell(f2, 2)}{f'（WARN {w}）' if w else ''} |")
        detail.append(f"## {r['slug']}")
        detail += [f"- {'❌' if lv == 'FAIL' else '⚠️' if lv == 'WARN' else '⏭' if lv == 'SKIP' else '✅'} 第{ly}層 {item}：{msg}" for ly, lv, item, msg in res]
        detail.append("")
        print(r["slug"], "FAIL", f1 + f2, "WARN", w)
    lines += ["", f"FAIL 合計 {total_fail}", "",
              "要人看（機器查不到）：手機寬 390 看表格圖不用左右滑；/guide 列表卡片有封面；分類按鈕點進去找得到這篇。", ""] + detail
    rep = proj / "前台檢查報告.md"
    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"報告：{rep}｜FAIL 合計 {total_fail}")
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
