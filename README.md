# hk-live

香港即時資訊單頁（即時天氣／雨量／假期、停車場、路邊感應咪錶、手沖咖啡、漁護署遠足徑、設施），
地圖頁的圖層由左下角開關控制，清單用底部面板。

## 設施圖層（OSM，每週更新）

`data/facilities.json` 由 `tools/refresh_facilities.py` 每週一 10:00 HKT（`facilities.yml`）更新：

- 公共廁所 `amenity=toilets`
- 地鐵站出入口 `railway=subway_entrance`（連出口編號）
- 油站 `amenity=fuel`
- 醫院 `amenity=hospital`

以 bbox 向 Overpass API 抓，再用粗略香港邊界多邊形隔走深圳／內地結果；
資料 © OpenStreetMap contributors，ODbL 1.0，只顯示名稱與位置。
地圖上分別以 WC（藍）、M（紅）、F（橙）、H（紫）徽章顯示，各自有最低 zoom（廁所最密，要 zoom ≥14）。

## 咪錶即時（開住面板就更新）

咪錶面板（`#meter`）開着時，瀏覽器直連運輸署原始 CSV
`https://resource.data.one.gov.hk/td/psiparkingspaces/occupancystatus/occupancystatus.csv`（CORS `*`、CDN 只緩 60 秒），
即場比對新舊狀態，唔使等 workflow：

- 有設定「☆ 提醒」時每 75 秒拉一次（等同 ~1 分鐘延遲，夠貼近官方「實時」）；
- 冇提醒時每 3 分鐘；- 開咗省流模式或 2G 就 5 分鐘；收起面板即停。

每次約 716 KB（無 gzip）。關掉網頁之後的通知靠下面 workflow。

## 提醒清單（全區／全街／單一位）

咪錶面板最上方「★ 提醒清單」集中管理：每項顯示現時空置數，✕ 即取消。

- 地區：下拉選一個地區，再按「☆ 提醒 南區」＝全區任何一個位變空置都通知；
- 街道：清單每行右邊「☆ 提醒」；
- 單一位：展開街道後逐個位撳。

三者可同時存在，同一輪有變化會合併成一句（例：`有位！南區 · 2 個位剛空出：1A、1B`）。

## WhatsApp 咪錶有位通知（免開網頁）

`tools/refresh_parking.py` 每 10 分鐘重建 `data/meters.json`；
workflow 會先 snapshot 上一版，跑完再比對，命中「佔用中 → 空置」就發 WhatsApp。

1. 開 `tools/whatsapp_watch.json` 填想追蹤的範圍（街道／地區／個別位號），全部留空＝不推送。
2. 在 WhatsApp 加 CallMeBot 號碼 `+34 644 51 95 23`，發一句
   `I allow callmebot to send me messages`，它會回你一組 apikey。
3. Repo → Settings → Secrets and variables → Actions，新增兩個 secret：
   - `WA_PHONE` 例如 `85291234567`（國際區號，不要 +）
   - `WA_KEY`   CallMeBot 給你的 apikey
4. 之後每次偵測到變化都會推一條「🅿️ hk-live 咪錶有位（n 個）」訊息，內含街道、位號、地區與網站連結。

未設定 secret 時 workflow 只會把訊息印在 log、不會失敗。
想改用官方 WhatsApp Cloud API／Twilio，把 `tools/notify_whatsapp.py` 最後那段發送換掉即可。

<!-- publish probe 074145 -->
