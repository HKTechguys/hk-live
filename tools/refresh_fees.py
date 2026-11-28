#!/usr/bin/env python3
"""收集停車場收費 -> data/park_fees.json

來源 1（站內 worker 已有）：出行易 WFS 的 OTHER_INFO 收費文字
來源 2（本腳本）：領展 linkhk 停車場頁 -> apim JSON 的 allRateHtmlTc

輸出 key = 出行易 PARK_ID（有 EPARK_ID 就用 EPARK_ID，同 worker /parks 一致）
"""
import json, re, sys, time, urllib.request

HKEM = ("https://www.hkemobility.gov.hk/api/drss/layer/map/"
        "?typeName=DRSS%3AVW_CAR_PARK_TC&service=WFS&version=1.0.0&request=GetFeature"
        "&outputFormat=application%2Fjson&srsName=EPSG%3A4326")
LINK_API = "https://apim-gateway-prd.azure.linkreit.com/MPCMS/PRD2/parking/{}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def get(url, referer, tries=2):
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": referer,
                "Accept": "application/json,*/*",
            })
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if n == tries - 1:
                print("  ! fail", url[:80], e)
                return None
            time.sleep(1.5)


def plain(html):
    s = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&amp;", "&").replace("&nbsp;", " ")
         .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'"))
    s = re.sub(r"[ \t\u3000]+", " ", s)
    return re.sub(r"\n{2,}", "\n", s).strip()


def money(s):
    v = re.findall(r"\$\s*(\d+(?:\.\d+)?)", s)
    return [float(x) for x in v]


def link_fee(key):
    raw = get(LINK_API.format(key), "https://www.linkhk.com/")
    if not raw:
        return None
    try:
        j = json.loads(raw)
    except Exception:
        return None
    info = (j.get("data") or {}).get("parkingInfo") or {}
    html = info.get("allRateHtmlTc") or info.get("allRateHtmlEn") or ""
    if not html:
        return None
    txt = plain(html)
    lines = [l.strip() for l in txt.split("\n") if l.strip()]

    h = hh = d12 = d12h = d24 = d24h = 0
    # 逐段切：時租 / 每12小時 / 每24小時
    blocks = {"h": "", "d12": "", "d24": ""}
    cur = None
    for l in lines:
        if re.search(r"時租|Hourly", l, re.I):
            cur = "h"
        elif re.search(r"12\s*小時|12-hour|12 hour", l, re.I):
            cur = "d12"
        elif re.search(r"24\s*小時|24-hour|24 hour", l, re.I):
            cur = "d24"
        if cur and "$" in l:
            blocks[cur] += " " + l
    hv = money(blocks["h"])
    dv = money(blocks["d12"])
    ev = money(blocks["d24"])
    if hv:
        h = int(hv[0]) if hv[0] < 1000 else 0
        hh = int(hv[1]) if len(hv) > 1 and hv[1] < 1000 else 0
    if dv:
        d12 = int(dv[0]); d12h = int(dv[1]) if len(dv) > 1 else 0
    if ev:
        d24 = int(ev[0]); d24h = int(ev[1]) if len(ev) > 1 else 0
    if not (h or d12 or d24):
        return None
    parts = []
    if h:
        parts.append("時租 $" + str(h) + ("／假 $" + str(hh) if hh else "") + " 每小時")
    if d12:
        parts.append("12 小時 $" + str(d12) + ("／假 $" + str(d12h) if d12h else ""))
    if d24:
        parts.append("24 小時 $" + str(d24) + ("／假 $" + str(d24h) if d24h else ""))
    note = ""
    m = re.search(r"只適用於([^\n#]{0,12})", txt)
    if m:
        note = "只適用於" + m.group(1).strip()
    return {
        "t": ("；".join(parts) + ("（" + note + "）" if note else ""))[:120],
        "h": h, "hh": hh, "d12": d12, "d24": d24,
        "s": "領展", "u": time.strftime("%Y-%m-%d"),
    }


