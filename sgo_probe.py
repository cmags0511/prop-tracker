"""One-off probe (Oct 30): what does SportsGameOdds' FREE plan return for NFL / college player props?
Which bookmakers, which player-prop stats (tackles? sacks?), and do those carry prices and lines?
Uses the SGO_API_KEY environment variable (GitHub Actions secret). Costs about 3 requests / 15 objects of the 2,500 a month."""
import os, json, collections, urllib.request, urllib.parse, urllib.error
KEY = os.environ.get("SGO_API_KEY", "").strip()
BASE = "https://api.sportsgameodds.com/v2"


def get(path, **params):
    req = urllib.request.Request(f"{BASE}{path}?{urllib.parse.urlencode(params)}", headers={"x-api-key": KEY, "Accept": "application/json", "User-Agent": "prop-tracker-probe"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r), dict(r.headers)
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode()[:300]}, {}


for lg in ("NFL", "NCAAF", "NBA"):
    d, hdr = get("/events", leagueID=lg, oddsAvailable="true", finalized="false", limit=5)
    print(f"\n=== {lg} ===")
    if "http_error" in d:
        print(d); continue
    evs = d.get("data") or []
    print("success:", d.get("success"), "| events returned:", len(evs), "| keys:", list(d.keys())[:6])
    rl = {k: v for k, v in hdr.items() if "limit" in k.lower() or "remaining" in k.lower() or "usage" in k.lower()}
    if rl: print("rate-limit headers:", rl)
    books = collections.Counter(); stats = collections.defaultdict(lambda: collections.Counter()); priced = collections.Counter(); sample = {}
    for ev in evs:
        teams = ev.get("teams") or {}
        print("  event:", (teams.get("away") or {}).get("names", {}).get("short"), "@", (teams.get("home") or {}).get("names", {}).get("short"), "|", (ev.get("status") or {}).get("startsAt"), "| odds:", len(ev.get("odds") or {}))
        for oid, o in (ev.get("odds") or {}).items():
            if o.get("statEntityID") in ("all", "home", "away", None):
                continue
            sid = o.get("statID")
            for b, v in (o.get("byBookmaker") or {}).items():
                if v.get("available", True) is False:
                    continue
                books[b] += 1; stats[sid][b] += 1
                if v.get("odds") is not None: priced[sid] += 1
                if sid not in sample: sample[sid] = (oid, b, v.get("odds"), v.get("overUnder"))
    print("player-prop quotes by bookmaker:", dict(books.most_common(15)))
    print("player-prop stats (quotes with a price):")
    for sid, c in sorted(stats.items(), key=lambda t: -sum(t[1].values())):
        print(f"  {sid:28s} {sum(c.values()):4d} quotes, {priced[sid]:4d} priced | books: {dict(c.most_common(4))} | e.g. {sample[sid]}")
    hit = [s for s in stats if any(w in str(s).lower() for w in ("tackle", "sack", "assist"))]
    print("tackle/sack/assist-like stats:", hit)
