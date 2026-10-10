"""Real sportsbook lines and prices for the app's top picks, from The Odds API (the-odds-api.com).

ESPN's free DraftKings feed has lines but no prices, and some lines lag. The Odds API has live
DraftKings / FanDuel / BetMGM lines AND prices for NFL and NBA player props. Its free plan (500 credits
a month) can't cover every prop, so this only prices the props people are most likely to bet: the
overs and all-sides Top 10s and the Best bet, and it spends credits carefully:
  * one request per game, asking only for the prop types that game's picks need (1 credit each),
  * a game's prices are refreshed at most every REFRESH_H hours,
  * it stops when the month's remaining credits drop below what's needed to last to month end.

Needs the ODDS_API_KEY environment variable (a GitHub Actions secret). Without it, it does nothing.
Output: odds.json {"fetched", "remaining", "props": {"<app key>": {"line", "over", "under", "book",
"books": {"FanDuel": {"line", "over", "under"}, ...}, "t": "<when fetched>"}}}

Usage: python fetch_odds.py [odds.json]
"""
import json, os, re, sys, unicodedata, datetime as dt, calendar
import urllib.request, urllib.parse

OUT = sys.argv[1] if len(sys.argv) > 1 else "odds.json"
KEY = os.environ.get("ODDS_API_KEY", "").strip()
API = "https://api.the-odds-api.com/v4"
REFRESH_H = float(os.environ.get("ODDS_REFRESH_H") or 8)
BOOKS = "draftkings,fanduel,betmgm"
SPORT = {"NFL": "americanfootball_nfl", "NBA": "basketball_nba"}
MARKET = {"pyd": "player_pass_yds", "cmp": "player_pass_completions", "att": "player_pass_attempts",
          "ptd": "player_pass_tds", "ryd": "player_rush_yds", "car": "player_rush_attempts",
          "rec": "player_receptions", "recyd": "player_reception_yds", "rry": "player_rush_reception_yds",
          "kpts": "player_kicking_points", "fgm": "player_field_goals", "pat": "player_pats",
          "tkl": "player_tackles_assists", "sck": "player_sacks", "td": "player_anytime_td",
          "pts": "player_points", "reb": "player_rebounds", "ast": "player_assists", "3pm": "player_threes",
          "pra": "player_points_rebounds_assists", "pr": "player_points_rebounds", "pa": "player_points_assists",
          "ra": "player_rebounds_assists"}
TEAM = {"NFL": {"ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
                "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
                "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
                "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
                "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
                "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
                "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
                "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders"},
        "NBA": {"ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets", "CHA": "Charlotte Hornets",
                "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
                "DET": "Detroit Pistons", "GS": "Golden State Warriors", "GSW": "Golden State Warriors", "HOU": "Houston Rockets",
                "IND": "Indiana Pacers", "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
                "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves", "NO": "New Orleans Pelicans",
                "NOP": "New Orleans Pelicans", "NY": "New York Knicks", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
                "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns", "POR": "Portland Trail Blazers",
                "SAC": "Sacramento Kings", "SA": "San Antonio Spurs", "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors",
                "UTAH": "Utah Jazz", "UTA": "Utah Jazz", "WSH": "Washington Wizards", "WAS": "Washington Wizards"}}
BOOKNAME = {"draftkings": "DraftKings", "fanduel": "FanDuel", "betmgm": "BetMGM"}
remaining = None


def get(path, **q):
    global remaining
    q["apiKey"] = KEY
    with urllib.request.urlopen(urllib.request.Request(f"{API}{path}?{urllib.parse.urlencode(q)}",
                                                      headers={"User-Agent": "prop-tracker"}), timeout=40) as r:
        rem = r.headers.get("x-requests-remaining")
        if rem is not None:
            remaining = float(rem)
        return json.loads(r.read())


