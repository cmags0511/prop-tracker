"""One-off probe (Oct 30): what does API-SPORTS' free plan return? Per sport host: the daily quota (response headers), and for
American football (NFL, college), NBA and basketball: injuries, games, odds (bookmakers and bet types) and anything lineup-like.
Uses the APISPORTS_KEY environment variable (GitHub Actions secret). About 20 requests in total, spread over the sports' own quotas."""
import os, json, urllib.request, urllib.parse, urllib.error
KEY = os.environ.get("APISPORTS_KEY", "").strip()
used = {}


def get(host, path, **params):
    url = f"https://{host}{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY, "Accept": "application/json", "User-Agent": "prop-tracker"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            h = {k.lower(): v for k, v in r.headers.items()}
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode()[:200]}, {}
    except Exception as e:
        return {"error": str(e)[:150]}, {}
    used[host] = used.get(host, 0) + 1
    q = {k: v for k, v in h.items() if "ratelimit" in k}
    return d, q


def show(host, path, label=None, n=2, **params):
    d, q = get(host, path, **params)
    print(f"\n--- {host}{path} {params or ''}")
    if q: print("quota headers:", q)
    if "http_error" in d or "error" in d:
        print(d); return d
    print("errors:", d.get("errors"), "| results:", d.get("results"), "| paging:", d.get("paging"))
    for x in (d.get("response") or [])[:n]:
        print("  ", json.dumps(x)[:420])
    return d


AF = "v1.american-football.api-sports.io"
BK = "v1.basketball.api-sports.io"
NBA = "v2.nba.api-sports.io"
FB = "v3.football.api-sports.io"
for h in (AF, BK, NBA, FB):
    d, q = get(h, "/status")
    print(f"\n=== {h} /status ===", json.dumps(d)[:420], q)

# American football: NFL (league 1) and NCAA (league 2)
show(AF, "/leagues", n=3, search="NFL")
show(AF, "/leagues", n=3, search="NCAA")
g = show(AF, "/games", n=2, league=1, season=2026, date="2026-11-01")
gid = ((g.get("response") or [{}])[0].get("game") or {}).get("id") if isinstance(g, dict) else None
show(AF, "/injuries", n=4, league=1, season=2026)
show(AF, "/odds/bookmakers", n=12)
show(AF, "/odds/bets", n=40)
if gid:
    show(AF, "/odds", n=2, game=gid)
show(AF, "/players/statistics", n=1, id=1, season=2025) if False else None
# NBA host and basketball host
show(NBA, "/games", n=2, date="2026-10-31")
show(NBA, "/players/statistics", n=1, game=1) if False else None
show(NBA, "/injuries", n=3) if False else None
show(BK, "/leagues", n=3, search="NBA")
show(BK, "/games", n=2, league=12, season="2026-2027", date="2026-10-31")
show(BK, "/odds/bets", n=30)
print("\nrequests made per host:", used)
