"""Sportsbook prices for player props from Pinnacle's and FanDuel's public odds feeds, into odds.json.

ESPN's free DraftKings feed has lines but no prices, so the record had to assume -110 on every pick. Both books'
websites read their odds from public APIs (no account, no credits):
  Pinnacle  one request lists every prop for a league and one more returns the over and under prices. The
            sharpest book, so its prices are a fair read of what a prop is really worth (they can be a little
            better than DraftKings' own). NFL, NBA and college.
  FanDuel   one request per game and prop tab. Fills what Pinnacle doesn't list (rush + rec yards, kicking points)
            or lists at a different line. NFL and college.

A price is only kept for the line the app shows (DraftKings', or for college the line the research found), because
picks.py takes the line from odds.json: a book's line that differs would quietly replace DraftKings'. When the
book's line differs (common on yardage props: usually by 1-2 yards), its price is moved to the app's line with a
normal model of the stat (`shift`) and marked estimated; lines too far apart go unpriced. For each prop the first
of these wins: Pinnacle at the same line, FanDuel at the same line, Pinnacle moved, FanDuel moved.
Kicking points: FanDuel only prices team ladders ("JAX 7+ / 10+ / 12+ / 15+ total kicking points", yes only), so
the over is read off the ladder (`ladder`) and the under is worked out from it: both marked estimated unless the
line sits on a rung, when the over is FanDuel's own price. Anytime TDs have no line to check: Pinnacle's "over 0.5
touchdowns", else FanDuel's anytime scorer price.

Like ESPN's feed, these APIs aren't documented and can change; if every fetch fails, the existing odds.json is kept.
Output: the same odds.json fetch_odds.py writes {"fetched", "source", "props": {"<app key>": {"line", "over",
"under", "est_over", "est_under", "book", "books": {"<book>": {...}}, "t", "game_t"}}}

Usage: python fetch_prices.py [odds.json]
"""
import json, math, re, sys, datetime as dt
from statistics import NormalDist
import urllib.request
from fetch_odds import norm, TEAM

OUT = sys.argv[1] if len(sys.argv) > 1 else "odds.json"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_KEY = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"  # the public guest key pinnacle.com's own pages send
PIN_LEAGUE = {"NFL": 889, "NBA": 487, "CFB": 880}
FD = "https://sbapi.nj.sportsbook.fanduel.com/api"
FD_KEY = "FhMFpcPWXMeyZxOx"  # the public app key sportsbook.fanduel.com's own pages send
FD_PAGE = {"NFL": "nfl", "CFB": "ncaaf"}
FD_TABS = ("passing-props", "rushing-props", "receiving-props", "td-scorer-props", "game-specials")
# Pinnacle's prop names ("Derrick Henry Total Rushing Yards") and FanDuel's ("Woody Marks - Rushing + Receiving Yds")
# -> the app's prop id
PIN_MARKET = {"Passing Yards": "pyd", "Pass Completions": "cmp", "Pass Attempts": "att", "Touchdown Passes": "ptd",
              "Rushing Yards": "ryd", "Rush Attempts": "car", "Receptions": "rec", "Receiving Yards": "recyd",
              "Field Goals": "fgm", "Touchdowns": "td", "Points": "pts", "Rebounds": "reb", "Assists": "ast",
              "Threes Made": "3pm", "Pts & Rebs & Asts": "pra", "Pts & Rebs": "pr", "Pts & Asts": "pa", "Rebs & Asts": "ra"}
FD_MARKET = {"Passing Yds": "pyd", "Passing TDs": "ptd", "Pass Completions": "cmp", "Pass Attempts": "att",
             "Rushing Yds": "ryd", "Rushing Attempts": "car", "Receiving Yds": "recyd", "Total Receptions": "rec",
             "Rushing + Receiving Yds": "rry"}
SAME_GAME = dt.timedelta(hours=2)  # the book's start time vs the app's, to tell games (and namesakes) apart
# a player's game-to-game spread as a share of his line (median over the slate's NFL players, last 16 games), used to
# move a book's price to DraftKings' line when the two differ: e.g. passing yards spread about 27% of the line,
# so 2 yards on a 230 line barely moves the price, while 2 receiving yards on a 40 line moves it a few cents
SPREAD = {"pyd": .27, "cmp": .27, "att": .25, "car": .35, "ryd": .73, "rec": .59, "recyd": .82, "rry": .6, "ptd": .7,
          "fgm": .6, "pts": .3, "reb": .4, "ast": .5, "3pm": .7, "pra": .25, "pr": .28, "pa": .3, "ra": .35}
MAX_SHIFT = .35  # in spreads: past this the lines are too far apart to call it the same bet
HOLD = 1.045     # a typical two-way margin (-110 / -110 is 1.048), to work out an under from a yes-only price
ND = NormalDist()


def imp(a):
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def american(p):
    return round(-100 * p / (1 - p)) if p >= .5 else round(100 * (1 - p) / p)


