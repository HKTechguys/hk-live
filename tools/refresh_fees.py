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


def main():
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

    out = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "src": "linkhk+mtr+apt",
           "n": len(fees), "fees": fees}
    with open("data/park_fees.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("written data/park_fees.json", len(fees), "parks")


if __name__ == "__main__":
    main()
