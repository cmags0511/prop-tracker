"""Lab #2, market-anchored picks on FanDuel: a side project that runs next to the main Top 10 and never changes it.

Every bet is a FanDuel player prop at FanDuel's own line and price (NFL: passing, rushing, receiving; NBA: points,
rebounds, assists, combos, threes), read from FanDuel's public odds feed. Each prop's chance starts from the market
and the app's stats only tilt it:
  - Pinnacle's price with its margin taken out (the sharpest book), moved to FanDuel's line with fetch_prices.shift
    when the two lines differ; else Kalshi's chance when its line is FanDuel's; with no market at all it's skipped
  - final log-odds = W x market + (1 - W) x the app's own chance (slate.json p_over, moved to FanDuel's line);
    W = .85 Pinnacle, .8 Kalshi, .1 less when Pinnacle's price was moved from another line
Then it takes the side with the better expected profit at FanDuel's price and lists the 10 best (expected profit +2%
or more, half credit for a moved Pinnacle price; one per player, at most 3 per prop type). Picks lock at kickoff and
are graded from the box scores at FanDuel's price, in lab_market.json, so the method can be judged on its own record.
Runs hourly after record.py. This is the same idea as PR #2, tried live instead of replacing the main ranking.
"""
import datetime as dt
import json
import math
import sys

import time
from statistics import NormalDist

from fetch_odds import norm
from fetch_prices import FD, FD_KEY, MAX_SHIFT, SAME_GAME, SPREAD, get, pinnacle, shift
from picks import LABEL, stat

ND = NormalDist()

OUT = sys.argv[1] if len(sys.argv) > 1 else "lab_market.json"
ANCHOR_W = {"Pinnacle": .85, "Kalshi": .8}
ANCHOR_EST = .1
MIN_EV = .02
TOP = 10
PER_MARKET = 3


def lg_(q):
    q = min(.985, max(.015, q))
    return math.log(q / (1 - q))


def sig(z):
    return 1 / (1 + math.exp(-z))


def imp(a):
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def dec(a):
    return 1 + (a / 100 if a > 0 else 100 / -a)


def load(f, d):
    try:
        return json.load(open(f))
    except (OSError, ValueError):
        return d


FD_LAB = {  # FanDuel page, player-prop tabs, days ahead
    "NFL": ("nfl", ("passing-props", "receiving-props", "rushing-props"), 8),
    "NBA": ("nba", ("player-points", "player-rebounds", "player-assists", "player-combos", "player-threes"), 2)}
FD_NAME = {"Passing Yds": "pyd", "Passing TDs": "ptd", "Pass Completions": "cmp", "Pass Attempts": "att",
           "Rushing Yds": "ryd", "Rushing Attempts": "car", "Receiving Yds": "recyd", "Total Receptions": "rec",
           "Rushing + Receiving Yds": "rry", "Points": "pts", "Rebounds": "reb", "Assists": "ast", "Made Threes": "3pm",
           "Pts + Reb + Ast": "pra", "Pts + Reb": "pr", "Pts + Ast": "pa", "Reb + Ast": "ra"}


def fd_board(lg, now):
    """every two-way FanDuel player prop (its own line and prices) for upcoming games: [(name, prop, start, line, o, u)]"""
    page_id, tabs, days = FD_LAB[lg]
    page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId={page_id}&_ak={FD_KEY}&timezone=America%2FNew_York")
    rows = []
    for ev in (page.get("attachments") or {}).get("events", {}).values():
        start = dt.datetime.fromisoformat(ev["openDate"].replace("Z", "+00:00"))
        if " @ " not in ev["name"] or "(" in ev["name"] or not now < start < now + dt.timedelta(days=days):
            continue  # (names in brackets are FanDuel's simulated games)
        for tab in tabs:
            try:
                d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}&tab={tab}")
            except Exception as e:
                print(f"FanDuel {ev['name']} {tab}: {e}")
                continue
            for m in (d.get("attachments") or {}).get("markets", {}).values():
                name, _, what = m.get("marketName", "").partition(" - ")
                rs = m.get("runners") or []
                if what not in FD_NAME or len(rs) != 2:
                    continue
                odds = lambda r: ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")
                o = next((r for r in rs if r["runnerName"].endswith(" Over")), None)
                u = next((r for r in rs if r["runnerName"].endswith(" Under")), None)
                if o and u and odds(o) and odds(u) and o.get("handicap") == u.get("handicap"):
                    rows.append((name, FD_NAME[what], start, o["handicap"], int(odds(o)), int(odds(u))))
            time.sleep(.15)
    return rows


