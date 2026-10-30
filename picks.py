"""Rank the next slate's player props against DraftKings lines and write picks.json.

Reads props_data.json / cfb_data.json (game logs + schedules), lines.json (DraftKings lines)
and notes.json (the daily research check). No third-party packages needed.

Each prop gets a probability-style score from:
  form      weighted hit rate vs the line (last 10, season, last 5) and how far his average sits from it
  matchup   what players at his position have done against this opponent (its last 10 games)
  game      the team's implied points from the spread and total (football)
  minutes   minutes trend, last 3 vs last 15 games (NBA)
  news      injury reports (context.json, every 3 hours): his own status, and for NBA the share of the
            team's production held by regulars who are ruled out (backtested: overs hit more often)
  weather   kickoff wind and cold for outdoor football (backtested: QB passing overs suffer above ~15 mph and
            below ~40 F, receiving a little in strong wind, kickers in the cold)
  research  injuries, role, game plan and news from the daily research check (notes.json)
Weights come from a walk-forward backtest on 2025 NFL / 2025-26 NBA games (see README).
Players ruled out by the injury report or the research check are dropped.

Usage: python picks.py [picks.json]
"""
import json, math, re, sys, datetime as dt

OUT = sys.argv[1] if len(sys.argv) > 1 else "picks.json"
KEEP = 30  # the daily research check reviews these, then the app shows the best 10
# backtested weights (log-odds units): form, distance from line, matchup, implied team total, minutes trend
# College blowouts (Oct 30 backtest of 2022-26 player games, 84 tests: spread size was the strongest signal): in a game with a
# spread of 14+ either way, overs on a player's last-10 average hit 26-49% for attempts and yards (starters sit, the game
# runs through the clock or the trailing side's drives die). Applied at less than half the backtested size because the real
# sportsbook line already shades for blowouts; tune.py re-learns its weight from graded results. Per prop-type share below.
BLOW_W = -.45   # log-odds at a spread of 24+ (ramps up from 10)
BLOW_M = {"pyd": 1.0, "att": 1.0, "cmp": .7, "ryd": 1.0, "car": 1.0, "recyd": .5}
W = {"NFL": dict(p=1.16, z=1.62, mu=.075, tot=.066, mtr=0), "CFB": dict(p=1.16, z=1.62, mu=.075, tot=.066, mtr=0),
     "NBA": dict(p=2.33, z=.65, mu=.046, tot=0, mtr=.86)}
# (research notes are read by research_dir / research_push below)
OUT_STATUS = {"Out", "Doubtful", "Injured Reserve", "Suspension", "Physically Unable to Perform", "Not Active"}
SHAKY = {"Questionable", "Day-To-Day"}
VAC_W_NFL = .25  # NFL catches / carries left by a ruled-out teammate (game-day inactives included); tune.py re-weights "news"
VAC_W = .4      # NBA: log-odds per unit of team production vacated by ruled-out regulars (backtest coef ~.38)
WIND_W = -.25   # NFL/CFB QB passing props: log-odds per 5 mph of wind above 12 mph, capped at -.6
                # (backtest: no drop at 10-15 mph, passing overs ~39% vs ~49% above 15 mph; 2023-26 refit -.30)
WIND_W_REC = -.1  # receptions / receiving yards: a weaker effect (refit -.04 overall, -.15 in 2025-26; overs 39.5% -> 34% at 16+ mph)
COLD_W = {"pyd": -.1, "cmp": -.1, "att": -.1, "ptd": -.1,  # per 10 F below 40 at kickoff, outdoors (2023-24 -.12, 2025-26 -.12)
          "fgm": -.2, "pat": -.2, "kpts": -.2}  # kickers: kicking points overs 47% above 45 F, 31% below freezing (shrunk: small sample)
QB_M = {"pyd", "cmp", "att", "ptd"}
# backtest by prop type: yardage overs were close to a coin flip even when the form score was confident
# (receiving 49%, rushing 52%, rush+rec 52%), so their form signal is shrunk toward the over side
YARD_OVER_SHRINK = {"recyd": .7, "ryd": .7, "rry": .7}
# lines of 0.5 / 1.5 on count props usually carry heavy juice (-200 and worse), which a hit rate can't see;
# they rank lower and get a "check odds" tag
LOW_LINE_M = {"rec", "ptd", "sck", "3pm", "fgm", "pat", "car", "ast", "reb", "tkl"}
PASS_M = {"pyd", "cmp", "att", "ptd", "rec", "recyd"}
VAC_KEY = {"pts": "pts", "3pm": "pts", "reb": "reb", "ast": "ast", "pra": "min", "pr": "min", "pa": "min", "ra": "min",
           "rec": "rec", "recyd": "rec", "car": "car", "ryd": "car", "rry": "car"}

UNIT = {"pyd": "passing yards", "cmp": "completions", "att": "pass attempts", "ptd": "passing TDs",
        "ryd": "rushing yards", "car": "carries", "rec": "receptions", "recyd": "receiving yards",
        "rry": "rush + rec yards", "pts": "points", "reb": "rebounds", "ast": "assists", "3pm": "threes",
        "pra": "pts + reb + ast", "pr": "pts + reb", "pa": "pts + ast", "ra": "reb + ast",
        "fgm": "field goals", "pat": "extra points", "kpts": "kicking points", "tkl": "tackles + assists",
        "sck": "sacks"}
LABEL = {"pyd": "Passing yards", "cmp": "Completions", "att": "Pass attempts", "ptd": "Passing TDs",
         "ryd": "Rushing yards", "car": "Rush attempts", "rec": "Receptions", "recyd": "Receiving yards",
         "rry": "Rush + Rec yards", "pts": "Points", "reb": "Rebounds", "ast": "Assists",
         "3pm": "3-pointers made", "pra": "Pts + Reb + Ast", "pr": "Pts + Reb", "pa": "Pts + Ast",
         "ra": "Reb + Ast", "fgm": "Field goals made", "pat": "Extra points made", "kpts": "Kicking points",
         "tkl": "Tackles + assists", "sck": "Sacks"}


def research_dir(n):
    """(side the research favors or None, strength 0-2, uncertain?) from a research note, however it was written.
    Researchers name a side and an adj; a negative adj means "against that side", so it's flipped to a positive adj
    for the other side. A caution with no clear lean (adj 0) has no direction; it only says the outlook is uncertain
    (questionable status, role in flux)."""
    side = n.get("side") if n.get("side") in ("over", "under") else None
    try:
        adj = max(-2.0, min(2.0, float(n.get("adj") or 0)))
    except (TypeError, ValueError):
        adj = 0.0
    if side and adj < 0:
        side, adj = ("under" if side == "over" else "over"), -adj
    uncertain = n.get("flag") == "caution" and adj < 1
    return (side if adj > 0 else None), adj, uncertain


def research_push(n, conf=1.0):
    """log-odds push toward the OVER from a note (negative = toward the under)"""
    side, adj, _ = research_dir(n)
    if not side:
        return 0.0
    s = .15 * adj + (.25 if n.get("flag") == "support" else .1)
    return conf * s * (1 if side == "over" else -1)


def stat(g, m):
    if m == "rry": return g["ryd"] + g["recyd"]
    if m == "kpts": return 3 * g["fgm"] + g["pat"]
    if m == "pra": return g["pts"] + g["reb"] + g["ast"]
    if m == "pr": return g["pts"] + g["reb"]
    if m == "pa": return g["pts"] + g["ast"]
    if m == "ra": return g["reb"] + g["ast"]
    return g[m]


def grp(lg, pos):
    pos = pos or ""
    if lg == "NBA":
        return "C" if "C" in pos else "G" if "G" in pos else "F"
    return "DEF" if pos in ("LB", "DB", "DL", "DEF") else pos


GROUPNAME = {"QB": "QBs", "RB": "RBs", "WR": "WRs", "TE": "TEs", "DEF": "defenders", "K": "kickers",
             "G": "guards", "F": "forwards", "C": "centers"}


def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def allowed_tables(players, cols, lg):
    """{(market, group): {opp: avg over opp's last 10 games}} of what each group produced vs each team."""
    cache = {}

    def get(m, g):
        if (m, g) in cache:
            return cache[(m, g)]
        tg = {}
        for p in players:
            if grp(lg, p.get("p")) != g:
                continue
            for row in p["g"]:
                r = dict(zip(cols, row))
                d = tg.setdefault(r["opp"], {})
                d[r["date"]] = d.get(r["date"], 0) + stat(r, m)
        avg = {}
        for opp, by in tg.items():
            ds = sorted(by)[-10:]
            if len(ds) >= 3:
                avg[opp] = sum(by[d] for d in ds) / len(ds)
        vals = sorted(avg.values(), reverse=True)
        mean = sum(vals) / len(vals) if vals else 0
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) if vals else 1
        out = {o: {"z": (a - mean) / (sd or 1), "rank": vals.index(a) + 1, "n": len(vals)} for o, a in avg.items()}
        cache[(m, g)] = out
        return out
    return get


