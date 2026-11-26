# douzo-guide-images

DOUZO 官網指南文章（douzo01.com/guide）的內文圖片。

## 放法
- 路徑固定是 `分類slug/文章slug/檔名`，跟官網網址 `/guide/分類/文章` 對得上。
- 內文圖照文章出現順序叫 `img01.webp`、`img02.webp`；表格圖叫 `table1.webp`、`table2.webp`。
- `圖片對照表.csv`：一張圖一列，記分類、文章、檔名、類型、放在哪個小標下、圖說、網址。網址只記在這裡。
- 正本在本機 `官網文章建置202611-23\articles\<文章slug>\`（`images\`、`table_images\`），這裡是複本。

## 網址
`https://cdn.jsdelivr.net/gh/Morgan-0516/douzo-guide-images@<版本>/<分類>/<文章>/<檔名>`
版本是上傳那次的 commit，網址固定不會被之後的改動影響。

## 換一張圖
1. 本機改正本（表格圖重跑 `table_img.py`）。
2. 跑 `python -I img_hosting.py articles/<文章slug>`：上傳、更新對照表、產生 `body_final.html`。
3. 後台那篇換成對照表的新網址。

## 搬家
整棵樹原樣搬到新空間，路徑不變；照 `圖片對照表.csv` 把網址開頭換成新空間，再批次換掉各篇後台的網址。
