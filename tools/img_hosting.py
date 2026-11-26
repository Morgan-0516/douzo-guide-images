"""一篇文章的圖片放上 GitHub（jsDelivr 網址），更新對照表，產生換好網址的內文。
用法：python -I -X utf8 tools/img_hosting.py <專案資料夾>/articles/<文章slug>（在哪個資料夾執行都可以）
- 素材正本：<文章資料夾>/images/NN.webp（內文圖）、table_images/tableN.webp（表格圖，先跑 table_img.py）
- 放到 repo：<分類slug>/<文章slug>/imgNN.webp、tableN.webp（分類取 <專案資料夾>/文章清單.csv「官網分類Slug(建議)」，清單沒有這篇就停）
- 對照表：repo 根目錄 圖片對照表.csv，網址只記在這裡；之後搬家整棵樹原樣搬、換網址開頭即可
- 產出：<文章資料夾>/body_final.html（整段貼進後台繁中分頁）
- 每次執行整篇圖片的網址版本都會變，所以要整段重貼 body_final.html"""
import sys, re, csv, html, shutil, subprocess, pathlib, urllib.request

REPO = pathlib.Path(__file__).resolve().parents[1]
GH = "Morgan-0516/douzo-guide-images"
MAP = REPO / "圖片對照表.csv"
COLS = ["分類", "文章", "檔名", "類型", "位置", "圖說", "網址"]
TRAILER = ""

d = pathlib.Path(sys.argv[1]).resolve()
slug = d.name
rows = list(csv.DictReader(open(d.parents[1] / "文章清單.csv", encoding="utf-8-sig")))
cat = next((r["官網分類Slug(建議)"] for r in rows if r["slug"] == slug), "")
if not cat:
    sys.exit(f"文章清單.csv 找不到 {slug}，或它的「官網分類Slug(建議)」是空的，先補好再跑")


def git(*a):
    return subprocess.run(["git", "-C", str(REPO), *a], check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


# 1. 複製素材到 repo
dest = REPO / cat / slug
if dest.exists():
    shutil.rmtree(dest)
dest.mkdir(parents=True)
for f in sorted((d / "images").glob("*.webp")):
    shutil.copy2(f, dest / f"img{f.stem}.webp")
for f in sorted((d / "table_images").glob("table*.webp")):
    shutil.copy2(f, dest / f.name)
git("add", "-A")
if git("status", "--porcelain"):
    git("commit", "-q", "-m", f"Images for {cat}/{slug}" + TRAILER)
    git("push", "-q")
ver = git("rev-parse", "--short", "HEAD")
base = f"https://cdn.jsdelivr.net/gh/{GH}@{ver}/{cat}/{slug}/"

# 2. 內文：圖片換網址、表格換成表格圖，同時記下每張圖的位置
src = (d / "body.html").read_text(encoding="utf-8")
entries, heading, tno = [], "", 0


def sub(m):
    global heading, tno
    t = m.group(0)
    if t.startswith("<h"):
        heading = re.sub(r"<[^>]+>", "", t).strip()
        return t
    if t.startswith("<img"):
        n = re.search(r'src="images/(\d+)\.webp"', t).group(1)
        alt = html.unescape(re.search(r'alt="([^"]*)"', t).group(1)).lstrip("▲ ").strip()
        name, kind = f"img{n}.webp", "內文圖"
    else:
        tno += 1
        name, kind, alt = f"table{tno}.webp", "表格圖", heading
    entries.append(dict(zip(COLS, [cat, slug, name, kind, heading, alt, base + name])))
    return f'<img src="{base + name}" alt="{html.escape(alt)}">'


out = re.sub(r"<h[23]>.*?</h[23]>|<img [^>]*>|<table[^>]*>.*?</table>", sub, src, flags=re.S)
# 刪掉標籤之間的換行，<pre> 裡的換行要留著（流程圖、對齊排版）
out = "".join(p if p.lower().startswith("<pre") else p.replace("\n", "")
              for p in re.split(r"(<pre\b.*?</pre>)", out, flags=re.S | re.I))
(d / "body_final.html").write_text(out, encoding="utf-8")

# 3. 對照表：換掉這篇的列
old = list(csv.DictReader(open(MAP, encoding="utf-8-sig"))) if MAP.exists() else []
keep = [r for r in old if not (r["分類"] == cat and r["文章"] == slug)]
with open(MAP, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, COLS)
    w.writeheader()
    w.writerows(sorted(keep + entries, key=lambda r: (r["分類"], r["文章"], r["檔名"])))
git("add", "-A")
if git("status", "--porcelain"):
    git("commit", "-q", "-m", f"Update 圖片對照表 for {cat}/{slug}" + TRAILER)
    git("push", "-q")

# 4. 確認沒登入也抓得到
bad = 0
for e in entries:
    try:
        with urllib.request.urlopen(e["網址"], timeout=30) as r:
            ok = r.status == 200 and r.headers.get_content_type() == "image/webp"
    except Exception:
        ok = False
    bad += not ok
    print("OK " if ok else "BAD", e["檔名"], e["位置"])
print(f"{cat}/{slug} @{ver}: {len(entries)} 張, 失敗 {bad}")
sys.exit(1 if bad else 0)
