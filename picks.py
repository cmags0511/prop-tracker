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
  weather   wind at kickoff for outdoor football (backtested: passing overs suffer above ~15 mph)
  research  injuries, role, game plan and news from the daily research check (notes.json)
Weights come from a walk-forward backtest on 2025 NFL / 2025-26 NBA games (see README).
Players ruled out by the injury report or the research check are dropped.

Usage: python picks.py [picks.json]
"""
import json, math, re, sys, datetime as dt

OUT = sys.argv[1] if len(sys.argv) > 1 else "picks.json"
KEEP = 30  # the daily research check reviews these, then the app shows the best 10
# backtested weights (log-odds units): form, distance from line, matchup, implied team total, minutes trend
W = {"NFL": dict(p=1.16, z=1.62, mu=.075, tot=.066, mtr=0), "CFB": dict(p=1.16, z=1.62, mu=.075, tot=.066, mtr=0),
     "NBA": dict(p=2.33, z=.65, mu=.046, tot=0, mtr=.86)}
RESEARCH = {"support": .25, "caution": -.35, "neutral": 0}
OUT_STATUS = {"Out", "Doubtful", "Injured Reserve", "Suspension", "Physically Unable to Perform", "Not Active"}
SHAKY = {"Questionable", "Day-To-Day"}
VAC_W = .4      # NBA: log-odds per unit of team production vacated by ruled-out regulars (backtest coef ~.38)
WIND_W = -.25   # NFL/CFB passing props: log-odds per 5 mph of wind above 12 mph, capped at -.6
                # (backtest: no drop at 10-15 mph, passing overs ~39% vs ~49% above 15 mph)
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


def main():
    data = json.load(open("props_data.json"))
    try:
        notes = json.load(open("notes.json"))
        fresh = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(notes["updated"].replace("Z", "+00:00")) < dt.timedelta(hours=36)
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
    try:  # what the graded results have taught (tune.py): prop-type, factor and research-confidence weights
        TUNE = json.load(open("tuning.json"))
    except Exception:
        TUNE = {}
    FXM, MKM = TUNE.get("factors") or {}, TUNE.get("market") or {}
    CONF = {"low": .6, "medium": 1.0, "high": 1.2, **(TUNE.get("research_conf") or {})}
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
        recent_from = max(meta["curStart"], (now - dt.timedelta(days=12 if lg == "NBA" else 16)).date().isoformat())
        team_recent = {}
        for tm, pls in by_team.items():
            ds = sorted({d for pl in pls for g in pl["g"][-6:] if (d := dict(zip(cols, g))["date"]) >= recent_from})[-4:]
            team_recent[tm] = ds

        def vacated(pl, key):
            """share of his team's usual `key` production (last 4 games) held by regulars now ruled out"""
            ds = team_recent.get(pl["t"]) or []
            if len(ds) < 3 or key is None:
                return 0.0, []
            tot, gone, who = 0.0, 0.0, []
            for mate in by_team[pl["t"]]:
                gs = [dict(zip(cols, g)) for g in mate["g"][-6:]]
                gs = [g for g in gs if g["date"] in ds]
                v = sum(g[key] for g in gs) / len(ds)
                tot += v
                st = inj_of(mate)
                if mate is not pl and len(gs) >= 3 and st and st["s"] in OUT_STATUS and v > 0:
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
                    # a sportsbook quote straight from the book beats ESPN's copy: use its line and prices
                    dk = dict(dk, line=od["line"], u=od["t"], price_over=od.get("over"), price_under=od.get("under"),
                              books=od.get("books"), book=od.get("book"))
                if dk.get("d") and dt.datetime.fromisoformat(dk["d"].replace("Z", "+00:00")) < now - dt.timedelta(hours=5):
                    continue  # line for a game that's already been played
                vals = [stat(g, mid) for g in games]
                if len(vals) < (5 if lg == "CFB" else 8):
                    continue
                line = dk["line"]
                cur = [stat(g, mid) for g in games if g["date"] >= meta["curStart"]]
                # college rosters and roles change a lot between seasons: judge college form on this season alone
                l10 = cur[-10:] if lg == "CFB" and len(cur) >= 3 else vals[-10:]
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
                if lg == "NBA" and len(games) >= 8 and (now.date() - dt.date.fromisoformat(games[-1]["date"])).days <= 30:
                    mins = [g["min"] for g in games]
                    base15 = sum(mins[-15:]) / len(mins[-15:])
                    mtr = max(-.5, min(.5, (sum(mins[-3:]) / 3 - base15) / max(base15, 10)))
                note = notes.get(f"{lg}|{p['id']}|{mid}") or {}
                if not note:
                    # no research on this exact prop: borrow half of what was found on his other props
                    # (injuries to him or his teammates usually move all his props the same way)
                    other = [v for k, v in notes.items() if k.startswith(f"{lg}|{p['id']}|")]
                    if other:
                        a = sum(RESEARCH.get(v.get("flag"), 0) / .15 + float(v.get("adj") or 0) for v in other) / len(other)
                        note = {"adj": a * .5, "borrowed": True}
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
                news = (VAC_W * min(vac, .6) if lg == "NBA" else 0.0) - (.1 if me_inj and me_inj["s"] in SHAKY else 0.0)
                wind = (wx or {}).get("wind")
                weather = max(-.6, WIND_W * max(0.0, (wind - 12) / 5)) if (wind is not None and mid in PASS_M and not wx.get("indoor")) else 0.0
                parts = {"form": trust * (w["p"] * (p_over - .5) + w["z"] * zc), "matchup": w["mu"] * (mu["z"] if mu else 0),
                         "game": w["tot"] * tot, "minutes": w["mtr"] * mtr, "news": news, "weather": weather}
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
                        age_h = (now - dt.datetime.fromisoformat(dk["u"].replace("Z", "+00:00"))).total_seconds() / 3600
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
                # the researcher's confidence in the evidence scales how much the research moves the pick
                conf = CONF.get(note.get("conf"), 1.0) * FXM.get("research", 1)
                adj = conf * (RESEARCH.get(note.get("flag"), 0) + .15 * max(-2, min(2, float(note.get("adj") or 0))))
                # research is written for a side: the one it names ("side"), else the side the stats lean to
                r_side_over = note["side"] == "over" if note.get("side") in ("over", "under") else stats_over
                r_over = adj if r_side_over else -adj
                lin += r_over
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
                confirmed = exact.get("side") == side and float(exact.get("adj") or 0) >= 1
                # a line far from his numbers usually means the book knows something: keep it out of the Top lists
                # unless the research checked it and still backs this side
                if gap > .25 and not confirmed:
                    score *= .6
                # the fact-checker found a different line in current odds pages: this one is probably out of date
                line_off = exact.get("line_now") is not None and abs(float(exact["line_now"]) - line) >= max(1, .05 * line)
                if line_off:
                    score *= .7
                # rank props the research hasn't looked at a little lower than ones it has (when research is current)
                if notes and not exact and (game["t"] - now) < dt.timedelta(hours=60):
                    score *= .85
                parts["research"] = r_over
                slate.append({"key": f"{lg}|{p['id']}|{mid}", "lg": lg, "name": p["n"], "team": p["t"], "pos": p.get("p"),
                              "opp": opp, "t": game["t"].isoformat(), "market": mid, "label": LABEL[mid], "line": line,
                              "avg10": round(avg, 1), "l10_over": hits(l10), "n10": len(l10),
                              "matchup": f"{mu['rank']}/{mu['n']}" if mu else None, "gap": round(gap, 2),
                              "missed_last": missed, "lean": "over" if stats_over else "under", "score": round(score, 3),
                              "status": me_inj["s"] if me_inj else None, "teammates_out": vac_who[:3], "vacated": round(vac, 2),
                              "wind": wind, "rain": (wx or {}).get("rain"), "indoor": (wx or {}).get("indoor"),
                              "market_over": round(p_mkt, 3) if p_mkt is not None else None,
                              "depth": f"{me_dep['role']} ({me_dep['slot']})" if me_dep else None})
                if score <= .05 and not note.get("side"):
                    continue
                # never show a pick the research argues against
                if exact.get("side") in ("over", "under") and exact["side"] != side and float(exact.get("adj") or 0) >= 1:
                    continue
                if exact.get("side") == side and exact.get("flag") == "caution" and float(exact.get("adj") or 0) <= -2:
                    continue
                side_hits = lambda a: hits(a) if over else len(a) - hits(a)
                last = re.sub(r"\s+(Jr|Sr|II|III|IV|V)\.?$", "", p["n"]).split()[-1]
                why = (f"{last} has gone {'over' if over else 'under'} {fmt(line)} in {side_hits(l10)} of his last "
                       f"{len(l10)}")
                if len(cur) >= 2:
                    why += f" and {side_hits(cur)} of {len(cur)} this season"
                why += f", averaging {avg:.1f} {UNIT[mid]} over the last 10."
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
                if vac_who and vac >= .05 and lg == "NBA" and over:
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
                    "l10": [side_hits(l10), len(l10)], "avg10": round(avg, 1), "score": round(score, 3), "why": why,
                    "prob": round(prob if over else 1 - prob, 3),
                    "factors": {k: round(v if over else -v, 3) for k, v in parts.items()},
                    "gap": round(gap, 2),
                    "status": me_inj["s"] if me_inj else None, "lowline": lowline,
                    "researched": bool(exact), "price": price, "price_other": dk.get("price_under") if over else dk.get("price_over"),
                    "books": dk.get("books"), "break_even": round(be, 3) if be else None, "role": me_dep["role"] if me_dep else None, "slot": me_dep["slot"] if me_dep else None,
                    "moved_up": bool(me_dep and me_dep.get("moved_up")),
                    "age_h": round(age_h, 1) if age_h is not None else None, "moved": round(med, 1) if moved else None,
                    "mkt": round(p_mkt if over else 1 - p_mkt, 3) if p_mkt is not None else None,
                })
    slate.sort(key=lambda s: (s["t"], -s["score"]))
    json.dump({"built": now.isoformat(timespec="minutes"),
               "about": "Every prop with a DraftKings line on the upcoming slate. matchup = opponent's rank (1 = allows the most "
                        "to this position, last 10 games); gap = how far the line is from his recent average; lean = stats side.",
               "props": slate}, open("slate.json", "w"), indent=0)
    out = {"built": now.isoformat(timespec="minutes"), "picks": []}
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

        out["picks"] = slate([c for c in cands if c["score"] > .12], 14)  # 10 shown + spares for ruled-out players
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
        out["games"] = per_game(cands)
        out["gamesOver"] = per_game(ov)
    # anytime-TD picks: the research's TD calls (no sportsbook line in the feed), with Kalshi's price and his history
    tdp = []
    meta = data.get("NFL", {})
    cols = meta.get("cols", [])
    pls = {p["id"]: p for p in meta.get("players", [])}
    ups = [{"t": dt.datetime.fromisoformat(u[0]), "away": u[1], "home": u[2]} for u in meta.get("upcoming", [])]
    for k, n in notes.items():
        lg, pid, mid = k.split("|")
        if mid != "td" or lg != "NFL" or n.get("side") != "over" or float(n.get("adj") or 0) < 1 or n.get("flag") == "out":
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
    # the research check's single best bet of the day
    if best_note.get("key"):
        c = next((c for c in cands if c["key"] == best_note["key"]), None)
        if c and dt.datetime.fromisoformat(c["t"]) > now:
            out["best"] = dict(c, why_research=best_note.get("why", ""), sources=best_note.get("sources", []))
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(out['picks'])} candidates")


if __name__ == "__main__":
    main()
