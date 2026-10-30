"""One-off probe 2 (Oct 30): API-SPORTS NBA host (v2.nba.api-sports.io), which allowed the current season on the free plan.
Which endpoints exist (injuries? lineups? odds?) and do they work for current games? ~8 requests of that host's 100 a day."""
import os, json, urllib.request, urllib.parse, urllib.error
KEY = os.environ.get("APISPORTS_KEY", "").strip()
H = "v2.nba.api-sports.io"


def show(path, n=2, **params):
    url = f"https://{H}{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY, "Accept": "application/json", "User-Agent": "prop-tracker"})
    print(f"\n--- {path} {params or ''}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            h = {k.lower(): v for k, v in r.headers.items() if "requests-remaining" in k.lower()}
            d = json.load(r)
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:200]); return {}
    print(h, "| errors:", d.get("errors"), "| results:", d.get("results"))
    for x in (d.get("response") or [])[:n]:
        print("  ", json.dumps(x)[:520])
    return d


g = show("/games", n=1, date="2026-10-30")
fin = [x for x in (g.get("response") or []) if (x.get("status") or {}).get("short") == 3]
gid = (fin[0] if fin else (g.get("response") or [{}])[0]).get("id")
print("sample game id", gid, "finished games:", len(fin))
show("/players/statistics", n=3, game=gid)
show("/games/statistics", n=1, id=gid)
show("/injuries", n=3)
show("/players", n=2, team=1, season=2026)
show("/odds", n=1, game=gid)
show("/standings", n=1, league="standard", season=2026)
