"""Sportsbook prices for the props nothing else prices, from SportsGameOdds' free plan (sportsgameodds.com).

Pinnacle and FanDuel (fetch_prices.py), FanDuel's board (lab_market.py) and The Odds API (fetch_odds.py) price most props, but
leave gaps: kicking props, some college receiving/rushing props, some NBA combos. picks.py takes SportsGameOdds' price ONLY for
a prop that has no price from any of those, and only at the line the app shows (a different line is moved to it by
fetch_prices.shift and marked estimated, like FanDuel's). The free plan is 2,500 "objects" a month, one object per game
returned, so this spends them carefully:
  * it only looks at games kicking off within WINDOW_H hours that have at least one unpriced prop (slate.json);
  * a league is fetched at most every REFRESH_H hours, for no more games than are needed (plus a small margin);
  * it stops at MONTH_CAP objects a month, and spreads them over the days left.
Needs the SGO_API_KEY environment variable (a GitHub Actions secret); without it, nothing happens.
Output: sgo.json {"fetched", "usage": {"YYYY-MM": objects}, "last": {league: time}, "props": {"<app key>": {"line", "over",
"under", "book", "books": {...}, "t", "game_t"}}}

Usage: python fetch_sgo.py [sgo.json]
"""
import json, os, sys, datetime as dt, calendar
import urllib.request, urllib.parse, urllib.error
from fetch_odds import norm

OUT = sys.argv[1] if len(sys.argv) > 1 else "sgo.json"
KEY = os.environ.get("SGO_API_KEY", "").strip()
BASE = "https://api.sportsgameodds.com/v2"
WINDOW_H = 30
REFRESH_H = float(os.environ.get("SGO_REFRESH_H") or 6)
MONTH_CAP = 2200
LEAGUE = {"NFL": "NFL", "NBA": "NBA", "CFB": "NCAAF"}
STAT = {"NFL": {"passing_yards": "pyd", "passing_attempts": "att", "passing_completions": "cmp", "passing_touchdowns": "ptd",
                "rushing_yards": "ryd", "rushing_attempts": "car", "receiving_yards": "recyd", "receiving_receptions": "rec",
                "rushing+receiving_yards": "rry", "kicking_totalPoints": "kpts", "fieldGoals_made": "fgm", "extraPoints_kicksMade": "pat"},
        "NBA": {"points": "pts", "rebounds": "reb", "assists": "ast", "threePointersMade": "3pm", "points+rebounds+assists": "pra",
                "points+rebounds": "pr", "points+assists": "pa", "rebounds+assists": "ra"}}
STAT["CFB"] = STAT["NFL"]
BOOKS = ["draftkings", "fanduel", "caesars", "betmgm", "espnbet", "bovada"]   # preference order
BOOK_NAME = {"draftkings": "DraftKings", "fanduel": "FanDuel", "caesars": "Caesars", "betmgm": "BetMGM", "espnbet": "ESPN BET", "bovada": "Bovada"}


