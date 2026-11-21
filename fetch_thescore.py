"""theScore Bet's college player-prop prices, from The Odds API (bookmaker key "espnbet": theScore Bet, formerly ESPN Bet).

Why: theScore Bet is the only book that offers college player-prop UNDERS, and the unders are most of what the app picks
in college. Pinnacle's price is the usual grade price, but you can't bet it; this is the price you can.

It spends credits carefully (the free plan is 500 a month, shared with fetch_odds.py):
  * only college games with at least one under pick (slate.json: lean "under", score >= MIN_SCORE), kickoff within WINDOW_H hours,
  * one request per game, asking only for the prop types we have a pick on (1 credit per type that comes back; a game theScore
    doesn't carry returns nothing and costs nothing),
  * at most two looks per game: when it first enters the window, and once more within LATE_H hours of kickoff,
  * a run spends at most MAX_RUN credits, any rolling 7 days at most WEEK_CAP, and it stops when the month's remaining credits
    drop below RESERVE_DAY per day left in the month,
  * the lowest remaining-credit count is written back to oddsapi.json so fetch_odds.py (which spends what is left) sees it.

Needs the ODDS_API_KEY environment variable (a GitHub Actions secret). Without it, it does nothing.
Output: thescore.json {"fetched", "remaining", "spent": [[iso, credits], ...], "tried": {game: [iso, ...]}, "log": [...],
"props": {"<app key>": {"line", "over", "under", "book": "theScore Bet", "t", "game_t"}}}. picks.py grades a college prop at
this price when it has one.

Usage: python fetch_thescore.py [thescore.json]
"""
import json, os, sys, datetime as dt, calendar
import urllib.request, urllib.parse
from fetch_odds import norm, find_event, MARKET

OUT = sys.argv[1] if len(sys.argv) > 1 else "thescore.json"
KEY = os.environ.get("ODDS_API_KEY", "").strip()
API = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_ncaaf"
BOOK = "espnbet"
BOOK_NAME = "theScore Bet"
WINDOW_H, LATE_H, MIN_SCORE = 30, 3.5, .12
MAX_RUN, WEEK_CAP, RESERVE_DAY = 12, 40, 2
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


def main_line(over_under):
    """{point: {Over: price, Under: price}} -> (point, over, under) for the point whose two prices are closest (the main line)"""
    best = None
    for pt, s in over_under.items():
        if "Over" in s and "Under" in s:
            gap = abs(abs(s["Over"]) - abs(s["Under"])) if (s["Over"] < 0) == (s["Under"] < 0) else abs(s["Over"] + s["Under"])
            if best is None or gap < best[0]:
                best = (gap, pt, s["Over"], s["Under"])
    return best[1:] if best else None


def wanted(slate, now):
    """{(team, opp, kickoff): {market: [prop, ...]}}: college props the app leans under on, kickoff inside the window"""
    out = {}
    for c in slate.get("props", []):
        if c["lg"] != "CFB" or c["market"] not in MARKET or c.get("lean") != "under" or (c.get("score") or 0) < MIN_SCORE:
            continue
        t = dt.datetime.fromisoformat(c["t"])
        if not dt.timedelta(0) < t - now < dt.timedelta(hours=WINDOW_H):
            continue
        a, b = sorted((c["team"], c["opp"]))
        out.setdefault((a, b, c["t"]), {}).setdefault(c["market"], []).append(c)
    return out


