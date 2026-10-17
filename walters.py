"""A Walters-structured NFL side model: a fair point spread for every game, locked at kickoff and graded.

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

Data: nflverse schedule (results, closing spreads, starting QBs), ESPN scoreboard (DraftKings spread and prices,
final scores), context.json (ESPN injuries: a projected starting QB listed Out or Doubtful counts as a change).
Output: walters.json {built, params, backtest, ratings, games}
Usage: python walters.py [walters.json]
"""
import csv, io, json, sys, datetime as dt, collections as C
import urllib.request
from zoneinfo import ZoneInfo

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
                      "qbn_h": r["home_qb_name"], "qbn_a": r["away_qb_name"]})
    games.sort(key=lambda g: (g["day"], g["time"]))
    done = [g for g in games if g["margin"] is not None]
    table = cover_table(done)

    # 1. replay every completed game: ratings as they stood before each week, and the backtest record
    M, season = Model(), None
    weeks = C.defaultdict(list)
    for g in done:
        weeks[(g["season"], g["week"])].append(g)
    bt = C.defaultdict(lambda: [0, 0, 0.0])  # season -> wins, losses, units at -110
    tiers = {"4-5": [0, 0], "5+": [0, 0]}
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
            ug = upcoming.get((h, a), {})
            # a listed starter the injury report has Out or Doubtful counts as a backup starting
            ph = -QB_PTS if (h, ug.get("qbn_h")) in out_qb and nxt.get(h) == ev["id"] else M.qb_adj(h, ug.get("qb_h"))
            pa = -QB_PTS if (a, ug.get("qbn_a")) in out_qb and nxt.get(a) == ev["id"] else M.qb_adj(a, ug.get("qb_a"))
            mu = M.expect(h, a, bool(c.get("neutralSite")), ph, pa)
            e.update({"t": t.isoformat(), "line": line, "open": num(((ps.get("home") or {}).get("open") or {}).get("line")),
                      "price_h": num(((ps.get("home") or {}).get("close") or {}).get("odds")),
                      "price_a": num(((ps.get("away") or {}).get("close") or {}).get("odds")),
                      "fair": round(-mu, 1), "qb_h": ug.get("qbn_h"), "qb_a": ug.get("qbn_a"),
                      "qb_note": [f"{t_} {'QB back' if v > 0 else 'backup QB'} ({v:+.1f})" for t_, v in ((h, ph), (a, pa)) if abs(v) >= .5]})
            if line is not None:
                d = mu + line  # model's home margin vs the market's (-line)
                pick = "home" if d >= EDGE else "away" if d <= -EDGE else None
                p = p_cover(table, mu, line)
                e.update({"edge": round(abs(d), 1), "pick": pick, "units": (2 if abs(d) >= EDGE2 else 1) if pick else 0,
                          "prob": round(p if pick != "away" else 1 - p, 3)})
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
            e["graded"] = now.isoformat(timespec="minutes")
    # games ESPN no longer lists in the window (graded long ago) stay as they are
    gl = sorted(rec.values(), key=lambda e: e["t"])

    ratings = sorted(((t, round(ALPHA * M.mkt[t] + (1 - ALPHA) * M.perf[t], 1), round(M.mkt[t], 1), round(M.perf[t], 1))
                      for t in set(M.mkt) | set(M.perf) if t in {g["h"] for g in games if g["season"] == games[-1]["season"]}),
                     key=lambda x: -x[1])
    allw = sum(v[0] for v in bt.values())
    alll = sum(v[1] for v in bt.values())
    out = {"built": now.isoformat(timespec="minutes"),
           "params": {"alpha": ALPHA, "w": W, "hfa": HFA, "qb": QB_PTS, "edge": EDGE, "edge2": EDGE2, "cap": CAP},
           "backtest": {"from": BT_FROM, "all": [allw, alll, round(sum(v[2] for v in bt.values()), 1)],
                        "seasons": {s: [v[0], v[1], round(v[2], 1)] for s, v in sorted(bt.items())}, "tiers": tiers},
           "ratings": ratings, "games": gl}
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    open_picks = [e for e in gl if e.get("pick") and e["status"] == "pending"]
    print(f"wrote {OUT}: backtest {allw}-{alll} ({allw / max(1, allw + alll):.1%}) since {BT_FROM}; "
          f"{len(gl)} games, {len(open_picks)} open picks")


if __name__ == "__main__":
    main()
