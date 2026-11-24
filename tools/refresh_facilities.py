#!/usr/bin/env python3
"""由 OpenStreetMap（Overpass API）更新香港四類設施 → data/facilities.json

類別：公共廁所（amenity=toilets）、地鐵站出入口（railway=subway_entrance）、
      油站（amenity=fuel）、醫院（amenity=hospital）
授權：© OpenStreetMap contributors（ODbL 1.0）

做法：用 bbox 抓（比 area 查詢輕，Overpass 公用 server 較易成功），
      再用粗略香港邊界多邊形隔走深圳／內地結果。

用法：
  python tools/refresh_facilities.py            # 更新 data/facilities.json
  python tools/refresh_facilities.py --dry-run  # 只印統計，唔寫檔
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "facilities.json")
HKT = timezone(timedelta(hours=8))

BBOX = "22.14,113.82,22.57,114.45"
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# 香港粗略邊界（lon,lat），只作隔走深圳／內地結果；北界故意壓低少少
HK_POLY = [
    (113.86, 22.24), (113.88, 22.30), (113.94, 22.34), (113.97, 22.42),
    (114.01, 22.47), (114.04, 22.49), (114.10, 22.51), (114.16, 22.52),
    (114.22, 22.52), (114.26, 22.51), (114.33, 22.50), (114.42, 22.47),
    (114.40, 22.40), (114.36, 22.32), (114.28, 22.25), (114.20, 22.18),
    (114.10, 22.14), (114.02, 22.13), (113.94, 22.18),
]

RULES = [("t", "amenity", "toilets"), ("m", "railway", "subway_entrance"),
         ("f", "amenity", "fuel"), ("h", "amenity", "hospital")]
LABEL = {"t": "公共廁所", "m": "地鐵站出入口", "f": "油站", "h": "醫院"}


def inside(lon, lat):
    n, c, j = len(HK_POLY), False, len(HK_POLY) - 1
    for i in range(n):
        xi, yi = HK_POLY[i]
        xj, yj = HK_POLY[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            c = not c
        j = i
    return c


def fetch(ty, key, val):
    q = "[out:json][timeout:120];nwr[%s=%s](%s);out center tags;" % (key, val, BBOX)
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(6):
        ep = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(ep, data=data, headers={
                "User-Agent": "hk-live/1.0 (refresh_facilities.py)",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
            if len(raw) > 2000:
                return json.loads(raw.decode("utf-8"))
            last = "HTTP %s / %d bytes" % (r.status, len(raw))
        except Exception as e:
            last = "%s: %s" % (ep, e)
        time.sleep(15 * (attempt + 1))
    raise SystemExit("%s 抓唔到：%s" % (ty, last))


def zh_part(s):
    """「中文 English」混合名只留中文部分。"""
    s = (s or "").strip()
    m = re.match(r"([^\x00-\x7f][^\x00-\x7f\s]*(?:\s*[^\x00-\x7f]+)*)", s)
    if s and m:
        return m.group(1).strip()
    return s


def name_of(tags, ty):
    for k in ("name:zh-Hant", "name:zh", "name", "name:en"):
        v = zh_part(tags.get(k) or "")
        if v:
            return v[:40]
    ref = (tags.get("ref") or "").strip()
    if ty == "m":
        return ("出口 " + ref) if ref else LABEL[ty]
    return LABEL[ty]


def extra_of(tags, ty):
    if ty == "m":
        p = []
        if tags.get("ref"):
            p.append("出口 " + str(tags["ref"]))
        if tags.get("level"):
            p.append("L" + str(tags["level"]))
        if tags.get("wheelchair") == "yes":
            p.append("有輪椅通道")
        return " · ".join(p)[:30]
    if ty == "t":
        op = str(tags.get("operator:short:zh") or tags.get("operator") or "")
        if "食環" in op or "FEHD" in op:
            return "食環署"
        if "AFCD" in op or "漁農" in op:
            return "漁護署"
        return ""
    return str(tags.get("brand") or tags.get("operator") or "").strip()[:24]


def main():
    dry = "--dry-run" in sys.argv
    items, seen, stats = [], set(), {}
    for ty, key, val in RULES:
        js = fetch(ty, key, val)
        keep = 0
        for el in js.get("elements", []):
            tags = el.get("tags") or {}
            if tags.get(key) != val:
                continue
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if not lat or not lon or not inside(float(lon), float(lat)):
                continue
            nm = name_of(tags, ty)
            dk = (ty, nm.lower(), round(float(lat), 3), round(float(lon), 3))
            if dk in seen:
                continue
            seen.add(dk)
            keep += 1
            items.append([ty, nm, round(float(lat), 6), round(float(lon), 6), extra_of(tags, ty)])
        stats[ty] = keep

    items.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    counts = {"t": 0, "m": 0, "f": 0, "h": 0}
    for it in items:
        counts[it[0]] += 1

    out = {
        "generated": datetime.now(HKT).strftime("%Y-%m-%d %H:%M"),
        "count": len(items),
        "counts": counts,
        "license": "ODbL 1.0",
        "source": "© OpenStreetMap contributors（Overpass API bbox＋香港邊界過濾）",
        "items": items,
    }
    print("counts=%s total=%d" % (counts, len(items)))
    if dry:
        return

    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding="utf-8"))
            if old.get("items") == items:
                print("no change, skip write")
                return
        except Exception:
            pass
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("wrote %s (%d bytes)" % (OUT, os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
