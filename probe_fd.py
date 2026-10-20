import json, datetime as dt
from fetch_prices import get, FD, FD_KEY
out = {}
now = dt.datetime.now(dt.timezone.utc)
for lg in ("nba", "nfl"):
    page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId={lg}&_ak={FD_KEY}&timezone=America%2FNew_York")
    evs = [ev for ev in (page.get("attachments") or {}).get("events", {}).values()
           if " @ " in ev["name"] and "(" not in ev["name"] and dt.datetime.fromisoformat(ev["openDate"].replace("Z", "+00:00")) > now + dt.timedelta(hours=2)]
    ev = sorted(evs, key=lambda e: e["openDate"])[0]
    out[lg + "_event"] = ev["name"]
    d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}")
    tabs = (d.get("layout") or {}).get("tabs") or {}
    out[lg + "_tabraw"] = list(tabs.values())[:3] if isinstance(tabs, dict) else str(tabs)[:1500]
    seo = [(t.get("title"), t.get("seoIdentifier"), t.get("id")) for t in (tabs.values() if isinstance(tabs, dict) else [])]
    out[lg + "_tabs"] = seo
    names = {}
    for title, s, i in seo:
        if not s: continue
        try:
            dd = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}&tab={s}")
        except Exception as e:
            names[s] = str(e); continue
        ms = list((dd.get("attachments") or {}).get("markets", {}).values())
        names[s] = [len(ms)] + sorted({m.get("marketName", "") for m in ms})[:25]
        ex = [m for m in ms if len(m.get("runners") or []) == 2 and " - " in m.get("marketName", "")][:2]
        if ex: names[s + "_example"] = [{"name": m["marketName"], "runners": [(r.get("runnerName"), r.get("handicap"), ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")) for r in m["runners"]]} for m in ex]
    out[lg + "_markets"] = names
json.dump(out, open("probe_fd.json", "w"), indent=1)
