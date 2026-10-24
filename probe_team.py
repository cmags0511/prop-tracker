import json, datetime as dt, collections
from fetch_prices import get, FD, FD_KEY, PIN, PIN_KEY
out = {}
now = dt.datetime.now(dt.timezone.utc)
head = {"X-API-Key": PIN_KEY}
lgs = get(f"{PIN}/sports/29/leagues?all=false", **head)
out["pin_leagues"] = sorted([(l["id"], l["name"], l.get("matchupCount")) for l in lgs], key=lambda x: -(x[2] or 0))[:60]
mus = get(f"{PIN}/leagues/1980/matchups", **head)
mk = get(f"{PIN}/leagues/1980/markets/straight", **head)
main = [m for m in mus if not m.get("special") and m.get("type") == "matchup"]
out["pin_main_example"] = main[:1]
mid = main[0]["id"] if main else None
out["pin_market_keys"] = collections.Counter(m.get("key", "").split(";")[0] + ";" + ";".join(m.get("key", "").split(";")[1:3]) for m in mk).most_common(30)
out["pin_markets_for_one"] = [m for m in mk if m.get("matchupId") == mid][:12]
sp = [m for m in mus if (m.get("special") or {}).get("category") == "Team Props" and (m.get("parentId") == mid or (m.get("parent") or {}).get("id") == mid)]
out["pin_specials_for_one"] = [{"desc": m["special"].get("description"), "parts": [(p.get("id"), p.get("name")) for p in m.get("participants", [])], "id": m["id"]} for m in sp][:40]
spm = {m["id"] for m in sp}
out["pin_special_prices"] = [m for m in mk if m.get("matchupId") in spm][:10]
# FanDuel: an EPL event, tabs Popular / Goals / Team Props / Half
page = get(f"{FD}/content-managed-page?page=SPORT&eventTypeId=1&_ak={FD_KEY}&timezone=America%2FNew_York")
evs = sorted([e for e in (page.get("attachments") or {}).get("events", {}).values() if e.get("competitionId") == 10932509 and dt.datetime.fromisoformat(e["openDate"].replace("Z", "+00:00")) > now], key=lambda e: e["openDate"])
e = evs[0]
out["fd_event"] = e["name"]
fdm = {}
for tab in ("popular", "goals", "team-props", "half"):
    try:
        d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={e['eventId']}&tab={tab}")
    except Exception as ex:
        fdm[tab] = str(ex); continue
    ms = list((d.get("attachments") or {}).get("markets", {}).values())
    fdm[tab] = [{"name": m.get("marketName"), "type": m.get("marketType"), "runners": [(r.get("runnerName"), r.get("handicap"), ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")) for r in (m.get("runners") or [])[:8]]} for m in ms]
out["fd_markets"] = fdm
json.dump(out, open("probe_team.json", "w"), indent=1, default=str)
