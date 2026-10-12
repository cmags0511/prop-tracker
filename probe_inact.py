import json, urllib.request
def get(u):
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))
    except Exception as e:
        return {"ERR": str(e)}
out = {}
sb = get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard")
evs = [(e["id"], e["status"]["type"]["state"], e["date"], e["shortName"]) for e in sb.get("events", [])]
out["events"] = evs
# a game today (pre or in) and a finished game
pick = [e for e in evs if e[1] != "post"][:1] + [e for e in evs if e[1] == "post"][:1]
for eid, st, d, nm in pick:
    s = get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={eid}")
    out[f"sum_{st}_keys"] = list(s.keys())
    out[f"sum_{st}_injuries"] = s.get("injuries")
    out[f"sum_{st}_gameInfo"] = s.get("gameInfo")
    comp = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{eid}/competitions/{eid}")
    out[f"core_{st}_keys"] = list(comp.keys())
    for c in comp.get("competitors", [])[:1]:
        tid = c.get("id")
        r = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{eid}/competitions/{eid}/competitors/{tid}/roster")
        out[f"roster_{st}"] = {"keys": list(r.keys()), "sample": (r.get("entries") or [])[:3], "n": len(r.get("entries") or []),
                               "inactive": [x for x in (r.get("entries") or []) if not x.get("active", True) or x.get("didNotPlay")][:10]}
json.dump(out, open("out/probe.json", "w"), indent=1, default=str)