def shift(line, over, under, to, mid):
    """a book's over / under prices at `line`, moved to the line `to` (normal model, the book's margin kept);
    None when the lines are too far apart"""
    sd = SPREAD.get(mid, .5) * max(to, line, 1)
    if abs(to - line) > MAX_SHIFT * sd:
        return None
    io, iu = imp(over), imp(under)
    p = ND.cdf(ND.inv_cdf(io / (io + iu)) - (to - line) / sd)  # fair chance of the over at the new line
    p = min(max(p, .02), .98)
    return american(p * (io + iu)), american((1 - p) * (io + iu))


def ladder(rungs, line):
    """over / under at `line` from yes-only prices for "k+" ({k: price}): the over's implied chance is read between
    the rungs either side (log-odds, straight line), or past the end rung by up to 1.5 points; None otherwise"""
    need = line + .5
    ks = sorted(rungs)
    lo = max((k for k in ks if k <= need), default=None)
    hi = min((k for k in ks if k >= need), default=None)
    if lo is None or hi is None:
        if len(ks) < 2 or not (ks[0] - 1.5 <= need <= ks[-1] + 1.5):
            return None
        lo, hi = (ks[0], ks[1]) if need < ks[0] else (ks[-2], ks[-1])
    lg = lambda k: math.log(imp(rungs[k]) / (1 - imp(rungs[k])))
    x = lg(lo) if lo == hi else lg(lo) + (lg(hi) - lg(lo)) * (need - lo) / (hi - lo)
    q = min(max(1 / (1 + math.exp(-x)), .03), .97)  # the over's implied chance, margin included
    return (rungs[need] if need in rungs else american(q)), american(min(max((1 - q / HOLD) * HOLD, .03), .97))


def get(url, **headers):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0",
                                               "Accept": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def pinnacle(lg, now):
    """[(player name, prop id, start, line, over, under)] for every pre-game Pinnacle prop"""
    head = {"X-API-Key": PIN_KEY}
    matchups = get(f"{PIN}/leagues/{PIN_LEAGUE[lg]}/matchups", **head)
    markets = get(f"{PIN}/leagues/{PIN_LEAGUE[lg]}/markets/straight", **head)
    price = {m["matchupId"]: m for m in markets
             if m.get("key") == "s;0;ou" and not m.get("isAlternate") and len(m.get("prices") or []) == 2}
    out = []
    for mu in matchups:
        sp = mu.get("special") or {}
        if sp.get("category") != "Player Props" or mu.get("isLive") or mu["id"] not in price:
            continue
        name, _, what = sp.get("description", "").rpartition(" Total ")
        start = dt.datetime.fromisoformat((mu.get("parent") or mu)["startTime"].replace("Z", "+00:00"))
        side = {pt["id"]: pt["name"] for pt in mu.get("participants", [])}
        q = {side.get(x["participantId"]): x for x in price[mu["id"]]["prices"]}
        if PIN_MARKET.get(what) and start > now and "Over" in q and "Under" in q:
            out.append((name, PIN_MARKET[what], start, q["Over"].get("points"), q["Over"]["price"], q["Under"]["price"]))
    return out


