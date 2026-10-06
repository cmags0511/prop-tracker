"""Fetch DraftKings and BetMGM player prop lines from The Odds API into odds.json.

Needs an API key from https://the-odds-api.com in the ODDS_API_KEY environment variable
(on GitHub: Settings > Secrets and variables > Actions > New repository secret).
Without a key it does nothing and leaves any existing odds.json alone.

Every request costs credits: (markets returned) x (regions). DraftKings + BetMGM count as
one region, so each game costs about one credit per prop type. The settings below keep
usage predictable, and the script stops before your remaining credits fall under
ODDS_RESERVE.

Optional settings (environment variables):
  ODDS_MARKETS_NFL / ODDS_MARKETS_NBA  comma-separated market keys (defaults below)
  ODDS_WINDOW_HOURS   only fetch games starting within this many hours   (default 36)
  ODDS_EVERY_HOURS    skip the fetch if the last one was more recent      (default 6)
  ODDS_RESERVE        never spend below this many remaining credits       (default 25)

Usage: python fetch_odds.py [odds.json]
"""
import json, os, re, sys, time, datetime as dt
import urllib.request, urllib.parse, urllib.error

OUT = sys.argv[1] if len(sys.argv) > 1 else "odds.json"
KEY = os.environ.get("ODDS_API_KEY", "").strip()
BASE = "https://api.the-odds-api.com/v4"
BOOKS = {"draftkings": "DK", "betmgm": "MGM"}

# The Odds API market key -> the prop id used in the app
MARKETS = {
    "NFL": {
        "player_pass_yds": "pyd", "player_pass_completions": "cmp", "player_pass_attempts": "att",
        "player_pass_tds": "ptd", "player_rush_yds": "ryd", "player_rush_attempts": "car",
        "player_receptions": "rec", "player_reception_yds": "recyd",
        "player_rush_reception_yds": "rry", "player_anytime_td": "td",
    },
    "NBA": {
        "player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "3pm",
        "player_points_rebounds_assists": "pra", "player_points_rebounds": "pr",
        "player_points_assists": "pa", "player_rebounds_assists": "ra",
    },
}
DEFAULTS = {
    "NFL": "player_pass_yds,player_rush_yds,player_reception_yds,player_receptions,player_anytime_td",
    "NBA": "player_points,player_rebounds,player_assists,player_threes,player_points_rebounds_assists",
}
SPORT = {"NFL": "americanfootball_nfl", "NBA": "basketball_nba"}
WINDOW = float(os.environ.get("ODDS_WINDOW_HOURS", 36))
EVERY = float(os.environ.get("ODDS_EVERY_HOURS", 6))
RESERVE = int(os.environ.get("ODDS_RESERVE", 25))


def norm(name):
    """Match player names across data sources: 'Kenneth Walker III' -> 'kenneth walker'."""
    n = re.sub(r"[^a-z ]", "", name.lower().replace("-", " "))
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)$", "", n.strip())
    return re.sub(r"\s+", " ", n).strip()


def implied(price):
    return 100 / (price + 100) if price > 0 else -price / (-price + 100)


remaining = None


def get(path, **params):
    global remaining
    params["apiKey"] = KEY
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        rem = r.headers.get("x-requests-remaining")
        if rem is not None:
            remaining = int(float(rem))
        return json.loads(r.read())


def main():
    if not KEY:
        print("ODDS_API_KEY not set; skipping sportsbook odds")
        return
    now = dt.datetime.now(dt.timezone.utc)
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    last = old.get("fetched")
    if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < EVERY * 3600:
        print(f"odds fetched at {last}; next fetch after {EVERY}h")
        return

    out = {"fetched": now.isoformat(timespec="minutes"), "books": list(BOOKS.values()), "NFL": {}, "NBA": {}}
    for lg in ("NFL", "NBA"):
        wanted = [m.strip() for m in (os.environ.get(f"ODDS_MARKETS_{lg}") or DEFAULTS[lg]).split(",")
                  if m.strip() in MARKETS[lg]]
        if not wanted:
            continue
        try:
            events = get(f"/sports/{SPORT[lg]}/events")  # free: does not use credits
        except urllib.error.HTTPError as e:
            print(f"{lg}: events request failed ({e.code})")
            continue
        soon = [e for e in events
                if 0 <= (dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - now).total_seconds()
                <= WINDOW * 3600]
        print(f"{lg}: {len(soon)} games in the next {WINDOW:.0f}h, {len(wanted)} prop types")
        for ev in soon:
            cost = len(wanted)
            if remaining is not None and remaining - cost < RESERVE:
                print(f"stopping: {remaining} credits left (reserve {RESERVE})")
                break
            try:
                data = get(f"/sports/{SPORT[lg]}/events/{ev['id']}/odds", regions="us",
                           bookmakers=",".join(BOOKS), markets=",".join(wanted), oddsFormat="american")
            except urllib.error.HTTPError as e:
                print(f"{lg} {ev['away_team']} @ {ev['home_team']}: request failed ({e.code})")
                if e.code in (401, 429):
                    break
                continue
            for bk in data.get("bookmakers", []):
                book = BOOKS.get(bk["key"])
                if not book:
                    continue
                for mk in bk.get("markets", []):
                    prop = MARKETS[lg].get(mk["key"])
                    if not prop:
                        continue
                    # group outcomes by player and line, then keep each player's main line
                    by = {}
                    for o in mk.get("outcomes", []):
                        who = o.get("description") or ""
                        side = o["name"].lower()
                        pt = o.get("point", 0.5)
                        slot = by.setdefault(norm(who), {}).setdefault(pt, {})
                        slot["over" if side in ("over", "yes") else "under"] = o["price"]
                    for who, lines in by.items():
                        best = min(lines.items(), key=lambda kv: abs(implied(kv[1].get("over", 100)) -
                                                                     implied(kv[1].get("under", 100))))
                        pt, px = best
                        out[lg].setdefault(who, {}).setdefault(prop, {})[book] = \
                            {"line": pt, "over": px.get("over"), "under": px.get("under")}
            time.sleep(0.3)
    out["remaining"] = remaining
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    n = sum(len(v) for k, v in out.items() if k in ("NFL", "NBA"))
    print(f"wrote {OUT}: {n} players with lines, {remaining} credits left")


if __name__ == "__main__":
    main()
