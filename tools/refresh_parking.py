"""Refresh TD parking datasets (runs inside GitHub Actions; no local data_raw needed).

Downloads the four Transport Department open-data files straight from
resource.data.one.gov.hk, then writes data/parking.json and data/meters.json
in the same shape the site reads.
"""

import csv
import io
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data")
os.makedirs(OUT, exist_ok=True)

BASE = "https://resource.data.one.gov.hk/td"
URLS = {
    "vacancy_all.json": BASE + "/carpark/vacancy_all.json",
    "basic_info_all.json": BASE + "/carpark/basic_info_all.json",
    "parkingspaces.csv": BASE + "/psiparkingspaces/spaceinfo/parkingspaces.csv",
    "occupancystatus.csv": BASE + "/psiparkingspaces/occupancystatus/occupancystatus.csv",
}


def fetch(name):
    req = urllib.request.Request(URLS[name], headers={"User-Agent": "hk-live-parking/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def load_json(name):
    return json.loads(fetch(name).decode("utf-8-sig"))


def read_csv(name, skip=2):
    text = fetch(name).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[skip]
    return [dict(zip(header, r)) for r in rows[skip + 1:] if len(r) == len(header)]


def hk_now():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


basic = {p["park_id"]: p for p in load_json("basic_info_all.json")["car_park"]}
vac = load_json("vacancy_all.json")["car_park"]

parks, latest = [], ""
for item in vac:
    pid = item.get("park_id")
    base = basic.get(pid)
    if not base:
        continue
    pc = pcd = 0
    for vt in item.get("vehicle_type", []):
        for sc in vt.get("service_category", []):
            if sc.get("category") != "HOURLY":
                continue
            if vt.get("type") == "P":
                pc += int(sc.get("vacancy") or 0)
            elif vt.get("type") == "P_D":
                pcd += int(sc.get("vacancy") or 0)
            ts = sc.get("lastupdate") or ""
            if ts > latest:
                latest = ts
    lat, lng = base.get("latitude"), base.get("longitude")
    if not lat or not lng:
        continue
    parks.append({
        "id": pid,
        "n": base.get("name_tc") or base.get("name_en") or pid,
        "e": base.get("name_en") or "",
        "a": base.get("displayAddress_tc") or "",
        "d": base.get("district_tc") or "",
        "la": round(float(lat), 5),
        "lo": round(float(lng), 5),
        "v": pc,
        "vd": pcd,
        "h": base.get("height") or 0,
    })

parks.sort(key=lambda p: -p["v"])
with open(os.path.join(OUT, "parking.json"), "w", encoding="utf-8") as fh:
    json.dump({
        "generated": hk_now(),
        "source": "運輸署 實時停車場空位 (vacancy_all.json / basic_info_all.json)",
        "last_update": latest,
        "count": len(parks),
        "parks": parks,
    }, fh, ensure_ascii=False, separators=(",", ":"))

spaces = read_csv("parkingspaces.csv")
occ, occ_time = {}, ""
for r in read_csv("occupancystatus.csv", skip=0):
    sid = r.get("ParkingSpaceId")
    if not sid:
        continue
    occ[sid] = 1 if (r.get("OccupancyStatus") or "").strip().upper() == "O" else 0
    ts = r.get("OccupancyDateChanged") or ""
    if ts > occ_time:
        occ_time = ts

meters = []
for r in spaces:
    sid = r.get("ParkingSpaceId")
    lat, lng = r.get("Latitude"), r.get("Longitude")
    if not sid or not lat or not lng:
        continue
    try:
        la, lo = round(float(lat), 5), round(float(lng), 5)
    except ValueError:
        continue
    meters.append([
        sid, la, lo, occ.get(sid, -1),
        (r.get("Street_tc") or "").strip(),
        (r.get("District_tc") or "").strip(),
        (r.get("VehicleType") or "").strip().upper(),   # A 任何車輛 / G 貨車 / C 旅遊巴
    ])

with open(os.path.join(OUT, "meters.json"), "w", encoding="utf-8") as fh:
    json.dump({
        "generated": hk_now(),
        "source": "運輸署 路邊泊車位位置 + 佔用狀態",
        "last_update": occ_time,
        "count": len(meters),
        "occupied": sum(1 for m in meters if m[3] == 1),
        "vacant": sum(1 for m in meters if m[3] == 0),
        "spaces": meters,
    }, fh, ensure_ascii=False, separators=(",", ":"))

print("parks: %d (vacancy update %s)" % (len(parks), latest))
print("meters: %d (vacant %d)" % (len(meters), sum(1 for m in meters if m[3] == 0)))
