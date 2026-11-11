"""Backtest: when a regular NBA teammate sits, who picks up his production? (role-aware absorption)

The live model (picks.py `vacated`) credits a player's over chances with the share of his team's usual points /
rebounds / assists held by teammates who are ruled out, the same for every teammate. This tests whether the boost
depends on role: same position group as the absentee (a guard's shots go to guards), starter vs bench.

Method (props_data.json game logs; a DNP leaves no row, so a regular who has no row on a team's game date sat out):
  * for every team game and every player in it: base = his average over his previous 10 games (what the app uses)
  * absent regulars = teammates who averaged 16+ minutes over the team's previous 10 games, played at least 5 of them,
    and have no row that day; share = his average production / team total
  * U (current): predicted = base * (1 + k * sum of shares)
  * R (role-aware): predicted = base * (1 + sum_k theta_k * shares by role cell), the cells being
    (absentee same position group or not) x (target starter or bench)
  * fit on games before CUT, scored on games from CUT on; scored by RMSE / MAE of the prediction against the actual
    stat, and by how often the over hit against a proxy line (base rounded to .5) when the model boosted by 8%+

Usage: python backtest_nba_absorb.py [CUT=2026-02-01]
"""
import collections
import json
import math
import sys

CUT = sys.argv[1] if len(sys.argv) > 1 else "2026-02-01"
STATS = ("pts", "reb", "ast", "3pm")
LAST = 10
REG_MIN = 16
REG_GP = 5


def grp(p):
    return "G" if p in ("G", "PG", "SG") else "B"      # guards vs bigs/forwards


def build():
    d = json.load(open("props_data.json"))["NBA"]
    cols = d["cols"]
    pl = {}
    teams = collections.defaultdict(lambda: collections.defaultdict(dict))   # team -> date -> pid -> row
    for p in d["players"]:
        pl[p["id"]] = {"t": p["t"], "pos": grp(p["p"]), "n": p["n"]}
        for r in p["g"]:
            g = dict(zip(cols, r))
            if g["po"]:
                continue                          # regular season only
            teams[p["t"]][g["date"]][p["id"]] = g
    # a real team game has most of the rotation in it (single rows are players traded in from elsewhere)
    for t in list(teams):
        for dte in list(teams[t]):
            if len(teams[t][dte]) < 5:
                del teams[t][dte]
    return pl, teams


def samples(pl, teams):
    out = []
    for t, days in teams.items():
        dates = sorted(days)
        hist = collections.defaultdict(list)     # pid -> list of rows (chronological, as played)
        for i, dte in enumerate(dates):
            prev = dates[max(0, i - LAST):i]
            if len(prev) < LAST:
                for pid, g in days[dte].items():
                    hist[pid].append(g)
                continue
            # team's regulars: minutes and production over the previous 10 team games
            reg = {}
            for pid, rows in hist.items():
                rr = [g for g in rows if g["date"] in prev]
                if len(rr) >= REG_GP:
                    avg_min = sum(g["min"] for g in rr) / len(prev)
                    if avg_min >= REG_MIN:
                        reg[pid] = {s: sum(g[s] for g in rr) / len(prev) for s in STATS} | {"min": avg_min}
            tot = {s: sum(v[s] for v in reg.values()) or 1 for s in STATS}
            starters = set(sorted(reg, key=lambda x: -reg[x]["min"])[:5])
            absent = [a for a in reg if a not in days[dte]]
            fresh = {a for a in absent if a in days[prev[-1]]}      # he played the team's previous game: new news
            for pid, g in days[dte].items():
                h = hist[pid]
                if len(h) >= LAST and pid in reg:
                    last = h[-LAST:]
                    base = {s: sum(x[s] for x in last) / LAST for s in STATS}
                    cell = collections.defaultdict(lambda: dict.fromkeys(STATS, 0.0))
                    for a in absent:
                        key = ("same" if pl[a]["pos"] == pl[pid]["pos"] else "diff", "S" if pid in starters else "B",
                               "new" if a in fresh else "old")
                        for s in STATS:
                            cell[key][s] += reg[a][s] / tot[s]
                    out.append({"date": dte, "pid": pid, "t": t, "base": base, "y": {s: g[s] for s in STATS},
                                "cell": {k: dict(v) for k, v in cell.items()}, "n_abs": len(absent)})
            for pid, g in days[dte].items():
                hist[pid].append(g)
    return out


