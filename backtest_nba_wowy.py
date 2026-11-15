"""Backtest: player-by-player on/off splits for NBA (who really gains when a given teammate sits).

backtest_nba_absorb.py tested a generic "share of vacated production" boost and found nothing over a player's
last-10 average. That treats every absentee alike and the last-10 average is itself polluted by earlier absences.
This tests the standard on/off (WOWY) approach instead, walk-forward with no look-ahead:

  delta(B, A) = B's average when teammate A sat  -  B's average when A played     (games before the target game only)
  prediction  = B's recent average  +  sum over today's absent regulars A of  delta(B, A) * n_off / (n_off + K)

compared with the plain last-10 and last-25 averages on RMSE / MAE, and on how the over hit against a proxy line
(last-10 average rounded to .5) when the adjustment is large.   Usage: python backtest_nba_wowy.py [CUT=2026-01-15]
"""
import collections
import math
import sys

import backtest_nba_absorb as ab

CUT = sys.argv[1] if len(sys.argv) > 1 else "2026-01-15"
STATS = ("pts", "reb", "ast", "min")
K = 6          # shrinkage: delta counts n_off / (n_off + K)
MIN_OFF = 3
BASE_N = 25


def run():
    pl, teams = ab.build()
    res = collections.defaultdict(list)
    for t, days in teams.items():
        dates = sorted(days)
        hist = collections.defaultdict(list)           # pid -> [(date, row)]
        for i, dte in enumerate(dates):
            prev = dates[max(0, i - 10):i]
            if len(prev) >= 10:
                reg = {}
                for pid, rows in hist.items():
                    rr = [g for d, g in rows if d in prev]
                    if len(rr) >= ab.REG_GP and sum(g["min"] for g in rr) / len(prev) >= ab.REG_MIN:
                        reg[pid] = True
                absent = [a for a in reg if a not in days[dte]]
                for pid, g in days[dte].items():
                    h = hist[pid]
                    if len(h) < 20 or pid not in reg:
                        continue
                    played = {d for d, _ in h}
                    for s in STATS:
                        last10 = [r[s] for _, r in h[-10:]]
                        lastN = [r[s] for _, r in h[-BASE_N:]]
                        b10, bN = sum(last10) / len(last10), sum(lastN) / len(lastN)
                        if b10 < 2 and s != "min":
                            continue
                        adj = 0.0
                        for a in absent:
                            # B's games (before today) with A in / out of the team's lineup that night
                            on = [r[s] for d, r in h if a_in(hist, a, d)]
                            off = [r[s] for d, r in h if not a_in(hist, a, d) and a_known(hist, a, d)]
                            if len(off) >= MIN_OFF and len(on) >= MIN_OFF:
                                n = len(off)
                                adj += (sum(off) / n - sum(on) / len(on)) * n / (n + K)
                        res[s].append({"date": dte, "b10": b10, "bN": bN, "adj": adj, "y": g[s], "n_abs": len(absent)})
            for pid, g in days[dte].items():
                hist[pid].append((dte, g))
    return res


_idx = {}


def a_in(hist, a, d):
    """did teammate a play on date d"""
    key = id(hist[a])
    s = _idx.get(key)
    if s is None or s[0] != len(hist[a]):
        s = _idx[key] = (len(hist[a]), {x for x, _ in hist[a]})
    return d in s[1]


def a_known(hist, a, d):
    """a was on the team's books by date d (has an earlier game), so missing d is an absence not a pre-arrival"""
    h = hist[a]
    return bool(h) and h[0][0] <= d


