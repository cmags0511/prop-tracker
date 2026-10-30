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
up = [r for r in rows if r.get("hasOdds") and r.get("startTime", "") > now and r.get("tournamentId") == 27653]
print("upcoming NCAAF with odds:", len(up))
cat = get("/markets")
cat = {str(x["marketId"]): x for x in cat} if isinstance(cat, list) else {}
print("catalogue rows:", len(cat))
US = ("draftkings", "fanduel", "betmgm", "pinnacle", "espnbet", "caesars", "thescore", "bet365", "hardrockbet", "fanatics")
for r in up[:2]:
    fid = r["fixtureId"]
    print("\n=== fixture", fid, r.get("startTime"))
    d = None
    for q in (dict(fixtureId=fid, bookmaker="draftkings,fanduel,pinnacle,betmgm"), dict(fixtureId=fid)):
        d = get("/odds", **q)
        if d and d.get("bookmakerOdds"):
            break
    bo = (d or {}).get("bookmakerOdds") or {}
    print("bookmakers returned:", len(bo), "| US-ish:", [b for b in bo if b in US])
    # player-prop markets: id -> {book: players}
    pm = {}
    for b, v in bo.items():
        for mid, m in (v.get("markets") or {}).items():
            n = 0
            for o in (m.get("outcomes") or {}).values():
                n = max(n, len([k for k in (o.get("players") or {}) if k != "0"]))
            if n:
                pm.setdefault(mid, {})[b] = n
    print("player-prop markets:", len(pm))
    for mid, books in sorted(pm.items(), key=lambda kv: -len(kv[1]))[:40]:
        c = cat.get(mid, {})
        us = {b: n for b, n in books.items() if b in US}
        print(mid, "|", c.get("marketName"), "|", c.get("marketType"), "| hcap", c.get("handicap"), "| books", len(books), "| US", us)
    # one over/under example
    for mid, books in pm.items():
        c = cat.get(mid, {})
        if "total" in str(c.get("marketType")) and any(b in US for b in books):
            b = next(b for b in books if b in US)
            print("EXAMPLE", b, mid, c.get("marketName"), json.dumps(bo[b]["markets"][mid])[:600]); break