BOOK_GAP = .05   # model more than this above the sportsbook's no-vig chance: halve the score (keeps it out of the Top lists)
                # (was .12; Oct 17-21 Top 10 picks 5-10 points above the book hit 35%, 10+ points 38%, within 5 points 56%)
KALSHI_AGAINST = .49  # Kalshi traders give the pick's side less than this: halve the score (keeps it out of the Top lists)
                # (Oct 8-27 graded props: when Kalshi gave the app's side under 49%, it hit 313 of 716 = 44%, vs the
                # 54% the app expected; NBA 178/434, NFL 135/282. The hit rate follows Kalshi's number, not the app's.)
LINE_MOVE = .12  # DraftKings line moved this share of the opening line away from the pick: score x .6
MKT_W = .8  # log-odds weight on the Kalshi market's probability of the over at DraftKings' line (capped ±.6)
MONTHS = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def market_prob(rec, line, game_t, now):
    """Kalshi traders' probability that he goes over `line`, read off the ladder for this game (pre-game only)."""
    if not rec or not rec.get("k") or game_t <= now:
        return None
    m = re.search(r"-(\d\d)([A-Z]{3})(\d\d)", rec.get("g", ""))
    if not m or dt.date(2000 + int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))) != game_t.astimezone(dt.timezone(dt.timedelta(hours=-4))).date():
        return None  # ladder is for a different game
    k = rec["k"]
    for (s0, p0, _), (s1, p1, _) in zip(k, k[1:]):
        if s0 <= line <= s1:
            return p0 if s1 == s0 else p0 + (p1 - p0) * (line - s0) / (s1 - s0)
    if len(k) == 1 and k[0][0] == line:
        return k[0][1]
    return None  # the line is outside the strikes traded


def market_median(rec, game_t, now):
    """the line Kalshi traders see as 50/50 (where the ladder crosses 0.5), for this game, pre-game only"""
    if not rec or not rec.get("k") or game_t <= now:
        return None
    m = re.search(r"-(\d\d)([A-Z]{3})(\d\d)", rec.get("g", ""))
    if not m or dt.date(2000 + int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))) != game_t.astimezone(dt.timezone(dt.timedelta(hours=-4))).date():
        return None
    k = rec["k"]
    for (s0, p0, _), (s1, p1, _) in zip(k, k[1:]):
        if p0 >= .5 >= p1 and p0 != p1:
            return s0 + (s1 - s0) * (p0 - .5) / (p0 - p1)
    return None


def fmt(v):
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


# Anytime-TD model (NFL), fit on 2025-26 player games (logistic; walk-forward test: log loss .543 vs .570 for the
# base rate, and calibrated: 20% predicted -> 19% hit, 30% -> 28%, 49% -> 48%). Inputs: share of his last 10 games
# with a TD, touches per game over his last 5, TDs per touch over his last 10, his team's implied points, position.
TD_W = dict(b=-.682, rate=.48, touch=.35, per=-.412, imp=.381, WR=.228, TE=.408, QB=-.321)
# red-zone usage (build_usage.py): log(1 + red-zone carries+targets per game, last 6) and goal-line carries, centered
# on the league average; backtest (train 2023-24, test 2025-26) added them on top of TD rate and touches
TD_RZ, TD_GL, RZ_MEAN, GL_MEAN = .16, .08, .41, .14
# usage signals for NFL props (build_usage.py), log-odds; the backtest coefficients were halved because the test's
# stand-in lines (recent averages) know less than a sportsbook's, so they overstate what usage adds over the book
USE_W = {"rec": .22, "recyd": .22, "ryd": .15, "car": .15, "rry": .15, "pyd": .12, "cmp": .12, "att": .12}
SNAP_W = .7     # x the change in snap share (last 2 games vs the 4 before), capped at +/-0.2
USAGE = {}
NBA_PACE_W = .06
TD_MKT = .6      # weight on Kalshi's "1+ TD" price when it has one (log-odds blend); the stats get the rest
TD_PER_TEAM = 2  # at most two scorers from one team in the Top 10


