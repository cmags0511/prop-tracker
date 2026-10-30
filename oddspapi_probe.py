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
fid = next((r.get("fixtureId") or r.get("id") for r in rows if (r.get("fixtureId") or r.get("id"))), None)
print("sample fixture id:", fid)
if fid:
    d = get("/odds", fixtureId=fid)
    if d:
        bo = d.get("bookmakerOdds") or {}
        print("bookmakers:", list(bo)[:20])
        mk = {}
        for b, v in bo.items():
            for mid, m in (v.get("markets") or {}).items():
                n = sum(1 for o in (m.get("outcomes") or {}).values() if any(k != "0" for k in (o.get("players") or {})))
                mk.setdefault(mid, [0, 0])[0] += 1; mk[mid][1] += n
        print("markets seen (id: [books, outcomes with players]):", dict(list(mk.items())[:60]))
        withp = [mid for mid, v in mk.items() if v[1]]
        print("market ids with player entries:", withp[:40])
        for b, v in bo.items():
            for mid in withp[:1]:
                m = (v.get("markets") or {}).get(mid)
                if m:
                    print(b, mid, json.dumps(m)[:700]); break
m = get("/markets")
if isinstance(m, list):
    want = ("rushing attempts", "carries", "receptions", "completions", "kicking", "field goal")
    hit = [x for x in m if any(w in json.dumps(x).lower() for w in want)]
    print("market catalogue:", len(m), "rows;", len(hit), "match", json.dumps(hit[:15])[:1500])
