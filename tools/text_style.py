"""檢查／修正文章 HTML 的 DOUZO 文字規範。
用法：python -I -X utf8 tools/text_style.py <專案資料夾>/articles/<文章slug> [--fix] [--show N]

自動修（--fix 寫回 <文章資料夾>/body.html，之後要重跑 table_img.py、img_hosting.py）：
- 中文與英文、數字之間加半形空格；% 跟中文之間加空格；全形括號、標點緊鄰英數不加空格。
  中文和英數被 a、strong、b、em、i、u、span 標籤隔開也算，空格放在標籤外側。
- 全形英數和 ％ 改半形。
- 範圍：標籤之間的文字和 alt 屬性。pre、code、script、style 裡面不動。

只列出、不自動改：「...」（應為「……」）、「！！」、品牌寫法（Douzo、Doya）。

寫回前的保護：用另一套解析器（html.parser）比對修前修後，標籤順序、alt 以外的屬性、
pre／code／script／style 裡的文字只要有一點不同，就不寫並結束碼 1。

不支援、遇到會停下來（結束碼 1）的寫法：屬性值裡有「>」、HTML 註解、pre／code／script／style 沒關。"""
import sys, re, pathlib
from html.parser import HTMLParser

CJK = "[㐀-䶿一-鿿]"
AN = "[A-Za-z0-9]"
RULES = [
    (re.compile(f"({CJK})({AN})"), r"\1 \2", "中文接英數沒空格"),
    (re.compile(f"({AN}|%)({CJK})"), r"\1 \2", "英數或 % 接中文沒空格"),
]
FLAGS = [
    (re.compile(r"\.{3,}"), "「...」應為「……」"),
    (re.compile(r"！！"), "連續驚嘆號"),
    (re.compile(r"\bDOUZO\b|\bdouzo\b(?![./@])"), "品牌寫法應為 Douzo"),
    (re.compile(r"\bDOYA\b|\bdoya\b(?![./-])"), "品牌寫法應為 Doya"),
]
FW = str.maketrans({chr(c): chr(c - 0xFEE0) for c in [0xFF05] + list(range(0xFF10, 0xFF1A)) + list(range(0xFF21, 0xFF3B)) + list(range(0xFF41, 0xFF5B))})
SKIP = {"pre", "code", "script", "style"}
INLINE = {"a", "strong", "b", "em", "i", "u", "span"}
TAGNAME = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9]*)")
ALT = re.compile(r"""((?<![\w-])alt\s*=\s*)("[^"]*"|'[^']*')""", re.I)


def stop(msg, code=1):
    sys.exit(f"{msg}\n用法：python -I -X utf8 tools/text_style.py <文章資料夾> [--fix] [--show N]" if code == 2 else msg)


# ---- 參數 ----
args = sys.argv[1:]
fix = "--fix" in args
show = 8
if "--show" in args:
    try:
        show = int(args[args.index("--show") + 1])
    except (IndexError, ValueError):
        stop("--show 後面要接數字", 2)
pos = [a for i, a in enumerate(args) if not a.startswith("--") and not (i and args[i - 1] == "--show")]
if len(pos) != 1:
    stop("要給一個文章資料夾", 2)
d = pathlib.Path(pos[0])
if not (d / "body.html").is_file():
    stop(f"找不到 {d / 'body.html'}", 2)
src = (d / "body.html").read_text(encoding="utf-8")

# ---- 不支援的寫法：停下來，不猜 ----
if "<!--" in src:
    stop(f"{d.name}: 有 HTML 註解，這支不處理，請手動看")
QTAG = re.compile(r"""</?[A-Za-z][^<>"']*(?:(?:"[^"]*"|'[^']*')[^<>"']*)*>""")
if any(">" in m.group(0)[:-1] for m in QTAG.finditer(src)):
    stop(f"{d.name}: 有屬性值含「>」，這支不處理，請手動看")

hits, flags = [], []


