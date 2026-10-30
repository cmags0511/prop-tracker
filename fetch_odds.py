"""Last-resort prices for props nothing else prices, from The Odds API (the-odds-api.com), free plan.

The free plan is 500 credits a month, so this is only the last resort. Pinnacle, FanDuel and ESPN's
DraftKings feed price most props; this fills the ones they miss (college rushing attempts, completions and
receptions, NFL kickers, the odd NBA name mismatch) using DraftKings / FanDuel / BetMGM quotes. It spends
credits carefully:
  * only props that slate.json shows with no price at all (po / pu empty) and a score of at least MIN_SCORE,
    in games starting within 28 hours,
  * one request per game, asking only for the prop types that game still needs (1 credit per type),
  * games with the most promising unpriced props go first, and a run spends at most MAX_RUN credits,
  * a game isn't asked again for the same prop types for REFRESH_H hours (even if nothing came back),
  * it stops when the month's remaining credits drop below RESERVE_DAY per day left in the month.

Needs the ODDS_API_KEY environment variable (a GitHub Actions secret). Without it, it does nothing.
Output: oddsapi.json {"fetched", "remaining", "tried": {...}, "log": [...], "props": {"<app key>": {"line", "over",
"under", "book", "books": {...}, "t", "game_t"}}}. picks.py uses these only when no other source prices the prop.

Usage: python fetch_odds.py [oddsapi.json]
"""
import json, os, re, sys, unicodedata, datetime as dt, calendar
import urllib.request, urllib.parse

OUT = sys.argv[1] if len(sys.argv) > 1 else "oddsapi.json"
KEY = os.environ.get("ODDS_API_KEY", "").strip()
API = "https://api.the-odds-api.com/v4"
BOOKS = "draftkings,fanduel,betmgm"
SPORT = {"NFL": "americanfootball_nfl", "NBA": "basketball_nba", "CFB": "americanfootball_ncaaf"}
REFRESH_H = float(os.environ.get("ODDS_REFRESH_H") or 12)
WINDOW_H, MAX_RUN, RESERVE_DAY, MIN_SCORE = 28, 30, 10, .12
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


def abbr_fits(ab, name):
    """does a college abbreviation (WIS, TULN, CLT) plausibly stand for this school name? letters in order, first letters aligned"""
    n = re.sub(r"[^a-z]", "", name.lower())
    a = re.sub(r"[^a-z]", "", ab.lower())
    if not a or not n or a[0] != n[0]:
        return False
    i = 0
    for ch in n:
        if i < len(a) and ch == a[i]:
            i += 1
    return i == len(a)


def find_event(lg, a, b, t, events):
    """the one event at kickoff time t between teams a and b (app abbreviations), or None when none or several fit"""
    near = [e for e in events if abs(dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - t) < dt.timedelta(minutes=20)]
    if lg == "CFB":
        hit = [e for e in near if (abbr_fits(a, e["home_team"]) and abbr_fits(b, e["away_team"]))
               or (abbr_fits(b, e["home_team"]) and abbr_fits(a, e["away_team"]))]
    else:
        names = {TEAM[lg].get(a), TEAM[lg].get(b)}
        hit = [e for e in near if {e["home_team"], e["away_team"]} == names]
    return hit[0] if len(hit) == 1 else None


def wanted(slate, old, now):
    """{(lg, team, opp, kickoff): {market: [prop, ...]}}: props with no price from any other source, or already filled
    by this source and about to start (one refresh)"""
    out = {}
    for c in slate.get("props", []):
        if c["lg"] not in SPORT or c["market"] not in MARKET or c["market"] == "td":
            continue
        t = dt.datetime.fromisoformat(c["t"])
        if not dt.timedelta(0) < t - now < dt.timedelta(hours=WINDOW_H):
            continue
        mine = c["key"] in old
        if not mine and not (c.get("po") is None or c.get("pu") is None):
            continue
        if not mine and (c.get("score") or 0) < MIN_SCORE:
            continue  # not near the top lists: not worth a credit
        a, b = sorted((c["team"], c["opp"]))
        out.setdefault((c["lg"], a, b, c["t"]), {}).setdefault(c["market"], []).append(c)
    return out