def td_board(data, ctx, MKTS, notes, CONF, now, ODDS=None):
    """the 10 likeliest anytime-TD scorers on the upcoming NFL slate (plus the full ranked list for the game views)"""
    meta = data.get("NFL") or {}
    cols = meta.get("cols", [])
    if not cols:
        return [], []
    lt = lambda v: math.log(v / (1 - v))
    sig = lambda z: 1 / (1 + math.exp(-z))
    INJ = (ctx.get("injuries") or {}).get("NFL", {})
    DEP = (ctx.get("depth") or {}).get("NFL", {})
    ups = sorted(({"t": dt.datetime.fromisoformat(u[0]), "away": u[1], "home": u[2], "spread": u[3], "total": u[4]}
                  for u in meta.get("upcoming", [])), key=lambda u: u["t"])
    ups = [u for u in ups if now < u["t"] < now + dt.timedelta(days=7)]
    res = []
    for p in meta.get("players", []):
        if p.get("p") not in ("RB", "WR", "TE", "QB"):
            continue
        game = next((u for u in ups if p["t"] in (u["away"], u["home"])), None)
        if not game:
            continue
        gs = [dict(zip(cols, r)) for r in p["g"]]
        cur = [g for g in gs if g["date"] >= meta["curStart"]]
        if len(gs) < 4 or not cur:
            continue
        aid = str(p.get("e") or p["id"])
        inj, dep = INJ.get(aid), DEP.get(aid)
        if inj and inj["s"] in OUT_STATUS:
            continue
        key = f"NFL|{p['id']}|td"
        note = notes.get(key) or {}
        if note.get("flag") == "out":
            continue
        l10, l5 = gs[-10:], gs[-5:]
        rate = (sum(1 for g in l10 if g["td"] > 0) + .6) / (len(l10) + 2)
        touch = sum(g["car"] + g["rec"] for g in l5) / len(l5)
        per = (sum(g["td"] for g in l10) + .5) / (sum(g["car"] + g["rec"] for g in l10) + 15)
        home = game["home"] == p["t"]
        sp = game["spread"] if home else (-game["spread"] if game["spread"] is not None else None)
        imp = game["total"] / 2 - sp / 2 if game["total"] is not None and sp is not None else 22.5
        z = (TD_W["b"] + TD_W["rate"] * lt(rate) + TD_W["touch"] * math.log(touch + 1) + TD_W["per"] * math.log(per * 100)
             + TD_W["imp"] * (imp - 22.5) / 7 + TD_W.get(p["p"], 0))
        us = (USAGE.get("players") or {}).get(p["id"]) or {}
        if us.get("rz") is not None:
            z += TD_RZ * (math.log1p(us["rz"]) - RZ_MEAN) + TD_GL * (math.log1p(us.get("gl") or 0) - GL_MEAN)
        p_stat = sig(z)
        lad = ((MKTS.get("NFL") or {}).get(p["id"]) or {}).get("td")
        kal = market_prob(lad, .5, game["t"], now) if lad else None
        zz = TD_MKT * lt(min(.97, max(.03, kal))) + (1 - TD_MKT) * z if kal is not None else z
        why = []
        r_fav, r_adj, _ = research_dir(note)
        adj = CONF.get(note.get("conf"), 1.0) * .15 * r_adj * (1 if r_fav == "over" else -1) if r_fav else 0.0
        zz += adj
        shaky = bool(inj and inj["s"] in SHAKY)
        if shaky:
            zz -= .3
        backup = bool(dep and dep.get("role") == "backup")
        prob = sig(zz)
        if prob < .12:
            continue
        edge = prob - kal if kal is not None else None
        score = prob + (.5 * max(0, p_stat - kal) if kal is not None else -.03)  # stats above the market: a small bump
        if backup and not adj > 0:
            score *= .7
        cur_td = sum(g["td"] for g in cur)
        why.append(f"Scored in {sum(1 for g in l10 if g['td'] > 0)} of his last {len(l10)} games ({cur_td} TD{'s' if cur_td != 1 else ''} in {len(cur)} games this season)")
        why.append(f"{touch:.0f} touches a game lately")
        why.append(f"{p['t']} projected for about {imp:.0f} points")
        if shaky:
            why.append(f"listed {inj['s'].lower()}")
        if backup:
            why.append(f"a backup on the depth chart ({dep.get('slot')})")
        # real sportsbook prices (The Odds API, when a key is set): the best price across books and its expected profit
        od = (ODDS or {}).get(key) or {}
        best = max(((b, v.get("over")) for b, v in (od.get("books") or {}).items() if isinstance(v.get("over"), (int, float))),
                   key=lambda x: x[1], default=(None, None))
        price, book = best[1], best[0]
        ev = None
        if price:
            dec = 1 + (price / 100 if price > 0 else 100 / -price)
            ev = round(prob * dec - 1, 3)
        res.append({"key": key, "lg": "NFL", "id": p["id"], "price": price, "book": book, "ev": ev, "name": p["n"], "team": p["t"], "pos": p["p"],
                    "opp": game["away"] if home else game["home"], "home": home, "t": game["t"].isoformat(),
                    "market": "td", "label": "Anytime TD", "side": "over", "line": .5,
                    "prob": round(prob, 3), "stat": round(p_stat, 3), "kalshi": round(kal, 3) if kal is not None else None,
                    "edge": round(edge, 3) if edge is not None else None, "score": round(score, 3),
                    "l10": [sum(1 for g in l10 if g["td"] > 0), len(l10)], "season_td": cur_td, "season_g": len(cur),
                    "touches": round(touch, 1), "implied": round(imp, 1), "status": inj["s"] if inj else None,
                    "backup": backup, "why": ". ".join(why) + ".", "research": note.get("note") if note.get("side") else None,
                    "conf": note.get("conf"), "radj": (r_adj * (1 if r_fav == "over" else -1)) if r_fav else (0 if note.get("side") else None), "buzz": note.get("buzz")})
    res.sort(key=lambda c: -c["score"])
    # Oct 27: a TD is only a "bet" when the best price (Pinnacle, or FanDuel from lab_market.py's fd_board.json) pays at
    # or near fair: 94% of the app's chance (TDs ran 50% predicted / 48% scored) x the payout >= 0.98. The lists still
    # show the likeliest scorers; record.py records only the bets
    try:
        fdtd = (json.load(open("fd_board.json")).get("td") or {})
    except Exception:
        fdtd = {}
    for c in res:
        fd = fdtd.get(c["key"])
        c["fd"] = fd
        ams = [a for a in (c.get("price"), fd) if isinstance(a, (int, float)) and a]
        c["bp"] = max(ams, key=lambda a: 1 + (a / 100 if a > 0 else 100 / -a)) if ams else None  # the better price
        c["td_edge"] = round(.94 * c["prob"] * (1 + (c["bp"] / 100 if c["bp"] > 0 else 100 / -c["bp"])) - 1, 3) if ams else None
        c["td_bet"] = c["td_edge"] is not None and c["td_edge"] >= -.02

    def pick10(pool):
        top, per_team = [], {}
        for c in pool:
            if per_team.get(c["team"], 0) >= TD_PER_TEAM or (c["radj"] is not None and c["radj"] <= -1):
                continue
            per_team[c["team"]] = per_team.get(c["team"], 0) + 1
            top.append(c)
            if len(top) == 10:
                break
        return top
    top = pick10(res)
    # plus-money list: fair odds better than even (20-48%), ranked toward players the stats or research rate above
    # the market's price, since that's where a longer-shot TD bet can carry value
    # only when two markets disagree in the bet's favor: Kalshi's chance beats the sportsbook price on offer (the old
    # list, with no price check, went 10-15 for -5.8 units)
    priced = lambda c: c.get("price") and c["kalshi"] is not None and c["kalshi"] * (1 + (c["price"] / 100 if c["price"] > 0 else 100 / -c["price"])) >= 1.0
    lng = sorted((c for c in res if .2 <= c["prob"] < .48 and c["kalshi"] is not None and c["kalshi"] < .48 and priced(c)),
                 key=lambda c: -(c["prob"] + (1.0 * max(0, c["stat"] - c["kalshi"]) if c["kalshi"] is not None else 0)
                                 + .05 * max(0, c["radj"] or 0) * (1 if c["research"] else 0)))
    for c in top:
        c["list"] = "likely"
    long10 = [dict(c, list="long") for c in pick10(lng)]
    keep = ("key", "lg", "id", "name", "team", "pos", "opp", "home", "t", "market", "label", "side", "line", "prob", "stat",
            "kalshi", "l10", "season_td", "season_g", "touches", "implied", "status", "research", "radj", "conf", "buzz",
            "price", "book", "ev", "fd", "bp", "td_edge", "td_bet")
    return top + long10, [{k: c[k] for k in keep} for c in res[:120] if c["radj"] is None or c["radj"] > -1]


# ---- pick grades and suggested stakes (Oct 27) ----
# Each pick gets a fair chance built from the sportsbook's own no-vig price (2,000+ graded props show it's well
# calibrated) plus what the app's picks have actually added on top of it, learned from every graded prop in
# calib.json each run: unders have beaten the book's price, overs haven't, and the app's most confident picks did
# worse, not better. Edge = that chance x the payout - 1. Grade and units (1 unit = 1% of a bankroll, roughly a
# quarter of the Kelly stake): A 5%+ edge 2u, B 3-5% 1u, C 1-3% 0.5u, D -2% to 1% = pass, F below -2% = avoid.
# No real price: C at most. Checked out of sample (fit on Oct 7-23, tested Oct 24-26): picks it graded worst
# returned -9.7%, the rest about -3% to 0%, so it ranks picks, but no group has proven profitable yet.
GRADES = ((.05, "A", 2.0), (.03, "B", 1.0), (.01, "C", 0.5))
MIN_PRICE = -130  # Top lists skip anything shorter (Oct 27)
# Oct 29 audit of the 215 Top 10 picks graded since real prices began (Oct 17): the lowest-scored half lost 13.5u while the top
# quarter broke even, and picks priced at plus money went 2-11 (-8.7u) against 9-4 at -150 or shorter. So the Top 10 needs a
# score of at least MIN_TOP_SCORE = .23 (the old floor was .12) and plus-money picks rank at PLUS_PEN of their score. The cutoff was
# chosen on the same sample it was measured on: re-check after another month of graded picks.
MIN_TOP_SCORE, PLUS_PEN = .23, .8
NBA_TOP_FROM = dt.datetime(2026, 11, 15, tzinfo=dt.timezone.utc)  # NBA Top 10 paused until then (Oct 27)
GRADE_LAM = 60.0  # pulls the learned adjustments toward zero (= trust the book) until there's lots of data


def _imp(a):
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def _lg(p):
    p = min(.97, max(.03, p))
    return math.log(p / (1 - p))


def grade_feats(side, app, bp, real=True):
    """what the graded props say matters on top of the book's price (Oct 27, 2,034 props, checked on each half):
    the side (overs lost in both halves), a modest gap over the book on an under (0-6 points: the app's best spot), and
    a big gap over the book on either side (6+ points: lost in both halves; the book usually knows something)"""
    g = app - bp if real else 0.0
    u = side == "under"
    return (1.0 if u else 0.0, 0.0 if u else 1.0, 1.0 if (real and u and 0 <= g < .06) else 0.0, 1.0 if (real and g >= .06) else 0.0)


GRADE_K = 4


def grade_model():
    """(b_under, b_over, b_small_gap_under, b_big_gap, n): log-odds adjustments to the book's no-vig chance, fit on graded props"""
    try:
        rows = json.load(open("calib.json"))["props"]
    except Exception:
        return (0.0,) * GRADE_K + (0,)
    X, Y, OFF = [], [], []
    for e in rows:
        if e.get("status") not in ("win", "loss") or not e.get("po") or not e.get("pu") or e.get("pe") or not e.get("prob"):
            continue
        bo = _imp(e["po"]) / (_imp(e["po"]) + _imp(e["pu"]))
        bp = bo if e["side"] == "over" else 1 - bo
        X.append(grade_feats(e["side"], e["prob"], bp))
        Y.append(1.0 if e["status"] == "win" else 0.0)
        OFF.append(_lg(bp))
    if len(X) < 200:
        return (0.0,) * GRADE_K + (len(X),)
    K = GRADE_K
    b = [0.0] * K
    for _ in range(30):  # Newton steps, ridge penalty GRADE_LAM on every coefficient
        g = [-GRADE_LAM * v for v in b]
        H = [[GRADE_LAM if i == j else 0.0 for j in range(K)] for i in range(K)]
        for x, y, o in zip(X, Y, OFF):
            p = 1 / (1 + math.exp(-(o + sum(bi * xi for bi, xi in zip(b, x)))))
            w = p * (1 - p)
            for i in range(K):
                g[i] += (y - p) * x[i]
                for j in range(K):
                    H[i][j] += w * x[i] * x[j]
        # solve H d = g (Gaussian elimination)
        A = [H[i][:] + [g[i]] for i in range(K)]
        for i in range(K):
            piv = A[i][i] or 1e-9
            for j in range(i + 1, K):
                f = A[j][i] / piv
                A[j] = [a - f * c for a, c in zip(A[j], A[i])]
        d = [0.0] * K
        for i in reversed(range(K)):
            d[i] = (A[i][K] - sum(A[i][j] * d[j] for j in range(i + 1, K))) / (A[i][i] or 1e-9)
        b = [bi + di for bi, di in zip(b, d)]
        if max(abs(v) for v in d) < 1e-6:
            break
    return tuple(round(v, 4) for v in b) + (len(X),)


