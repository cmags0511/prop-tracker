"""Last-resort prices for college and NFL props nothing else prices, from OddsPapi's free plan (oddspapi.io).

Free plan: 250 requests a month. One /odds request returns a whole game (every market, every book you ask for), so the
cost is per GAME, not per prop type. This only asks about games that still have unpriced props after Pinnacle, FanDuel,
ESPN's DraftKings feed and The Odds API, and only for DraftKings, FanDuel, BetMGM and Pinnacle quotes:
  * slate.json shows which props have no price (po / pu empty); games within 30 hours with at least 2 of them,
  * at most MAX_RUN game requests a run (plus 1 for the fixture list), never the same game again for 12 hours,
  * it keeps RESERVE_DAY requests per remaining day of the month,
  * oddspapi_markets.json is a small table of the player-prop markets (id -> type, line, Over / Under outcome ids), built
    once from the 19 MB /markets catalogue (python fetch_oddspapi.py --markets) and refreshed every 30 days.

Needs the ODDSPAPI_KEY environment variable (a GitHub Actions secret). Without it, it does nothing.
Output: oddspapi_prices.json {"fetched", "usage": {"YYYY-MM": requests}, "tried": {...}, "log": [...], "props": {"<app key>":
{"line", "over", "under", "book", "books", "t", "game_t"}}}. picks.py uses it only when nothing else prices the prop.

Usage: python fetch_oddspapi.py [oddspapi_prices.json]      |      python fetch_oddspapi.py --markets
"""
import json, os, re, sys, time, datetime as dt, calendar
import urllib.request, urllib.parse, urllib.error
from fetch_odds import norm, cfb_fits
from fetch_sgo import same_player

MODE_MARKETS = "--markets" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = args[0] if args else "oddspapi_prices.json"
TABLE = "oddspapi_markets.json"
KEY = os.environ.get("ODDSPAPI_KEY", "").strip()
API = "https://api.oddspapi.io/v4"
SPORT_ID = 14                                       # American football (NFL, NCAA, CFL...)
TOURNAMENT = {27653: "CFB", 31: "NFL"}              # NCAA regular season, NFL
BOOKS = ["draftkings", "fanduel", "betmgm", "pinnacle"]
BOOKNAME = {"draftkings": "DraftKings", "fanduel": "FanDuel", "betmgm": "BetMGM", "pinnacle": "Pinnacle"}
# OddsPapi marketType -> app market id
TYPE = {"playertotals-passyards": "pyd", "playertotals-passattempts": "att", "playertotals-passcompletions": "cmp",
        "playertotals-rushyards": "ryd", "playertotals-rushattempts": "car", "playertotals-receptions": "rec",
        "playertotals-receivingyards": "recyd", "playertotals-rushrec": "rry", "playertotals-sacks": "sck", "playertotals-tacass": "tkl",
        "playertotals-kickingpoints": "kpts", "playertotals-fieldgoals": "fgm", "playertotals-extrapoints": "pat"}
WINDOW_H, MAX_RUN, RESERVE_DAY, MIN_PROPS, REFRESH_H = 30, 10, 4, 2, 12
usage_now = 0


def get(path, **q):
    global usage_now
    q["apiKey"] = KEY
    url = f"{API}{path}?{urllib.parse.urlencode(q)}"
    for attempt in range(3):
        try:
            usage_now += 1
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "prop-tracker", "Accept": "application/json"}), timeout=90) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                usage_now -= 1
                try:
                    wait = json.loads(e.read())["error"]["retryMs"] / 1000
                except Exception:
                    wait = 1
                time.sleep(min(wait + .3, 10))
                continue
            raise