def novig(o, u):
    return imp(o) / (imp(o) + imp(u))


def move_p(p, frm, to, mid):
    """the chance of the over at line `frm`, moved to line `to` (normal model, as fetch_prices.shift); None if too far"""
    sd = SPREAD.get(mid, .5) * max(frm, to, 1)
    if abs(to - frm) > MAX_SHIFT * sd:
        return None
    return min(.98, max(.02, 1 - ND.cdf(ND.inv_cdf(min(.98, max(.02, 1 - p))) + (to - frm) / sd)))


def price_props(now):
    """FanDuel's board, each prop's chance anchored on Pinnacle (moved to FanDuel's line when they differ), else Kalshi
    when its line is FanDuel's; the app's own chance (slate.json, moved to FanDuel's line) tilts it"""
    data = load("props_data.json", {})
    slate = {s["key"]: s for s in load("slate.json", {"props": []})["props"]}
    out = []
    for lg in FD_LAB:
        meta = data.get(lg)
        if not meta:
            continue
        games = {}  # team -> [(start, opponent)]
        for u in meta.get("upcoming", []):
            t = dt.datetime.fromisoformat(u[0])
            games.setdefault(u[1], []).append((t, u[2]))
            games.setdefault(u[2], []).append((t, u[1]))
        by_name = {}
        for p in meta["players"]:
            by_name.setdefault(norm(p["n"]), []).append(p)

        def who(name, start):
            ps = [(p, opp) for p in by_name.get(norm(name), []) for t, opp in games.get(p["t"], []) if abs(t - start) < SAME_GAME]
            return ps[0] if len(ps) == 1 else (None, None)
        try:
            fd = fd_board(lg, now)
        except Exception as e:
            print(f"{lg} FanDuel failed: {e}")
            continue
        try:
            pin = {}
            for name, mid, start, line, o, u in pinnacle(lg, now):
                p, _ = who(name, start)
                if p:
                    pin[(p["id"], mid)] = (line, o, u)
        except Exception as e:
            print(f"{lg} Pinnacle failed: {e}")
            pin = {}
        for name, mid, start, line, fo, fu in fd:
            p, opp = who(name, start)
            if not p or mid not in LABEL:
                continue
            key = f"{lg}|{p['id']}|{mid}"
            s = slate.get(key) or {}
            anchor, src, est = None, None, False
            pq = pin.get((p["id"], mid))
            if pq:
                if pq[0] == line:
                    anchor, src = novig(pq[1], pq[2]), "Pinnacle"
                else:
                    mv = shift(pq[0], pq[1], pq[2], line, mid)
                    if mv:
                        anchor, src, est = novig(*mv), "Pinnacle", True
            if anchor is None and s.get("market_over") is not None and s.get("line") == line:
                anchor, src = s["market_over"], "Kalshi"
            if anchor is None:
                continue
            app = move_p(s["p_over"], s["line"], line, mid) if s.get("p_over") is not None else None
            w = ANCHOR_W[src] - (ANCHOR_EST if est else 0)
            pr = sig(w * lg_(anchor) + (1 - w) * lg_(app)) if app is not None else anchor
            ev_o, ev_u = pr * dec(fo) - 1, (1 - pr) * dec(fu) - 1
            over = ev_o >= ev_u
            ev = ev_o if over else ev_u
            # an anchor moved from Pinnacle's nearby line is rougher: half credit for ranking and the +2% bar
            rank = ev * (.5 if est else 1)
            out.append({"key": key, "lg": lg, "id": p["id"], "name": p["n"], "team": p["t"], "opp": opp,
                        "t": start.isoformat(), "market": mid, "label": LABEL[mid], "line": line,
                        "side": "over" if over else "under", "price": fo if over else fu, "book": "FanDuel",
                        "other": fu if over else fo, "anchor": src, "prob": round(pr if over else 1 - pr, 3),
                        "mkt": round(anchor if over else 1 - anchor, 3),
                        "app": round(app if over else 1 - app, 3) if app is not None else None,
                        "ev": round(ev, 3), "est": est, "rank": round(rank, 3)})
        print(f"{lg}: FanDuel {len(fd)} props, {sum(1 for c in out if c['lg'] == lg)} with a market to anchor on")
    return out


