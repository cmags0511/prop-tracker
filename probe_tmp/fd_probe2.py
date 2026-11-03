import json, sys, datetime as dt
sys.path.insert(0, ".")
from fetch_prices import FD, FD_KEY, get
out = {}
page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId=nhl&_ak={FD_KEY}&timezone=America%2FNew_York")
evs = (page.get("attachments") or {}).get("events", {})
now = dt.datetime.now(dt.timezone.utc)
ups = sorted([e for e in evs.values() if " @ " in e["name"] and dt.datetime.fromisoformat(e["openDate"].replace("Z", "+00:00")) > now], key=lambda e: e["openDate"])
ev = ups[0]
out["event"] = ev["name"]; out["n_events"] = len(ups)
out["event_keys"] = [k for k in ev.keys()]
d0 = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}")
a = d0.get("attachments") or {}
out["tabs_in_default"] = {k: (v if not isinstance(v, (dict, list)) else str(v)[:300]) for k, v in a.items() if k != "markets" and k != "events"}
for tab in ("goalie-props", "goalie", "saves", "goalie-saves", "player-props", "goalies", "player-saves", "specials"):
    try:
        d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}&tab={tab}")
        ms = (d.get("attachments") or {}).get("markets", {}).values()
        names = [m.get("marketName") for m in ms]
        out[tab] = [n for n in names if n and ("ave" in n or "oalie" in n)] or f"{len(names)} markets, none goalie"
    except Exception as e:
        out[tab] = f"err {e}"
allm = {}
for tab in ("popular", "shots"):
    d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}&tab={tab}")
    for m in (d.get("attachments") or {}).get("markets", {}).values():
        allm[m.get("marketName")] = m.get("marketType")
out["all_names_sample"] = sorted(allm)[:80]
json.dump(out, open("probe_tmp/fd_probe2_out.json", "w"), indent=1, default=str)
