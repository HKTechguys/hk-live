#!/usr/bin/env python3
"""一次性補丁：把 index.html 的搜尋框由「本地四類」升級成「任何地名」。
跑完即可刪走本檔與 tools/wire_search.js。
"""

P = "index.html"
h = open(P, encoding="utf-8").read()
new = open("tools/wire_search.js", encoding="utf-8").read()

s = h.index("  function wireSearch(){")
e = h.index("\n  function setBtn(id, on){")
h = h[:s] + new + h[e:]

old_ph = 'aria-label="搜尋車場、街道或 Cafe" placeholder="車場／街道／Cafe／山徑，例如 中環"'
new_ph = 'aria-label="搜尋任何地點、大廈、車場" placeholder="任何地點／大廈／商場 · 例如 旺角中心"'
if new_ph not in h and old_ph in h:
    h = h.replace(old_ph, new_ph)

anchor = '<li><b>新增「設施」圖層</b>'
entry = ('<li><b>搜尋框變成「任何地名」</b>：除原有車場／Cafe／咪錶／山徑，'
         '打大廈、商場、街道名（如「旺角中心」「皇廷廣場」）會經 OpenStreetMap 即時查坐标，飛去並落一個藍針；'
         '本地資料照舊優先。</li>\n      ')
if "搜尋框變成「任何地名」" not in h and anchor in h:
    h = h.replace(anchor, entry + anchor, 1)

open(P, "w", encoding="utf-8").write(h)
print("patched", P, len(h))
