import json, datetime as dt
from fetch_lines import get
out = {}
for sport, league in (("basketball", "nba"), ("football", "nfl")):
    day = dt.date.today()
    evs = []
    for k in range(4):
        evs += get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates={day + dt.timedelta(days=k):%Y%m%d}").get("events", [])
    for ev in evs:
        if ev.get("status", {}).get("type", {}).get("state") != "pre":
            continue
        try:
            d = get(f"https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{ev['id']}/competitions/{ev['id']}/odds/100/propBets?limit=1000")
        except Exception as e:
            out[league + "_err"] = str(e); continue
        out.setdefault(league, []).extend(d.get("items", []))
        if len(out[league]) > 600: break
json.dump(out, open("probe_dk.json", "w"), indent=1)
