import json, datetime as dt
from fetch_prices import get, FD, FD_KEY, PIN, PIN_KEY
out = {}
now = dt.datetime.now(dt.timezone.utc)
# FanDuel: soccer page -> an upcoming big-league match -> tabs -> player markets
for pid in ("soccer", "premier-league", "epl"):
    try:
        page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId={pid}&_ak={FD_KEY}&timezone=America%2FNew_York")
    except Exception as e:
        out["fd_" + pid] = str(e); continue
    evs = [ev for ev in (page.get("attachments") or {}).get("events", {}).values() if " v " in ev.get("name", "") or " @ " in ev.get("name", "")]
    comps = {c.get("name") for c in ((page.get("attachments") or {}).get("competitions") or {}).values()}
    out["fd_" + pid] = {"events": [(e["name"], e["openDate"], e.get("competitionId")) for e in evs[:15]], "comps": sorted(c for c in comps if c)[:40]}
    if evs and "fd_event" not in out:
        ev = sorted([e for e in evs if dt.datetime.fromisoformat(e["openDate"].replace("Z", "+00:00")) > now], key=lambda e: e["openDate"])
        for e in ev[:6]:
            d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={e['eventId']}")
            tabs = (d.get("layout") or {}).get("tabs") or {}
            titles = [t.get("title") for t in (tabs.values() if isinstance(tabs, dict) else [])]
            if not any("Player" in (t or "") or "Shots" in (t or "") for t in titles):
                continue
            out["fd_event"] = {"name": e["name"], "tabs": titles}
            mk = {}
            for t in titles:
                if not t or not any(w in t for w in ("Player", "Shots", "Goal", "Scorer")):
                    continue
                slug = t.lower().replace(" ", "-")
                try:
                    dd = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={e['eventId']}&tab={slug}")
                except Exception as ex:
                    mk[slug] = str(ex); continue
                ms = list((dd.get("attachments") or {}).get("markets", {}).values())
                mk[slug] = [{"name": m.get("marketName"), "runners": [(r.get("runnerName"), r.get("handicap"), ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")) for r in (m.get("runners") or [])[:6]]} for m in ms[:8]]
            out["fd_markets"] = mk
            break
# Pinnacle: soccer leagues, then player props for one big league
try:
    head = {"X-API-Key": PIN_KEY}
    lgs = get(f"{PIN}/sports/29/leagues?all=false", **head)
    big = [l for l in lgs if l.get("name") in ("England - Premier League", "Spain - La Liga", "Germany - Bundesliga", "Italy - Serie A", "UEFA - Champions League")]
    out["pin_leagues"] = [(l["id"], l["name"]) for l in big]
    for l in big[:3]:
        mus = get(f"{PIN}/leagues/{l['id']}/matchups", **head)
        cats = {}
        for m in mus:
            sp = m.get("special") or {}
            if sp:
                cats.setdefault(sp.get("category"), []).append(sp.get("description"))
        out["pin_" + l["name"]] = {k: (len(v), v[:8]) for k, v in cats.items()}
except Exception as e:
    out["pin_err"] = str(e)
json.dump(out, open("probe_soc.json", "w"), indent=1)
