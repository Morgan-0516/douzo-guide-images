"""檢查／修正文章 HTML 的 DOUZO 文字規範（只動文字和 alt，不動標籤、網址）。
用法：python -I -X utf8 tools/text_style.py <專案資料夾>/articles/<文章slug> [--fix] [--show N]
- 中文與英文、數字之間加半形空格；% 跟中文之間加空格；全形括號、標點緊鄰英數不加空格。
  中文和英數被 a、strong、b、em、i、u、span 標籤隔開也算，空格放在標籤外側。
- 一串 3 個以上的「.」改「……」；全形英數和 ％ 改半形。
- pre、code、script、style 裡面不動。
- 「！！」、品牌寫法（Douzo、Doya）只列出，不自動改。
--fix 會改寫 <文章資料夾>/body.html；之後要重跑 table_img.py、img_hosting.py。"""
import sys, re, pathlib

CJK = "[㐀-䶿一-鿿]"
AN = "[A-Za-z0-9]"
RULES = [
    (re.compile(f"({CJK})({AN})"), r"\1 \2", "中文接英數沒空格"),
    (re.compile(f"({AN}|%)({CJK})"), r"\1 \2", "英數或 % 接中文沒空格"),
    (re.compile(r"\.{3,}"), "……", "「...」應為「……」"),
]
FLAGS = [
    (re.compile(r"！！"), "連續驚嘆號"),
    (re.compile(r"\bDOUZO\b|\bdouzo\b(?![./@])"), "品牌寫法應為 Douzo"),
    (re.compile(r"\bDOYA\b|\bdoya\b(?![./-])"), "品牌寫法應為 Doya"),
]
FW = str.maketrans({chr(c): chr(c - 0xFEE0) for c in [0xFF05] + list(range(0xFF10, 0xFF1A)) + list(range(0xFF21, 0xFF3B)) + list(range(0xFF41, 0xFF5B))})
SKIP = {"pre", "code", "script", "style"}
INLINE = {"a", "strong", "b", "em", "i", "u", "span"}
TAG = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9]*)")
ALT = re.compile(r"""((?<![\w-])alt=)("[^"]*"|'[^']*')""")


def usage(msg):
    sys.exit(f"{msg}\n用法：python -I -X utf8 tools/text_style.py <文章資料夾> [--fix] [--show N]")


args = sys.argv[1:]
fix = "--fix" in args
show = 8
if "--show" in args:
    try:
        show = int(args[args.index("--show") + 1])
    except (IndexError, ValueError):
        usage("--show 後面要接數字")
pos = [a for i, a in enumerate(args) if not a.startswith("--") and not (i and args[i - 1] == "--show")]
if len(pos) != 1:
    usage("要給一個文章資料夾")
d = pathlib.Path(pos[0])
if not (d / "body.html").is_file():
    usage(f"找不到 {d / 'body.html'}")

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


src = (d / "body.html").read_text(encoding="utf-8")
toks = re.split(r"(<[^>]*>)", src)  # 偶數位是文字，奇數位是標籤
skip = 0
for i, t in enumerate(toks):
    if i % 2:
        m = TAG.match(t)
        if m and m.group(2).lower() in SKIP:
            skip += -1 if m.group(1) else 1
            skip = max(skip, 0)
        elif not skip:
            toks[i] = ALT.sub(lambda a: a.group(1) + a.group(2)[0] + fix_text(a.group(2)[1:-1]) + a.group(2)[-1], t)
    elif t and not skip:
        for rx, why in FLAGS:
            for f in rx.finditer(t):
                flags.append((why, t[max(0, f.start() - 8):f.end() + 8]))
        toks[i] = fix_text(t)

# 跨標籤：兩段文字中間只隔 inline 標籤時，接縫補空格，放在閉合標籤之後、開頭標籤之前
need = re.compile(f"(?:{CJK}|{AN}|%)$")
inserts = []
i = 0
while i < len(toks):
    if i % 2 == 0 and toks[i] and need.search(toks[i]):
        j, ok = i + 1, True
        while j < len(toks) and (j % 2 or toks[j] == ""):
            if j % 2:
                m = TAG.match(toks[j])
                if not m or m.group(2).lower() not in INLINE:
                    ok = False
                    break
            j += 1
        if ok and j < len(toks) and j > i + 1:
            a, b = toks[i][-1], toks[j][0]
            pair = a + b
            if re.fullmatch(f"{CJK}{AN}|(?:{AN}|%){CJK}", pair):
                run = list(range(i + 1, j, 2))
                closes = [k for k in run if toks[k].startswith("</")]
                at = closes[-1] + 1 if closes else run[0]
                inserts.append(at)
                hits.append(("標籤兩側中英沒空格", re.sub(r"<[^>]+>", "", "".join(toks[i:j + 1]))[-30:]))
        i = j if j > i else i + 1
    else:
        i += 1
for at in sorted(inserts, reverse=True):
    toks.insert(at, " ")
    toks.insert(at, "")  # 保持奇偶：插入一對（空標籤位、空格文字位）不影響輸出
out = "".join(toks)

print(f"{d.name}: 要改 {len(hits)} 處，要人看 {len(flags)} 處")
for why, ctx in hits[:show]:
    print("  改", why, "｜", ctx.replace("\n", " "))
for why, ctx in flags:
    print("  看", why, "｜", ctx.replace("\n", " "))
if fix and out != src:
    (d / "body.html").write_text(out, encoding="utf-8")
    print("  已寫回 body.html")
