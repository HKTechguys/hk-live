"""每日刷新 Cafe 名單：由 cafe.qualitylife.coffee 官方 API 取最新店舖資料。

只更新事實欄位（名、座標、區、營業時間、價格區間）；
地址／電話／簡介沿用上次抓落嘅值（新店才會去 detail 頁補）。
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://cafe.qualitylife.coffee/api/cafes.json"
DETAIL = "https://cafe.qualitylife.coffee/cafe/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "cafes.json")
UA = "hk-live-cafe-refresh/1.0 (+https://hktechguys.github.io/hk-live/)"
HKT = timezone(timedelta(hours=8))

NEW_CAP = 40  # 每次最多補幾多間新店嘅 detail 頁


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def hours_text(code):
    """code 例：'540-1140|540-1140|...'（7 日，分鐘）→ 人類可讀字串。"""
    if not code:
        return None
    parts = code.split("|")
    if len(parts) != 7:
        return None

    def one(p):
        p = (p or "").strip()
        if p in ("", "0-0", "-"):
            return "休息"
        try:
            a, b = p.split("-")
            a, b = int(a), int(b)
        except ValueError:
            return None
        a = min(a, 1439)
        b = min(b, 1439)
        return "%02d:%02d-%02d:%02d" % (a // 60, a % 60, b // 60, b % 60)

    vals = [one(p) for p in parts]
    if any(v is None for v in vals):
        return None
    if len(set(vals)) == 1:
        return "每日 " + vals[0] if vals[0] != "休息" else "每日休息"
    if len(set(vals[:5])) == 1 and vals[5] == vals[6]:
        if vals[0] != "休息" and vals[5] == "休息":
            return "星期一至五 %s" % vals[0]
        return "星期一至五 %s · 星期六至日 %s" % (vals[0], vals[5])
    return None  # 太複雜就唔覆蓋舊值


def district(slug):
    if not slug:
        return ""
    return " ".join(w.capitalize() for w in re.split(r"[-_]", slug))


def price(rec):
    lo, hi = rec.get("pm"), rec.get("px")
    if isinstance(lo, int) and isinstance(hi, int):
        return "HK$%d" % lo if lo == hi else "HK$%d–%d" % (lo, hi)
    if isinstance(lo, int):
        return "HK$%d" % lo
    return None


def detail(slug):
    """新店先去 detail 頁抽 address / telephone / description（JSON-LD 優先）。"""
    try:
        html = get(DETAIL + slug)
    except Exception:
        return {}
    out = {}
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        objs = data if isinstance(data, list) else [data]
        for o in objs:
            if not isinstance(o, dict):
                continue
            if o.get("@type") in ("CafeOrCoffeeShop", "Restaurant", "LocalBusiness", "Store"):
                addr = o.get("address")
                if isinstance(addr, dict):
                    bits = [addr.get("streetAddress"), addr.get("addressLocality"),
                            addr.get("addressRegion")]
                    s = "".join(x for x in bits if isinstance(x, str))
                    out.setdefault("a", s)
                elif isinstance(addr, str):
                    out.setdefault("a", addr)
                if isinstance(o.get("telephone"), str):
                    out.setdefault("t", o["telephone"])
                if isinstance(o.get("description"), str):
                    out.setdefault("x", re.sub(r"<[^>]+>", "", o["description"]).strip()[:180])
    return {k: v for k, v in out.items() if v}


def main():
    dry = "--dry-run" in sys.argv
    api = json.loads(get(API))
    recs = api.get("cafes") or []
    if not recs:
        raise SystemExit("API 冇 cafes，停止（唔好覆蓋現有資料）")

    old = json.load(open(OUT, encoding="utf-8"))
    olds = {c.get("s") or c.get("u", "").rstrip("/").split("/")[-1]: c for c in old.get("cafes", [])}

    fresh, added, dropped, changed = [], [], [], 0
    new_left = NEW_CAP
    for rec in recs:
        slug = rec.get("s")
        if not slug:
            continue
        base = olds.get(slug) or {
            "s": slug,
            "n": rec.get("e") or rec.get("z") or slug,
            "a": "", "d": district(rec.get("a")),
            "la": rec.get("la"), "lo": rec.get("ln"),
            "t": "", "p": "", "h": hours_text(rec.get("h")) or "",
            "x": "", "u": DETAIL + slug,
        }
        if slug not in olds:
            added.append(slug)
            if new_left > 0:
                new_left -= 1
                base.update({k: v for k, v in detail(slug).items() if v})

        def coord(new, oldv):
            try:
                n, o = float(new), float(oldv)
                if abs(n - o) < 0.001:   # 約 100 米內當同一位置，唔製造無謂 diff
                    return oldv
                return round(n, 5)
            except (TypeError, ValueError):
                return oldv if oldv is not None else new

        item = {
            "s": slug,
            "n": rec.get("e") or rec.get("z") or base.get("n") or slug,
            "a": base.get("a", ""),
            "d": district(rec.get("a")) or base.get("d", ""),
            "la": coord(rec.get("la"), base.get("la")),
            "lo": coord(rec.get("ln"), base.get("lo")),
            "t": base.get("t", ""),
            "p": price(rec) or base.get("p", ""),
            "h": hours_text(rec.get("h")) or base.get("h", ""),
            "x": base.get("x", ""),
            "u": DETAIL + slug,
        }
        if olds.get(slug):
            before = {k: olds[slug].get(k) for k in ("n", "h", "d", "la", "lo", "p")}
            after = {k: item[k] for k in ("n", "h", "d", "la", "lo", "p")}
            if before != after:
                changed += 1
        fresh.append(item)

    for slug in olds:
        if slug and slug not in {r.get("s") for r in recs}:
            dropped.append(slug)

    doc = {
        "generated": datetime.now(HKT).strftime("%Y-%m-%d %H:%M"),
        "source": old.get("source", "cafe.qualitylife.coffee"),
        "count": len(fresh),
        "cafes": fresh,
    }

    print("api=%d old=%d new=%d added=%d dropped=%d changed=%d" %
          (len(recs), len(old.get("cafes", [])), len(fresh), len(added), len(dropped), changed))
    if added:
        print("added:", ", ".join(added[:10]))
    if dropped:
        print("dropped:", ", ".join(dropped[:10]))

    if dry:
        return
    if not changed and not added and not dropped:
        print("no change")
        return
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    print("written", OUT)


if __name__ == "__main__":
    main()
