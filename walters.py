"""A Walters-structured NFL side model: a fair point spread for every game, locked at kickoff and graded. Each
side play is also locked the first hour it shows up (Walters bet early) and graded separately as the early record.

Billy Walters' book (Gambler, 2023) lays out the structure but not his numbers: neutral-field team power ratings
updated slowly (each week keeps 90% of the old rating and adds 10% of how the team actually played), player
values (a starting QB is worth about a touchdown), a home-field value he says has fallen under a point, and a fair
line priced against the key numbers (3, then 6, 7, 14). His ratings, factor chart and half-point table aren't
public, so this rebuilds the structure from free data and fits the numbers by backtest (walk-forward, every
regular-season game since 2012, graded against the closing line):

  rating   80% market-implied (each team's rating solved from the closing spreads of its last ~30 weeks of games,
           recent weeks counting more) + 20% performance (Walters' 90/10 rule on each game's result, adjusted
           for the opponent and home field, margins capped at 21 so garbage time doesn't count)
  QB       QB_PTS (4) for the main QB (most starts in the last 17 games) vs who started the last 4: a backup
           stepping in costs it, the main QB returning earns it back. The backtest put it at 4 rather than
           Walters' touchdown because the market already moves for most of a QB change
  home     HFA points (1.5) on top of the ratings, none at neutral sites
  price    the chance of covering comes from how often real games landed on each margin when the line was near
           the model's number, so 3 and 7 carry their real weight

A pick needs the model 4+ points off DraftKings' spread (smaller gaps were a coin flip in the backtest: 49% at
3-4 points, then 54% at 4-5 and 57% at 5+): 1 unit at 4-5 points, 2 at 5+ (Walters sized 0.5-3 units of 1%
bankroll by edge). Units are graded at the DraftKings price
ESPN shows for that side when the game kicked off. This is a paper record: not betting advice.

Totals: no rating-based totals model beat closing totals in the backtest (47-50%), but Walters' weather factor did:
unders at outdoor games with 12-19 mph wind at kickoff went 57% (both halves of the sample), and so did unders with
2mm+ of rain over the first 3 hours (walters_wx.py), so those are the totals picks, 1 unit, graded at DraftKings'
under price. Non-QB injuries are listed per game (see POS_PTS) without moving
the line.

Walters picks: a second line per game with the book's full method (walters_book.py): the same ratings plus every
injury at full value and his game factors at 0.2 points each, sized by his key-number stars (units = stars). In the
backtest the factors beat the closing line in 2012-18 but not since 2019, and only 3-star plays clearly won, so the
tuned picks above leave them out; both are tracked.

Data: nflverse schedule (results, closing spreads and totals, kickoff wind, starting QBs) and snap counts, ESPN
scoreboard (DraftKings spread, total and prices, final scores), context.json (ESPN injuries; Open-Meteo kickoff wind), walters_wx.py (Open-Meteo rain, snow and
temperature at past and coming kickoffs).
Output: walters.json {built, params, backtest, ratings, games}
Usage: python walters.py [walters.json]
"""
import csv, io, json, sys, datetime as dt, collections as C
import urllib.request
from zoneinfo import ZoneInfo
import walters_book as B
import walters_wx as X

