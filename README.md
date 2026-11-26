# douzo-guide-images

DOUZO 官網指南文章（douzo01.com/guide）的內文圖片和表格圖。官網後台的圖片鈕只能貼網址，所以圖片放這裡，用 jsDelivr 網址插進文章。

## 放法
- 路徑固定是 `分類slug/文章slug/檔名`，跟官網網址 `/guide/分類/文章` 對得上。
- 內文圖照文章出現順序叫 `img01.webp`、`img02.webp`；表格圖叫 `table1.webp`、`table2.webp`。
- `圖片對照表.csv`：一張圖一列，記分類、文章、檔名、類型、放在哪個小標下、圖說（也是 alt 文字）、網址。網址只記在這裡。
- 正本在搬運專案資料夾 `官網文章建置202611-23\articles\<文章slug>\`（`images\`、`table_images\`），這裡是複本。

網址格式：
`https://cdn.jsdelivr.net/gh/Morgan-0516/douzo-guide-images@<版本>/<分類>/<文章>/<檔名>`
`@<版本>` 是上傳那次的 commit，網址固定，之後改 repo 不會影響已經貼進後台的圖。

## 前置需求
- Python 3，裝好 Pillow（`pip install pillow`）。
- 本機有 Chrome（`table_img.py` 用它把表格畫成圖）。
- 這個 repo clone 在本機，而且有 push 權限（`gh auth status` 看得到 Morgan-0516）。
- 搬運專案資料夾裡有 `文章清單.csv`，這篇文章那一列的「官網分類Slug(建議)」有填。沒填 `img_hosting.py` 會停下來。

## 新文章的完整順序
在這個 repo 的根目錄執行（`<專案>` 是搬運專案資料夾的路徑）：
1. 有表格的文章先把表格做成圖：
   `python -I -X utf8 tools/table_img.py <專案>/articles/<文章slug>`
   會在 `table_images\` 產生 `table1.webp`…，每張壓到 150KB 以下。跑完打開看一遍有沒有跑版。
2. 上傳並產生內文：
   `python -I -X utf8 tools/img_hosting.py <專案>/articles/<文章slug>`
   它會：把圖複製到 `分類/文章/`、commit、push、更新 `圖片對照表.csv`、用沒登入的連線確認每張都抓得到，最後產生 `<專案>/articles/<文章slug>/body_final.html`。結尾印「失敗 0」、結束碼 0 才算成功。
3. 把 `body_final.html` 整段貼進後台那篇的「繁體中文」內容分頁，存檔。

## 換一張圖
1. 改本機正本（內文圖換 `images\NN.webp`；表格圖重跑步驟 1）。
2. 重跑步驟 2。每跑一次，整篇所有圖的網址版本都會換成新的。
3. 把新的 `body_final.html` 整段重貼進後台，不要只改一張的網址。

## 搬家（改放別的空間，例如官網自己的圖片空間）
1. 整個 `分類/文章/檔名` 資料夾樹原樣搬過去，路徑不變。
2. 新網址 = 新空間的開頭 + 同一段路徑。舊網址裡的 `cdn.jsdelivr.net/gh/Morgan-0516/douzo-guide-images@<版本>/` 整段換掉，`@<版本>` 也要拿掉。
3. 更新 `圖片對照表.csv` 的網址欄。
4. 官網後台沒有批次取代功能，要逐篇改：用瀏覽器自動化打開每篇的編輯頁，照對照表換掉內文裡的網址，存檔，再重新打開確認圖片都載入。
