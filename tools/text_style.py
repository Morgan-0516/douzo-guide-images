"""檢查／修正文章 HTML 的 DOUZO 文字規範（只動文字和 alt，不動標籤、網址）。
用法：python -I -X utf8 tools/text_style.py <專案資料夾>/articles/<文章slug> [--fix]
- 中文與英文、數字之間加半形空格；% 跟中文之間加空格；全形括號、標點緊鄰英數不加空格。
- 「...」改「……」；全形英數改半形。
- 「！！！」、品牌寫法（Douzo、Doya）只列出，不自動改。
--fix 會改寫 <文章資料夾>/body.html；之後要重跑 table_img.py、img_hosting.py。"""
import sys, re, pathlib

CJK = r"[㐀-䶿一-鿿]"
AN = r"[A-Za-z0-9]"
RULES = [
    (re.compile(f"({CJK})({AN})"), r"\1 \2", "中文接英數沒空格"),
    (re.compile(f"({AN}|%)({CJK})"), r"\1 \2", "英數或 % 接中文沒空格"),
    (re.compile(r"\.\.\."), "……", "「...」應為「……」"),
]
FLAGS = [
    (re.compile(r"！！"), "連續驚嘆號"),
    (re.compile(r"\bDOUZO\b|\bdouzo\b(?![./@])"), "品牌寫法應為 Douzo"),
    (re.compile(r"\bDOYA\b|\bdoya\b(?![./-])"), "品牌寫法應為 Doya"),
]
FW = str.maketrans({chr(c): chr(c - 0xFEE0) for c in list(range(0xFF10, 0xFF1A)) + list(range(0xFF21, 0xFF3B)) + list(range(0xFF41, 0xFF5B))})


def fix_text(t, hits):
    t2 = t.translate(FW)
    if t2 != t:
        hits.append(("全形英數", t[:40]))
    for rx, rep, why in RULES:
        for m in rx.finditer(t2):
            hits.append((why, t2[max(0, m.start() - 8):m.end() + 8]))
        t2 = rx.sub(rep, t2)
    return t2


d = pathlib.Path(sys.argv[1])
src = (d / "body.html").read_text(encoding="utf-8")
hits, flags = [], []


def seg(m):
    tag, text = m.group(1), m.group(2)
    tag = re.sub(r'alt="([^"]*)"', lambda a: 'alt="' + fix_text(a.group(1), hits) + '"', tag)
    for rx, why in FLAGS:
        for f in rx.finditer(text):
            flags.append((why, text[max(0, f.start() - 8):f.end() + 8]))
    return tag + fix_text(text, hits)


out = re.sub(r"(<[^>]*>)([^<]*)", seg, src)
# 跨標籤：「到<a>Douzo」「Douzo</a>是」這種中文和英數被標籤隔開的情況
for rx, rep in [(re.compile(f"({CJK})((?:<(?:a|strong|em)\\b[^>]*>)+)(?={AN})"), r"\1 \2"),
                (re.compile(f"(?<={AN})((?:</(?:a|strong|em)>)+)({CJK})"), r"\1 \2")]:
    for m in rx.finditer(out):
        hits.append(("標籤兩側中英沒空格", re.sub(r"<[^>]+>", "", out[max(0, m.start() - 20):m.end() + 12])))
    out = rx.sub(rep, out)
print(f"{d.name}: 要改 {len(hits)} 處，要人看 {len(flags)} 處")
for why, ctx in hits[:int(sys.argv[3]) if len(sys.argv) > 3 else 8]:
    print("  改", why, "｜", ctx.replace("\n", " "))
for why, ctx in flags:
    print("  看", why, "｜", ctx.replace("\n", " "))
if "--fix" in sys.argv and out != src:
    (d / "body.html").write_text(out, encoding="utf-8")
    print("  已寫回 body.html")
