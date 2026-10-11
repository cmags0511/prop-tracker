"""Calibration check for the soccer model: replay every appearance in soccer_hist.json.gz using only the matches
before it, and compare the predicted chance of each milestone with how often it happened.
(No historical prices are stored, so this tests the stats model on its own; the app also blends in DraftKings' price.)
Usage: python backtest_soccer.py
"""
import gzip, json, math, sys
from soccer_data import priors, lam_for, pois_ge, pos_group, logit, sig, calibrate

TESTS = [("g", 1), ("g", 2), ("a", 1), ("sh", 1), ("sh", 2), ("sh", 3), ("sh", 4), ("sot", 1), ("sot", 2), ("sot", 3),
         ("sv", 1), ("sv", 2), ("sv", 3), ("sv", 4), ("sv", 5), ("sv", 6), ("fc", 1), ("fc", 2), ("fc", 3), ("yc", 1)]
IDX = {"g": 8, "a": 9, "sh": 10, "sot": 11, "fc": 12, "yc": 13, "sv": 15}


def fit(v):
    """p' = sig(a + b * logit(p)): the recalibration that best fits the outcomes (logistic regression, 1 feature)"""
    a, b = 0.0, 1.0
    xs = [logit(p) for p, _ in v]
    ys = [1.0 if h else 0.0 for _, h in v]
    n = len(xs)
    for _ in range(300):
        ga = gb = 0.0
        for x, y in zip(xs, ys):
            e = sig(a + b * x) - y
            ga += e
            gb += e * x
        a -= .5 * ga / n
        b -= .5 * gb / n
    return round(a, 3), round(b, 3)


def main():
    hist = json.load(gzip.open("soccer_hist.json.gz", "rt"))
    pri = priors(hist)
    out = {}
    for p in hist["players"].values():
        rows = sorted(p["g"])
        for i in range(5, len(rows)):
            r = rows[i]
            past = {"pos": p.get("pos"), "g": rows[:i]}
            for stat, k in TESTS:
                if stat == "sv" and pos_group(p.get("pos")) != "G":
                    continue
                if stat != "sv" and pos_group(p.get("pos")) == "G":
                    continue
                lam = lam_for(past, stat, pri, 1.0 if r[6] else 0.0)
                pr = pois_ge(lam, k)
                if "--raw" not in sys.argv:
                    pr = calibrate(stat, k, pr)
                hit = (r[IDX[stat]] or 0) >= k
                out.setdefault((stat, k), []).append((pr, hit))
    if "--raw" in sys.argv:
        print("CAL =", {f"{s}{k}": fit(v) for (s, k), v in out.items()})
    for (stat, k), v in out.items():
        n = len(v)
        pred = sum(a for a, _ in v) / n
        act = sum(1 for _, h in v if h) / n
        line = f"{stat}{k}+ n={n:6d} pred {pred:.3f} actual {act:.3f} |"
        for lo, hi in ((0, .1), (.1, .2), (.2, .35), (.35, .5), (.5, .7), (.7, 1.01)):
            b = [h for a, h in v if lo <= a < hi]
            pb = [a for a, h in v if lo <= a < hi]
            if len(b) >= 30:
                line += f" {lo:.2f}-{hi:.2f}: {sum(pb)/len(pb):.2f}->{sum(b)/len(b):.2f} ({len(b)})"
        print(line)


if __name__ == "__main__":
    main()
