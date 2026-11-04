import json, os, urllib.request, urllib.parse
K = os.environ["ODDS_API_KEY"]
B = "https://api.the-odds-api.com/v4"
def get(path, **q):
    q["apiKey"] = K
    with urllib.request.urlopen(f"{B}{path}?{urllib.parse.urlencode(q)}", timeout=40) as r:
        return json.loads(r.read()), {k: v for k, v in r.headers.items() if k.lower().startswith("x-requests")}
out = {}
evs, h = get("/sports/americanfootball_nfl/events")   # free
out["events_headers"] = h
ev = evs[0]; out["event"] = {k: ev[k] for k in ("id", "home_team", "away_team", "commence_time")}
d, h = get(f"/sports/americanfootball_nfl/events/{ev['id']}/odds", regions="us", bookmakers="draftkings", markets="player_pass_yds", oddsFormat="american", includeLinks="true", includeSids="true")
out["odds_headers"] = h
bk = d.get("bookmakers") or []
out["n_bookmakers"] = len(bk)
for b in bk:
    out["bookmaker"] = {k: v for k, v in b.items() if k != "markets"}
    for m in b.get("markets", [])[:1]:
        out["market"] = {k: v for k, v in m.items() if k != "outcomes"}
        out["outcomes"] = m["outcomes"][:4]
json.dump(out, open("probe_tmp/link_probe_out.json", "w"), indent=1)
print(json.dumps(out)[:1500])