def main():
    res = run()
    for s in STATS:
        rows = [r for r in res[s] if r["date"] >= CUT]
        if not rows:
            continue
        def rm(f):
            return math.sqrt(sum((f(r) - r["y"]) ** 2 for r in rows) / len(rows)), sum(abs(f(r) - r["y"]) for r in rows) / len(rows)
        print(f"\n{s}: n={len(rows)} ({sum(1 for r in rows if abs(r['adj']) > 1e-9)} with an on/off adjustment)")
        for nm, f in (("last10", lambda r: r["b10"]), ("last25", lambda r: r["bN"]), ("last25+onoff", lambda r: r["bN"] + r["adj"]),
                      ("last10+onoff", lambda r: r["b10"] + r["adj"])):
            a, b = rm(f)
            print(f"   {nm:13} RMSE {a:.3f}  MAE {b:.3f}")
        big = [r for r in rows if r["adj"] >= (1.5 if s != "min" else 2.5)]
        if big:
            ov = sum(1 for r in big if r["y"] > r["b10"] + 0.01)
            print(f"   big boost (adj>=): n={len(big)}  actual above last10: {ov / len(big):.0%}; mean actual - last10 {sum(r['y'] - r['b10'] for r in big) / len(big):+.2f}, mean adj {sum(r['adj'] for r in big) / len(big):+.2f}")
        neg = [r for r in rows if r["adj"] <= -(1.5 if s != "min" else 2.5)]
        if neg:
            print(f"   big drop (adj<=-): n={len(neg)}  mean actual - last10 {sum(r['y'] - r['b10'] for r in neg) / len(neg):+.2f}, mean adj {sum(r['adj'] for r in neg) / len(neg):+.2f}")




def run_all():
    """on/off adjustment for every (player id, date, stat), including the newest games"""
    pl, teams = ab.build()
    out = {}
    for t, days in teams.items():
        dates = sorted(days)
        hist = collections.defaultdict(list)
        for i, dte in enumerate(dates):
            prev = dates[max(0, i - 10):i]
            if len(prev) >= 10:
                reg = {}
                for pid, rows in hist.items():
                    rr = [g for d, g in rows if d in prev]
                    if len(rr) >= ab.REG_GP and sum(g["min"] for g in rr) / len(prev) >= ab.REG_MIN:
                        reg[pid] = True
                absent = [a for a in reg if a not in days[dte]]
                for pid in days[dte]:
                    h = hist[pid]
                    if len(h) < 20:
                        continue
                    for s in ("pts", "reb", "ast"):
                        adj = 0.0
                        for a in absent:
                            on = [r[s] for d, r in h if a_in(hist, a, d)]
                            off = [r[s] for d, r in h if not a_in(hist, a, d) and a_known(hist, a, d)]
                            if len(off) >= MIN_OFF and len(on) >= MIN_OFF:
                                adj += (sum(off) / len(off) - sum(on) / len(on)) * len(off) / (len(off) + K)
                        out[(pid, dte, s)] = adj
            for pid, g in days[dte].items():
                hist[pid].append((dte, g))
    return out


def market_test(lam=0.35):
    """Does the on/off adjustment beat the BOOK? Over rate vs the book's no-vig over chance, by size of the adjustment
    (sum of the stat parts in the prop; lam scales the raw adjustment: big raw adjustments were ~3x too large)."""
    import json
    res = run_all()
    cal = json.load(open("calib.json"))["props"]
    dec = lambda a: a / 100 + 1 if a > 0 else 100 / -a + 1
    parts = {"pts": ("pts",), "reb": ("reb",), "ast": ("ast",), "pa": ("pts", "ast"), "pr": ("pts", "reb"),
             "ra": ("reb", "ast"), "pra": ("pts", "reb", "ast")}
    rows = []
    for e in cal:
        if e["lg"] != "NBA" or e["status"] not in ("win", "loss") or not e.get("po") or e.get("pe") or e["market"] not in parts:
            continue
        vals = [res.get((e["id"], e["t"][:10], s)) for s in parts[e["market"]]]
        if any(v is None for v in vals):
            continue
        io, iu = 1 / dec(e["po"]), 1 / dec(e["pu"])
        over_hit = 1 if ((e["status"] == "win") == (e["side"] == "over")) else 0
        rows.append((sum(vals) * lam, io / (io + iu), over_hit))
    print(f"\nvs the book: {len(rows)} priced NBA props with an adjustment (lam {lam})")
    for lo, hi in ((-99, -2), (-2, -1), (-1, -.3), (-.3, .3), (.3, 1), (1, 2), (2, 99)):
        sel = [r for r in rows if lo <= r[0] < hi]
        if len(sel) >= 40:
            print(f"   adj {lo:+}..{hi:+}: n={len(sel)}  over hit {sum(r[2] for r in sel) / len(sel):.1%}  "
                  f"book over chance {sum(r[1] for r in sel) / len(sel):.1%}  edge {sum(r[2] - r[1] for r in sel) / len(sel):+.1%}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "market":
        market_test()
    else:
        main()