def grade_picks(cands, GM):
    """adds p_cal, edge, grade, units, parlay (and pair) to each candidate"""
    coef = GM[:GRADE_K]
    for c in cands:
        app = c.get("prob")
        if app is None:
            continue
        real = c.get("price") is not None and not c.get("price_est") and c.get("book_p") is not None
        if real:
            bp, price = c["book_p"], c["price"]
        elif c.get("price") is not None and c.get("price_other") is not None:
            # prices worked out for this line from a nearby one (fetch_prices.py shift): usable, but C at most
            bp = _imp(c["price"]) / (_imp(c["price"]) + _imp(c["price_other"]))
            price = c["price"]
        else:
            c.update(p_cal=None, edge=None, grade=None, units=None, parlay=False)  # no price yet: can't be graded
            continue
        adj = sum(b_ * x for b_, x in zip(coef, grade_feats(c["side"], app, bp, True)))
        p = 1 / (1 + math.exp(-(_lg(bp) + adj)))
        d = 1 + (price / 100 if price > 0 else 100 / -price)
        edge = p * d - 1
        g, u = ("D" if edge >= -.02 else "F"), 0.0  # D: about break-even, pass; F: clearly costs money, avoid
        for lo, gg, uu in GRADES:
            if edge >= lo:
                g, u = gg, uu
                break
        if not real and g in ("A", "B"):
            g, u = "C", 0.5  # no real price to check against
        c.update(p_cal=round(p, 3), edge=round(edge, 3), grade=g, units=u, parlay=g in ("A", "B") and p >= .55)
    # a parlay partner: another good leg in the same game that tends to hit together (a QB's passing over with his own
    # receiver's over, or both unders on the same team's passing game)
    PASS, RECV = {"pyd", "cmp", "att", "ptd"}, {"rec", "recyd"}
    legs = [c for c in cands if c.get("parlay")]
    for c in legs:
        for o in legs:
            if o is c or o["team"] != c["team"] or o["t"] != c["t"] or o["side"] != c["side"] or o["id"] == c["id"]:
                continue
            if (c["market"] in PASS and o["market"] in RECV) or (c["market"] in RECV and o["market"] in PASS):
                c["pair"] = f"{o['name']} {o['side']} {fmt(o['line'])} {o['label'].lower()}"
                break


