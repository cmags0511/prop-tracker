"""fwarnk: "the math has to add up". A hidden side project that bets FanDuel player props when a team's own player
lines don't add up to what the team as a whole is expected to do. It uses no player predictions and no line moves,
only the book's numbers and how teams split their production.

NFL passing. Every receiving yard is also a passing yard, so a team's receiving lines should keep pace with its QB's
passing line. Add up the team's 4 biggest FanDuel receiving-yards lines and divide by the QB's passing-yards line.
The usual share is learned from the slates (median of the team-games seen, today's included; 0.69 until there are
10: DraftKings lines Oct 9-20 averaged 0.691, sd 0.07). 0.05 or more above the usual, the receivers look pricey:
  - NFL unders: the unders on the team's 2 biggest receiving lines (counts)
  - NFL unders + Pinnacle: the same unders only when Pinnacle's price at FanDuel's line also leans under (a subset,
    its own record, to see whether the check helps)
0.05 or more below, the receivers look cheap: NFL overs (tracked), recorded but not counted, since cheap teams' overs
went 50% in the first look (FanDuel's -114 needs 53.3%) while pricey teams' unders went about 60-63%.
A team with a receiver averaging 30+ yards on the injury report (out, doubtful, questionable) is skipped: his
absence changes who's in the top 4 and fakes a signal.

NBA points. A team's expected points come from FanDuel's game total and spread (home: total/2 - spread/2). The points
lines of its 6 biggest scorers should be a steady share of that. The usual share is learned the same way; no NBA picks
until 10 team-games have been seen. 6% or more below the usual: bet the overs on its 2 biggest lines; 6% or more above: the unders.

At most 2 bets per team; NFL receiving lines of 15.5+ only. Every pick is at FanDuel's line and price (fd_board.json,
saved by lab_market.py the same hour), locked at kickoff and graded from the box score at that price, in fwarnk.json.
"""
import datetime as dt
import json
import statistics as st
import sys

from fetch_prices import shift
from lab_market import dec, grader, load, novig

OUT = sys.argv[1] if len(sys.argv) > 1 else "fwarnk.json"
NFL_TOP = 4         # a team's biggest receiving lines counted in its share
NFL_PRIOR = .69
NFL_GAP = .05
NFL_MIN_LINE = 15.5
NBA_TOP = 6         # a team's biggest scorers counted in its share
NBA_PRIOR = .80
NBA_GAP = .06
PER_TEAM = 2
INJ = {"Out", "Doubtful", "Questionable", "Day-To-Day"}
NFL_INJ_YDS = 30    # a receiver this good (avg receiving yards, last 3 games) on the injury report: skip his team
NBA_INJ_PTS = 15    # a scorer this good (avg points, last 10 games) on the injury report: skip his team
M_UNDER, M_OVER, M_PIN, M_NBA = "NFL unders", "NFL overs (tracked)", "NFL unders + Pinnacle", "NBA points"


def nfl_ratios(props):
    """{(team, kickoff): (share, qb, top receivers)}: the top-4 receiving lines added up / the QB's passing line"""
    games, out = {}, {}
    for c in props:
        if c["lg"] == "NFL" and c["market"] in ("pyd", "recyd"):
            games.setdefault((c["team"], c["t"]), []).append(c)
    for k, cs in games.items():
        qbs = [c for c in cs if c["market"] == "pyd"]
        rec = sorted([c for c in cs if c["market"] == "recyd"], key=lambda c: -c["line"])[:NFL_TOP]
        if qbs and len(rec) == NFL_TOP:
            qb = max(qbs, key=lambda c: c["line"])  # the starter has the biggest passing line
            out[k] = (sum(c["line"] for c in rec) / qb["line"], qb, rec)
    return out


def nfl_picks(ratios, base, skip, pin):
    """pricey teams: unders on the top 2 receivers (M_UNDER), and the same unders only where Pinnacle's price at
    FanDuel's line also leans under (M_PIN). Cheap teams: overs, tracked separately (M_OVER), they haven't held up."""
    out = []
    for (team, t), (share, qb, rec) in ratios.items():
        if abs(share - base) < NFL_GAP or team in skip:
            continue
        over = share < base
        why = {"qb": qb["name"], "qb_line": qb["line"], "n": len(rec), "sum": round(sum(x["line"] for x in rec), 1),
               "share": round(share, 3), "usual": round(base, 3)}
        for c in [c for c in rec if c["line"] >= NFL_MIN_LINE][:PER_TEAM]:
            pick = dict(c, side="over" if over else "under", price=c["over"] if over else c["under"],
                        other=c["under"] if over else c["over"], gap=round((base - share) / base, 3), why=dict(why))
            if over:
                out.append(dict(pick, method=M_OVER))
                continue
            out.append(dict(pick, method=M_UNDER))
            pq = pin.get(c["key"])
            if pq:  # Pinnacle's fair chance of the under at FanDuel's line
                mv = (pq[1], pq[2]) if pq[0] == c["line"] else shift(pq[0], pq[1], pq[2], c["line"], "recyd")
                if mv:
                    q_under = 1 - novig(*mv)
                    if q_under >= .5:
                        out.append(dict(pick, method=M_PIN, why=dict(why, pin_line=pq[0], pin_under=round(q_under, 3))))
    return out