def fix_text(t):
    t2 = t.translate(FW)
    if t2 != t:
        hits.append(("全形英數或 ％", t[:40]))
    for rx, rep, why in RULES:
        for m in rx.finditer(t2):
            hits.append((why, t2[max(0, m.start() - 8):m.end() + 8]))
        t2 = rx.sub(rep, t2)
    return t2


# ---- 第一輪：切成文字／標籤，記下哪些在 pre/code/script/style 裡 ----
toks = re.split(r"(<[^>]*>)", src)  # 偶數位是文字，奇數位是標籤
inskip = [False] * len(toks)
depth = 0
for i, t in enumerate(toks):
    if i % 2:
        m = TAGNAME.match(t)
        if m and m.group(2).lower() in SKIP:
            depth = depth - 1 if m.group(1) else depth + 1
            if depth < 0:
                stop(f"{d.name}: </{m.group(2)}> 沒有對應的開頭，這支不處理")
            inskip[i] = True
            continue
    inskip[i] = depth > 0
if depth:
    stop(f"{d.name}: pre／code／script／style 沒關，這支不處理")

for i, t in enumerate(toks):
    if inskip[i] or not t:
        continue
    if i % 2:
        toks[i] = ALT.sub(lambda a: a.group(1) + a.group(2)[0] + fix_text(a.group(2)[1:-1]) + a.group(2)[-1], t)
    else:
        for rx, why in FLAGS:
            for f in rx.finditer(t):
                flags.append((why, t[max(0, f.start() - 8):f.end() + 8]))
        toks[i] = fix_text(t)

# ---- 第二輪：兩段文字只隔 inline 標籤時，接縫補空格（放在閉合標籤之後、開頭標籤之前）----
inserts = []
i = 0
while i < len(toks):
    if i % 2 == 0 and toks[i] and not inskip[i]:
        j, ok = i + 1, True
        while j < len(toks) and (j % 2 or toks[j] == ""):
            if j % 2:
                m = TAGNAME.match(toks[j])
                if inskip[j] or not m or m.group(2).lower() not in INLINE:
                    ok = False
                    break
            j += 1
        if ok and j < len(toks) and j > i + 1 and not inskip[j]:
            if re.fullmatch(f"{CJK}{AN}|(?:{AN}|%){CJK}", toks[i][-1] + toks[j][0]):
                run = list(range(i + 1, j, 2))
                closes = [k for k in run if toks[k].startswith("</")]
                inserts.append(closes[-1] + 1 if closes else run[0])
                hits.append(("標籤兩側中英沒空格", toks[i][-10:] + "｜" + toks[j][:10]))
        i = j if j > i else i + 1
    else:
        i += 1
for at in sorted(inserts, reverse=True):
    toks.insert(at, " ")
out = "".join(toks)


# ---- 保護：用 html.parser 比對修前修後，結構不能變 ----
class Shape(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.ev, self.depth = [], 0

    def handle_starttag(self, tag, attrs):
        self.ev.append(("start", tag, [(k, v) for k, v in attrs if k != "alt"]))
        if tag in SKIP:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        self.ev.append(("start", tag, [(k, v) for k, v in attrs if k != "alt"]))

    def handle_endtag(self, tag):
        self.ev.append(("end", tag))
        if tag in SKIP:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.ev.append(("raw", data))

    def handle_comment(self, data):
        self.ev.append(("comment", data))


def shape(s):
    p = Shape()
    p.feed(s)
    p.close()
    return p.ev


a, b = shape(src), shape(out)
if a != b:
    k = next((n for n, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    stop(f"{d.name}: 保護擋下，修完會動到標籤、屬性或程式碼區塊，沒寫回。\n  修前：{a[k] if k < len(a) else '（無）'}\n  修後：{b[k] if k < len(b) else '（無）'}")

print(f"{d.name}: 要改 {len(hits)} 處，要人看 {len(flags)} 處")
for why, ctx in hits[:show]:
    print("  改", why, "｜", ctx.replace("\n", " "))
for why, ctx in flags:
    print("  看", why, "｜", ctx.replace("\n", " "))
if fix and out != src:
    (d / "body.html").write_text(out, encoding="utf-8")
    print("  已寫回 body.html")
