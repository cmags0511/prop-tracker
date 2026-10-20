"""fwarnk: "the math has to add up". A hidden side project that bets FanDuel player props when a team's own player
lines don't add up to what the team as a whole is expected to do. It uses no player predictions and no line moves,
only the books' numbers and how teams split their production.

NFL passing. Every receiving yard is also a passing yard, so a team's receiving lines should keep pace with its QB's
passing line. Add up the FanDuel receiving-yards lines of the team's receivers (3+ needed) and divide by the QB's
passing-yards line. Usually that's about 0.76 (the listed receivers catch about 83% of his yards in reality). Below
0.70 the receivers are cheap: bet the overs on its 2 biggest receiving lines. Above 0.82 they're pricey: the unders.
Replay on DraftKings lines, Oct 9-20 (in sample, small): overs on cheap teams 38-31 (55%), first weekend 50%, second
57%; unders on pricey teams 72-55 (57%). Weak, and a per-receiver version went 33-50, so this is a test, not a finding.

NBA points. A team's expected points come from FanDuel's game total and spread (home: total/2 - spread/2). The points
lines of its six biggest scorers on FanDuel should be a steady share of that. The usual share is learned from the
slate itself (median of the last 200 team-games seen; 0.80 to start). When a team's six are 6%+ below the usual share,
bet the overs on its two biggest lines; 6%+ above, the unders.

At most 2 bets per team; NFL receiving lines of 15.5+ only. Every pick
is at FanDuel's line and price (from fd_board.json, saved by lab_market.py), locked at kickoff and graded from the box
score at that price, in fwarnk.json.
"""
import datetime as dt
import json
import statistics as st
import sys

from lab_market import dec, grader, load

OUT = sys.argv[1] if len(sys.argv) > 1 else "fwarnk.json"
NFL_MID, NFL_LOW, NFL_HIGH = .76, .70, .82  # receivers' lines / QB's line: usual, cheap below, pricey above
NFL_MIN_LINE = 15.5
NBA_TOP = 6         # a team's biggest scorers counted in its share
NBA_GAP = .06       # team's share vs the usual share
NBA_PRIOR = .80
PER_TEAM = 2


def nfl_picks(props, data, now):
    """team-level: the receivers' receiving lines added up, as a share of their QB's passing line"""
    out = []
    games = {}
    for c in props:
        if c["lg"] == "NFL" and c["market"] in ("pyd", "recyd"):
            games.setdefault((c["team"], c["t"]), []).append(c)
    for (team, t), cs in games.items():
        qbs = [c for c in cs if c["market"] == "pyd"]
        rec = sorted([c for c in cs if c["market"] == "recyd"], key=lambda c: -c["line"])
        if not qbs or len(rec) < 3:
            continue
        qb = max(qbs, key=lambda c: c["line"])  # the starter has the biggest passing line
        share = sum(c["line"] for c in rec) / qb["line"]
        over = share < NFL_LOW
        if not over and share <= NFL_HIGH:
            continue
        for c in [c for c in rec if c["line"] >= NFL_MIN_LINE][:PER_TEAM]:  # his biggest receivers
            out.append(dict(c, side="over" if over else "under", price=c["over"] if over else c["under"],
                            other=c["under"] if over else c["over"], method="NFL passing",
                            gap=round((NFL_MID - share) / NFL_MID, 3),
                            why={"qb": qb["name"], "qb_line": qb["line"], "n": len(rec),
                                 "sum": round(sum(x["line"] for x in rec), 1), "share": round(share, 3), "usual": NFL_MID}))
    return out


def nba_picks(props, games, base):
    out, ratios = [], []
    pts = {}
    for c in props:
        if c["lg"] == "NBA" and c["market"] == "pts":
            pts.setdefault((c["team"], c["t"][:13]), []).append(c)
    for g in games:
        if g["lg"] != "NBA" or g.get("total") is None or g.get("spread_home") is None:
            continue
        for team, home in ((g["home"], True), (g["away"], False)):
            implied = g["total"] / 2 - g["spread_home"] / 2 if home else g["total"] / 2 + g["spread_home"] / 2
            cs = sorted(pts.get((team, g["t"][:13]), []), key=lambda c: -c["line"])[:NBA_TOP]
            if len(cs) < NBA_TOP or implied <= 0:
                continue
            r = sum(c["line"] for c in cs) / implied
            ratios.append({"t": g["t"], "team": team, "r": round(r, 4)})
            gap = r / base - 1
            if abs(gap) >= NBA_GAP:
                over = gap < 0  # the team's scorers are priced below their share of its expected points
                for c in cs[:PER_TEAM]:
                    out.append(dict(c, side="over" if over else "under", price=c["over"] if over else c["under"],
                                    other=c["under"] if over else c["over"], method="NBA points", gap=round(-gap, 3),
                                    why={"implied": round(implied, 1), "sum": round(sum(x["line"] for x in cs), 1),
                                         "share": round(r, 3), "usual": round(base, 3)}))
    return out, ratios


def main():
    now = dt.datetime.now(dt.timezone.utc)
    old = load(OUT, {})
    board = load("fd_board.json", {"props": [], "games": []})
    data = load("props_data.json", {})
    fresh = board.get("built") and now - dt.datetime.fromisoformat(board["built"]) < dt.timedelta(hours=3)
    props = [c for c in board.get("props", []) if dt.datetime.fromisoformat(c["t"]) > now] if fresh else []
    # the usual NBA share, learned from earlier slates (one sample per team-game, the last one seen before tip-off)
    hist = {(h["t"], h["team"]): h for h in old.get("nba_ratios", [])}
    base = st.median([h["r"] for h in hist.values()][-200:]) if len(hist) >= 20 else NBA_PRIOR
    picks = nfl_picks(props, data, now) if data.get("NFL") else []
    nba, ratios = nba_picks(props, board.get("games", []), base)
    picks += nba
    for r in ratios:
        hist[(r["t"], r["team"])] = r
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
               "nba_usual": round(base, 4), "picks": picks, "record": record, "summary": summ,
               "nba_ratios": sorted(hist.values(), key=lambda h: h["t"])[-400:]},
              open(OUT, "w"), separators=(",", ":"))
    print(f"fwarnk: {len(picks)} picks ({sum(c['method'] == 'NFL passing' for c in picks)} NFL, "
          f"{sum(c['method'] == 'NBA points' for c in picks)} NBA); NBA usual share {base:.3f}; record {summ['all']}")
    for c in picks[:8]:
        print(f"  {c['method']}: {c['name']} {c['side']} {c['line']} {c['label']} {c['price']:+d} gap {c['gap']:+.2f} {c['why']}")


if __name__ == "__main__":
    main()
