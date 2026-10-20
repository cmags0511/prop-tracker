"""fwarnk: "the math has to add up". A hidden side project that bets FanDuel player props when a team's own player
lines don't add up to what the team as a whole is expected to do. It uses no player predictions and no line moves,
only the book's numbers and how teams split their production.

NFL passing. Every receiving yard is also a passing yard, so a team's receiving lines should keep pace with its QB's
passing line. Add up the team's 4 biggest FanDuel receiving-yards lines and divide by the QB's passing-yards line.
The usual share is learned from the slates (median of the team-games seen, today's included; 0.69 until there are
10: DraftKings lines Oct 9-20 averaged 0.691, sd 0.07). 0.05 or more below the usual, the receivers look cheap: bet
the overs on the team's 2 biggest receiving lines. 0.05 or more above, they look pricey: the unders.
First look (DraftKings lines, Oct 9-20, small and checked after the fact): pricey teams' top 2 receivers went under
about 60-63%, cheap teams' went over only 50%; an earlier version that split the QB's line between receivers by their
recent share went 33-50. So this is a test, not a finding.

NBA points. A team's expected points come from FanDuel's game total and spread (home: total/2 - spread/2). The points
lines of its 6 biggest scorers should be a steady share of that. The usual share is learned the same way (0.80 until
10 team-games). 6% or more below the usual: bet the overs on its 2 biggest lines; 6% or more above: the unders.

At most 2 bets per team; NFL receiving lines of 15.5+ only. Every pick is at FanDuel's line and price (fd_board.json,
saved by lab_market.py the same hour), locked at kickoff and graded from the box score at that price, in fwarnk.json.
"""
import datetime as dt
import json
import statistics as st
import sys

from lab_market import dec, grader, load

OUT = sys.argv[1] if len(sys.argv) > 1 else "fwarnk.json"
NFL_TOP = 4         # a team's biggest receiving lines counted in its share
NFL_PRIOR = .69
NFL_GAP = .05
NFL_MIN_LINE = 15.5
NBA_TOP = 6         # a team's biggest scorers counted in its share
NBA_PRIOR = .80
NBA_GAP = .06
PER_TEAM = 2


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


def nfl_picks(ratios, base):
    out = []
    for (team, t), (share, qb, rec) in ratios.items():
        if abs(share - base) < NFL_GAP:
            continue
        over = share < base
        for c in [c for c in rec if c["line"] >= NFL_MIN_LINE][:PER_TEAM]:
            out.append(dict(c, side="over" if over else "under", price=c["over"] if over else c["under"],
                            other=c["under"] if over else c["over"], method="NFL passing", gap=round((base - share) / base, 3),
                            why={"qb": qb["name"], "qb_line": qb["line"], "n": len(rec), "sum": round(sum(x["line"] for x in rec), 1),
                                 "share": round(share, 3), "usual": round(base, 3)}))
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


def nba_picks(ratios, base):
    out = []
    for (team, t), (r, implied, cs) in ratios.items():
        gap = r / base - 1
        if abs(gap) < NBA_GAP:
            continue
        over = gap < 0  # the team's scorers are priced below their share of its expected points
        for c in cs[:PER_TEAM]:
            out.append(dict(c, side="over" if over else "under", price=c["over"] if over else c["under"],
                            other=c["under"] if over else c["over"], method="NBA points", gap=round(-gap, 3),
                            why={"implied": round(implied, 1), "sum": round(sum(x["line"] for x in cs), 1),
                                 "share": round(r, 3), "usual": round(base, 3)}))
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
    picks = nfl_picks(rn, base_n) + nba_picks(rb, base_b)
    for (t, tm), r in now_n.items():
        hn[(t, tm)] = {"t": t, "team": tm, "r": round(r, 4)}
    for (t, tm), r in now_b.items():
        hb[(t, tm)] = {"t": t, "team": tm, "r": round(r, 4)}
    if not fresh and old.get("picks"):
        print("no fresh FanDuel board; keeping the previous list")
        picks = [c for c in old["picks"] if dt.datetime.fromisoformat(c["t"]) > now]
    rec = {(e["key"], e["t"]): e for e in old.get("record", [])}
    for k, e in list(rec.items()):  # pending picks are replaced until kickoff, then locked
        if e["status"] == "pending" and dt.datetime.fromisoformat(e["t"]) > now:
            del rec[k]
    for c in picks:
        rec[(c["key"], c["t"])] = dict(c, status="pending", result=None)
    grade = grader(now)
    for e in rec.values():
        if e["status"] == "pending" and now - dt.datetime.fromisoformat(e["t"]) > dt.timedelta(hours=4):
            grade(e)
    record = sorted(rec.values(), key=lambda e: (e["t"], e["name"]))
    summ = {}
    for m in ("NFL passing", "NBA points", "all"):
        d = [e for e in record if e["status"] in ("win", "loss") and (m == "all" or e["method"] == m)]
        w = sum(e["status"] == "win" for e in d)
        summ[m] = {"w": w, "l": len(d) - w, "units": round(sum((dec(e["price"]) - 1) if e["status"] == "win" else -1 for e in d), 2)}
    json.dump({"built": now.isoformat(timespec="minutes"), "started": old.get("started") or now.date().isoformat(),
               "nfl_usual": round(base_n, 4), "nba_usual": round(base_b, 4), "picks": picks, "record": record,
               "summary": summ, "nfl_ratios": sorted(hn.values(), key=lambda h: h["t"])[-400:],
               "nba_ratios": sorted(hb.values(), key=lambda h: h["t"])[-400:]},
              open(OUT, "w"), separators=(",", ":"))
    print(f"fwarnk: {len(picks)} picks ({sum(c['method'] == 'NFL passing' for c in picks)} NFL, "
          f"{sum(c['method'] == 'NBA points' for c in picks)} NBA); usual share NFL {base_n:.3f} ({len(now_n)} today), "
          f"NBA {base_b:.3f} ({len(now_b)} today); record {summ['all']}")
    for c in picks[:10]:
        print(f"  {c['method']}: {c['name']} {c['side']} {c['line']} {c['label']} {c['price']:+d} gap {c['gap']:+.2f} {c['why']}")


if __name__ == "__main__":
    main()