def norm(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'\-]", " ", n)
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


def wanted(picks, now):
    """{(lg, game key): {market: [pick, ...]}} for the props worth pricing"""
    out = {}
    pool = list(picks.get("picksOver", [])[:14]) + list(picks.get("picks", [])[:12]) + ([picks["best"]] if picks.get("best") else [])
    pool += list(picks.get("tdPicks", [])[:5])
    for c in pool:
        if c["lg"] not in SPORT or c["market"] not in MARKET or dt.datetime.fromisoformat(c["t"]) <= now:
            continue
        home, away = (c["team"], c["opp"]) if c["home"] else (c["opp"], c["team"])
        out.setdefault((c["lg"], away, home, c["t"]), {}).setdefault(c["market"], []).append(c)
    return out


def main():
    now = dt.datetime.now(dt.timezone.utc)
    if not KEY:
        print("no ODDS_API_KEY set; skipping sportsbook prices")
        return
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    props = {k: v for k, v in (old.get("props") or {}).items() if dt.datetime.fromisoformat(v["game_t"]) > now}
    picks = json.load(open("picks.json"))
    want = wanted(picks, now)
    if not want:
        print("no top picks in NFL/NBA to price")
    events = {}
    for lg in {w[0] for w in want}:
        try:  # the events list is free
            events[lg] = get(f"/sports/{SPORT[lg]}/events")
        except Exception as e:
            print(f"{lg} events failed: {e}")
            events[lg] = []
    days_left = calendar.monthrange(now.year, now.month)[1] - now.day + 1
    spent = 0
    for (lg, away, home, t), mk in sorted(want.items(), key=lambda kv: kv[0][3]):
        fresh = [c["key"] for cs in mk.values() for c in cs if c["key"] in props
                 and now - dt.datetime.fromisoformat(props[c["key"]]["t"]) < dt.timedelta(hours=REFRESH_H)]
        if len(fresh) == sum(len(cs) for cs in mk.values()):
            continue
        cost = len(mk)
        # keep enough credits to last the month: about 15 a day
        if remaining is not None and remaining - cost < 15 * (days_left - 1):
            print(f"stopping: {remaining:.0f} credits left with {days_left} days to go")
            break
        ev = next((e for e in events.get(lg, []) if e.get("home_team") == TEAM[lg].get(home)
                   and e.get("away_team") == TEAM[lg].get(away)), None)
        if not ev:
            print(f"{lg} {away}@{home}: no matching event")
            continue
        try:
            d = get(f"/sports/{SPORT[lg]}/events/{ev['id']}/odds", regions="us", oddsFormat="american",
                    markets=",".join(MARKET[m] for m in mk), bookmakers=BOOKS)
        except Exception as e:
            print(f"{lg} {away}@{home} odds failed: {e}")
            continue
        spent += cost
        for m, cs in mk.items():
            for c in cs:
                books = {}
                for b in d.get("bookmakers", []):
                    for mm in b.get("markets", []):
                        if mm.get("key") != MARKET[m]:
                            continue
                        oc = [o for o in mm.get("outcomes", []) if norm(o.get("description", "")) == norm(c["name"])]
                        if m == "td":
                            yes = next((o for o in oc if o.get("name") in ("Yes", "Over")), None)
                            if yes:
                                books[BOOKNAME[b["key"]]] = {"line": .5, "over": yes.get("price"), "under": None}
                            continue
                        o = next((x for x in oc if x.get("name") == "Over"), None)
                        u = next((x for x in oc if x.get("name") == "Under" and o and x.get("point") == o.get("point")), None)
                        if o:
                            books[BOOKNAME[b["key"]]] = {"line": o.get("point"), "over": o.get("price"),
                                                         "under": u.get("price") if u else None}
                if books:
                    main = books.get("DraftKings") or next(iter(books.values()))
                    props[c["key"]] = {"line": main["line"], "over": main["over"], "under": main["under"],
                                       "book": "DraftKings" if "DraftKings" in books else next(iter(books)),
                                       "books": books, "t": now.isoformat(timespec="minutes"), "game_t": t}
    json.dump({"fetched": now.isoformat(timespec="minutes"), "remaining": remaining, "source": "The Odds API",
               "props": props}, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(props)} priced props, spent {spent} credits, {remaining} left")


if __name__ == "__main__":
    main()
