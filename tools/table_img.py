"""body.html 裡的每個表格各做成一張 WebP 圖（配官網前台：底 #0F0F0F、字 #FCFAEE、金色表頭），輸出到 <文章資料夾>/table_images/。
用法：python -I -X utf8 tools/table_img.py <專案資料夾>/articles/<文章slug>　需要本機有 Chrome、Python 的 Pillow。"""
import sys, re, subprocess, pathlib, tempfile
from PIL import Image

CHROME = next(p for p in [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
] if pathlib.Path(p).exists())

CSS = """
@font-face{font-family:'LatinQuote';src:local('Segoe UI');unicode-range:U+2018-201D}
html,body{margin:0;background:#0f0f0f}
body{font-family:'LatinQuote','Noto Sans TC','Microsoft JhengHei',sans-serif;padding:28px;width:1144px}
table{border-collapse:collapse;width:100%;font-size:22px;line-height:1.55;color:#FCFAEE}
th{background:#1c1a14;color:#EACD76;font-weight:700;text-align:left}
th,td{border:1px solid #3a3a3a;padding:14px 18px;vertical-align:top}
tr:nth-child(even) td{background:#161616}
td p{margin:0}
"""

d = pathlib.Path(sys.argv[1])
tables = re.findall(r"<table[^>]*>.*?</table>", (d / "body.html").read_text(encoding="utf-8"), flags=re.S)
out_dir = d / "table_images"; out_dir.mkdir(exist_ok=True)
tmp = pathlib.Path(tempfile.mkdtemp())
for i, t in enumerate(tables, 1):
    # 12 字以內的短格不換行，避免「123 / 2B」在窄欄斷行
    t = re.sub(r"<(td|th)>([^<]{1,12})</\1>", r'<\1 style="white-space:nowrap">\2</\1>', t)
    h = tmp / f"t{i}.html"
    h.write_text(f"<!doctype html><meta charset=utf-8><style>{CSS}</style><body>{t}</body>", encoding="utf-8")
    png = tmp / f"t{i}.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", "--window-size=1200,1400",
                    f"--screenshot={png}", h.as_uri()], check=True, capture_output=True)
    im = Image.open(png).convert("RGB")
    # 裁掉底部空白：找最後一列非背景像素
    px = im.load(); w, hgt = im.size; bottom = hgt
    for y in range(hgt - 1, 0, -1):
        if any(sum(px[x, y]) > 60 for x in range(0, w, 8)):
            bottom = min(hgt, y + 56); break
    im = im.crop((0, 0, w, bottom))
    out = out_dir / f"table{i}.webp"
    for q in (85, 80, 75, 70):
        im.save(out, "WEBP", quality=q, method=6)
        if out.stat().st_size < 150 * 1024: break
    print(out.name, im.size, round(out.stat().st_size / 1024, 1), "KB")
