import json, re, time, datetime as dt
from fetch_prices import get, FD, FD_KEY
now = dt.datetime.now(dt.timezone.utc)
page = get(f"{FD}/content-managed-page?page=SPORT&eventTypeId=1&_ak={FD_KEY}&timezone=America%2FNew_York")
comps = {c.get("competitionId") or k: c.get("name") for k, c in ((page.get("attachments") or {}).get("competitions") or {}).items()}
want = {"English Premier League", "Spanish La Liga", "German Bundesliga", "Italian Serie A", "French Ligue 1", "UEFA Champions League", "UEFA Europa League"}
evs = [e for e in (page.get("attachments") or {}).get("events", {}).values()
       if dt.datetime.fromisoformat(e["openDate"].replace("Z", "+00:00")) > now and str(comps.get(e.get("competitionId")) or comps.get(str(e.get("competitionId")))) in want]
evs.sort(key=lambda e: e["openDate"])
rows = []
MK = {"Player To Have 1 Or More Shots": ("sh", 1), "Player To Have 2 Or More Shots": ("sh", 2), "Player To Have 3 Or More Shots": ("sh", 3),
      "Player To Have 4 Or More Shots": ("sh", 4), "Player To Have 1 Or More Shots On Target": ("sot", 1),
      "Player To Have 2 Or More Shots On Target": ("sot", 2), "Anytime Goalscorer": ("g", 1), "To Score 2 or More Goals": ("g", 2), "Anytime Assist": ("a", 1)}
for e in evs[:30]:
    for tab in ("shots", "shots-on-target", "goal-scorer", "assists"):
        try:
            d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={e['eventId']}&tab={tab}")
        except Exception:
            continue
        for m in (d.get("attachments") or {}).get("markets", {}).values():
            if m.get("marketName") in MK:
                mk, k = MK[m["marketName"]]
                for r in m.get("runners") or []:
                    am = ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")
                    if am is not None:
                        rows.append([e["name"], e["openDate"], comps.get(e.get("competitionId")), r["runnerName"], mk, k, am])
        time.sleep(.1)
json.dump({"events": len(evs[:30]), "rows": rows}, open("probe_soc.json", "w"))
print(len(evs), len(rows))
