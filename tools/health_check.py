"""HK Live 每日健康檢查。

檢查自動管線有冇靜靜死：Worker 即時數據、運輸署咪錶來源、線上網站、各份 data 檔新鮮度。
有任何致命問題就 exit 1（GitHub Actions 會發失敗通知）。
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://hktechguys.github.io/hk-live/"
WORKER = "https://hk-live-push.hklive.workers.dev"
TD_CSV = "https://resource.data.one.gov.hk/td/psiparkingspaces/occupancystatus/occupancystatus.csv"
UA = "hk-live-health/1.0 (+https://hktechguys.github.io/hk-live/)"
HKT = timezone(timedelta(hours=8))
problems = []
warns = []


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.getcode(), r.read()


def check_worker():
    try:
        code, body = fetch(WORKER + "/parks?h=" + str(int(datetime.now().timestamp())))
    except Exception as e:
        problems.append("Worker /parks 拉唔到：%s" % e)
        return
    try:
        d = json.loads(body)
        rows = d.get("rows") or []
        at = int(d.get("at") or 0)
        if not rows:
            problems.append("Worker /parks rows 係 0（出行易可能改格式或死咗）")
        elif len(rows) < 1000:
            warns.append("Worker /parks 只得 %d 個場（正常約 1,654）" % len(rows))
        age = (datetime.now().timestamp() * 1000 - at) / 60000
        if age > 30:
            problems.append("Worker /parks 數據 %.0f 分鐘前（>30 分鐘，可能快取或上游壞）" % age)
        print("worker ok: %d rows, %.1f 分鐘前" % (len(rows), age))
    except Exception as e:
        problems.append("Worker /parks 內容解析失敗：%s" % e)


def check_td():
    try:
        code, body = fetch(TD_CSV)
        head = body.decode("utf-8", "replace").splitlines()[0]
        if "ParkingSpaceId" not in head:
            problems.append("運輸署咪錶 CSV 表頭唔對：%s" % head[:80])
        else:
            print("td ok: %s" % head[:60])
    except Exception as e:
        problems.append("運輸署咪錶 CSV 拉唔到：%s" % e)


def check_site():
    try:
        code, body = fetch(SITE + "index.html?hc=" + str(int(datetime.now().timestamp())))
        txt = body.decode("utf-8", "replace")
        missing = [n for n in ('id="p-park"', 'id="tab-map"', "hk-live-push") if n not in txt]
        if missing:
            problems.append("線上 index.html 缺少 %s（Pages 可能未部署）" % "、".join(missing))
        else:
            print("site ok: %.0f KB" % (len(txt) / 1024))
    except Exception as e:
        problems.append("線上網站拉唔到：%s" % e)


def age_hours(val):
    if isinstance(val, (int, float)) and val > 1e11:      # epoch ms
        dt = datetime.fromtimestamp(val / 1000, HKT)
    else:
        try:
            dt = datetime.strptime(str(val)[:16], "%Y-%m-%d %H:%M").replace(tzinfo=HKT)
        except Exception:
            return None
    return (datetime.now(HKT) - dt).total_seconds() / 3600


def check_data():
    for name, limit_h, fatal_h in (("cafes.json", 36, 96), ("parking.json", 12, 48),
                                   ("meters.json", 12, 48), ("park_fees.json", 240, 480)):
        p = os.path.join(ROOT, "data", name)
        if not os.path.exists(p):
            problems.append("data/%s 唔存在" % name)
            continue
        d = json.load(open(p, encoding="utf-8"))
        gen = d.get("generated") or d.get("at") or ""
        h = age_hours(gen) if gen else None
        if h is None:
            warns.append("data/%s 冇 generated 時間" % name)
            continue
        if h > fatal_h:
            problems.append("data/%s 已 %.0f 小時冇更新（>%d 小時，自動更新停咗）" % (name, h, fatal_h))
        elif h > limit_h:
            warns.append("data/%s 已 %.0f 小時冇更新" % (name, h))
        else:
            print("data/%s ok: %.1f 小時前" % (name, h))


def main():
    check_worker()
    check_td()
    check_site()
    check_data()
    for w in warns:
        print("WARN:", w)
    for p in problems:
        print("FAIL:", p)
    if problems:
        print("健康檢查失敗（%d 項）" % len(problems))
        return 1
    print("全部正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
