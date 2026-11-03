import json, sys, datetime as dt
sys.path.insert(0, ".")
from fetch_prices import FD, FD_KEY, get
out = {}
page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId=nhl&_ak={FD_KEY}&timezone=America%2FNew_York")
evs = (page.get("attachments") or {}).get("events", {})
now = dt.datetime.now(dt.timezone.utc)
ups = sorted([e for e in evs.values() if " @ " in e["name"] and dt.datetime.fromisoformat(e["openDate"].replace("Z", "+00:00")) > now], key=lambda e: e["openDate"])
ev = ups[0]
out["event"] = ev["name"]
for tab in ("goals", "points-assists", "shots", "quick-hits", "period-player-props", "popular"):
    d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}&tab={tab}")
    ms = (d.get("attachments") or {}).get("markets", {}).values()
    t = {}
    for m in ms:
        rs = m.get("runners") or []
        t[m.get("marketName")] = {"type": m.get("marketType"), "n": len(rs), "bettingType": m.get("bettingType"),
            "sample": [(r.get("runnerName"), r.get("handicap"), ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")) for r in rs[:4]]}
    out[tab] = t
json.dump(out, open("probe_tmp/fd_probe_out.json", "w"), indent=0, default=str)
print(len(json.dumps(out)))