def mtr_fees():
    """港鐵車站停車場：一頁全站，逐段抓「標準收費」"""
    html = get("https://www.mtr.com.hk/ch/customer/services/stations_carpark.html",
               "https://www.mtr.com.hk/")
    if not html:
        return {}
    t = plain(html)
    heads = [(m.start(), m.group(1)) for m in
             re.finditer(r"([\u4e00-\u9fa5]{2,7}站)\s*車位數目", t)]
    out = {}
    for i, (pos, name) in enumerate(heads):
        seg = t[pos:(heads[i + 1][0] if i + 1 < len(heads) else pos + 400)]
        h = hh = 0
        m = re.search(r"每小時港幣(\d+)元", seg)
        if m:
            h = int(m.group(1))
        else:
            m2 = re.search(r"每半小時港幣(\d+)元", seg)
            if m2:
                h = int(m2.group(1)) * 2
        m3 = re.search(r"每小時港幣(\d+)元\s*[–\-]\s*只限星期六", seg)
        if m3:
            hh = int(m3.group(1))
        if h:
            out[name] = {"h": h, "hh": hh}
    print("mtr stations:", len(out))
    return out


def apt_fees():
    """機場停車場時租表（一號／三號／四號）"""
    html = get("https://www.hongkongairport.com/tc/transport/parking/parking-charges.page",
               "https://www.hongkongairport.com/")
    if not html:
        return {}
    t = plain(html)
    out = {}
    m = re.search(r"首一小時：\$(\d+)\s*其後每小時：\$(\d+)", t)
    if m:
        out["一號"] = {"h": int(m.group(1)), "hh": 0,
                    "t": f"時租 首小時 ${m.group(1)}／其後 ${m.group(2)}"}
    m2 = re.search(r"其後每小時：\$(\d+)\s+\$(\d+)\s+\$(\d+)", t)
    if m2:
        out.setdefault("三號", {"h": int(m2.group(2)), "hh": 0,
                               "t": f"時租 ${m2.group(2)}/小時"})
        out.setdefault("四號", {"h": int(m2.group(3)), "hh": 0,
                               "t": f"時租 ${m2.group(3)}/小時"})
    print("airport parks:", len(out))
    return out


SINO = {
    "tm": "https://www.tmtp.com.hk/tc/Parking",          # 屯門市廣場 1/2/3 期
    "cw": "https://www.citywalk.com.hk/tc/Parking",      # 荃新天地 / 荃新天地2
    "gc": "https://www.goldcoastpiazza.com.hk/tc/parking/",  # 黃金海岸商場
}
# 出行易 PARK_ID -> 官網分期 key（id 穩定，優先；名稱只做 fallback）
SINO_ID = {"tdc25p3": "tm1", "tdc25p43": "tm2", "tdc25p22": "tm3",
           "tdc25p29": "cw", "tdc25p30": "cw", "tdc25p23": "gc"}

# 信和官網冇公開時租表嘅場：第三方查核價（範圍寫法，前端標「非官方」，唔會蓋官方文字）
# 資料日 2026-11-28；來源 ParkingLotHK / kkleo / inpark / carparkhero
SINO_REF = {
    "tdc25p27": {"h": 19, "t": "時租約 $19–22／小時（第三方參考，非官方）"},
    "tdc25p24": {"h": 18, "t": "時租約 $18–24／小時（第三方參考，非官方）"},
    "tdc25p31": {"h": 21, "t": "時租約 $21–28／小時（第三方參考，非官方）"},
    "tdc25p15": {"h": 28, "t": "時租約 $28–38／小時（第三方參考，非官方）；日泊 $200、夜泊 $90"},
    "tdc25p25": {"h": 18, "t": "時租約 $18 起／小時（第三方參考，非官方）"},
    "tdc16p259": {"h": 24, "t": "時租約 $24 起／小時（第三方參考，非官方）"},
    "tdc25p2": {"h": 35, "t": "時租約 $35–37／小時（第三方參考，非官方）；日泊 $160"},
    "tdc25p14": {"h": 35, "t": "時租約 $35–39／小時（第三方參考，非官方）"},
}


def sino_mall(name):
    n = name or ""
    if "屯門市廣場" in n:
        if "第一" in n or "1期" in n:
            return "tm1"
        if "第二" in n:
            return "tm2"
        if "第三" in n:
            return "tm3"
    if "荃新天地" in n:      # 1 期 / 2 期同價
        return "cw"
    if "黃金海岸商場" in n:
        return "gc"
    return ""