def get(path, **params):
    req = urllib.request.Request(f"{BASE}{path}?{urllib.parse.urlencode(params)}",
                                 headers={"x-api-key": KEY, "Accept": "application/json", "User-Agent": "prop-tracker"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def american(x):
    try:
        return int(str(x).replace("+", ""))
    except (TypeError, ValueError):
        return None


def player_name(ent):
    """'MICHAEL_PENIX_JR_1_NFL' -> 'michael penix' (norm drops Jr/Sr/II)"""
    parts = ent.split("_")
    if len(parts) >= 3 and parts[-2].isdigit():
        parts = parts[:-2]
    return norm(" ".join(parts))


LOG = []
_print = print


def print(*a, **k):
    LOG.append(" ".join(str(x) for x in a)[:240])
    _print(*a, **k)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat(timespec="minutes")
    if not KEY:
        print("no SGO_API_KEY set; skipping")
        return
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    props = {k: v for k, v in (old.get("props") or {}).items() if dt.datetime.fromisoformat(v["game_t"]) > now}
    usage, last = dict(old.get("usage") or {}), dict(old.get("last") or {})
    month = now.strftime("%Y-%m")
    used = usage.get(month, 0)
    days_left = calendar.monthrange(now.year, now.month)[1] - now.day + 1
    slate = json.load(open("slate.json")).get("props", [])
    # props no other source prices (ESPN's feed prices, Pinnacle, FanDuel and The Odds API all land in slate po/pu), plus the
    # ones this file already prices (their slate row now carries our price, so they stay ours until the game starts)
    need = []
    for s in slate:
        t = dt.datetime.fromisoformat(s["t"])
        if not (now < t < now + dt.timedelta(hours=WINDOW_H)) or s["lg"] not in LEAGUE or s["market"] not in STAT[s["lg"]].values():
            continue
        if (s.get("po") is None and s.get("pu") is None) or s["key"] in props:
            need.append(s)
    print(f"{len(need)} props in the next {WINDOW_H}h without another source's price, {sum(1 for s in need if s['key'] in props)} already ours; "
          f"{used} of {MONTH_CAP} objects used this month")
    for lg in ("NFL", "NBA", "CFB"):
        rows = [s for s in need if s["lg"] == lg and s["key"] not in props]
        if not rows:
            continue
        if last.get(lg) and now - dt.datetime.fromisoformat(last[lg]) < dt.timedelta(hours=REFRESH_H):
            print(f"{lg}: fetched {last[lg]}, waiting")
            continue
        games = len({(s["team"], s["opp"], s["t"]) for s in rows}) // 1
        lim = min(40, games + 3)
        if used + lim > MONTH_CAP or used + lim > MONTH_CAP * (1 - (days_left - 1) / calendar.monthrange(now.year, now.month)[1]) + 120:
            print(f"{lg}: skipping, {used} objects used with {days_left} days left")
            continue
        start, end = now - dt.timedelta(hours=1), now + dt.timedelta(hours=WINDOW_H)
        try:
            d = get("/events", leagueID=LEAGUE[lg], oddsAvailable="true", finalized="false", limit=lim,
                    startsAfter=start.strftime("%Y-%m-%dT%H:%M:%SZ"), startsBefore=end.strftime("%Y-%m-%dT%H:%M:%SZ"))
        except urllib.error.HTTPError as e:
            print(f"{lg}: HTTP {e.code} {e.read().decode()[:200]}")
            continue
        except Exception as e:
            print(f"{lg}: failed {str(e)[:100]}")
            continue
        if not d.get("success", True):
            print(f"{lg}: {str(d.get('error'))[:200]}")
            continue
        evs = d.get("data") or []
        used += len(evs); last[lg] = stamp
        print(f"{lg}: {len(evs)} games returned for {len(rows)} unpriced props ({d.get('notice') or ''})"[:200])
        want = {}
        for s in rows:
            want.setdefault((norm(s["name"]), s["market"]), []).append(s)
        got = 0
        alltable = {}
        for ev in evs:
            try:
                ev_t = dt.datetime.fromisoformat(((ev.get("status") or {}).get("startsAt") or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            table = {}      # (player, market) -> book -> {over, under, line}
            for oid, o in (ev.get("odds") or {}).items():
                ent = o.get("statEntityID")
                m = STAT[lg].get(o.get("statID"))
                if not m or o.get("betTypeID") != "ou" or o.get("periodID") != "game" or ent in (None, "all", "home", "away"):
                    continue
                side = o.get("sideID")
                for b, v in (o.get("byBookmaker") or {}).items():
                    if v.get("available", True) is False or b not in BOOKS:
                        continue
                    px, ln = american(v.get("odds")), v.get("overUnder")
                    try:
                        ln = float(ln)
                    except (TypeError, ValueError):
                        continue
                    if px is None or side not in ("over", "under"):
                        continue
                    q = table.setdefault((player_name(ent), m), {}).setdefault(b, {"line": ln})
                    if q["line"] == ln:
                        q[side] = px
            alltable.update(table)
            for (nm, m), books in table.items():
                for s in want.get((nm, m), []):
                    if abs((dt.datetime.fromisoformat(s["t"]) - ev_t).total_seconds()) > 3 * 3600 or s["key"] in props:
                        continue
                    ok = {b: q for b, q in books.items() if "over" in q and "under" in q}
                    if not ok:
                        continue
                    # the book at the app's own line first, then the preferred book
                    best = next((b for b in BOOKS if b in ok and ok[b]["line"] == s["line"]), None) or next(b for b in BOOKS if b in ok)
                    q = ok[best]
                    props[s["key"]] = {"line": q["line"], "over": q["over"], "under": q["under"], "book": BOOK_NAME[best],
                                       "books": {BOOK_NAME[b]: {k: v for k, v in x.items()} for b, x in ok.items()}, "t": stamp, "game_t": s["t"]}
                    got += 1
        seen_names = {n for (n, _m) in alltable}
        want_names = {n for (n, _m) in want}
        print(f"{lg}: priced {got} of {len(rows)} props; SGO listed {len(seen_names)} players (any prop), {len(want_names & seen_names)} of our {len(want_names)} unpriced players among them")
        miss = sorted(want_names - seen_names)[:4]
        print(f"{lg}: not found e.g. {miss}; SGO has e.g. {sorted(seen_names)[:4]}")
        wm = [(n, m) for (n, m) in want if n in seen_names and (n, m) not in alltable][:4]
        print(f"{lg}: player listed but not that prop e.g. {wm}")
    usage[month] = used
    json.dump({"fetched": stamp, "usage": usage, "last": last, "log": LOG[-14:], "props": props}, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(props)} props, {used} objects used in {month}")


if __name__ == "__main__":
    main()
