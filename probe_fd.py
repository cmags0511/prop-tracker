import json, datetime as dt
from fetch_prices import get, FD, FD_KEY
out = {}
for lg in ("nba", "nfl"):
    try:
        page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId={lg}&_ak={FD_KEY}&timezone=America%2FNew_York")
    except Exception as e:
        out[lg] = str(e); continue
    evs = [ev for ev in (page.get("attachments") or {}).get("events", {}).values() if " @ " in ev["name"]]
    out[lg + "_events"] = [(e["name"], e["openDate"]) for e in evs[:20]]
    if not evs: continue
    ev = sorted(evs, key=lambda e: e["openDate"])[0]
    d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}")
    lay = d.get("layout") or {}
    out[lg + "_tabs"] = [(t.get("title"), t.get("seoIdentifier") or t.get("id")) for t in (lay.get("tabs") or {}).values()] if isinstance(lay.get("tabs"), dict) else str(lay.get("tabs"))[:2000]
    names = {}
    for tab in [t[1] for t in out[lg + "_tabs"]] if isinstance(out[lg + "_tabs"], list) else []:
        try:
            dd = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}&tab={tab}")
        except Exception as e:
            names[tab] = str(e); continue
        ms = (dd.get("attachments") or {}).get("markets", {}).values()
        names[tab] = sorted({m.get("marketName", "").partition(" - ")[2] or m.get("marketName", "") for m in ms})[:60]
    out[lg + "_markets"] = names
json.dump(out, open("probe_fd.json", "w"), indent=1)
