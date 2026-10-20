"""Lab #2, market-anchored picks: a side project that runs next to the main Top 10 and never changes it.

Each prop's chance starts from the betting market and the app's stats only tilt it:
  - Pinnacle's price with its margin taken out (the sharpest book), else FanDuel's, with Kalshi blended in at a quarter
    when it has a price; with no sportsbook price, Kalshi alone; with no market at all the prop is skipped
  - final log-odds = W x market + (1 - W) x the app's own chance (slate.json p_over); W = .85 Pinnacle, .75 FanDuel,
    .8 Kalshi, .1 less when the book's price was worked out from a nearby line
Then it takes whichever side has the better expected profit at the best real price on offer (the anchor book's own
quote, or DraftKings' price at the same line from ESPN's feed, NBA only) and lists the 10 best (expected profit
+2% or more, one per player, at most 3 per prop type). Picks lock at kickoff and are graded from the box scores at the
price shown, in lab_market.json, so the method can be judged on its own record.
Runs hourly after record.py. This is the same idea as PR #2, tried live instead of replacing the main ranking.
"""
import datetime as dt
import json
import math
import sys

from picks import stat

OUT = sys.argv[1] if len(sys.argv) > 1 else "lab_market.json"
ANCHOR_W = {"Pinnacle": .85, "FanDuel": .75, "Kalshi": .8}
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


def dk_prices():
    """DraftKings' own over / under prices from lines.json (NBA), keyed like slate.json"""
    lines, data = load("lines.json", {}), load("props_data.json", {})
    out = {}
    for lg in ("NFL", "NBA"):
        ids = {str(p.get("espn") or p["id"]): p["id"] for p in (data.get(lg) or {}).get("players", [])}
        for eid, mk in (lines.get(lg) or {}).items():
            for m, r in (mk or {}).items():
                if isinstance(r, dict) and r.get("po") and r.get("pu"):
                    out[f"{lg}|{ids.get(eid, eid)}|{m}"] = (r["line"], r["po"], r["pu"])
    return out


def price_props(slate, dkp=None):
    dkp = dkp or {}
    out = []
    for s in slate:
        po, pu = s.get("po"), s.get("pu")
        anchor, src, w = None, None, 0.0
        if isinstance(po, (int, float)) and isinstance(pu, (int, float)) and po and pu:
            qb = imp(po) / (imp(po) + imp(pu))
            src = s.get("pb") or "Pinnacle"
            w = ANCHOR_W.get(src, .75) - (ANCHOR_EST if s.get("pe") else 0)
            anchor = lg_(qb)
            if s.get("market_over") is not None:
                anchor = .75 * anchor + .25 * lg_(s["market_over"])
        elif s.get("market_over") is not None:
            src, w, anchor = "Kalshi", ANCHOR_W["Kalshi"], lg_(s["market_over"])
        if anchor is None or s.get("p_over") is None:
            continue
        p = sig(w * anchor + (1 - w) * lg_(s["p_over"]))
        q_mkt = sig(anchor)
        # the price we'd get: the better of the anchor book's own price and DraftKings' (same line), per side.
        # Only real quoted prices count: none made up from Kalshi or assumed at -110.
        offers = {"over": [], "under": []}
        if isinstance(po, (int, float)) and po and not s.get("pe"):
            offers["over"].append((po, src))
        if isinstance(pu, (int, float)) and pu and not s.get("pe"):
            offers["under"].append((pu, src))
        d = dkp.get(s["key"])
        if d and d[0] == s["line"]:
            offers["over"].append((d[1], "DraftKings"))
            offers["under"].append((d[2], "DraftKings"))
        best = {k: max(v, key=lambda x: dec(x[0])) for k, v in offers.items() if v}
        if not best:
            continue
        ev_o = p * dec(best["over"][0]) - 1 if "over" in best else -1
        ev_u = (1 - p) * dec(best["under"][0]) - 1 if "under" in best else -1
        over = ev_o >= ev_u
        ev = ev_o if over else ev_u
        price, book = best["over" if over else "under"]
        # an anchor worked out from the book's price at a nearby line (fetch_prices.py "est") is rougher: half credit when
        # ranking and for the +2% bar, so a shaky estimate can't top the list
        rank = ev * (.5 if s.get("pe") else 1)
        out.append({"key": s["key"], "lg": s["lg"], "id": s["id"], "name": s["name"], "team": s["team"], "opp": s["opp"],
                    "t": s["t"], "market": s["market"], "label": s["label"], "line": s["line"],
                    "side": "over" if over else "under", "price": price, "book": book,
                    "anchor": src, "prob": round(p if over else 1 - p, 3), "mkt": round(q_mkt if over else 1 - q_mkt, 3),
                    "app": round(s["p_over"] if over else 1 - s["p_over"], 3), "ev": round(ev, 3),
                    "est": bool(s.get("pe")), "rank": round(rank, 3), "avg10": s.get("avg10")})
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
    slate = load("slate.json", {"props": []})["props"]
    old = load(OUT, {})
    rec = {(e["key"], e["t"]): e for e in old.get("record", [])}
    cands = price_props(slate, dk_prices())
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
        print(f"  {c['name']} {c['side']} {c['line']} {c['label']} {c['price']:+d} prob {c['prob']} mkt {c['mkt']} app {c['app']} ev {c['ev']:+.3f}")


if __name__ == "__main__":
    main()
