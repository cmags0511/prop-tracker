"""Backtest nhl_model.py on finished games: for each game day, predict every dressed player's props using only the games
before that day, at the lines books usually post, and check the chances against what happened (calibration and log loss).
No historical lines exist in the history, so this tests whether the chances are honest, not whether they beat a price.

Usage: python nhl_backtest.py [nhl_hist.json.gz] [days back, default 45]
"""
import gzip
import json
import math
import sys
from collections import defaultdict

import nhl_model as M

hist = json.load(gzip.open(sys.argv[1] if len(sys.argv) > 1 else "nhl_hist.json.gz", "rt"))
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 45
H = M.Hist(hist)
days = sorted({r[0] for p in H.p.values() for r in p["g"]})
test_days = days[-DAYS:]
print(f"{len(days)} game days, {len(H.p)} skaters, {len(H.g)} goalies; testing the last {len(test_days)} ({test_days[0]} to {test_days[-1]})")


def rows_for(day):
    out = []   # (market, line, mu, outcome(1/0), team, pid)
    for pid, p in H.p.items():
        r = next((x for x in p["g"] if x[0] == day), None)
        if not r:
            continue
        opp = r[1]
        for mk, ix, lines in (("sog", 7, (1.5, 2.5, 3.5, 4.5)), ("pts", None, (.5, 1.5)), ("ast", 6, (.5,)), ("goal", 5, (.5,))):
            mu = H.mu(pid, mk, p["t"], opp, day)
            if mu is None:
                continue
            val = r[5] + r[6] if mk == "pts" else r[ix]
            for ln in lines:
                if mk == "sog" and abs(mu - ln) > 1.1:
                    continue
                if mk in ("pts", "ast") and not (.35 <= mu <= 1.6):
                    continue
                if mk == "goal" and mu < .12:
                    continue
                out.append((mk, ln, mu, 1 if val > ln else 0))
    for gid, g in H.g.items():
        r = next((x for x in g["g"] if x[0] == day), None)
        if not r or r[3] < 40:
            continue
        mu = H.goalie_mu(gid, g["t"], r[1], day)
        if mu is None:
            continue
        ln = math.floor(mu) + .5
        out.append(("sv", ln, mu, 1 if r[5] > ln else 0))
    return out


def evaluate(label):
    res = defaultdict(list)
    for d in test_days:
        for mk, ln, mu, y in rows_for(d):
            res[mk].append((M.p_over(mk, mu, ln), y, mu, ln))
    print(f"\n=== {label}")
    tot_ll = tot_ll0 = tot_n = 0
    for mk, v in sorted(res.items()):
        n = len(v)
        base = sum(y for _, y, *_ in v) / n
        ll = -sum(math.log(min(.999, max(.001, p if y else 1 - p))) for p, y, *_ in v) / n
        ll0 = -sum(math.log(base if y else 1 - base) for _, y, *_ in v) / n
        bins = defaultdict(list)
        for p, y, *_ in v:
            bins[min(int(p * 10), 9)].append((p, y))
        cal = " ".join(f"{b*10}-{b*10+10}%:{len(a)}:{sum(p for p, _ in a)/len(a):.2f}/{sum(y for _, y in a)/len(a):.2f}" for b, a in sorted(bins.items()) if len(a) >= 15)
        print(f"{mk:5s} n={n:5d} base={base:.3f} avg p={sum(p for p,*_ in v)/n:.3f} logloss={ll:.4f} (base-rate only {ll0:.4f})  [bin:n:pred/actual] {cal}")
        tot_ll += ll * n
        tot_ll0 += ll0 * n
        tot_n += n
    print(f"all: logloss {tot_ll/tot_n:.4f} vs base-rate {tot_ll0/tot_n:.4f}")
    return tot_ll / tot_n


evaluate("current settings")
orig = (M.HALF, M.K_PRIOR, M.R_SHOTS, M.R_SAVES, M.OPP_EXP)
for name, setter in (("HALF 5", lambda: setattr(M, "HALF", 5.0)), ("HALF 12", lambda: setattr(M, "HALF", 12.0)), ("HALF 20", lambda: setattr(M, "HALF", 20.0)),
                     ("K_PRIOR 2", lambda: setattr(M, "K_PRIOR", 2.0)), ("K_PRIOR 10", lambda: setattr(M, "K_PRIOR", 10.0)),
                     ("R_SHOTS 7", lambda: setattr(M, "R_SHOTS", 7.0)), ("R_SHOTS 30", lambda: setattr(M, "R_SHOTS", 30.0)),
                     ("R_SAVES 40", lambda: setattr(M, "R_SAVES", 40.0)), ("R_SAVES 250", lambda: setattr(M, "R_SAVES", 250.0)),
                     ("OPP_EXP 0", lambda: setattr(M, "OPP_EXP", 0.0)), ("OPP_EXP 1.2", lambda: setattr(M, "OPP_EXP", 1.2))):
    M.HALF, M.K_PRIOR, M.R_SHOTS, M.R_SAVES, M.OPP_EXP = orig
    setter()
    evaluate(name)