def build_table():
    cat = get("/markets")
    t = {}
    for m in cat:
        typ = m.get("marketType")
        if m.get("sportId") != SPORT_ID or not m.get("playerProp") or typ not in TYPE:
            continue
        out = {o["outcomeName"].lower(): o["outcomeId"] for o in m.get("outcomes", [])}
        if "over" in out and "under" in out:
            t[str(m["marketId"])] = [TYPE[typ], m.get("handicap"), out["over"], out["under"]]
    seen = sorted({m.get("marketType") for m in cat if m.get("sportId") == SPORT_ID and m.get("playerProp")})
    print("player-prop market types for American football:", seen)
    json.dump({"built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "markets": t}, open(TABLE, "w"), separators=(",", ":"))
    print(f"wrote {TABLE}: {len(t)} markets")
    return t


def abbr_fits(ab, name):
    n = re.sub(r"[^a-z]", "", name.lower())
    a = re.sub(r"[^a-z]", "", ab.lower())
    if not a or not n or a[0] != n[0]:
        return False
    i = 0
    for ch in n:
        if i < len(a) and ch == a[i]:
            i += 1
    return i == len(a)


def team_fits(lg, ab, fx, side):
    name, short, abbr = fx[f"participant{side}Name"], fx[f"participant{side}ShortName"], fx[f"participant{side}Abbr"]
    if lg == "NFL":  # app abbreviations are the usual ones; match the city or nickname through fetch_odds.TEAM
        from fetch_odds import TEAM
        return TEAM["NFL"].get(ab) == name or ab == abbr
    return ab == abbr or cfb_fits(ab, name, short)


def american(s):
    try:
        v = int(str(s).replace("+", ""))
        return v if abs(v) >= 100 else None
    except Exception:
        return None


def flip(n):
    """'Williams, Chance' -> 'chance williams'"""
    if "," in n:
        last, _, first = n.partition(",")
        n = f"{first.strip()} {last.strip()}"
    return norm(n)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    if not KEY:
        print("no ODDSPAPI_KEY set; skipping")
        return
    if MODE_MARKETS:
        build_table()
        return
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    month = now.strftime("%Y-%m")
    used = (old.get("usage") or {}).get(month, 0)
    props = {k: v for k, v in (old.get("props") or {}).items() if dt.datetime.fromisoformat(v["game_t"]) > now}
    tried = {k: v for k, v in (old.get("tried") or {}).items() if now - dt.datetime.fromisoformat(v) < dt.timedelta(hours=48)}
    log = []
    try:
        slate = json.load(open("slate.json"))
        tbl = json.load(open(TABLE))
        built = dt.datetime.fromisoformat(tbl["built"])
        tbl = tbl["markets"]
    except Exception as e:
        print("no slate.json or market table:", e)
        return
    want = {}
    for c in slate.get("props", []):
        t = dt.datetime.fromisoformat(c["t"])
        if c["lg"] not in ("CFB", "NFL") or c["market"] not in TYPE.values() or not dt.timedelta(0) < t - now < dt.timedelta(hours=WINDOW_H):
            continue
        if c.get("po") is not None and c.get("pu") is not None:
            continue
        want.setdefault((c["lg"], tuple(sorted((c["team"], c["opp"]))), c["t"]), []).append(c)
    want = {k: v for k, v in want.items() if len(v) >= MIN_PROPS}
    if not want:
        print("nothing to price")
        json.dump(dict(old, fetched=now.isoformat(timespec="minutes"), props=props, tried=tried), open(OUT, "w"), separators=(",", ":"))
        return
    days_left = calendar.monthrange(now.year, now.month)[1] - now.day + 1
    left = 250 - used
    if left - 1 < RESERVE_DAY * (days_left - 1):
        log.append(f"stopped: {left} requests left with {days_left} days to go")
        want = {}
    fixtures = []
    if want:
        d = get("/fixtures", sportId=SPORT_ID, **{"from": str(now.date()), "to": str((now + dt.timedelta(hours=WINDOW_H + 24)).date())})
        fixtures = [f for f in d if f.get("hasOdds") and f.get("tournamentId") in TOURNAMENT and f.get("statusName") != "Cancelled"]
    n = 0
    for (lg, teams, t), cs in sorted(want.items(), key=lambda kv: -sum(c.get("score") or 0 for c in kv[1])):
        tk = f"{lg}|{teams[0]}|{teams[1]}|{t}"
        if tk in tried and now - dt.datetime.fromisoformat(tried[tk]) < dt.timedelta(hours=REFRESH_H):
            continue
        if n >= MAX_RUN:
            log.append(f"run cap reached ({MAX_RUN} games)")
            break
        kick = dt.datetime.fromisoformat(t)
        hit = [f for f in fixtures if TOURNAMENT[f["tournamentId"]] == lg
               and abs(dt.datetime.fromisoformat(f["startTime"].replace("Z", "+00:00")) - kick) < dt.timedelta(minutes=20)
               and ((team_fits(lg, teams[0], f, 1) and team_fits(lg, teams[1], f, 2)) or (team_fits(lg, teams[1], f, 1) and team_fits(lg, teams[0], f, 2)))]
        if len(hit) != 1:
            log.append(f"{lg} {teams[0]}/{teams[1]}: {len(hit)} matching fixtures")
            continue
        try:
            d = get("/odds", fixtureId=hit[0]["fixtureId"], bookmaker=",".join(BOOKS))
        except Exception as e:
            log.append(f"{lg} {teams[0]}/{teams[1]} odds failed: {e}")
            continue
        n += 1
        tried[tk] = now.isoformat(timespec="minutes")
        time.sleep(.5)
        # quotes[(app market, player)] = {book: [(line, over, under)]}
        q = {}
        for b, bv in (d.get("bookmakerOdds") or {}).items():
            if b not in BOOKNAME:
                continue
            for mid, m in (bv.get("markets") or {}).items():
                info = tbl.get(mid)
                if not info:
                    continue
                mk, line, oid, uid = info
                ov, un = (m.get("outcomes") or {}).get(str(oid)), (m.get("outcomes") or {}).get(str(uid))
                if not ov or not un or line is None:
                    continue
                for pid, po in (ov.get("players") or {}).items():
                    pu = (un.get("players") or {}).get(pid)
                    if not pu or not po.get("active") or not pu.get("active") or not po.get("playerName"):
                        continue
                    a, bb = american(po.get("priceAmerican")), american(pu.get("priceAmerican"))
                    if a is None or bb is None:
                        continue
                    q.setdefault((mk, flip(po["playerName"])), {}).setdefault(BOOKNAME[b], []).append((line, a, bb))
        filled = 0
        for c in cs:
            nm = norm(c["name"])
            cand = next((v for (mk, pn), v in q.items() if mk == c["market"] and same_player(nm, pn)), None)
            if not cand:
                continue
            books = {}
            for bk in ("DraftKings", "FanDuel", "BetMGM", "Pinnacle"):
                rows = cand.get(bk)
                if rows:
                    ln, o, u = min(rows, key=lambda r: abs(r[0] - (c["line"] or r[0])))
                    books[bk] = {"line": ln, "over": o, "under": u}
            if books:
                best = next(bk for bk in books if books[bk]["line"] == c["line"]) if any(v["line"] == c["line"] for v in books.values()) else next(iter(books))
                props[c["key"]] = {"line": books[best]["line"], "over": books[best]["over"], "under": books[best]["under"],
                                   "book": best, "books": books, "t": now.isoformat(timespec="minutes"), "game_t": t}
                filled += 1
        log.append(f"{lg} {teams[0]}/{teams[1]}: {filled}/{len(cs)} priced")
    usage = dict(old.get("usage") or {})
    usage[month] = used + usage_now
    json.dump({"fetched": now.isoformat(timespec="minutes"), "usage": usage, "source": "OddsPapi", "tried": tried,
               "log": log[-40:], "props": props}, open(OUT, "w"), separators=(",", ":"))
    print("\n".join(log) or "nothing to price")
    print(f"wrote {OUT}: {len(props)} priced props; {usage_now} requests this run, {usage[month]} this month of 250")
    if built and now - built > dt.timedelta(days=30):
        print("market table is over 30 days old: run fetch_oddspapi.py --markets")


if __name__ == "__main__":
    main()