def due(tk, tried, kick, now):
    """a game gets one look when it enters the window and one more close to kickoff"""
    looks = [dt.datetime.fromisoformat(x) for x in tried.get(tk, [])]
    if not looks:
        return True
    return len(looks) < 2 and kick - now <= dt.timedelta(hours=LATE_H) and now - looks[-1] >= dt.timedelta(hours=2)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    if not KEY:
        print("no ODDS_API_KEY set; skipping")
        return
    try:
        o = json.load(open(OUT))
    except Exception:
        o = {}
    global remaining
    remaining = o.get("remaining")
    props = {k: v for k, v in (o.get("props") or {}).items() if dt.datetime.fromisoformat(v["game_t"]) > now}
    tried = {k: [x for x in v if now - dt.datetime.fromisoformat(x) < dt.timedelta(hours=72)] for k, v in (o.get("tried") or {}).items()}
    tried = {k: v for k, v in tried.items() if v}
    spent_log = [s for s in (o.get("spent") or []) if now - dt.datetime.fromisoformat(s[0]) < dt.timedelta(days=7)]
    try:
        slate = json.load(open("slate.json"))
    except Exception:
        print("no slate.json yet")
        return
    want = wanted(slate, now)
    order = sorted(want.items(), key=lambda kv: -sum(c.get("score") or 0 for cs in kv[1].values() for c in cs))
    log, spent, events = [], 0, None
    days_left = calendar.monthrange(now.year, now.month)[1] - now.day + 1
    for (a, b, t), mk in order:
        kick = dt.datetime.fromisoformat(t)
        tk = f"CFB|{a}|{b}|{t}"
        if not due(tk, tried, kick, now):
            continue
        cost = len(mk)
        week = sum(s[1] for s in spent_log) + spent
        if spent + cost > MAX_RUN:
            log.append(f"run cap reached ({MAX_RUN} credits)")
            break
        if week + cost > WEEK_CAP:
            log.append(f"stopped: {week:.0f} credits used in the last 7 days (cap {WEEK_CAP})")
            break
        if remaining is not None and remaining - cost < RESERVE_DAY * (days_left - 1):
            log.append(f"stopped: {remaining:.0f} credits left with {days_left} days to go")
            break
        if events is None:
            try:  # the events list is free
                events = get(f"/sports/{SPORT}/events")
            except Exception as e:
                print(f"events failed: {e}")
                return
        ev = find_event("CFB", a, b, kick, events)
        if not ev:
            log.append(f"CFB {a}/{b}: no single matching event")
            continue
        try:
            d = get(f"/sports/{SPORT}/events/{ev['id']}/odds", bookmakers=BOOK, oddsFormat="american",
                    markets=",".join(MARKET[m] for m in mk))
        except Exception as e:
            log.append(f"CFB {a}/{b} odds failed: {e}")
            continue
        tried.setdefault(tk, []).append(now.isoformat(timespec="minutes"))
        filled, used = 0, set()
        for bk in d.get("bookmakers", []):
            if bk.get("key") != BOOK:
                continue
            for m, cs in mk.items():
                mm = next((x for x in bk.get("markets", []) if x.get("key") == MARKET[m]), None)
                if not mm:
                    continue
                used.add(m)
                for c in cs:
                    ladder = {}
                    for x in mm.get("outcomes", []):
                        if norm(x.get("description", "")) == norm(c["name"]) and x.get("point") is not None:
                            ladder.setdefault(x["point"], {})[x.get("name")] = x.get("price")
                    ml = main_line(ladder)
                    if ml:
                        props[c["key"]] = {"line": ml[0], "over": ml[1], "under": ml[2], "book": BOOK_NAME,
                                           "t": now.isoformat(timespec="minutes"), "game_t": t}
                        filled += 1
        credits = len(used)  # empty responses and markets theScore doesn't carry aren't charged
        spent += credits
        if credits:
            spent_log.append([now.isoformat(timespec="minutes"), credits])
        n = sum(len(cs) for cs in mk.values())
        log.append(f"CFB {a}/{b}: {filled}/{n} priced at theScore Bet, {credits} credits")
    json.dump({"fetched": now.isoformat(timespec="minutes"), "remaining": remaining, "source": "The Odds API (theScore Bet)",
               "spent": spent_log, "tried": tried, "log": log[-40:], "props": props}, open(OUT, "w"), separators=(",", ":"))
    if remaining is not None:  # let fetch_odds.py see the credits this run used
        try:
            oa = json.load(open("oddsapi.json"))
            if oa.get("remaining") is None or remaining < oa["remaining"]:
                oa["remaining"] = remaining
                json.dump(oa, open("oddsapi.json", "w"), separators=(",", ":"))
        except Exception:
            pass
    print("\n".join(log) or "nothing to price")


if __name__ == "__main__":
    main()
