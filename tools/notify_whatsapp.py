"""Push a WhatsApp message when a watched metered space goes occupied -> vacant.

Usage (inside GitHub Actions):
    python tools/notify_whatsapp.py /tmp/meters_prev.json data/meters.json

Provider: CallMeBot (personal WhatsApp gateway, no business verification).
Needs repo secrets:
    WA_PHONE  phone in international format, e.g. 85291234567
    WA_KEY    CallMeBot apikey
Missing secrets => exits 0 quietly so the workflow never fails.

Filter file: tools/whatsapp_watch.json
    {"streets": ["麼地道", "廣東道"], "districts": ["油尖旺"], "ids": ["1234A"], "max": 5}
Empty filter => nothing is pushed (avoid spamming every 10 minutes).
"""

import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCH = os.path.join(ROOT, "tools", "whatsapp_watch.json")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def st_map(doc):
    out = {}
    for row in (doc or {}).get("spaces", []):
        try:
            out[str(row[0])] = (int(row[3]), row[4] or "", row[5] or "")
        except (IndexError, TypeError, ValueError):
            continue
    return out


def main():
    if len(sys.argv) < 3:
        print("usage: notify_whatsapp.py PREV NEW")
        return 0

    prev = st_map(load(sys.argv[1], {}))
    new = st_map(load(sys.argv[2], {}))
    if not prev:
        print("no previous snapshot, nothing to compare")
        return 0

    w = load(WATCH, {})
    streets = set(w.get("streets") or [])
    districts = set(w.get("districts") or [])
    ids = {str(i) for i in (w.get("ids") or [])}
    maxn = int(w.get("max", 5))

    if not (streets or districts or ids):
        print("whatsapp_watch.json has no filter; skipping push")
        return 0

    hits = []
    for sid, (st, street, dist) in new.items():
        old = prev.get(sid)
        if not old or old[0] != 1 or st != 0:
            continue
        if not (sid in ids or street in streets or dist in districts):
            continue
        hits.append((street, sid, dist))

    if not hits:
        print("no watched space turned vacant")
        return 0

    hits.sort()
    lines = ["🅿️ hk-live 咪錶有位（%d 個）" % len(hits)]
    for street, sid, dist in hits[:maxn]:
        lines.append("· %s %s%s" % (street or "路邊位", sid, ("（%s）" % dist) if dist else ""))
    if len(hits) > maxn:
        lines.append("…另有 %d 個" % (len(hits) - maxn))
    lines.append("https://hktechguys.github.io/hk-live/#meter")
    msg = "\n".join(lines)

    phone = os.environ.get("WA_PHONE")
    key = os.environ.get("WA_KEY")
    if not (phone and key):
        print("WA_PHONE / WA_KEY not configured; message that would be sent:")
        print(msg)
        return 0

    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
        {"phone": phone, "text": msg, "apikey": key}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "hk-live/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            print("callmebot:", r.status, r.read()[:120].decode("utf-8", "ignore"))
    except Exception as exc:
        print("callmebot failed:", exc)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