def nba_ratios(props, games):
    """{(team, tip-off): (share, implied points, top scorers)}: the six biggest points lines added up / team points"""
    pts, out = {}, {}
    for c in props:
        if c["lg"] == "NBA" and c["market"] == "pts":
            pts.setdefault((c["team"], c["t"][:13]), []).append(c)
    for g in games:
        if g["lg"] != "NBA" or g.get("total") is None or g.get("spread_home") is None:
            continue
        for team, home in ((g["home"], True), (g["away"], False)):
            implied = g["total"] / 2 - g["spread_home"] / 2 if home else g["total"] / 2 + g["spread_home"] / 2
            cs = sorted(pts.get((team, g["t"][:13]), []), key=lambda c: -c["line"])[:NBA_TOP]
            if len(cs) == NBA_TOP and implied > 0:
                out[(team, cs[0]["t"])] = (sum(c["line"] for c in cs) / implied, implied, cs)
    return out


def nba_picks(ratios, base, skip):
    out = []
    for (team, t), (r, implied, cs) in ratios.items():
        gap = r / base - 1
        if abs(gap) < NBA_GAP or team in skip:
            continue
        over = gap < 0  # the team's scorers are priced below their share of its expected points
        for c in cs[:PER_TEAM]:
            out.append(dict(c, side="over" if over else "under", price=c["over"] if over else c["under"],
                            other=c["under"] if over else c["over"], method=M_NBA, gap=round(-gap, 3),
                            why={"implied": round(implied, 1), "sum": round(sum(x["line"] for x in cs), 1),
                                 "share": round(r, 3), "usual": round(base, 3)}))
    return out


def skip_teams(lg, data, ctx, props, now):
    """{team: reason}: a good player on the injury report (his absence would fake a signal), and for the NBA the
    second night of a back-to-back (rest decisions are unpredictable)"""
    out = {}
    meta = (data or {}).get(lg)
    if not meta:
        return out
    ix = {c: i for i, c in enumerate(meta["cols"])}
    by_e = {str(p.get("e") or p["id"]): p for p in meta["players"]}
    inj = ((ctx or {}).get("injuries") or {}).get(lg) or {}
    for eid, i in inj.items():
        p = by_e.get(str(eid))
        if not p or i.get("s") not in INJ:
            continue
        if lg == "NFL":
            gs = p["g"][-3:]
            avg = sum(g[ix["recyd"]] or 0 for g in gs) / max(1, len(gs))
            if avg >= NFL_INJ_YDS and gs and p["t"] == i.get("t", p["t"]):
                out[p["t"]] = f"{p['n']} ({i['s'].lower()})"
        else:
            gs = p["g"][-10:]
            avg = sum(g[ix["pts"]] or 0 for g in gs) / max(1, len(gs))
            if avg >= NBA_INJ_PTS and p["t"] == i.get("t", p["t"]):
                out[p["t"]] = f"{p['n']} ({i['s'].lower()})"
    if lg == "NBA":
        last = {}
        for p in meta["players"]:
            if p["g"]:
                last[p["t"]] = max(last.get(p["t"], ""), p["g"][-1][ix["date"]])
        for c in props:
            if c["lg"] == "NBA":
                day = (dt.datetime.fromisoformat(c["t"]) - dt.timedelta(hours=5)).date()
                if last.get(c["team"]) == (day - dt.timedelta(days=1)).isoformat():
                    out.setdefault(c["team"], "second night of a back-to-back")
    return out


def usual(hist, now_vals, prior):
    """the median share over the team-games seen so far (last 300, today's included); the prior until there are 10"""
    vals = [h["r"] for h in hist.values()][-300:] + now_vals
    return st.median(vals) if len(vals) >= 10 else prior


