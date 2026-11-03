"""NHL prop board and ranked picks -> nhl.json (run after nhl_data.py; hourly).

For every upcoming NHL game it reads FanDuel's public player markets (shots on goal over/under, anytime goal scorer,
1+/2+ points, 1+/2+ assists), takes the book's margin out to get the chance the market gives, works out our own chance
from the box-score history (nhl_model.py) and blends the two. The blend leans on the market (BLEND_MODEL = 35% model),
because the stats model alone has no price to check against and so far only beats a plain base rate, not the book.

  * top  = the likeliest hits (one bet per player, at most 2 per game)
  * value = the few bets whose blended chance beats the price by a clear margin
  * record = every top / value pick, locked at the last price seen before puck drop and graded from the box scores
    (win / loss, push for a landed line, void if the player didn't play)

Prices are FanDuel's: DraftKings' NHL player prices aren't available to us, so the app labels them "check DraftKings".
Goalie saves aren't priced by FanDuel's feed, so they aren't listed.

Usage: python nhl_picks.py [nhl.json] [nhl_hist.json.gz]
"""
import datetime as dt
import gzip
import json
import math
import re
import sys
import time
import unicodedata
from zoneinfo import ZoneInfo

import nhl_model as M
from fetch_prices import FD, FD_KEY, get as fd_get

OUT = sys.argv[1] if len(sys.argv) > 1 else "nhl.json"
HIST = sys.argv[2] if len(sys.argv) > 2 else "nhl_hist.json.gz"
ET = ZoneInfo("America/New_York")
BLEND_MODEL = .35
HOLD_YES = {"goal": 1.12, "pts": 1.06, "ast": 1.06}   # typical margin in a yes-only "1+" price (nothing pairs it with a "no")
MAX_GAP = .15                                          # model vs market gap beyond which the book likely knows something (lineup, role)
TOP_N, VALUE_N, PER_GAME = 12, 10, 2
TOP_MIN_DEC = 1.4          # nothing shorter than -250 in the top list
LABEL = {"sog": "shots on goal", "goal": "goal", "pts": "points", "ast": "assists"}
TABS = ("goals", "points-assists", "shots")
KEEP_DAYS = 400