def _cells(tr):
    s = re.sub(r"<[^>]+>", "\x00", tr)
    s = (s.replace("&amp;", "&").replace("&nbsp;", " ").replace("&lt;", "<")
         .replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"'))
    s = s.replace("\xa0", " ").replace("\u3000", " ")
    s = re.sub(r"[ \t\r\n]+", " ", s)
    return [c.strip() for c in s.split("\x00") if c.strip()]


def _rows(html):
    out = []
    for tb in re.findall(r"<table[^>]*>.*?</table>", html, re.S | re.I):
        rs = [_cells(tr) for tr in re.findall(r"<tr[^>]*>.*?</tr>", tb, re.S | re.I)]
        rs = [r for r in rs if r]
        if rs:
            out.append(rs)
    return out


def _num(s):
    m = re.search(r"\$\s?(\d+)", s)
    return int(m.group(1)) if m else 0


def sino_fees():
    """信和官網有明碼時租嘅場。抽唔到就回空 dict，由 main 保留舊價。"""
    out = {}

    h = get(SINO["tm"], "https://www.tmtp.com.hk/")
    if h:
        for rs in _rows(h):
            txt = " ".join(" ".join(r) for r in rs)
            if "期停車場" not in txt:
                continue
            if "浮動車位" in txt or "車架" in txt or "0800" in txt:   # 月租表／日泊表
                continue
            cur = ""
            for r in rs:
                if re.match(r"[123]\s*期停車場", r[0]):
                    cur = r[0][0]
                    continue
                if not cur or r[0].startswith("貨車"):   # 私家車/輕型貨車 唔可以當貨車 skip
                    continue
                price = _num(r[-1])
                if not price:
                    continue
                e = out.setdefault("tm" + cur, {"h": 0, "hh": 0, "d12": 0, "d24": 0})
                j = " ".join(r)
                if re.search(r"星期一至五|一至五|星期一至日", j):
                    e["h"] = price
                elif re.search(r"星期六|六、日|公眾假期", j):
                    e["hh"] = price
                elif "私家車" in j:
                    e["h"] = e["hh"] = price
            break                                                    # 只用第一個時租表

    h = get(SINO["cw"], "https://www.citywalk.com.hk/")
    if h:
        for rs in _rows(h):
            if "荃新天地2" not in " ".join(" ".join(r) for r in rs):
                continue
            e = out.setdefault("cw", {"h": 0, "hh": 0, "d12": 0, "d24": 0})
            for r in rs:
                price = _num(r[-1])
                if not price:
                    continue
                j = " ".join(r)
                if "星期一至五" in j:
                    e["h"] = price
                elif "星期六" in j:
                    e["hh"] = price
            break

    h = get(SINO["gc"], "https://www.goldcoastpiazza.com.hk/")
    if h:
        for rs in _rows(h):
            if "半小時" not in " ".join(" ".join(r) for r in rs):
                continue
            e = out.setdefault("gc", {"h": 0, "hh": 0, "d12": 0, "d24": 0})
            night = 0
            for r in rs:
                j = " ".join(r)
                price = _num(j)
                if not price:
                    continue
                if "星期一至四" in j:
                    e["h"] = price * 2
                elif "星期五至日" in j:
                    e["hh"] = price * 2
                elif "夜泊" in j:
                    night = price
            e["t"] = ("時租 $%d／半小時（一至四）、$%d／半小時（五六日及公假）"
                      % (e["h"] // 2, e["hh"] // 2) + ("；夜泊 $%d" % night if night else ""))
            if night:                       # 夜泊：全晚總額 20:00-08:00，前端夜晚自動切換
                e["nt"], e["ns"], e["ne"] = night, 20, 8
            break

    for k, e in out.items():
        if not e.get("t"):
            if e["h"] and e["hh"] and e["hh"] != e["h"]:
                e["t"] = "時租 $%d／假 $%d 每小時" % (e["h"], e["hh"])
            elif e["h"]:
                e["t"] = "時租 $%d 每小時" % e["h"]
        if k == "tm2":
            e["t"] = "時租 $%d 每小時（私家車；貨車 $30）" % e["h"]
        e["s"], e["u"] = "信和", time.strftime("%Y-%m-%d")
    print("sino malls:", {k: v["t"] for k, v in out.items()})
    return out


def norm(s):
    s = (s or "").replace("（", "(").replace("）", ")").replace("　", " ")
    s = re.sub(r"\s+", "", s)
    for w in ("停車場", "停車場(時租)", "(時租)", "車場"):
        s = s.replace(w, "")
    return s.strip()


YX = "https://www.yuexiuaptparking.com"


def yuexiu_list():
    """越秀亞通：6 頁清單 -> [(article_id, name)]"""
    ids, seen = [], set()
    for pg in range(1, 7):
        url = YX + ("/list-find.html?lang=tc" if pg == 1 else f"/list-find.html?page={pg}&lang=tc")
        html = get(url, YX + "/")
        if not html:
            continue
        for m in re.finditer(r"/article-find-(\d+)\.html", html):
            i = m.group(1)
            if i not in seen:
                seen.add(i)
                ids.append(i)
        time.sleep(0.3)
    print("yuexiu articles:", len(ids))
    return ids


def yuexiu_fee(aid):
    html = get(f"{YX}/article-find-{aid}.html?lang=tc", YX + "/")
    if not html:
        return None, ""
    mt = re.search(r"<title>(.*?)</title>", html, re.S)
    name = (mt.group(1).strip() if mt else "")
    name = re.split(r"[|\-–]", name)[0].strip()
    t = plain(html)
    i = t.find("時租")
    if i < 0:
        return None, name
    seg = t[i:i + 160]
    cut = re.search(r"日\s*泊|24\s*小時|月租", seg)
    if cut:
        seg = seg[:cut.start()]
    # 有時段：(07:00 - 23:00) HK$21 (23:00 - 07:00) HK$17
    pairs = re.findall(r"(\d{1,2})\s*:\s*(\d{2})\s*[-–~至]\s*(\d{1,2})\s*:\s*(\d{2})[^$\d]{0,24}\$\s*(\d+)", seg)
    day = night = nh = ne = 0
    for a, _b, c, e, v in pairs:
        a, c, v = int(a), int(c), int(v)
        if (a >= 20 or c <= 10) and night == 0:
            night, nh, ne = v, a, c
        elif day == 0:
            day = v
    note = ""
    if not day:
        # 首2小時 $17、第三小時起 $34
        m = re.search(r"首\s*(\d+)\s*小時[\s\S]{0,40}?\$\s*(\d+)", seg)
        if m:
            day, note = int(m[2]), f"首{m[1]}小時"
        else:
            nums = [int(x) for x in re.findall(r"HK\s*\$?\s*(\d+)", seg)]
            day = nums[0] if nums else 0
    if not day:
        return None, name
    if note:
        txt = f"{note} ${day}/小時（其後見官網）（越秀官網）"
    elif night:
        txt = f"時租 {pairs[0][0]}:{pairs[0][1]}-{pairs[0][2]}:{pairs[0][3]} ${day}／夜間 ${night}（越秀官網）"
    else:
        txt = f"時租 ${day}/小時（越秀官網）"
    return {"t": txt, "h": day, "hh": night, "nh": nh, "ne": ne, "w": 0,
            "d12": 0, "d24": 0, "s": "越秀", "u": time.strftime("%Y-%m-%d")}, name


def main():
    old = {}
    try:
        with open("data/park_fees.json", encoding="utf-8") as fh:
            old = (json.load(fh) or {}).get("fees") or {}
    except Exception:
        old = {}
    raw = get(HKEM, "https://www.hkemobility.gov.hk/tc/")
    if not raw:
        sys.exit("cannot fetch hkem layer")
    feats = json.loads(raw).get("features", [])
    sites = {}
    fees = {}
    for f in feats:
        p = f.get("properties") or {}
        pid = p.get("PARK_ID")
        if not pid:
            continue
        key = p.get("EPARK_ID") or pid
        if key not in sites:
            sites[key] = {"web": "", "fee": "", "n": (p.get("NAME") or "").strip()}
        w = (p.get("WEBSITE") or "").strip()
        if w and not sites[key]["web"]:
            sites[key]["web"] = w
        fee = plain(p.get("OTHER_INFO") or p.get("REMARK") or "")
        if fee and not sites[key]["fee"]:
            sites[key]["fee"] = fee

    link_ids = [k for k, v in sites.items()
                if re.search(r"linkhk\.com/\w+/parking/\d+", v["web"])]
    names = {k: v["n"] for k, v in sites.items()}
    print("link parks:", len(link_ids))
    for i, k in enumerate(link_ids):
        m = re.search(r"/parking/(\d+)", sites[k]["web"])
        got = link_fee(m.group(1)) if m else None
        if got:
            fees[k] = got
        if i % 20 == 0:
            print(f"  {i}/{len(link_ids)} ok={len(fees)}")
        time.sleep(0.25)

    # 港鐵：按站名對回停車場名（「港鐵香港站停車場」含「香港站」）
    mtr = mtr_fees()
    mtr_hit = 0
    for k, v in sites.items():
        if "mtr.com.hk" not in v["web"] or v["fee"]:
            continue
        nm = ""
        # 用 park id 反查名稱要靠 features，先建 names
        nm = names.get(k, "")
        for st in sorted(mtr, key=len, reverse=True):
            core = st[:-1]
            if st in nm or core in nm:
                e = mtr[st]
                fees[k] = {"t": f"時租 ${e['h']}/小時" + (f"（假日 ${e['hh']}）" if e["hh"] else ""),
                           "h": e["h"], "hh": e["hh"], "d12": 0, "d24": 0,
                           "s": "港鐵", "u": time.strftime("%Y-%m-%d")}
                mtr_hit += 1
                break
    print("mtr mapped:", mtr_hit)

    # 機場：按名含「一號／三號／四號」
    apt = apt_fees()
    apt_hit = 0
    for k, v in sites.items():
        if "hongkongairport.com" not in v["web"] or v["fee"]:
            continue
        nm = names.get(k, "")
        for tag, e in apt.items():
            if tag in nm:
                fees[k] = {"t": e["t"], "h": e["h"], "hh": 0, "d12": 0, "d24": 0,
                           "s": "機管局", "u": time.strftime("%Y-%m-%d")}
                apt_hit += 1
                break
    print("airport mapped:", apt_hit)

    # 越秀亞通（官網逐場價），按名配對：官網名 vs 出行易場名
    yx_map = {}
    for k, v in sites.items():
        if v["n"]:
            yx_map.setdefault(norm(v["n"]), []).append(k)
    # 出行易用較長名／分期名，官網用簡名
    ALIAS = {
        "南山邨": ["南山邨多層停車場"],
        "富蝶邨": ["富蝶邨一期停車場", "富蝶邨二期停車場"],
        "碩門邨": ["碩門邨一期停車場", "碩門邨二期停車場"],
        "白田邨7及8期": ["白田邨7&8期停車場"],
        "白田邨": ["白田邨（瑞田樓）停車場"],
        "興華(二)邨": ["興華二邨停車場"],
        "蘇屋邨(一期)": ["蘇屋邨停車場一期"],
    }
    yx_hit = 0
    for aid in yuexiu_list():
        got, name = yuexiu_fee(aid)
        time.sleep(0.35)
        if not got or not name:
            continue
        keys = yx_map.get(norm(name))
        if not keys:
            keys = [yx_map.get(norm(a), []) for a in ALIAS.get(name, [])]
            keys = [k for sub in keys for k in sub]
        for k in keys:
            fees[k] = got          # 越秀官網價優先用（結構化：日／夜／時段）
            yx_hit += 1
    print("yuexiu mapped:", yx_hit)

    # 信和官網時租（屯門市廣場 1/2/3 期、荃新天地、黃金海岸）；官網冇明碼嘅場唔碰
    sino = sino_fees()
    sino_hit = 0
    for k, v in sites.items():
        mall = SINO_ID.get(k) or sino_mall(v["n"])
        if not mall or mall not in sino:
            continue
        fees[k] = dict(sino[mall])
        sino_hit += 1
    print("sino mapped:", sino_hit)
    # 官網冇明碼嘅信和場：第三方參考價（標非官方，唔蓋官方／出行易文字）
    ref_hit = 0
    for k, e in SINO_REF.items():
        if k in sites and k not in fees:
            fees[k] = dict(e, s="非官方", u="2026-11-28")
            ref_hit += 1
    print("sino ref (non-official):", ref_hit)
    # 官網今次抽唔到（改版／被封）就保留舊信和價，唔好靜靜地掉咗
    for k, v in old.items():
        if v.get("s") in ("信和", "非官方") and k not in fees:
            fees[k] = v

    out = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "src": "linkhk+mtr+yuexiu+sino+ref",
           "n": len(fees), "fees": fees}
    with open("data/park_fees.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("written data/park_fees.json", len(fees), "parks")


if __name__ == "__main__":
    main()