OUT = sys.argv[1] if len(sys.argv) > 1 else "walters.json"
NFLV = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ET = ZoneInfo("America/New_York")
ALPHA = .8        # weight on the market-implied rating; the rest is the 90/10 performance rating
W = .06           # Walters uses 10%; with the market carrying most of the rating, 6% fit best
REG = 1 / 3       # performance ratings shrink a third toward average between seasons
HFA = 1.5
QB_PTS = 4.0
CAP = 21
DECAY, LAM, WINDOW = .85, 2.0, 30   # market ratings: weight per week back, pull toward 0, weeks kept
EDGE, EDGE2 = 4.0, 5.0              # points off the line for a 1-unit and a 2-unit pick
WIND_LO, WIND_HI = 12, 20           # totals: the under when kickoff wind is 12-19 mph outdoors (Walters' weather factor)
INJ_K = 0.0                         # non-QB injuries move the line by INJ_K x their points: 0 = shown, not used (see below)
# non-QB injuries, in Walters' terms: points for a full-time starter by position (Wirfs, a tackle, was 1.3; the best
# non-QBs 2.5-3; most players ~0), times his snap share over the team's last 4 games (0 for games he missed, so a
# player who's been out for weeks is already in the ratings), x1.5 when 2+ starters are out in one unit.
# Backtested at several weights against closing lines, they didn't help (the market has the Friday report by
# kickoff), so they're listed on the page but don't move the line unless INJ_K is raised
POS_PTS = {"OL": .6, "WR": .8, "TE": .5, "RB": .3, "DL": .6, "LB": .3, "CB": .7, "S": .4}
GROUP = {"T": "OL", "G": "OL", "C": "OL", "OT": "OL", "OG": "OL", "WR": "WR", "TE": "TE", "RB": "RB", "FB": "RB",
         "DE": "DL", "DT": "DL", "NT": "DL", "LB": "LB", "OLB": "LB", "ILB": "LB", "MLB": "LB", "CB": "CB",
         "FS": "S", "SS": "S", "S": "S", "DB": "S"}
UNIT = {"OL": "OL", "WR": "PC", "TE": "PC", "DL": "DL", "CB": "DB", "S": "DB", "RB": "RB", "LB": "LB"}
SNAPS = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{}.csv"
START = 2009                        # replay from here; backtest record from BT_FROM
BT_FROM = 2012
# nflverse uses the team's abbreviation at the time; ESPN uses today's
FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA", "WSH": "WAS"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "prop-tracker"}), timeout=60) as r:
        return r.read()


def tm(a):
    return FRANCHISE.get(a, a)


def solve(hist):
    """market-implied ratings: least squares on spread = R_home - R_away + HFA, each game weighted DECAY**age,
    ridge-pulled toward 0 (coordinate descent; 32 teams converge in a few dozen passes)"""
    R = C.defaultdict(float)
    rows = [(h, a, s - (0 if neu else HFA), DECAY ** age) for age, (h, a, s, neu) in hist]
    by = C.defaultdict(list)
    for i, (h, a, y, w) in enumerate(rows):
        by[h].append((i, 1))
        by[a].append((i, -1))
    for _ in range(40):
        for t, gs in by.items():
            num = den = 0.0
            for i, sg in gs:
                h, a, y, w = rows[i]
                other = R[a] if sg == 1 else R[h]
                num += w * (sg * y + other)
                den += w
            R[t] = num / (den + LAM)
    return R


class Model:
    def __init__(self):
        self.perf = C.defaultdict(float)
        self.starts = C.defaultdict(list)
        self.hist = []
        self.mkt = C.defaultdict(float)

    def primary(self, t):
        """the team's main QB: most starts in its last 17 games (None before 4 games)"""
        s = self.starts[t][-17:]
        return C.Counter(s).most_common(1)[0][0] if len(s) >= 4 else None

    def qb_adj(self, t, qb):
        """points for who starts vs who has been starting: the ratings reflect the last few games, so a backup
        stepping in costs QB_PTS, the main QB returning after missing games gets them back, and a new starter
        who has held the job for weeks changes nothing"""
        p = self.primary(t)
        if not qb or not p:
            return 0.0
        recent = self.starts[t][-4:]
        return QB_PTS * ((qb == p) - sum(q == p for q in recent) / len(recent))

    def expect(self, h, a, neutral, adj_h=0.0, adj_a=0.0):
        """expected home margin"""
        hfa = 0 if neutral else HFA
        mk = self.mkt[h] - self.mkt[a] + hfa
        pf = self.perf[h] - self.perf[a] + hfa
        return ALPHA * mk + (1 - ALPHA) * pf + adj_h - adj_a

    def result(self, g, adj_h, adj_a):
        """Walters' update: 90/10 (here 94/6) of the old rating and this game's performance level, where the
        performance level is the capped margin plus the opponent's rating, net of home field and QB changes"""
        h, a, neutral = g["h"], g["a"], g["neutral"]
        hfa = 0 if neutral else HFA
        m = max(-CAP, min(CAP, g["margin"]))
        th = m + (self.perf[a] + adj_a) - hfa - adj_h
        ta = -m + (self.perf[h] + adj_h) + hfa - adj_a
        self.perf[h] = (1 - W) * self.perf[h] + W * th
        self.perf[a] = (1 - W) * self.perf[a] + W * ta
        self.starts[h].append(g["qb_h"])
        self.starts[a].append(g["qb_a"])

    def new_season(self):
        for t in self.perf:
            self.perf[t] *= (1 - REG)
        self.hist = [(age + 6, x) for age, x in self.hist]  # the offseason counts as a few weeks

    def close_week(self, games):
        self.hist = [(age + 1, x) for age, x in self.hist if age + 1 < WINDOW]
        self.hist += [(0, (g["h"], g["a"], g["spread"], g["neutral"])) for g in games if g["spread"] is not None]
        self.mkt = solve(self.hist)