def norm(n):
    n = unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[.'\-]", " ", n).split())


def imp(a):
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def dec_of(a):
    return 1 + (a / 100 if a > 0 else 100 / -a)


def logit(p):
    p = min(.995, max(.005, p))
    return math.log(p / (1 - p))


def sig(z):
    return 1 / (1 + math.exp(-z))


def runner_price(r):
    return ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")


def load_json(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def fanduel_games(names, upcoming, now):
    """[(hist game, {tab: markets})] for the upcoming games FanDuel lists"""
    page = fd_get(f"{FD}/content-managed-page?page=CUSTOM&customPageId=nhl&_ak={FD_KEY}&timezone=America%2FNew_York")
    evs = [e for e in (page.get("attachments") or {}).get("events", {}).values() if " @ " in e.get("name", "")]
    full = {abbr: norm(n) for abbr, n in names.items()}
    out = []
    for g in upcoming:
        want = f"{full.get(g['away'])} @ {full.get(g['home'])}"
        ev = next((e for e in evs if norm(e["name"]) == want), None)
        if not ev or dt.datetime.fromisoformat(g["t"]) <= now:
            continue
        mk = {}
        for tab in TABS:
            try:
                mk[tab] = ((fd_get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}&tab={tab}").get("attachments") or {}).get("markets", {}))
            except Exception as e:
                print(f"{ev['name']} {tab}: {e}")
                mk[tab] = {}
            time.sleep(.15)
        out.append((g, mk))
    return out


def parse_markets(markets):
    """-> [(player name, market, line, side, american price, fair chance of that side)]"""
    res = []
    for mk in markets.values():
        mt = mk.get("marketType") or ""
        rs = mk.get("runners") or []
        if mt == "PLAYER_TOTAL_SHOTS":
            ov = next((r for r in rs if r.get("runnerName", "").endswith("- Over")), None)
            un = next((r for r in rs if r.get("runnerName", "").endswith("- Under")), None)
            if not ov or not un or runner_price(ov) is None or runner_price(un) is None:
                continue
            name = ov["runnerName"].rsplit(" - ", 1)[0]
            line = float(ov.get("handicap") or 0)
            io, iu = imp(runner_price(ov)), imp(runner_price(un))
            res.append((name, "sog", line, "over", runner_price(ov), io / (io + iu)))
            res.append((name, "sog", line, "under", runner_price(un), iu / (io + iu)))
        else:
            spec = {"ANY_TIME_GOAL_SCORER": ("goal", .5), "PLAYER_TO_RECORD_1+_POINTS": ("pts", .5), "PLAYER_TO_RECORD_2+_POINTS": ("pts", 1.5),
                    "PLAYER_TO_RECORD_1+_ASSISTS": ("ast", .5), "PLAYER_TO_RECORD_2+_ASSISTS": ("ast", 1.5)}.get(mt)
            if not spec:
                continue
            hold = HOLD_YES[spec[0]] * (1.04 if spec[1] > 1 else 1.0)
            for r in rs:
                a = runner_price(r)
                if a is not None:
                    res.append((r.get("runnerName"), spec[0], spec[1], "over", a, min(.97, imp(a) / hold)))
    return res


def stat_of(row, market):
    return {"sog": row[7], "goal": row[5], "ast": row[6], "pts": row[5] + row[6]}[market]


def main():
    now = dt.datetime.now(dt.timezone.utc)
    hist = json.load(gzip.open(HIST, "rt"))
    H = M.Hist(hist)
    old = load_json(OUT, {})
    today = now.astimezone(ET).date().isoformat()
    games = fanduel_games(hist.get("names", {}), hist.get("upcoming", []), now)
    by_team = {}
    for pid, p in H.p.items():
        by_team.setdefault(p["t"], {}).setdefault(norm(p["n"]), pid)
    cands, matches, unmatched = [], [], 0
    for g, mk in games:
        quotes = []
        for tab in TABS:
            quotes += parse_markets(mk.get(tab, {}))
        pinfo, rows = {}, []
        for name, m, line, side, am, q_fair in quotes:
            pid = by_team.get(g["away"], {}).get(norm(name)) or by_team.get(g["home"], {}).get(norm(name))
            if not pid:
                unmatched += 1
                continue
            p = H.p[pid]
            team = p["t"]
            opp = g["home"] if team == g["away"] else g["away"]
            mu = H.mu(pid, m, team, opp, "9999-12-31")
            if mu is None or H.rate(pid, "9999-12-31")["n"] < 8:
                continue
            p_over = M.p_over(m, mu, line)
            p_mod = p_over if side == "over" else 1 - p_over
            prob = sig((BLEND_MODEL) * logit(p_mod) + (1 - BLEND_MODEL) * logit(q_fair))
            dec = dec_of(am)
            last10 = p["g"][-10:]
            hits = sum(1 for r in last10 if (stat_of(r, m) > line) == (side == "over"))
            pinfo[pid] = {"n": p["n"], "pos": p["p"], "team": team}
            rows.append({"key": f"NHL|{pid}|{m}|{line:g}|{side}|{g['id']}", "pid": pid, "name": p["n"], "pos": p["p"], "team": team, "opp": opp,
                         "home": 1 if team == g["home"] else 0, "id": g["id"], "t": g["t"], "m": m, "line": line, "side": side,
                         "label": f"{side} {line:g} {LABEL[m]}" if m == "sog" else (f"{int(line + .5)}+ {LABEL[m]}"),
                         "price": am, "dec": round(dec, 3), "prob": round(prob, 3), "model": round(p_mod, 3), "book": round(q_fair, 3),
                         "ev": round(prob * dec - 1, 3), "hits": [hits, len(last10)]})
        rows.sort(key=lambda r: -r["ev"])
        matches.append({"id": g["id"], "t": g["t"], "away": g["away"], "home": g["home"],
                        "away_n": hist["names"].get(g["away"], g["away"]), "home_n": hist["names"].get(g["home"], g["home"]),
                        "players": pinfo,
                        "P": [[r["pid"], r["m"], r["line"], r["side"], r["price"], r["prob"], r["ev"], r["model"], r["book"], r["hits"][0], r["hits"][1]]
                              for r in rows if r["prob"] >= .08]})
        cands += rows
    sane = lambda c: abs(c["model"] - c["book"]) <= MAX_GAP

    def top(pool, key, n, per_game=PER_GAME):
        out, seen, pg = [], set(), {}
        for c in sorted(pool, key=key):
            if c["pid"] in seen or pg.get(c["id"], 0) >= per_game:
                continue
            seen.add(c["pid"])
            pg[c["id"]] = pg.get(c["id"], 0) + 1
            out.append(c)
            if len(out) == n:
                break
        return out
    tops = top([c for c in cands if c["dec"] >= TOP_MIN_DEC and sane(c)], lambda c: -c["prob"], TOP_N)
    value = top([c for c in cands if c["ev"] >= .03 and c["prob"] >= .2 and c["dec"] <= 6 and sane(c)], lambda c: -c["ev"], VALUE_N)

    # ---- record: lock at the last price before the game starts, then grade from the box scores
    rec = old.get("record") or {"picks": []}
    book = {r["key"]: r for r in rec["picks"]}
    for c in tops + value:
        if dt.datetime.fromisoformat(c["t"]) <= now:
            continue
        r = book.get(c["key"])
        if r is None:
            r = book[c["key"]] = {"key": c["key"], "pid": c["pid"], "name": c["name"], "team": c["team"], "opp": c["opp"], "id": c["id"],
                                  "t": c["t"], "m": c["m"], "line": c["line"], "side": c["side"], "label": c["label"], "open": c["price"],
                                  "list": "top" if c in tops else "value"}
        r.update({"price": c["price"], "dec": c["dec"], "prob": c["prob"], "model": c["model"], "book": c["book"], "ev": c["ev"]})
        if c in tops and c in value:
            r["list"] = "both"
        elif c in value:
            r["list"] = "both" if r["list"] == "top" else "value"
        elif c in tops:
            r["list"] = "both" if r["list"] == "value" else "top"
    teamdays = {(t, r[0], r[1]) for t, rows in H.t.items() for r in rows}
    for r in book.values():
        if r.get("res"):
            continue
        d = dt.datetime.fromisoformat(r["t"]).astimezone(ET).date().isoformat()
        if (r["team"], d, r["opp"]) not in teamdays:
            continue    # game not in the history yet
        row = next((x for x in H.p.get(r["pid"], {"g": []})["g"] if x[0] == d and x[1] == r["opp"]), None)
        if row is None:
            r["res"], r["v"] = "void", None
            continue
        v = stat_of(row, r["m"])
        r["v"] = v
        r["res"] = "push" if v == r["line"] else ("win" if (v > r["line"]) == (r["side"] == "over") else "loss")
        r["paid"] = r["dec"] if r["res"] == "win" else (1.0 if r["res"] == "push" else 0.0)
    cut = (now - dt.timedelta(days=KEEP_DAYS)).isoformat(timespec="minutes")
    rec["picks"] = sorted((r for r in book.values() if r["t"] >= cut), key=lambda r: r["t"])

    matches.sort(key=lambda m: m["t"])
    json.dump({"built": now.isoformat(timespec="minutes"), "matches": matches, "top": tops, "value": value, "record": rec,
               "hist_built": hist.get("built")}, open(OUT, "w"), separators=(",", ":"))
    done = [r for r in rec["picks"] if r.get("res") in ("win", "loss")]
    print(f"wrote {OUT}: {len(matches)} games, {len(cands)} priced props ({unmatched} names unmatched), top {len(tops)}, value {len(value)}; "
          f"record {sum(1 for r in done if r['res'] == 'win')}-{sum(1 for r in done if r['res'] == 'loss')} of {len(rec['picks'])} locked")


if __name__ == "__main__":
    main()