def fit(rows, stat, feats):
    """least squares of (y/base - 1) on the feature columns (no intercept), by normal equations with a small ridge"""
    X, Y, W = [], [], []
    for r in rows:
        if r["base"][stat] < 2:
            continue
        X.append([f(r, stat) for f in feats])
        Y.append(r["y"][stat] / r["base"][stat] - 1)
        W.append(r["base"][stat])        # weight by size so low-volume stats don't dominate the noise
    n = len(feats)
    A = [[sum(w * x[i] * x[j] for x, w in zip(X, W)) + (1e-3 if i == j else 0) for j in range(n)] for i in range(n)]
    b = [sum(w * x[i] * y for x, y, w in zip(X, Y, W)) for i in range(n)]
    for i in range(n):                    # gauss
        piv = max(range(i, n), key=lambda k: abs(A[k][i]))
        A[i], A[piv], b[i], b[piv] = A[piv], A[i], b[piv], b[i]
        for k in range(i + 1, n):
            f = A[k][i] / A[i][i]
            for j in range(i, n):
                A[k][j] -= f * A[i][j]
            b[k] -= f * b[i]
    th = [0.0] * n
    for i in range(n - 1, -1, -1):
        th[i] = (b[i] - sum(A[i][j] * th[j] for j in range(i + 1, n))) / A[i][i]
    return th


def cellsum(keys):
    return lambda r, s: sum(r["cell"].get(k, {}).get(s, 0.0) for k in keys)


ROLE = [(p, t) for p in ("same", "diff") for t in ("S", "B")]
CELLS = [(p, t, f) for f in ("new", "old") for p, t in ROLE]
F_U = [cellsum([c for c in CELLS if c[2] == "new"]), cellsum([c for c in CELLS if c[2] == "old"])]   # new vs long-term absences
F_R = [cellsum([c]) for c in CELLS]


def predict(r, stat, feats, th):
    return r["base"][stat] * (1 + sum(t * f(r, stat) for t, f in zip(th, feats)))


def score(rows, stat, feats, th):
    se = ae = n = 0
    ov = [0, 0]       # over hit vs proxy line when boosted 8%+
    for r in rows:
        b = r["base"][stat]
        if b < 2:
            continue
        p = predict(r, stat, feats, th) if th else b
        y = r["y"][stat]
        se += (p - y) ** 2
        ae += abs(p - y)
        n += 1
        line = round(b * 2) / 2
        if p >= b * 1.08 and y != line and not (line == b and False):
            ov[0 if y > line else 1] += 1
    return math.sqrt(se / n), ae / n, n, ov


def main():
    pl, teams = build()
    rows = samples(pl, teams)
    tr = [r for r in rows if r["date"] < CUT]
    te = [r for r in rows if r["date"] >= CUT]
    print(f"{len(rows)} player-games ({len(tr)} train / {len(te)} test from {CUT}); "
          f"{sum(1 for r in rows if r['n_abs'])} with a regular absent")
    for stat in STATS:
        thU, thR = fit(tr, stat, F_U), fit(tr, stat, F_R)
        b = score(te, stat, F_U, None)
        u = score(te, stat, F_U, thU)
        rr = score(te, stat, F_R, thR)
        print(f"\n{stat}: n={b[2]}  RMSE base {b[0]:.3f}  U {u[0]:.3f}  R {rr[0]:.3f}   MAE base {b[1]:.3f}  U {u[1]:.3f}  R {rr[1]:.3f}")
        print(f"   U k(new,old)={thU[0]:+.2f},{thU[1]:+.2f}   R theta " + "  ".join(f"{'/'.join(c)} {t:+.2f}" for c, t in zip(CELLS, thR)))
        for nm, s in (("U", u), ("R", rr)):
            o = s[3]
            print(f"   {nm}: boosted 8%+ -> over hit {o[0]}-{o[1]}" + (f" ({o[0] / (o[0] + o[1]):.0%})" if o[0] + o[1] else ""))


if __name__ == "__main__":
    main()