def main():
    now = dt.datetime.now(dt.timezone.utc)
    old = load(OUT, {})
    board = load("fd_board.json", {"props": [], "games": []})
    fresh = bool(board.get("built")) and now - dt.datetime.fromisoformat(board["built"]) < dt.timedelta(hours=3)
    props = [c for c in board.get("props", []) if dt.datetime.fromisoformat(c["t"]) > now] if fresh else []
    # each sport's usual share (one sample per team-game: the last one seen before kickoff)
    hn = {(h["t"], h["team"]): h for h in old.get("nfl_ratios", [])}
    hb = {(h["t"], h["team"]): h for h in old.get("nba_ratios", [])}
    rn, rb = nfl_ratios(props), nba_ratios(props, board.get("games", []))
    now_n = {(t, tm): v[0] for (tm, t), v in rn.items()}
    now_b = {(t, tm): v[0] for (tm, t), v in rb.items()}
    base_n = usual({k: v for k, v in hn.items() if k not in now_n}, list(now_n.values()), NFL_PRIOR)
    base_b = usual({k: v for k, v in hb.items() if k not in now_b}, list(now_b.values()), NBA_PRIOR)
    # NBA's starting share is a guess, so no NBA picks until 10 team-games have been seen (NFL's comes from real lines)
    nba_ok = len({**hb, **{k: 1 for k in now_b}}) >= 10
    data, ctx = load("props_data.json", {}), load("context.json", {})
    skip_n, skip_b = skip_teams("NFL", data, ctx, props, now), skip_teams("NBA", data, ctx, props, now)
    picks = nfl_picks(rn, base_n, skip_n, board.get("pin") or {}) + (nba_picks(rb, base_b, skip_b) if nba_ok else [])
    for (t, tm), r in now_n.items():
        hn[(t, tm)] = {"t": t, "team": tm, "r": round(r, 4)}
    for (t, tm), r in now_b.items():
        hb[(t, tm)] = {"t": t, "team": tm, "r": round(r, 4)}
    if not fresh and old.get("picks"):
        print("no fresh FanDuel board; keeping the previous list")
        picks = [c for c in old["picks"] if dt.datetime.fromisoformat(c["t"]) > now]
    rec = {(e.get("method"), e["key"], e["t"]): e for e in old.get("record", [])}
    for k, e in list(rec.items()):  # pending picks are replaced until kickoff, then locked
        if e["status"] == "pending" and dt.datetime.fromisoformat(e["t"]) > now:
            del rec[k]
    for c in picks:
        rec[(c["method"], c["key"], c["t"])] = dict(c, status="pending", result=None)
    grade = grader(now)
    for e in rec.values():
        if e["status"] == "pending" and now - dt.datetime.fromisoformat(e["t"]) > dt.timedelta(hours=4):
            grade(e)
    record = sorted(rec.values(), key=lambda e: (e["t"], e["name"]))
    summ = {}
    for m in (M_UNDER, M_PIN, M_NBA, M_OVER, "main"):
        # "main" = the methods that count: NFL unders and NBA points (the Pinnacle check is a subset; overs are tracked)
        d = [e for e in record if e["status"] in ("win", "loss") and (e["method"] == m or (m == "main" and e["method"] in (M_UNDER, M_NBA)))]
        w = sum(e["status"] == "win" for e in d)
        summ[m] = {"w": w, "l": len(d) - w, "units": round(sum((dec(e["price"]) - 1) if e["status"] == "win" else -1 for e in d), 2)}
    json.dump({"built": now.isoformat(timespec="minutes"), "started": old.get("started") or now.date().isoformat(),
               "skipped": {"NFL": skip_n, "NBA": skip_b}, "nfl_usual": round(base_n, 4), "nba_usual": round(base_b, 4), "picks": picks, "record": record,
               "summary": summ, "nfl_ratios": sorted(hn.values(), key=lambda h: h["t"])[-400:],
               "nba_ratios": sorted(hb.values(), key=lambda h: h["t"])[-400:]},
              open(OUT, "w"), separators=(",", ":"))
    counts = ", ".join(f"{m} {sum(c['method'] == m for c in picks)}" for m in (M_UNDER, M_PIN, M_OVER, M_NBA))
    print(f"fwarnk: {len(picks)} picks ({counts}); "
          f"skipped NFL {skip_n} NBA {skip_b}; usual share NFL {base_n:.3f} ({len(now_n)} today), "
          f"NBA {base_b:.3f} ({len(now_b)} today); record {summ['main']}")
    for c in picks[:10]:
        print(f"  {c['method']}: {c['name']} {c['side']} {c['line']} {c['label']} {c['price']:+d} gap {c['gap']:+.2f} {c['why']}")


if __name__ == "__main__":
    main()