def main():
    now = dt.datetime.now(dt.timezone.utc)
    if not KEY:
        print("no ODDS_API_KEY set; skipping")
        return
    try:
        o = json.load(open(OUT))
    except Exception:
        o = {}
    props = {k: v for k, v in (o.get("props") or {}).items() if dt.datetime.fromisoformat(v["game_t"]) > now}
    tried = {k: v for k, v in (o.get("tried") or {}).items() if now - dt.datetime.fromisoformat(v) < dt.timedelta(hours=48)}
    global remaining
    remaining = o.get("remaining")
    try:
        slate = json.load(open("slate.json"))
    except Exception:
        print("no slate.json yet")
        return
    want = wanted(slate, props, now)
    # best first: games whose unpriced props score highest
    order = sorted(want.items(), key=lambda kv: -sum(c.get("score") or 0 for cs in kv[1].values() for c in cs))
    events, log, spent = {}, [], 0
    for lg in {w[0] for w in want}:
        try:  # the events list is free
            events[lg] = get(f"/sports/{SPORT[lg]}/events")
        except Exception as e:
            print(f"{lg} events failed: {e}")
            events[lg] = []
    days_left = calendar.monthrange(now.year, now.month)[1] - now.day + 1
    for (lg, a, b, t), mk in order:
        tk = f"{lg}|{a}|{b}|{t}|{','.join(sorted(mk))}"
        if tk in tried and now - dt.datetime.fromisoformat(tried[tk]) < dt.timedelta(hours=REFRESH_H):
            continue
        cost = len(mk)
        if spent + cost > MAX_RUN:
            log.append(f"run cap reached ({MAX_RUN} credits)")
            break
        if remaining is not None and remaining - cost < RESERVE_DAY * (days_left - 1):
            log.append(f"stopped: {remaining:.0f} credits left with {days_left} days to go")
            break
        ev = find_event(lg, a, b, dt.datetime.fromisoformat(t), events.get(lg, []))
        if not ev:
            log.append(f"{lg} {a}/{b}: no single matching event")
            continue
        try:
            d = get(f"/sports/{SPORT[lg]}/events/{ev['id']}/odds", regions="us", oddsFormat="american",
                    markets=",".join(MARKET[m] for m in mk), bookmakers=BOOKS)
        except Exception as e:
            log.append(f"{lg} {a}/{b} odds failed: {e}")
            continue
        tried[tk] = now.isoformat(timespec="minutes")
        filled = 0
        for m, cs in mk.items():
            for c in cs:
                books = {}
                for bk in d.get("bookmakers", []):
                    for mm in bk.get("markets", []):
                        if mm.get("key") != MARKET[m]:
                            continue
                        oc = [x for x in mm.get("outcomes", []) if norm(x.get("description", "")) == norm(c["name"])]
                        ov = next((x for x in oc if x.get("name") == "Over"), None)
                        un = next((x for x in oc if x.get("name") == "Under" and ov and x.get("point") == ov.get("point")), None)
                        if ov and un:
                            books[BOOKNAME[bk["key"]]] = {"line": ov.get("point"), "over": ov.get("price"), "under": un.get("price")}
                if books:
                    first = books.get("DraftKings") or next(iter(books.values()))
                    props[c["key"]] = {"line": first["line"], "over": first["over"], "under": first["under"],
                                       "book": "DraftKings" if "DraftKings" in books else next(iter(books)),
                                       "books": books, "t": now.isoformat(timespec="minutes"), "game_t": t}
                    filled += 1
        spent += cost
        n = sum(len(cs) for cs in mk.values())
        log.append(f"{lg} {a}/{b}: {filled}/{n} priced, {cost} credits")
    json.dump({"fetched": now.isoformat(timespec="minutes"), "remaining": remaining, "source": "The Odds API",
               "tried": tried, "log": log[-40:], "props": props}, open(OUT, "w"), separators=(",", ":"))
    print("\n".join(log) or "nothing to price")
    print(f"wrote {OUT}: {len(props)} priced props, spent {spent} credits, {remaining} left")


if __name__ == "__main__":
    main()
