#!/usr/bin/env python3
"""One-off: add search section, renumber, new 2026-11-27 log block."""
import re
import sys

P = "index.html"
h = open(P, encoding="utf-8").read()


def need(s):
    if s not in h:
        sys.exit("missing anchor: " + s[:80])


h2 = re.sub(r'\n      <li><b>搜尋框變成「任何地名」</b>[^\n]*', "", h)
if h2 == h:
    sys.exit("misplaced search bullet not found")
h = h2

need('<h3 class="wn-h">⑩ 資料來源（Credit）</h3>')
h = h.replace('<h3 class="wn-h">⑩ 資料來源（Credit）</h3>',
              '<h3 class="wn-h">⑪ 資料來源（Credit）</h3>')
h = h.replace('（見上面 ⑩）', '（見上面 ⑪）')
h = h.replace('<h3 class="wn-h">⑨ 一撳加到主畫面</h3>',
              '<h3 class="wn-h">⑩ 一撳加到主畫面</h3>')
h = h.replace('<h3 class="wn-h">⑧ 空位通知（Web Push，免費）</h3>',
              '<h3 class="wn-h">⑨ 空位通知（Web Push，免費）</h3>')

anchor = '<h3 class="wn-h">⑦ 設施 · 廁所／地鐵出口／油站／醫院</h3>'
need(anchor)
sec = "\n".join([
    '<h3 class="wn-h">⑦ 搜尋 · 任何地名（大廈／商場／街道）</h3>',
    '    <ul class="wn-list">',
    '      <li>搜尋框唔再局限四類：打<b>大廈、商場、街道、店舖</b>名（例：旺角中心、皇廷廣場、ifc）都會搵到。</li>',
    '      <li>本地資料（車場連即時空位、Cafe、咪錶、山徑）<b>排先</b>；本地冇先用 OpenStreetMap 查，結果標示「地名 · 街道 · 區」。一撳即飛去目標並落一個藍針，popup 顯示名稱。</li>',
    '      <li>大廈／商場／店舖用 zoom 17、街道 16、其他 14；只喺香港範圍查，唔會跳去深圳。</li>',
    '      <li><b>資料來源</b>：Photon（photon.komoot.io，基於 OpenStreetMap），免費公用服務；慢或掛嘅時候只顯示本地結果。</li>',
    '    </ul>',
    '',
    '    ',
])
h = h.replace(anchor, sec + '<h3 class="wn-h">⑧ 設施 · 廁所／地鐵出口／油站／醫院</h3>')

old_day = '<div class="wn-day"><span class="d">2026-11-24</span><span class="t">版面與使用流程'
need(old_day)
day = "\n".join([
    '<div class="wn-day"><span class="d">2026-11-27</span><span class="t">地圖搜尋 × 設施徽章 <span class="wn-tag">最新</span></span></div>',
    '    <ul class="wn-list">',
    '      <li><b>搜尋框變「任何地名」</b>：打大廈／商場／街道名（旺角中心、皇廷廣場、ifc…）即時用 OpenStreetMap 查座標，飛去目標並落一個藍針；車場即時空位、Cafe、咪錶、山徑照舊排先。</li>',
    '      <li><b>地鐵出口改寫出口編號</b>（A1／B2／D1…，冇編號才顯示 M），popup 顯示所屬站名（旺角站、旺角東站、太子站…）。</li>',
    '      <li><b>油站改用品牌色徽章</b>：Shell／Esso／Caltex／Sinopec／中石油，popup 顯示中文品牌名。</li>',
    '      <li>搜尋用免費 OSM 地理編碼（Photon），只查香港範圍，350ms 防手震＋同一字快取。</li>',
    '    </ul>',
    '',
    '    ',
])
h = h.replace(old_day, day + old_day, 1)
h = h.replace('收費解析全面校正 <span class="wn-tag">最新</span>', '收費解析全面校正')

open(P, "w", encoding="utf-8").write(h)
print("patched ok, len=%d" % len(h))
