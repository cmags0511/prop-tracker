import json, datetime as dt
from fetch_prices import get, FD, FD_KEY
out = {}
now = dt.datetime.now(dt.timezone.utc)
page = get(f"{FD}/content-managed-page?page=SPORT&eventTypeId=1&_ak={FD_KEY}&timezone=America%2FNew_York")
evs = [e for e in (page.get("attachments") or {}).get("events", {}).values() if e.get("competitionId") == 10932509 and dt.datetime.fromisoformat(e["openDate"].replace("Z", "+00:00")) > now]
evs.sort(key=lambda e: e["openDate"])
for e in evs[:2]:
    d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={e['eventId']}")
    tabs = (d.get("layout") or {}).get("tabs") or {}
    titles = [t.get("title") for t in (tabs.values() if isinstance(tabs, dict) else [])]
    rec = {"tabs": titles, "markets": {}}
    for t in titles:
        if not t or not any(w in t.lower() for w in ("player", "shot", "scorer", "card", "assist")):
            continue
        slug = t.lower().replace(" ", "-").replace("/", "-")
        try:
            dd = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={e['eventId']}&tab={slug}")
        except Exception as ex:
            rec["markets"][slug] = str(ex); continue
        ms = list((dd.get("attachments") or {}).get("markets", {}).values())
        names = sorted({m.get("marketName") for m in ms})
        ex = [{"name": m.get("marketName"), "runners": [(r.get("runnerName"), r.get("handicap"), ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")) for r in (m.get("runners") or [])[:12]]}
              for m in ms if any(w in (m.get("marketName") or "").lower() for w in ("shot", "goalscorer", "to score"))][:4]
        rec["markets"][slug] = {"names": names[:30], "examples": ex}
    out[e["name"]] = rec
json.dump(out, open("probe_soc.json", "w"), indent=1)