def fanduel(lg, now, games):
    """FanDuel props for the games in `games` (kickoff times the app still needs prices for):
    ([(player name, prop id, start, line, over, under)], {(team nickname, start): {k: yes price for k+ kicking points}})"""
    page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId={FD_PAGE[lg]}&_ak={FD_KEY}&timezone=America%2FNew_York")
    out, kick = [], {}
    for ev in (page.get("attachments") or {}).get("events", {}).values():
        start = dt.datetime.fromisoformat(ev["openDate"].replace("Z", "+00:00"))
        if " @ " not in ev["name"] or start <= now or not any(abs(t - start) < SAME_GAME for t in games):
            continue
        for tab in FD_TABS:
            try:
                d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}&tab={tab}")
            except Exception as e:
                print(f"FanDuel {ev['name']} {tab}: {e}")
                continue
            for m in (d.get("attachments") or {}).get("markets", {}).values():
                odds = lambda r: ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")
                name, _, what = m.get("marketName", "").partition(" - ")
                if what in FD_MARKET and len(m.get("runners") or []) == 2:
                    o = next((r for r in m["runners"] if r["runnerName"].endswith(" Over")), None)
                    u = next((r for r in m["runners"] if r["runnerName"].endswith(" Under")), None)
                    if o and u and odds(o) and odds(u) and o.get("handicap") == u.get("handicap"):
                        out.append((name, FD_MARKET[what], start, o["handicap"], odds(o), odds(u)))
                elif m.get("marketName") == "Any Time Touchdown Scorer":
                    out += [(r["runnerName"], "td", start, .5, odds(r), None) for r in m.get("runners") or [] if odds(r)]
                elif m.get("marketName") == "Game Specials - Kicking":
                    for r in m.get("runners") or []:
                        x = re.match(r"\S+ (.+) (\d+)\+ Total Kicking Points$", r["runnerName"])
                        if x and odds(r):
                            kick.setdefault((x.group(1), start), {})[int(x.group(2))] = odds(r)
    return out, kick


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        lines = json.load(open("lines.json"))
    except Exception:
        lines = {}
    data = json.load(open("props_data.json"))
    try:
        data["CFB"] = json.load(open("cfb_data.json"))
    except Exception:
        pass
    try:  # college lines come from the research (published previews), not the DraftKings feed
        notes = json.load(open("notes.json"))
        for k, v in (notes.get("cfb_lines") or {}).items():
            _, pid, mid = k.split("|")
            lines.setdefault("CFB", {}).setdefault(pid, {}).setdefault(mid, {"line": v["line"], "d": v["t"]})
    except Exception:
        pass
    props, tried, failed = {}, 0, 0
    for lg in ("NFL", "NBA", "CFB"):
        meta = data.get(lg)
        if not meta:
            continue
        # each team's upcoming kickoffs, and every player by name
        kick = {}
        for u in meta.get("upcoming", []):
            t = dt.datetime.fromisoformat(u[0])
            for tm in (u[1], u[2]):
                kick.setdefault(tm, []).append(t)
        by_name = {}
        for p in meta["players"]:
            by_name.setdefault(norm(p["n"]), []).append(p)
        L = lines.get(lg) or {}
        best = {}  # app key -> (rank, quote, start); lower rank wins

        def offer(book, name, mid, start, line, over, under, rank):
            who = [p for p in by_name.get(norm(name), []) if any(abs(t - start) < SAME_GAME for t in kick.get(p["t"], []))]
            if len(who) != 1 or over is None:
                return
            p = who[0]
            quote = {"line": line, "over": over, "under": under, "est_over": False, "est_under": under is None}
            if mid == "td":
                if line != .5 or lg != "NFL":  # the app's TD model is NFL only
                    return
            else:
                dk = L.get(str(p.get("e") or p["id"]), {}).get(mid)
                if not dk or under is None:
                    return
                if dk["line"] != line:  # price DraftKings' line, never move the app off it
                    moved = shift(line, over, under, dk["line"], mid)
                    if not moved:
                        return
                    quote = {"line": dk["line"], "over": moved[0], "under": moved[1], "est_over": True,
                             "est_under": True, "from": [line, over, under]}
                    rank += 2
            key = f"{lg}|{p['id']}|{mid}"
            if key not in best or rank < best[key][0]:
                best[key] = (rank, dict(quote, book=book), start)

        try:
            tried += 1
            for row in pinnacle(lg, now):
                offer("Pinnacle", *row, rank=0)
        except Exception as e:
            print(f"{lg} Pinnacle failed: {e}")
            failed += 1
        if lg in FD_PAGE:
            # only the games with a line Pinnacle left unpriced or only estimated (one request per game and tab)
            gaps = set()
            espn = {str(p.get("e") or p["id"]): p for p in meta["players"]}
            for pid, mk in L.items():
                p = espn.get(pid)
                if not p:
                    continue
                for mid in mk:
                    b = best.get(f"{lg}|{p['id']}|{mid}")
                    if not b or b[0] > 0:
                        gaps.update(t for t in kick.get(p["t"], []) if t > now)
            if lg == "NFL":  # anytime TDs have no DraftKings line: check every game's scorers
                gaps.update(t for ts in kick.values() for t in ts if t > now)
            try:
                tried += 1
                rows, ladders = fanduel(lg, now, gaps) if gaps else ([], {})
                for row in rows:
                    offer("FanDuel", *row, rank=1)
                nick = {TEAM.get(lg, {}).get(tm, "").split(" ")[-1]: tm for tm in kick}
                for (nk, start), rungs in ladders.items():
                    tm = nick.get(nk)
                    for p in (pl for pl in meta["players"] if pl["t"] == tm):
                        dk = L.get(str(p.get("e") or p["id"]), {}).get("kpts")
                        got = dk and ladder(rungs, dk["line"])
                        if got:
                            on = dk["line"] + .5 in rungs
                            key = f"{lg}|{p['id']}|kpts"
                            best[key] = (1 if on else 3, {"line": dk["line"], "over": got[0], "under": got[1],
                                                          "est_over": not on, "est_under": True, "book": "FanDuel"}, start)
            except Exception as e:
                print(f"{lg} FanDuel failed: {e}")
                failed += 1
        for key, (rank, quote, start) in best.items():
            book = quote.pop("book")
            props[key] = dict(quote, book=book, books={book: {k: quote[k] for k in ("line", "over", "under")}},
                              t=now.isoformat(timespec="minutes"), game_t=start.isoformat())
        n = {b: sum(1 for k in best if props[k]["book"] == b) for b in ("Pinnacle", "FanDuel")}
        est = sum(1 for k in best if props[k]["est_over"])
        print(f"{lg}: {len(best)} props priced (Pinnacle {n['Pinnacle']}, FanDuel {n['FanDuel']}; {est} estimated)")
    # a source that failed goes unpriced until the next run rather than keeping old quotes: picks.py takes the line
    # from odds.json, so a stale one could override a DraftKings line that has since moved. record.py keeps the
    # last price it saw for a pick whose line hasn't changed.
    if tried and failed == tried:
        print(f"every fetch failed; keeping {OUT}")
        return
    json.dump({"fetched": now.isoformat(timespec="minutes"), "source": "Pinnacle, FanDuel", "props": props},
              open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(props)} priced props")


if __name__ == "__main__":
    main()