def pick10(cands, now):
    out, seen, per = [], set(), {}
    for c in sorted(cands, key=lambda c: -c["rank"]):
        if c["rank"] < MIN_EV or dt.datetime.fromisoformat(c["t"]) <= now:
            continue
        if c["id"] in seen or per.get(c["market"], 0) >= PER_MARKET:
            continue
        seen.add(c["id"])
        per[c["market"]] = per.get(c["market"], 0) + 1
        out.append(c)
        if len(out) == TOP:
            break
    return out


def grader(now):
    data = load("props_data.json", {})
    cfb = load("cfb_data.json", None)
    if cfb:
        data["CFB"] = cfb
    box = load("box_recent.json", {"cols": [], "players": {}})
    players = {lg: {p["id"]: p for p in data[lg]["players"]} for lg in ("NFL", "NBA", "CFB") if lg in data}

    def grade(e):
        t = dt.datetime.fromisoformat(e["t"])
        day = (t - dt.timedelta(hours=5)).date()  # US game day
        g = None
        if e["lg"] == "NFL":
            for row in box["players"].get(e["id"], []):
                if abs((dt.date.fromisoformat(row[0]) - day).days) <= 1 and row[1] == e["opp"]:
                    g = dict(zip(box["cols"], row))
                    break
        p = players.get(e["lg"], {}).get(e["id"])
        if g is None and p:
            cols = data[e["lg"]]["cols"]
            for row in p["g"]:
                gm = dict(zip(cols, row))
                if abs((dt.date.fromisoformat(gm["date"]) - day).days) <= 1 and gm["opp"] == e["opp"]:
                    g = gm
                    break
        if g is None:
            if now - t > dt.timedelta(days=3):
                e["status"] = "void"  # no stat line three days on: he didn't play (books refund it)
            return
        v = stat(g, e["market"])
        e["result"] = v
        e["status"] = "push" if v == e["line"] else "win" if (v > e["line"]) == (e["side"] == "over") else "loss"
        e["graded"] = now.isoformat(timespec="minutes")
    return grade


def main():
    now = dt.datetime.now(dt.timezone.utc)
    old = load(OUT, {})
    rec = {(e["key"], e["t"]): e for e in old.get("record", [])}
    cands = price_props(now)
    if not cands and old.get("picks"):
        print("no FanDuel or Pinnacle prices this run; keeping the previous list")
        cands = [c for c in old["picks"] if dt.datetime.fromisoformat(c["t"]) > now]
    top = pick10(cands, now)
    # pending picks that haven't started are replaced by the current list; started ones stay locked
    for k, e in list(rec.items()):
        if e["status"] == "pending" and dt.datetime.fromisoformat(e["t"]) > now:
            del rec[k]
    for c in top:
        rec[(c["key"], c["t"])] = dict(c, status="pending", result=None, locked=None)
    grade = grader(now)
    for e in rec.values():
        if e["status"] == "pending" and dt.datetime.fromisoformat(e["t"]) <= now:
            e["locked"] = e.get("locked") or e["t"]
            if now - dt.datetime.fromisoformat(e["t"]) > dt.timedelta(hours=4):
                grade(e)
    record = sorted(rec.values(), key=lambda e: (e["t"], -e["ev"]))
    done = [e for e in record if e["status"] in ("win", "loss")]
    units = sum((dec(e["price"]) - 1) if e["status"] == "win" else -1 for e in done)
    json.dump({"built": now.isoformat(timespec="minutes"), "started": old.get("started") or now.date().isoformat(),
               "picks": top, "n_priced": len(cands), "record": record,
               "summary": {"w": sum(e["status"] == "win" for e in done), "l": sum(e["status"] == "loss" for e in done),
                           "units": round(units, 2)}},
              open(OUT, "w"), separators=(",", ":"))
    print(f"lab_market: {len(cands)} props with a market price, {len(top)} picks; record "
          f"{sum(e['status'] == 'win' for e in done)}-{sum(e['status'] == 'loss' for e in done)} ({units:+.2f}u)")
    for c in top[:5]:
        print(f"  {c['name']} {c['side']} {c['line']} {c['label']} {c['price']:+d} prob {c['prob']} mkt {c['mkt']} app {c['app']} ev {c['ev']:+.3f}{' est' if c['est'] else ''}")


if __name__ == "__main__":
    main()
