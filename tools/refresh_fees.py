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
            sites[key] = {"web": "", "fee": ""}
        w = (p.get("WEBSITE") or "").strip()
        if w and not sites[key]["web"]:
            sites[key]["web"] = w
        fee = plain(p.get("OTHER_INFO") or p.get("REMARK") or "")
        if fee and not sites[key]["fee"]:
            sites[key]["fee"] = fee

    link_ids = [k for k, v in sites.items()
                if re.search(r"linkhk\.com/\w+/parking/\d+", v["web"])]
    print("link parks:", len(link_ids))
    for i, k in enumerate(link_ids):
        m = re.search(r"/parking/(\d+)", sites[k]["web"])
        got = link_fee(m.group(1)) if m else None
        if got:
            fees[k] = got
        if i % 20 == 0:
            print(f"  {i}/{len(link_ids)} ok={len(fees)}")
        time.sleep(0.25)

    out = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "src": "linkhk",
           "n": len(fees), "fees": fees}
    with open("data/park_fees.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("written data/park_fees.json", len(fees), "parks")


if __name__ == "__main__":
    main()