def main():
    data = json.load(open("props_data.json"))
    try:
        notes = json.load(open("notes.json"))
        fresh = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(notes["updated"].replace("Z", "+00:00")) < dt.timedelta(hours=72)
        best_note = (notes.get("best") or {}) if fresh else {}
        cfb_lines = (notes.get("cfb_lines") or {}) if fresh else {}
        notes = notes.get("notes", {}) if fresh else {}
    except Exception:
        notes, best_note, cfb_lines = {}, {}, {}
    out_players = {"|".join(k.split("|")[:2]) for k, v in notes.items() if v.get("flag") == "out"}
    try:
        data["CFB"] = json.load(open("cfb_data.json"))
    except Exception:
        pass
    try:
        lines = json.load(open("lines.json"))
    except Exception:
        lines = {}
    now = dt.datetime.now(dt.timezone.utc)
    try:
        ctx = json.load(open("context.json"))
        if now - dt.datetime.fromisoformat(ctx["built"]) > dt.timedelta(hours=30):
            ctx = {}
    except Exception:
        ctx = {}
    try:  # real sportsbook lines and prices for the top picks (fetch_odds.py, The Odds API), when available
        ODDS = {k: v for k, v in (json.load(open("odds.json")).get("props") or {}).items()
                if now - dt.datetime.fromisoformat(v["t"]) < dt.timedelta(hours=14)}
    except Exception:
        ODDS = {}
    try:  # FanDuel's own lines and prices for every NFL/NBA player prop (lab_market.py -> fd_board.json, hourly): the
        # price fallback when Pinnacle hasn't posted and ESPN's feed has none (its NFL feed never has prices; Oct 28)
        fdb = json.load(open("fd_board.json"))
        FDB = {c["key"]: c for c in fdb.get("props", []) if now - dt.datetime.fromisoformat(fdb["built"]) < dt.timedelta(hours=6)}
    except Exception:
        FDB = {}
    global USAGE
    try:  # how each NFL player is being used: snaps, target / carry share, red zone (build_usage.py)
        USAGE = json.load(open("usage.json"))
        if now - dt.datetime.fromisoformat(USAGE["built"]) > dt.timedelta(days=9):
            USAGE = {}
    except Exception:
        USAGE = {}
    try:  # what the graded results have taught (tune.py): prop-type, factor and research-confidence weights
        TUNE = json.load(open("tuning.json"))
    except Exception:
        TUNE = {}
    FXM, MKM = TUNE.get("factors") or {}, TUNE.get("market") or {}
    # self-correction (tune.py, from every graded slate prop): logit P(over) = c + b * raw logit, plus per prop type
    CALB = TUNE.get("calibration") or {}
    CONF = {"low": .6, "medium": 1.0, "high": 1.2, **(TUNE.get("research_conf") or {})}
    CONF["low"] = 0.0  # low-confidence research calls went 4-12: shown as notes, but they no longer move picks
    try:  # Kalshi prediction-market prices (fetch_markets.py); stale prices are ignored
        MKTS = json.load(open("markets.json"))
        if now - dt.datetime.fromisoformat(MKTS["fetched"]) > dt.timedelta(hours=8):
            MKTS = {}
    except Exception:
        MKTS = {}
    cands, slate = [], []
    for lg in ("NFL", "NBA", "CFB"):
        if lg not in data:
            continue
        L = lines.get(lg) or {}
        if lg == "CFB" and cfb_lines:
            # no DraftKings college props in the feed: use the lines the research found in published previews
            L = {k: dict(v) for k, v in L.items()}
            for k, v in cfb_lines.items():
                _, pid, mid = k.split("|")
                if dt.datetime.fromisoformat(v["t"]) > now and mid not in L.get(pid, {}):
                    L.setdefault(pid, {})[mid] = {"line": v["line"], "open": None, "d": v["t"], "book": v.get("book")}
        meta = data[lg]
        cols = meta["cols"]
        # a player's team comes from his last box score; after a trade or signing (or before his new team's
        # first game) that's stale, so use the team ESPN's current depth chart lists him on
        try:
            if now - dt.datetime.fromisoformat((ctx.get("fetched") or {}).get(lg) or ctx["built"]) < dt.timedelta(hours=30):
                for pl in meta["players"]:
                    d = ((ctx.get("depth") or {}).get(lg) or {}).get(str(pl.get("e") or pl["id"]))
                    if d and d.get("t") and d["t"] != pl["t"]:
                        pl["t"] = d["t"]
        except Exception:
            pass
        allowed = allowed_tables(meta["players"], cols, lg)
        team_last = {}
        for pl in meta["players"]:
            if pl["g"]:
                d = dict(zip(cols, pl["g"][-1]))["date"]
                if d > team_last.get(pl["t"], ""):
                    team_last[pl["t"]] = d
        w = W[lg]
        INJ = (ctx.get("injuries") or {}).get(lg, {})
        DEP = (ctx.get("depth") or {}).get(lg, {})  # ESPN depth charts: starter or backup
        try:  # ignore a league's injury report if it couldn't be refreshed for 30+ hours
            if now - dt.datetime.fromisoformat((ctx.get("fetched") or {}).get(lg) or ctx["built"]) > dt.timedelta(hours=30):
                INJ, DEP = {}, {}
        except Exception:
            INJ, DEP = {}, {}
        inj_of = lambda pl: INJ.get(str(pl.get("e") or pl["id"]))
        # each team's recent games, to see which regulars an injury report takes away
        by_team = {}
        for pl in meta["players"]:
            by_team.setdefault(pl["t"], []).append(pl)
        # only this season's games from the last couple of weeks count, so a long-term absence the team has
        # already adjusted to (or last season's roster) isn't treated as fresh news
        recent_from = max(meta["curStart"], (now - dt.timedelta(days=12 if lg == "NBA" else 29)).date().isoformat())
        team_recent = {}
        for tm, pls in by_team.items():
            ds = sorted({d for pl in pls for g in pl["g"][-6:] if (d := dict(zip(cols, g))["date"]) >= recent_from})[-4:]
            team_recent[tm] = ds

        def vacated(pl, key):
            """share of his team's usual `key` production (last 4 games) held by regulars now ruled out"""
            ds = team_recent.get(pl["t"]) or []
            need = 3 if lg == "NBA" else 2  # football: weekly games, so two recent games is a fair read
            if len(ds) < need or key is None:
                return 0.0, []
            tot, gone, who = 0.0, 0.0, []
            for mate in by_team[pl["t"]]:
                gs = [dict(zip(cols, g)) for g in mate["g"][-6:]]
                gs = [g for g in gs if g["date"] in ds]
                v = sum(g[key] for g in gs) / len(ds)
                tot += v
                st = inj_of(mate)
                if mate is not pl and len(gs) >= need and st and st["s"] in OUT_STATUS and v > 0:
                    gone += v
                    who.append((v, mate["n"]))
            if tot <= 0:
                return 0.0, []
            return gone / tot, [n for v, n in sorted(who, reverse=True)]
        ups = [{"t": dt.datetime.fromisoformat(u[0]), "away": u[1], "home": u[2], "spread": u[3], "total": u[4]}
               for u in meta.get("upcoming", [])]
        ups = [u for u in ups if u["t"] >= now - dt.timedelta(hours=3)]
        for p in meta["players"]:
            espn = p.get("e") or p["id"]
            e = L.get(espn)
            if not e:
                continue
            game = next((u for u in sorted(ups, key=lambda u: u["t"]) if p["t"] in (u["away"], u["home"])), None)
            if not game:
                continue
            if f"{lg}|{p['id']}" in out_players:
                continue
            me_inj = inj_of(p)
            me_dep = DEP.get(str(p.get("e") or p["id"]))
            if me_dep is None and lg == "NFL" and len(DEP) > 500:
                me_dep = {"role": "backup", "slot": "reserve", "n": 9}  # not on his team's depth chart at all
            if me_inj and me_inj["s"] in OUT_STATUS:
                continue  # on the injury report as out
            wx = (ctx.get("weather") or {}).get(f"{lg}|{game['away']}@{game['home']}|{game['t'].astimezone(dt.timezone.utc):%Y-%m-%d}")
            games = [dict(zip(cols, g)) for g in p["g"]]
            for mid, dk in e.items():
                if mid not in UNIT:
                    continue
                od = ODDS.get(f"{lg}|{p['id']}|{mid}")
                if od and od.get("line") is not None:
                    # a sportsbook quote straight from the book beats ESPN's copy: use its line and prices (est_over / est_under:
                    # a price fetch_prices.py worked out for this line rather than one the book quoted at it)
                    dk = dict(dk, line=od["line"], u=od["t"], price_over=od.get("over"), price_under=od.get("under"),
                              books=od.get("books"), book=od.get("book"), est_over=od.get("est_over"), est_under=od.get("est_under"))
                elif FDB.get(f"{lg}|{p['id']}|{mid}") and dk.get("line") is not None:
                    fq = FDB[f"{lg}|{p['id']}|{mid}"]
                    if fq["line"] == dk["line"]:
                        dk = dict(dk, price_over=fq["over"], price_under=fq["under"], book="FanDuel", est_over=False, est_under=False)
                    else:  # FanDuel's prices moved to DraftKings' line (fetch_prices.shift): an estimate, graded C at most
                        try:
                            from fetch_prices import shift
                            mv = shift(fq["line"], fq["over"], fq["under"], dk["line"], mid)
                        except Exception:
                            mv = None
                        if mv:
                            dk = dict(dk, price_over=mv[0], price_under=mv[1], book="FanDuel", est_over=True, est_under=True)
                elif dk.get("po") is not None and dk.get("pu") is not None:
                    # no Pinnacle / FanDuel quote: DraftKings' own prices at this line, from ESPN's feed (fetch_lines.py).
                    # Without these most NBA picks had no price at all, so they couldn't be graded (Oct 27)
                    dk = dict(dk, price_over=dk["po"], price_under=dk["pu"], book="DraftKings", est_over=False, est_under=False)
                if dk.get("d") and dt.datetime.fromisoformat(dk["d"].replace("Z", "+00:00")) < now - dt.timedelta(hours=5):
                    continue  # line for a game that's already been played
                vals = [stat(g, mid) for g in games]
                if len(vals) < (5 if lg == "CFB" else 8):
                    continue
                line = dk["line"]
                cur = [stat(g, mid) for g in games if g["date"] >= meta["curStart"]]
                # college rosters and roles change a lot between seasons: judge college form on this season alone.
                # NBA too (from Oct 22): lines are set for this season's roles, so last season's games don't count;
                # until he has 3 games this season his recent results aren't used at all (nba_early)
                nba_early = lg == "NBA" and len(cur) < 3
                l10 = cur[-10:] if lg in ("CFB", "NBA") and len(cur) >= 3 else vals[-10:]
                l5 = l10[-5:]
                hits = lambda a: sum(v > line for v in a)
                sh = lambda a: (hits(a) + 1) / (len(a) + 2)
                p_over = .45 * sh(l10) + .35 * (sh(cur) if len(cur) >= 3 else sh(vals)) + .2 * sh(l5)
                avg = sum(l10) / len(l10)
                sd = max(math.sqrt(sum((v - avg) ** 2 for v in l10) / len(l10)), line * .12, 1)
                z = (avg - line) / sd
                home = game["home"] == p["t"]
                opp = game["away"] if home else game["home"]
                mu = allowed(mid, grp(lg, p.get("p"))).get(opp)
                tot = 0.0
                if lg != "NBA" and game["total"] is not None and game["spread"] is not None:
                    tsp = game["spread"] if home else -game["spread"]
                    tot = (game["total"] / 2 - tsp / 2 - (22.5 if lg == "NFL" else 28)) / 4
                mtr = 0.0
                # a minutes trend from last season's final weeks (rest days, tanking) says nothing about opening week
                # (this season's games only, like the rest of NBA form: from a player's 4th game)
                cur_g = [g for g in games if g["date"] >= meta["curStart"]]
                if lg == "NBA" and len(cur_g) >= 4:
                    mins = [g["min"] for g in cur_g]
                    base15 = sum(mins[-15:]) / len(mins[-15:])
                    mtr = max(-.5, min(.5, (sum(mins[-3:]) / 3 - base15) / max(base15, 10)))
                note = notes.get(f"{lg}|{p['id']}|{mid}") or {}
                if not note:
                    # no research on this exact prop: borrow half of what was found on his other props
                    # (injuries to him or his teammates usually move all his props the same way)
                    other = [v for k, v in notes.items() if k.startswith(f"{lg}|{p['id']}|") and not k.endswith("|td")]
                    if other:
                        # what was found about his production in general (more or less), at half weight
                        note = {"push": .5 * sum(research_push(v) for v in other) / len(other), "borrowed": True}
                # a DraftKings line far from his recent numbers usually means the book knows something
                # (injury, role change), so trust the stats less there; z is capped to the backtested range
                ratio = max(avg, line) / max(min(avg, line), 1)
                gap = ratio - 1
                trust = 1.0 if ratio <= 1.25 else max(.15, 1 - (ratio - 1.25) * 1.5)
                missed = team_last.get(p["t"], "") > games[-1]["date"]  # sat out his team's latest game
                if missed:
                    trust *= .5
                zc = max(-1.0, min(1.0, z))
                vac, vac_who = vacated(p, VAC_KEY.get(mid))
                news = (VAC_W * min(vac, .6) if lg == "NBA" else VAC_W_NFL * min(vac, .5) if lg == "NFL" else 0.0) - (.1 if me_inj and me_inj["s"] in SHAKY else 0.0)
                wind = (wx or {}).get("wind")
                weather = 0.0
                if wx and not wx.get("indoor") and lg in ("NFL", "CFB"):
                    if wind is not None and mid in PASS_M:
                        weather += (WIND_W if mid in QB_M else WIND_W_REC) * max(0.0, (wind - 12) / 5)
                    if wx.get("temp") is not None and mid in COLD_W:
                        weather += COLD_W[mid] * max(0.0, (40 - wx["temp"]) / 10)
                    weather = max(-.6, weather)
                blow = 0.0
                if lg == "CFB" and game["spread"] is not None and mid in BLOW_M:
                    blow = BLOW_W * BLOW_M[mid] * min(max(abs(game["spread"]) - 10, 0), 14) / 14
                parts = {"form": 0.0 if nba_early else trust * (w["p"] * (p_over - .5) + w["z"] * zc), "matchup": w["mu"] * (mu["z"] if mu else 0),
                         "game": w["tot"] * tot, "minutes": w["mtr"] * mtr, "news": news, "weather": weather, "blowout": blow}
                pc = meta.get("pace") or {}
                if lg == "NBA" and pc.get(p["t"]) and pc.get(opp):
                    lg_pace = sum(pc.values()) / len(pc)
                    # a fast matchup means more possessions for everyone (backtest +0.07 log-odds per 5 possessions)
                    parts["game"] = NBA_PACE_W * max(-1.5, min(1.5, ((pc[p["t"]] + pc[opp]) / 2 - lg_pace) / 5))
                us = (USAGE.get("players") or {}).get(p["id"]) if lg == "NFL" else None
                if us and us.get("team") == p["t"] and mid in USE_W and (us.get("proj") or {}).get(mid) is not None:
                    upj = max(-1.5, min(1.5, (us["proj"][mid] - line) / sd))
                    # a role change the book may not have caught up with yet
                    u_proj, u_snap = USE_W[mid] * upj, SNAP_W * max(-.2, min(.2, us.get("snap_tr") or 0)) * (0 if missed else 1)
                    parts["usage"] = u_proj + u_snap
                for f, mlt in FXM.items():
                    if f in parts:
                        parts[f] *= mlt
                if mid in YARD_OVER_SHRINK and sum(parts.values()) > 0:
                    parts["form"] *= YARD_OVER_SHRINK[mid]
                lin = sum(parts.values())
                stats_over = lin >= 0
                mrec = ((MKTS.get(lg) or {}).get(p["id"]) or {}).get(mid)
                p_mkt = market_prob(mrec, line, game["t"], now)
                # ESPN's DraftKings lines can go stale for days; Kalshi's live market shows where the line really is
                age_h = None
                try:
                    if dk.get("u"):
                        age_h = max(0.0, (now - dt.datetime.fromisoformat(dk["u"].replace("Z", "+00:00"))).total_seconds() / 3600)  # ESPN stamps can run ahead
                except ValueError:
                    pass
                med = market_median(mrec, game["t"], now)
                moved = med is not None and abs(med - line) >= max(1.5 if mid not in ("rec", "cmp", "car", "att", "ptd", "td", "sck") else 1.0, .08 * line) \
                    and (age_h is None or age_h > 6)
                if moved:
                    p_mkt = None  # the price at a line that's probably gone isn't a signal
                if p_mkt is not None:
                    pm = min(.97, max(.03, p_mkt))
                    parts["market"] = max(-.6, min(.6, MKT_W * math.log(pm / (1 - pm)))) * FXM.get("market", 1)
                    lin += parts["market"]
                # the research's over/under leans no longer move the chance (Oct 26: leans went 74-96, 44%); its news
                # (ruled out, role changes, questionable) still counts below and through the injury report
                RESEARCH_IN_RANKING = False
                conf = CONF.get(note.get("conf"), 1.0) * FXM.get("research", 1)
                r_over = note["push"] * conf if note.get("borrowed") else research_push(note, conf)
                if RESEARCH_IN_RANKING:
                    lin += r_over
                    parts["research"] = r_over
                # the model's own parts with the learned factor weights taken back out, so tune.py can re-learn them
                fraw = {f: round((v / FXM.get(f, 1)) if FXM.get(f) else v, 3) for f, v in parts.items() if abs(v) >= .001}
                raw_lin = lin
                cm, bm = (CALB.get("per") or {}).get(f"{lg}|{mid}") or (0.0, 1.0)
                lin = CALB.get("c", 0.0) + cm + CALB.get("b", 1.0) * bm * lin
                over = lin >= 0
                prob = 1 / (1 + math.exp(-lin))
                score = abs(prob - .5) * 4
                score *= MKM.get(f"{lg}|{mid}|{'over' if over else 'under'}", 1)  # learned from graded results
                lowline = mid in LOW_LINE_M and line <= 1.5
                if moved:
                    score *= .6   # the real line has likely moved away from this one
                elif age_h is not None and age_h > 24:
                    score *= .9   # unconfirmed for a day or more
                # backups' roles swing week to week, so they rank much lower unless research says his role grew
                backup = bool(me_dep and me_dep["role"] == "backup")
                if backup and not (note.get("side") == ("over" if over else "under") and float(note.get("adj") or 0) >= 1):
                    score *= .5
                if lowline:
                    score *= .7
                side = "over" if over else "under"
                price = dk.get("price_over") if over else dk.get("price_under")
                be = None
                if isinstance(price, (int, float)) and price != 0:
                    be = 100 / (price + 100) if price > 0 else -price / (-price + 100)  # break-even win rate at this price
                    if (prob if over else 1 - prob) < be:
                        score *= .7  # the price asks for more than the numbers give him
                exact = note if note and not note.get("borrowed") else {}
                r_fav, r_adj, r_unc = research_dir(exact) if exact else (None, 0, False)
                if exact and r_unc:
                    score *= .85  # the research found the outlook uncertain (questionable, role in flux)
                # a line far from his numbers usually means the book knows something: keep it out of the Top lists
                # (the research no longer vouches for these: its leans lost)
                if gap > .25:
                    score *= .6
                # the fact-checker found a different line in current odds pages: this one is probably out of date
                line_off = exact.get("line_now") is not None and abs(float(exact["line_now"]) - line) >= max(1, .05 * line)
                if line_off:
                    score *= .7
                # the sportsbook strongly disagrees: when the model is 12+ points more confident than the book's no-vig price,
                # the book usually knows something (benching, role change). Oct 17-18 graded props: model 15+ points above the
                # book hit 4 of 17 (24%), 5-15 points above hit 47% vs the 60% the model expected. Research can't override this.
                book_p = book_gap = None
                po_, pu_ = dk.get("price_over"), dk.get("price_under")
                if po_ is not None and pu_ is not None and not (dk.get("est_over") or dk.get("est_under")):
                    imp_ = lambda a: 100 / (a + 100) if a > 0 else -a / (-a + 100)
                    bo = imp_(po_) / (imp_(po_) + imp_(pu_))
                    book_p = bo if over else 1 - bo
                    book_gap = (prob if over else 1 - prob) - book_p
                    if book_gap > BOOK_GAP:
                        score *= .5
                # Kalshi's traders favor the other side at this line: the stats outvoted the market, and the market has
                # usually been right (see KALSHI_AGAINST)
                kal_side = (p_mkt if over else 1 - p_mkt) if p_mkt is not None else None
                kal_against = kal_side is not None and kal_side < KALSHI_AGAINST
                if kal_against:
                    score *= .5
                # DraftKings has moved the line hard away from this side since it opened (Skattebo: 15.5 -> 11.5 carries
                # before he was benched): news the stats can't see yet. Research can't override this either.
                d0 = e.get(mid) or {}
                mv = (d0["line"] - d0["open"]) if d0.get("open") is not None and d0.get("line") is not None else 0
                moved_against = (mv < 0 if over else mv > 0) and abs(mv) >= max(1.0, LINE_MOVE * d0["open"]) if mv else False
                if moved_against:
                    score *= .6
                slate.append({"key": f"{lg}|{p['id']}|{mid}", "lg": lg, "id": p["id"], "p_over": round(prob, 3),
                              "x": round(raw_lin, 3), "f": fraw,
                              # the sportsbook's prices at this line (fetch_prices.py), kept with the graded props so the
                              # market-anchored ranking (PR #2) can be tested on real results
                              **({"po": dk.get("price_over"), "pu": dk.get("price_under"), "pb": dk.get("book"),
                                  "pe": bool(dk.get("est_over") or dk.get("est_under"))} if dk.get("price_over") or dk.get("price_under") else {}), "name": p["n"], "team": p["t"], "pos": p.get("p"),
                              "opp": opp, "t": game["t"].isoformat(), "market": mid, "label": LABEL[mid], "line": line,
                              "avg10": round(avg, 1), "l10_over": hits(l10), "n10": len(l10), "open": d0.get("open"),
                              "book_p": round(book_p, 3) if book_p is not None else None,
                              "matchup": f"{mu['rank']}/{mu['n']}" if mu else None, "gap": round(gap, 2),
                              "missed_last": missed, "lean": "over" if stats_over else "under", "score": round(score, 3),
                              "status": me_inj["s"] if me_inj else None, "teammates_out": vac_who[:3], "vacated": round(vac, 2),
                              "wind": wind, "rain": (wx or {}).get("rain"), "indoor": (wx or {}).get("indoor"),
                              "market_over": round(p_mkt, 3) if p_mkt is not None else None,
                              "depth": f"{me_dep['role']} ({me_dep['slot']})" if me_dep else None})
                if score <= .05:
                    continue
                side_hits = lambda a: hits(a) if over else len(a) - hits(a)
                last = re.sub(r"\s+(Jr|Sr|II|III|IV|V)\.?$", "", p["n"]).split()[-1]
                if nba_early:
                    why = (f"{last} has played {len(cur)} game{'' if len(cur) == 1 else 's'} this season"
                           + (f" ({', '.join(str(v) for v in cur)} {UNIT[mid]})" if cur else "")
                           + ", so his recent numbers don't count yet: this pick comes from the matchup, the pace, the market"
                           " and the news, not last season's games.")
                else:
                    why = (f"{last} has gone {'over' if over else 'under'} {fmt(line)} in {side_hits(l10)} of his last "
                           f"{len(l10)}{' this season' if lg in ('CFB', 'NBA') and len(cur) >= 3 else ''}")
                    if len(cur) >= 2 and not (lg in ("CFB", "NBA") and len(cur) >= 3 and len(cur) <= 10):
                        why += f" and {side_hits(cur)} of {len(cur)} this season"
                    why += f", averaging {avg:.1f} {UNIT[mid]} over {'those games' if len(l10) < 10 else 'the last 10'}."
                vs = [stat(g, mid) for g in games if g["opp"] == opp]
                if vs:
                    why += f" Against {opp}: {', '.join(str(v) for v in vs)}."
                if dk.get("open") is not None and dk["open"] != line:
                    why += (f" The line has moved {'up' if line > dk['open'] else 'down'} "
                            f"{fmt(abs(line - dk['open']))} since it opened at {fmt(dk['open'])}.")
                if missed:
                    why += " He did not play in his team's most recent game, so check his status before betting."
                if trust < 1 and not missed:
                    why += (f" Caution: the line is {'well above' if line > avg else 'well below'} his recent average, which often"
                            f" means a role change or injury news, so this pick is weighted down.")
                if mu:
                    why += (f" {opp} has allowed the {ordinal(mu['rank']) if mu['rank'] <= mu['n'] / 2 else ordinal(mu['n'] - mu['rank'] + 1)}-"
                            f"{'most' if mu['rank'] <= mu['n'] / 2 else 'fewest'} {UNIT[mid]} to {GROUPNAME.get(grp(lg, p.get('p')), 'players')} over its last 10.")
                if "usage" in parts and abs(us.get("snap_tr") or 0) >= .1 and not missed:
                    st = us["snap_tr"]
                    why += (f" His snap share has {'jumped' if st > 0 else 'dropped'} {abs(st) * 100:.0f} points over his last 2 games"
                            f"{', a role the line may not have caught up with' if (st > 0) == over else ', which works against this pick'}.")
                if "usage" in parts and abs(u_proj) >= .06:
                    pj = us["proj"][mid]
                    agree = (u_proj > 0) == over
                    share = (f"{us['tsh'] * 100:.0f}% of {p['t']}'s targets" if mid in ("rec", "recyd") else
                             f"{us['csh'] * 100:.0f}% of {p['t']}'s carries" if mid in ("ryd", "car") else
                             f"{us['csh'] * 100:.0f}% of the carries and {us['tsh'] * 100:.0f}% of the targets" if mid == "rry" else
                             f"{p['t']}'s {USAGE['teams'][p['t']]['drop']:.0f} dropbacks a game")
                    why += (f" Usage {'backs this' if agree else 'cuts against this'}: {share} over his last 6 projects about "
                            f"{pj:.0f} {UNIT[mid]}.") if mid not in ("pyd", "cmp", "att") else (
                            f" Usage {'backs this' if agree else 'cuts against this'}: {share} lately projects about {pj:.0f} {UNIT[mid]}.")

                if vac_who and ((vac >= .05 and lg == "NBA") or (vac >= .1 and lg == "NFL")) and over:
                    names = [re.sub(r"\s+(Jr|Sr|II|III|IV|V)\.?$", "", n).split()[-1] for n in vac_who[:2]]
                    why += (f" With {' and '.join(names)} ruled out, about {vac * 100:.0f}% of {p['t']}'s recent "
                            f"{ {'pts': 'scoring', 'reb': 'rebounding', 'ast': 'assists', 'min': 'minutes', 'rec': 'catches', 'car': 'carries'}[VAC_KEY[mid]] } is up for grabs.")
                if me_inj and me_inj["s"] in SHAKY:
                    why += f" He's listed {me_inj['s'].lower()}{' (' + me_inj['inj'].lower() + ')' if me_inj.get('inj') else ''}, so check his status before betting."
                if wind is not None and not wx.get("indoor") and (wind >= 15 or (wx.get("rain") or 0) >= 60) and lg != "NBA":
                    why += f" Forecast at kickoff: {wind:.0f} mph wind" + (f", {wx['rain']:.0f}% chance of rain" if (wx.get("rain") or 0) >= 40 else "") + "."
                if backup:
                    why += f" He's a backup on the depth chart ({me_dep['slot']}), so his role can swing a lot."
                elif me_dep and me_dep.get("moved_up"):
                    why += " He moves into the starting lineup because the player ahead of him is ruled out."
                if moved:
                    why += (f" Heads up: this DraftKings line hasn't updated in {age_h / 24:.0f} day{'s' if age_h >= 36 else ''} and Kalshi's market"
                            f" centers near {fmt(round(med * 2) / 2)}, so the live line has probably moved." if age_h else
                            f" Heads up: Kalshi's market centers near {fmt(round(med * 2) / 2)}, so check the live line.")
                if book_gap is not None and book_gap > BOOK_GAP:
                    why += (f" Warning: the sportsbook's price gives the {'over' if over else 'under'} only about {book_p * 100:.0f}%,"
                            f" well below this model's {(prob if over else 1 - prob) * 100:.0f}%. Big disagreements like this have"
                            f" usually gone the book's way, so this pick is weighted down.")
                if kal_against:
                    why += (f" Warning: Kalshi traders lean the other way ({kal_side * 100:.0f}% for the {'over' if over else 'under'})."
                            f" When they've disagreed with this model, they've usually been right, so this pick is weighted down.")
                if moved_against:
                    why += (f" Warning: DraftKings moved this line {'down' if mv < 0 else 'up'} {fmt(abs(mv))} from {fmt(d0['open'])},"
                            f" against this pick; a move that size usually means role or injury news.")
                if line_off:
                    why += f" Current odds pages show {fmt(float(exact['line_now']))}, so check the live line before betting."
                if p_mkt is not None:
                    why += f" Kalshi traders put the {'over' if over else 'under'} at {round((p_mkt if over else 1 - p_mkt) * 100)}%."
                if lg == "NBA" and abs(mtr) >= .08:
                    why += f" His minutes are {'up' if mtr > 0 else 'down'} lately ({sum(mins[-3:]) / 3:.0f} a game over the last 3)."
                if lg in ("NFL", "CFB") and game["total"] is not None:
                    sp = game["spread"] if home else (None if game["spread"] is None else -game["spread"])
                    why += f" Game total {fmt(game['total'])}"
                    why += f", {p['t']} {'+' if sp > 0 else ''}{fmt(sp)}." if sp is not None else "."
                cands.append({
                    "key": f"{lg}|{p['id']}|{mid}", "lg": lg, "id": p["id"], "name": p["n"], "team": p["t"],
                    "pos": p.get("p"), "opp": opp, "home": home, "t": game["t"].isoformat(), "market": mid,
                    "label": LABEL[mid], "side": "over" if over else "under", "line": line, "open": dk.get("open"), "book": dk.get("book") or "DraftKings",
                    "l10": [side_hits(cur), len(cur)] if nba_early else [side_hits(l10), len(l10)],
                    "avg10": round(sum(cur) / len(cur), 1) if nba_early and cur else round(avg, 1), "score": round(score, 3), "why": why,
                    "prob": round(prob if over else 1 - prob, 3),
                    "factors": {k: round(v if over else -v, 3) for k, v in parts.items()},
                    "gap": round(gap, 2),
                    "status": me_inj["s"] if me_inj else None, "lowline": lowline,
                    "researched": bool(exact), "price": price, "price_other": dk.get("price_under") if over else dk.get("price_over"),
                    "price_est": bool(price is not None and dk.get("est_over" if over else "est_under")),
                    "books": dk.get("books"), "break_even": round(be, 3) if be else None, "role": me_dep["role"] if me_dep else None, "slot": me_dep["slot"] if me_dep else None,
                    "moved_up": bool(me_dep and me_dep.get("moved_up")),
                    "age_h": round(age_h, 1) if age_h is not None else None, "moved": round(med, 1) if moved else None,
                    "mkt": round(p_mkt if over else 1 - p_mkt, 3) if p_mkt is not None else None,
                    "book_p": round(book_p, 3) if book_p is not None else None, "moved_against": moved_against,
                })
    slate.sort(key=lambda s: (s["t"], -s["score"]))
    json.dump({"built": now.isoformat(timespec="minutes"),
               "about": "Every prop with a DraftKings line on the upcoming slate. matchup = opponent's rank (1 = allows the most "
                        "to this position, last 10 games); gap = how far the line is from his recent average; lean = stats side.",
               "props": slate}, open("slate.json", "w"), indent=0)
    GM = grade_model()
    grade_picks(cands, GM)
    print(f"grades: book chance adjusted by under {GM[0]:+.3f}, over {GM[1]:+.3f}, modest-gap under {GM[2]:+.3f}, "
          f"big gap {GM[3]:+.3f} (log-odds, from {GM[4]} graded props); "
          + ", ".join(f"{g} {sum(1 for c in cands if c.get('grade') == g)}" for g in "ABCDF"))
    out = {"built": now.isoformat(timespec="minutes"), "picks": []}
    out["grading"] = {"under": GM[0], "over": GM[1], "gap_small_under": GM[2], "gap_big": GM[3], "n": GM[4]}
    if cands:
        first = min(dt.datetime.fromisoformat(c["t"]) for c in cands)

        def pick_from(pool):
            pool = sorted(pool, key=lambda c: -c["score"])
            res, seen, per_game = [], set(), {}
            for c in pool:
                gk = (c["lg"], c["t"], *sorted((c["team"], c["opp"])))
                if (c["lg"], c["id"]) in seen or per_game.get(gk, 0) >= 3:
                    continue
                seen.add((c["lg"], c["id"])); per_game[gk] = per_game.get(gk, 0) + 1
                res.append(c)
                if len(res) == KEEP:
                    break
            return res

        def slate(pool, need):
            # start with the next day's games and widen until there are enough picks
            start = min(dt.datetime.fromisoformat(c["t"]) for c in pool)
            chosen = []
            for hours in (18, 42, 96, 168):
                chosen = pick_from([c for c in pool if dt.datetime.fromisoformat(c["t"]) <= start + dt.timedelta(hours=hours)])
                if len(chosen) >= need:
                    break
            return chosen

        # Oct 27 owner's changes: the Top lists skip picks graded F (the price says they cost money) and picks priced
        # worse than -130 (NFL went 18-12 after Oct 22 but lost units on short prices), and the NBA Top 10 is paused
        # until players have about 10 games this season (46%, -12.7u through Oct 27). Every prop stays on the board.
        full = cands
        cands = [c for c in cands if c.get("grade") != "F" and not (c.get("price") is not None and c["price"] < MIN_PRICE)
                 and not (c["lg"] == "NBA" and now < NBA_TOP_FROM)]
        for c in cands:  # plus-money prices rank lower (2-11 in the Oct 17-28 record)
            if c.get("price") is not None and c["price"] > 0:
                c["score"] = round(c["score"] * PLUS_PEN, 3)
        print(f"Top lists: {len(cands)} of {len(full)} candidates listable (no F grades, nothing shorter than {MIN_PRICE}, NBA paused)")
        top_pool = [c for c in cands if c["score"] >= MIN_TOP_SCORE]
        out["picks"] = slate(top_pool, 14) if top_pool else []  # 10 shown + spares for ruled-out players
        out["byMarket"] = {}
        for k in sorted({(c["lg"], c["market"]) for c in cands}):
            pool = [c for c in cands if (c["lg"], c["market"]) == k]
            out["byMarket"][f"{k[0]}|{k[1]}"] = slate(pool, 12)[:12]
        # the same lists with overs only (the app shows these by default)
        ov = [c for c in cands if c["side"] == "over"]
        out["picksOver"] = slate([c for c in ov if c["score"] > .05], 14) if ov else []
        out["byMarketOver"] = {}
        for k in sorted({(c["lg"], c["market"]) for c in ov}):
            pool = [c for c in ov if (c["lg"], c["market"]) == k]
            out["byMarketOver"][f"{k[0]}|{k[1]}"] = slate(pool, 12)[:12]
        # top 5 for every upcoming game (best play per player), shown when a game is opened in the app
        def per_game(pool):
            games = {}
            for c in sorted(pool, key=lambda c: -c["score"]):
                if dt.datetime.fromisoformat(c["t"]) <= now or c["score"] <= .05:
                    continue
                g = games.setdefault((c["lg"], c["t"], *sorted((c["team"], c["opp"]))), [])
                if len(g) < 5 and all(x["id"] != c["id"] for x in g):
                    g.append(c)
            return [c for g in games.values() for c in g]
        # the game views keep NBA (browsing, not the recorded Top 10) but still skip F grades and short prices
        out["games"] = per_game([c for c in full if c.get("grade") != "F" and not (c.get("price") is not None and c["price"] < MIN_PRICE)])
        out["gamesOver"] = per_game(ov)
    # anytime-TD picks: the research's TD calls (no sportsbook line in the feed), with Kalshi's price and his history
    tdp = []
    meta = data.get("NFL", {})
    cols = meta.get("cols", [])
    pls = {p["id"]: p for p in meta.get("players", [])}
    ups = [{"t": dt.datetime.fromisoformat(u[0]), "away": u[1], "home": u[2]} for u in meta.get("upcoming", [])]
    for k, n in notes.items():
        parts = k.split("|")
        if len(parts) != 3:  # soccer team-bet keys (SOCT|...) have more parts
            continue
        lg, pid, mid = parts
        if mid != "td" or lg != "NFL" or research_dir(n)[0] != "over" or research_dir(n)[1] < 1 or n.get("flag") == "out":
            continue
        p = pls.get(pid)
        game = p and next((u for u in sorted(ups, key=lambda u: u["t"]) if p["t"] in (u["away"], u["home"]) and u["t"] > now), None)
        if not game:
            continue
        gs = [dict(zip(cols, r)) for r in p["g"]]
        l10 = gs[-10:]
        lad = ((MKTS.get("NFL") or {}).get(pid) or {}).get("td")
        kal = market_prob(lad, .5, game["t"], now) if lad else None
        conf = {"low": .6, "medium": 1.0, "high": 1.2}.get(n.get("conf"), 1.0)
        home = game["home"] == p["t"]
        tdp.append({"key": k, "lg": "NFL", "id": pid, "name": p["n"], "team": p["t"], "pos": p.get("p"),
                    "opp": game["away"] if home else game["home"], "home": home, "t": game["t"].isoformat(),
                    "market": "td", "label": "Anytime TD", "side": "over", "line": .5,
                    "l10": [sum(1 for g in l10 if g["td"] > 0), len(l10)], "kalshi": round(kal, 3) if kal is not None else None,
                    "score": round(conf * float(n.get("adj") or 0) + (kal or 0), 3), "why": n.get("note", ""), "conf": n.get("conf")})
    out["tdPicks"] = sorted(tdp, key=lambda c: -c["score"])[:8]
    out["tdTop"], out["tdAll"] = td_board(data, ctx, MKTS, notes, CONF, now, ODDS)
    # pre-game TD chances for games now underway (kept from the last pre-game run), so the app's live TD tracker can
    # start from what was expected before kickoff and update it with the live box score
    try:
        prev = json.load(open(OUT))
        keep = {}
        for c in prev.get("tdLive", []) + prev.get("tdAll", []):
            t = dt.datetime.fromisoformat(c["t"])
            if t <= now and now - t < dt.timedelta(hours=6) and c["key"] + c["t"] not in keep:
                keep[c["key"] + c["t"]] = c
        out["tdLive"] = sorted(keep.values(), key=lambda c: -c["prob"])[:200]
    except Exception:
        out["tdLive"] = []
    # the research check's single best bet of the day
    BEST_BET_ON = False  # the research's best bet is off (Oct 26): its leans went 74-96 and best bets 3-5
    if BEST_BET_ON and best_note.get("key"):
        c = next((c for c in cands if c["key"] == best_note["key"]), None)
        # not when the markets lean the other way: the sportsbook's no-vig price or Kalshi's chance below the 52.4% a
        # -110 bet needs, or the line moved against it (Oct 19: Daniels over with Kalshi at 44%)
        mk = [x for x in (c.get("book_p"), c.get("mkt")) if x is not None] if c else []
        if c and dt.datetime.fromisoformat(c["t"]) > now and not c.get("moved_against") and all(x >= .5 for x in mk):
            out["best"] = dict(c, why_research=best_note.get("why", ""), sources=best_note.get("sources", []))
        elif c:
            print(f"best bet {c['name']} {c['market']} skipped: markets {mk}, moved against {c.get('moved_against')}")
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(out['picks'])} candidates")


if __name__ == "__main__":
    main()
