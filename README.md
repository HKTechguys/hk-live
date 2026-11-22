# hk-live

香港即時資訊單頁（即時天氣／雨量／假期、停車場、路邊感應咪錶、手沖咖啡、漁護署遠足徑），
地圖頁的圖層由左下角開關控制，清單用底部面板。

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
