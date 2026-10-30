"""One-off probe (Oct 30): does OddsPapi's free plan return college football player props?
Uses a handful of the 250 monthly requests. Prints trimmed responses; no key is printed."""
import os, json, urllib.request, urllib.parse, urllib.error, datetime as dt
KEY = os.environ.get("ODDSPAPI_KEY", "").strip()
B = "https://api.oddspapi.io/v4"


def get(path, **q):
    q["apiKey"] = KEY
    url = f"{B}{path}?{urllib.parse.urlencode(q)}"
    print(f"\n--- GET {path} {({k: v for k, v in q.items() if k != 'apiKey'})}")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "prop-tracker", "Accept": "application/json"}), timeout=60) as r:
            hd = {k: v for k, v in r.headers.items() if "limit" in k.lower() or "remaining" in k.lower() or "quota" in k.lower()}
            body = r.read()
        print("status 200", hd, len(body), "bytes")
        return json.loads(body)
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:300])
    except Exception as e:
        print("error", e)


today = dt.date.today()
fx = None
for path, q in (("/fixtures", dict(sportId=14, from_=str(today), to=str(today + dt.timedelta(days=2)))),
                ("/fixtures", dict(tournamentId=27653)),
                ("/fixtures", dict(sportId=14))):
    q = {("from" if k == "from_" else k): v for k, v in q.items()}
    fx = get(path, **q)
    if fx:
        break
rows = fx if isinstance(fx, list) else (fx or {}).get("data") or (fx or {}).get("fixtures") or []
print("fixtures:", len(rows)); print(json.dumps(rows[:2])[:600])
now = dt.datetime.now(dt.timezone.utc).isoformat()
up = [r for r in rows if r.get("hasOdds") and r.get("startTime", "") > now]
print("upcoming with odds:", len(up), "tournaments:", {t: sum(1 for r in up if r["tournamentId"] == t) for t in {r["tournamentId"] for r in up}})
r0 = next(r for r in up if r["tournamentId"] == 27653)
print("FULL ROW KEYS:", list(r0)); print(json.dumps({k: v for k, v in r0.items() if k != "externalProviders"})[:900])
print("participants keys:", [k for k in r0 if "articipant" in k or "name" in k.lower()])
nfl = next((r for r in up if r["tournamentId"] != 27653), None)
print("OTHER TOURNAMENT ROW:", json.dumps({k: v for k, v in (nfl or {}).items() if k != "externalProviders"})[:600])
for path, q in (("/participants", dict(sportId=14)), ("/tournaments", dict(sportId=14))):
    d = get(path, **q)
    if isinstance(d, list):
        print(path, len(d), json.dumps(d[:3])[:500])
        if path == "/tournaments":
            print([x for x in d if x.get("tournamentId") in (27653, 790, 31)][:5])
    else:
        print(path, json.dumps(d)[:300])