def cover_table(games):
    """margins of past games by the line's expected margin, rounded to the half point"""
    by = C.defaultdict(list)
    for g in games:
        if g["spread"] is not None:
            by[round(g["spread"] * 2) / 2].append(g["margin"])
    return by


def p_cover(table, mu, line):
    """chance the home side covers `line` (home spread, negative = home favored) when the model expects a home
    margin of `mu`: the share of past games with a line near mu that beat it, pushes left out"""
    mu2 = round(mu * 2) / 2
    ms = []
    for w in (0, .5, 1, 1.5, 2, 3):
        ms = [m for k in {mu2 - w, mu2 + w} for m in table.get(k, [])]
        if len(ms) >= 150:
            break
    # center the sample on mu so a wider window doesn't drag it
    shift = mu - (sum(ms) / len(ms)) if ms else 0
    win = sum(1 for m in ms if round(m + shift) + line > 0)
    lose = sum(1 for m in ms if round(m + shift) + line < 0)
    return win / (win + lose) if win + lose else .5


def nm(s):
    s = "".join(c for c in s.lower() if c.isalnum() or c == " ")
    return " ".join(w for w in s.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


def injury_losses(snaps, team, week, names):
    """[(name, group, share)] for the players in `names` (listed Out / Doubtful) who've been playing: share = mean snap
    share over the team's last 4 games before `week`, 0 for a game he missed"""
    wk = snaps.get(team, {})
    prev = sorted(w for w in wk if w < week)[-4:]
    out = []
    for n in names:
        k = nm(n)
        sh = [wk[w].get(k, (0, None))[0] for w in prev]
        g = next((wk[w][k][1] for w in prev if k in wk[w]), None)
        if g and prev and sum(sh) / len(prev) >= .25:
            out.append((n, g, round(sum(sh) / len(prev), 2)))
    return out


def injury_points(losses):
    by = C.defaultdict(list)
    for n, g, sh in losses:
        by[UNIT[g]].append((POS_PTS[g] * sh, sh))
    return sum(sum(p for p, _ in v) * (1.5 if sum(sh >= .6 for _, sh in v) >= 2 else 1) for v in by.values())


def fl(x):
    return float(x) if x not in ("", "NA", None) else None


def book_pick(mu, line, price_h, price_a):
    """Walters' bet strength: (side, % of games landing between his number and the line, stars). `mu` = expected
    home margin, `line` = the home spread (negative = home favored)"""
    side = "home" if mu > -line else "away"
    sp, pr, fair = (line, price_h, mu) if side == "home" else (-line, price_a, -mu)
    pct = B.value(fair, -B.implicit(sp, pr))
    return side, pct, B.stars(pct)


def payout(price):
    return price / 100 if price > 0 else 100 / -price


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    rows = list(csv.DictReader(io.StringIO(get(NFLV).decode())))
    games = []
    for r in rows:
        if int(r["season"]) < START:
            continue
        games.append({"season": int(r["season"]), "week": int(r["week"]), "type": r["game_type"],
                      "day": r["gameday"], "time": r["gametime"], "h": tm(r["home_team"]), "a": tm(r["away_team"]),
                      "neutral": r["location"] == "Neutral",
                      # nflverse's spread is the home side's expected margin (positive = home favored)
                      "spread": float(r["spread_line"]) if r["spread_line"] else None,
                      "margin": float(r["result"]) if r["result"] else None,
                      "qb_h": r["home_qb_id"], "qb_a": r["away_qb_id"],
                      "total": float(r["total_line"]) if r["total_line"] else None,
                      "pts": float(r["total"]) if r["total"] else None, "outdoor": r["roof"] in ("outdoors", "open"),
                      "wind": float(r["wind"]) if r["wind"] else None,
                      "qbn_h": r["home_qb_name"], "qbn_a": r["away_qb_name"],
                      # for the book's game factors (walters_book.py)
                      "id": r["game_id"], "weekday": r["weekday"], "rh": r["home_team"], "ra": r["away_team"],
                      "ot": r["overtime"] == "1", "rest_h": fl(r["home_rest"]), "rest_a": fl(r["away_rest"]),
                      "surface": r["surface"], "roof": r["roof"], "temp": fl(r["temp"]), "stadium_id": r["stadium_id"],
                      "coach_h": r["home_coach"], "coach_a": r["away_coach"],
                      "sp_h": fl(r["home_spread_odds"]), "sp_a": fl(r["away_spread_odds"])})
    games.sort(key=lambda g: (g["day"], g["time"]))
    done = [g for g in games if g["margin"] is not None]
    table = cover_table(done)
    sched = B.Schedule(games)
    sched.prep()
    wxh = X.history(games, now)
    rain_of = lambda g: (wxh.get(g["id"]) or {}).get("rain") if g["outdoor"] else None

    # 1. replay every completed game: ratings as they stood before each week, and the backtest record
    M, season = Model(), None
    weeks = C.defaultdict(list)
    for g in done:
        weeks[(g["season"], g["week"])].append(g)
    bt = C.defaultdict(lambda: [0, 0, 0.0])  # season -> wins, losses, units at -110
    btt = C.defaultdict(lambda: [0, 0, 0.0])  # the same for weather unders (wind or rain)
    btw, btr = [0, 0, 0.0], [0, 0, 0.0]       # each rule on its own
    tiers = {"4-5": [0, 0], "5+": [0, 0]}
    btb = C.defaultdict(lambda: [0, 0, 0.0])  # the book line (game factors + star sizing), units = stars
    stars = C.defaultdict(lambda: [0, 0])
    bt3 = C.defaultdict(lambda: [0, 0, 0.0])  # 3-star plays only, at his sizing (3 stars = 3 units), as the page's 3-star section
    rating = lambda t: ALPHA * M.mkt[t] + (1 - ALPHA) * M.perf[t]
    for wk in sorted(weeks):
        if wk[0] != season:
            season = wk[0]
            M.new_season()
        for g in weeks[wk]:
            ph, pa = M.qb_adj(g["h"], g["qb_h"]), M.qb_adj(g["a"], g["qb_a"])
            mu = M.expect(g["h"], g["a"], g["neutral"], ph, pa)
            if g["season"] >= BT_FROM and g["type"] == "REG" and g["spread"] is not None:
                d = mu - g["spread"]
                if abs(d) >= EDGE:
                    r = (g["margin"] - g["spread"]) * (1 if d > 0 else -1)
                    if r:
                        u = 2 if abs(d) >= EDGE2 else 1
                        s = bt[g["season"]]
                        s[0 if r > 0 else 1] += 1
                        s[2] += u * (100 / 110) if r > 0 else -u
                        tiers["5+" if abs(d) >= EDGE2 else "4-5"][0 if r > 0 else 1] += 1
                side, pct, st = book_pick(mu + B.net(sched.factors(g, rating, rain=rain_of(g))), -g["spread"], g["sp_h"], g["sp_a"])
                r = (g["margin"] - g["spread"]) * (1 if side == "home" else -1)
                if st and r:
                    s = btb[g["season"]]
                    s[0 if r > 0 else 1] += 1
                    s[2] += st * payout(g["sp_h" if side == "home" else "sp_a"] or -110) if r > 0 else -st
                    stars[st][0 if r > 0 else 1] += 1
                    if st >= 3:
                        s = bt3[g["season"]]
                        s[0 if r > 0 else 1] += 1
                        s[2] += st * payout(g["sp_h" if side == "home" else "sp_a"] or -110) if r > 0 else -st
            wind, rain = g.get("wind"), rain_of(g)
            by_wind = wind is not None and WIND_LO <= wind < WIND_HI
            by_rain = rain is not None and rain >= X.RAIN_MM
            if g["season"] >= BT_FROM and g["type"] == "REG" and g["total"] is not None and g["outdoor"] \
                    and (by_wind or by_rain) and g["pts"] != g["total"]:
                for s, on in ((btt[g["season"]], True), (btw, by_wind), (btr, by_rain)):
                    if on:
                        s[0 if g["pts"] < g["total"] else 1] += 1
                        s[2] += 100 / 110 if g["pts"] < g["total"] else -1
            M.result(g, ph, pa)
        M.close_week(weeks[wk])

    # 2. the coming games: DraftKings' spread and prices from ESPN's scoreboard
    rec = {g["id"]: g for g in old.get("games", [])}
    # ESPN's scoreboard takes one date at a time: the last 4 days (to grade) and the next 8 (to price)
    events, seen = [], set()
    for k in range(-4, 9):
        day = (now + dt.timedelta(days=k)).astimezone(ET)
        try:
            for ev in json.loads(get(f"{ESPN}?dates={day:%Y%m%d}")).get("events", []):
                if ev["id"] not in seen:
                    seen.add(ev["id"])
                    events.append(ev)
        except Exception as e:
            print(f"ESPN scoreboard {day:%Y-%m-%d} failed: {e}")
    try:
        ctx = json.load(open("context.json"))
        inj = ctx.get("injuries", {}).get("NFL", {})
    except Exception:
        inj = {}
    out_qb = {(v.get("t"), v.get("n")) for v in inj.values() if v.get("pos") == "QB" and v.get("s") in ("Out", "Doubtful", "Injured Reserve", "IR")}
    out_nonqb = C.defaultdict(list)  # this week's Out / Doubtful non-QBs by team (IR players are already in the ratings)
    for v in inj.values():
        if v.get("pos") != "QB" and v.get("s") in ("Out", "Doubtful"):
            out_nonqb[tm(v.get("t") or "")].append(v.get("n") or "")
    weather = (ctx.get("weather") or {}) if inj else {}
    cur = max(g["season"] for g in games)
    snaps = C.defaultdict(dict)  # team -> week -> {name: (share, group)}
    try:
        for r in csv.DictReader(io.StringIO(get(SNAPS.format(cur)).decode())):
            g = GROUP.get(r["position"])
            if g:
                sh = max(float(r["offense_pct"] or 0), float(r["defense_pct"] or 0))
                snaps[tm(r["team"])].setdefault(int(r["week"]), {})[nm(r["player"])] = (sh, g)
    except Exception as e:
        print(f"snap counts failed: {e}")
    week_of = {(g["h"], g["a"]): g["week"] for g in games if g["season"] == cur}
    qbs, prate = X.qb_records(done, wxh), X.pass_rates(cur)
    upcoming = {(g["h"], g["a"]): g for g in games if g["margin"] is None}
    nxt = {}  # each team's next game: this week's injury report only speaks for that one
    for ev in sorted(events, key=lambda e: e["date"]):
        if ev["competitions"][0]["status"]["type"]["state"] == "pre":
            for x in ev["competitions"][0]["competitors"]:
                nxt.setdefault(tm(x["team"]["abbreviation"]), ev["id"])
    for ev in events:
        c = ev["competitions"][0]
        side = {x["homeAway"]: x for x in c["competitors"]}
        h, a = tm(side["home"]["team"]["abbreviation"]), tm(side["away"]["team"]["abbreviation"])
        t = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
        e = rec.get(ev["id"]) or {"id": ev["id"], "t": t.isoformat(), "home": h, "away": a, "status": "pending"}
        state = c["status"]["type"]["state"]
        if state == "pre" and t > now:
            # until kickoff: today's line, price and model number (frozen once the game starts)
            o = (c.get("odds") or [{}])[0]
            ps = o.get("pointSpread") or {}
            num = lambda x: float(str(x).replace("+", "")) if x not in (None, "", "OFF", "EVEN") else (0.0 if x == "EVEN" else None)
            line = o.get("spread")
            # ESPN sometimes drops DraftKings' line for a while (books pull next week's lines during Sunday's games):
            # keep the last line and prices seen, so the picks stay matched to the line they came from and still grade
            stale = line is None and e.get("line") is not None
            if stale:
                line = e["line"]
            ug = upcoming.get((h, a), {})
            # a listed starter the injury report has Out or Doubtful counts as a backup starting
            ph = -QB_PTS if (h, ug.get("qbn_h")) in out_qb and nxt.get(h) == ev["id"] else M.qb_adj(h, ug.get("qb_h"))
            pa = -QB_PTS if (a, ug.get("qbn_a")) in out_qb and nxt.get(a) == ev["id"] else M.qb_adj(a, ug.get("qb_a"))
            wk_n = week_of.get((h, a), 99)
            lh = injury_losses(snaps, h, wk_n, out_nonqb.get(h, [])) if nxt.get(h) == ev["id"] else []
            la = injury_losses(snaps, a, wk_n, out_nonqb.get(a, [])) if nxt.get(a) == ev["id"] else []
            ih, ia = injury_points(lh), injury_points(la)
            mu = M.expect(h, a, bool(c.get("neutralSite")), ph - INJ_K * ih, pa - INJ_K * ia)
            # the book line: the same ratings plus every injury at full value and Walters' game factors
            wx0 = weather.get(f"NFL|{a}@{h}|{t:%Y-%m-%d}") or {}
            out_door = not (wx0.get("indoor") or (c.get("venue") or {}).get("indoor"))
            fc = X.forecast(ug, t) if out_door and ug.get("id") else None    # rain and snow amounts at kickoff
            fs = sched.factors(ug, rating, temp=wx0.get("temp") if out_door else None,
                               rain=(fc or {}).get("rain") if out_door else None) if ug.get("id") else []
            mu_b = M.expect(h, a, bool(c.get("neutralSite")), ph - ih, pa - ia) + B.net(fs)
            # totals: DraftKings' total and prices; the under when the kickoff forecast has 12-19 mph wind or 2mm+
            # of rain outdoors
            tot = o.get("total") or {}
            wx = weather.get(f"NFL|{a}@{h}|{t:%Y-%m-%d}") or {}
            wind = None if wx.get("indoor") or c.get("venue", {}).get("indoor") else wx.get("wind")
            tl = o.get("overUnder")
            rain = (fc or {}).get("rain") if out_door else None
            why = [x for x, on in (("wind", wind is not None and WIND_LO <= wind < WIND_HI),
                                   ("rain", rain is not None and rain >= X.RAIN_MM)) if on]
            e.update({"tline": tl, "tprice_o": num(((tot.get("over") or {}).get("close") or {}).get("odds")),
                      "tprice_u": num(((tot.get("under") or {}).get("close") or {}).get("odds")),
                      "wind": wind, "indoor": bool(wx.get("indoor") or (c.get("venue") or {}).get("indoor")),
                      "rain": rain, "snow": (fc or {}).get("snow") if out_door else None,
                      "tpick": "under" if tl is not None and why else None, "twhy": why,
                      "wnotes": X.notes(ug, fc, not out_door, qbs, prate, tm) if ug.get("id") else [],
                      "inj_h": [[n, g, sh] for n, g, sh in lh], "inj_a": [[n, g, sh] for n, g, sh in la],
                      "injp_h": round(ih, 1), "injp_a": round(ia, 1)})
            e.update({"t": t.isoformat(), "line": line, "lstale": stale,
                      "open": e.get("open") if stale else num(((ps.get("home") or {}).get("open") or {}).get("line")),
                      "price_h": e.get("price_h") if stale else num(((ps.get("home") or {}).get("close") or {}).get("odds")),
                      "price_a": e.get("price_a") if stale else num(((ps.get("away") or {}).get("close") or {}).get("odds")),
                      "fair": round(-mu, 1), "qb_h": ug.get("qbn_h"), "qb_a": ug.get("qbn_a"),
                      "qb_note": [f"{t_} {'QB back' if v > 0 else 'backup QB'} ({v:+.1f})" for t_, v in ((h, ph), (a, pa)) if abs(v) >= .5]})
            if line is not None:
                d = mu + line  # model's home margin vs the market's (-line)
                pick = "home" if d >= EDGE else "away" if d <= -EDGE else None
                p = p_cover(table, mu, line)
                e.update({"edge": round(abs(d), 1), "pick": pick, "units": (2 if abs(d) >= EDGE2 else 1) if pick else 0,
                          "prob": round(p if pick != "away" else 1 - p, 3)})
                side, pct, st = book_pick(mu_b, line, e["price_h"], e["price_a"])
                e.update({"bfair": round(-mu_b, 1), "bpct": round(pct, 1), "bpick": side if st else None, "bstars": st,
                          "factors": [[s_, v, why] for s_, v, why in fs], "fnet": round(B.net(fs), 2)})
                # early locks, Walters' timing: the first hour a play shows up, its line and price are kept and graded
                # on their own (the main record still locks at kickoff, when injuries and weather are settled); only an
                # hour with a real, fresh price locks, so an early pick is never stuck at an assumed -110 or a carried line
                at = now.isoformat(timespec="minutes")
                if pick and not stale and not e.get("epick") and e["price_h" if pick == "home" else "price_a"] is not None:
                    e.update({"epick": pick, "eline": line, "eprice": e["price_h" if pick == "home" else "price_a"],
                              "eunits": e["units"], "et": at})
                if e["bpick"] and not stale and not e.get("ebpick") and e["price_h" if e["bpick"] == "home" else "price_a"] is not None:
                    e.update({"ebpick": e["bpick"], "ebline": line, "ebprice": e["price_h" if e["bpick"] == "home" else "price_a"],
                              "ebstars": st, "ebt": at})
            rec[ev["id"]] = e
        elif state == "post" and e.get("status") == "pending" and ev["id"] in rec:
            hs, as_ = float(side["home"].get("score") or 0), float(side["away"].get("score") or 0)
            e["score"] = [int(as_), int(hs)]
            if e.get("pick") and e.get("line") is not None:
                r = (hs - as_ + e["line"]) * (1 if e["pick"] == "home" else -1)
                price = e.get("price_h" if e["pick"] == "home" else "price_a") or -110
                e["status"] = "win" if r > 0 else "loss" if r < 0 else "push"
                e["units_won"] = round(e["units"] * payout(price), 2) if r > 0 else -e["units"] if r < 0 else 0
            else:
                e["status"] = "nopick"
            if e.get("bpick") and e.get("line") is not None:
                r = (hs - as_ + e["line"]) * (1 if e["bpick"] == "home" else -1)
                price = e.get("price_h" if e["bpick"] == "home" else "price_a") or -110
                e["bstatus"] = "win" if r > 0 else "loss" if r < 0 else "push"
                e["bunits_won"] = round(e["bstars"] * payout(price), 2) if r > 0 else -e["bstars"] if r < 0 else 0
            # early locks: graded at the line and price they locked at; clv = points the line moved their way by kickoff
            for k, n in (("e", "eunits"), ("eb", "ebstars")):
                if e.get(k + "pick") and e.get(k + "line") is not None:
                    sg = 1 if e[k + "pick"] == "home" else -1
                    r = (hs - as_ + e[k + "line"]) * sg
                    e[k + "status"] = "win" if r > 0 else "loss" if r < 0 else "push"
                    e[k + "units_won"] = round(e[n] * payout(e.get(k + "price") or -110), 2) if r > 0 else -e[n] if r < 0 else 0
                    if e.get("line") is not None:
                        e[k + "clv"] = round((e[k + "line"] - e["line"]) * sg, 1)
            if e.get("tpick") and e.get("tline") is not None:
                r = e["tline"] - (hs + as_)  # > 0: under wins
                price = e.get("tprice_u") or -110
                e["tstatus"] = "win" if r > 0 else "loss" if r < 0 else "push"
                e["tunits_won"] = round(payout(price), 2) if r > 0 else -1 if r < 0 else 0
            e["graded"] = now.isoformat(timespec="minutes")
    # games ESPN no longer lists in the window (graded long ago) stay as they are
    gl = sorted(rec.values(), key=lambda e: e["t"])

    ratings = sorted(((t, round(ALPHA * M.mkt[t] + (1 - ALPHA) * M.perf[t], 1), round(M.mkt[t], 1), round(M.perf[t], 1))
                      for t in set(M.mkt) | set(M.perf) if t in {g["h"] for g in games if g["season"] == games[-1]["season"]}),
                     key=lambda x: -x[1])
    allw = sum(v[0] for v in bt.values())
    alll = sum(v[1] for v in bt.values())
    out = {"built": now.isoformat(timespec="minutes"),
           "params": {"alpha": ALPHA, "w": W, "hfa": HFA, "qb": QB_PTS, "edge": EDGE, "edge2": EDGE2, "cap": CAP, "inj_k": INJ_K},
           "backtest": {"from": BT_FROM, "all": [allw, alll, round(sum(v[2] for v in bt.values()), 1)],
                        "seasons": {s: [v[0], v[1], round(v[2], 1)] for s, v in sorted(bt.items())}, "tiers": tiers},
           "backtest_book": {"from": BT_FROM, "all": [sum(v[0] for v in btb.values()), sum(v[1] for v in btb.values()),
                                                      round(sum(v[2] for v in btb.values()), 1)],
                             "seasons": {s: [v[0], v[1], round(v[2], 1)] for s, v in sorted(btb.items())},
                             "stars": {str(k): v for k, v in sorted(stars.items())},
                             "all3": [sum(v[0] for v in bt3.values()), sum(v[1] for v in bt3.values()), round(sum(v[2] for v in bt3.values()), 1)],
                             "seasons3": {s: [v[0], v[1], round(v[2], 1)] for s, v in sorted(bt3.items())}},
           "backtest_totals": {"from": BT_FROM, "wind": [WIND_LO, WIND_HI], "rain_mm": X.RAIN_MM,
                               "by_wind": [btw[0], btw[1], round(btw[2], 1)], "by_rain": [btr[0], btr[1], round(btr[2], 1)],
                               "all": [sum(v[0] for v in btt.values()), sum(v[1] for v in btt.values()), round(sum(v[2] for v in btt.values()), 1)],
                               "seasons": {s: [v[0], v[1], round(v[2], 1)] for s, v in sorted(btt.items())}},
           "ratings": ratings, "games": gl}
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    open_picks = [e for e in gl if e.get("pick") and e["status"] == "pending"]
    print(f"wrote {OUT}: backtest {allw}-{alll} ({allw / max(1, allw + alll):.1%}) since {BT_FROM}; "
          f"{len(gl)} games, {len(open_picks)} open picks")


if __name__ == "__main__":
    main()
