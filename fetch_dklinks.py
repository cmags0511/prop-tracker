"""DraftKings game-page IDs from ESPN's free scoreboard -> dklinks.json.

ESPN's odds block carries DraftKings' own links (they go through ESPN's affiliate gateway; the DraftKings event ID is
inside). The app turns an ID into https://sportsbook.draftkings.com/event/<id> for an "Open in DraftKings" button on
every bet. It opens that game's page: the feed has no link to a single player prop (those need The Odds API's paid
per-bet links, which the app doesn't use), so the button comes with a "Copy bet" so the prop can be searched.

Output: {"built", "games": [{"lg", "ev" (ESPN event id), "t", "away", "home", "dk"}]}   (upcoming games only)

Usage: python fetch_dklinks.py [dklinks.json]
"""
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request

OUT = sys.argv[1] if len(sys.argv) > 1 else "dklinks.json"
BASE = "https://site.api.espn.com/apis/site/v2/sports"
MAIN = {"NFL": "football/nfl", "NBA": "basketball/nba", "CFB": "football/college-football", "NHL": "hockey/nhl"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def strings(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)
    elif isinstance(o, str):
        yield o


def dk_id(ev):
    for s in strings(ev.get("competitions", [{}])[0].get("odds", [])):
        if "draftkings" in s:
            m = re.search(r"sportsbook\.draftkings\.com/event/(\d+)", urllib.parse.unquote(urllib.parse.unquote(s)))
            if m:
                return m.group(1)
    return None


def games(lg, path, days, now):
    out, seen = [], set()
    for k in range(days + 1):
        d = now.date() + dt.timedelta(days=k)
        try:
            sb = get(f"{BASE}/{path}/scoreboard?dates={d:%Y%m%d}")
        except Exception as e:
            print(f"{lg} {d}: {e}")
            continue
        for ev in sb.get("events", []):
            if ev["status"]["type"].get("state") != "pre" or ev["id"] in seen:
                continue
            seen.add(ev["id"])
            dk = dk_id(ev)
            cs = {c["homeAway"]: c["team"].get("abbreviation", "") for c in ev["competitions"][0]["competitors"]}
            if dk and "home" in cs and "away" in cs:
                out.append({"lg": lg, "ev": str(ev["id"]), "t": ev["date"].replace("Z", "+00:00"), "away": cs["away"], "home": cs["home"], "dk": dk})
    return out


def main():
    now = dt.datetime.now(dt.timezone.utc)
    res = []
    for lg, path in MAIN.items():
        g = games(lg, path, 8, now)
        print(f"{lg}: {len(g)} games with a DraftKings page")
        res += g
    try:   # soccer: only the leagues that have matches in soccer.json
        leagues = sorted({m["lg"] for m in json.load(open("soccer.json")).get("matches", [])})
    except Exception:
        leagues = []
    for lgid in leagues:
        res += games("SOC", f"soccer/{lgid}", 4, now)
    json.dump({"built": now.isoformat(timespec="minutes"), "games": res}, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(res)} games")


if __name__ == "__main__":
    main()
