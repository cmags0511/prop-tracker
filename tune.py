"""Learn from graded picks: nudge the ranking toward what has actually been winning.

Reads record.json (the app's Top 10 picks and the research's calls, locked at kickoff and graded) and
writes tuning.json, which picks.py applies:

  market    per league + prop type + side (e.g. NFL kicking-points overs): a score multiplier from the
            graded hit rate, shrunk toward break-even (52.4%) with 12 imaginary games so a hot or cold
            week can't swing it, and kept between 0.6 and 1.25. Needs 8+ graded picks.
  factors   per factor (form, matchup, game script, research, Kalshi market...): how often picks won when
            the factor backed them vs when it didn't. A factor that keeps backing losers is weighted
            down, one that keeps backing winners up (0.5 to 1.5). Needs 25+ graded picks on each side.
  research  per confidence level (high / medium / low): how much the research moves a pick (replaces
            the default 1.2 / 1.0 / 0.6), from the graded research calls. Needs 10+ graded calls.

  calibration  the app's percentages checked against every graded slate prop (calib.json, not just the Top 10):
            logit P(over) = c + b * (the model's raw over-logit). b < 1 shrinks over-confident chances toward 50%,
            c shifts every prop toward overs (c > 0) or unders (c < 0). Each prop type also gets its own small
            offset and slope on top. Fit by ridge-penalised logistic regression, pulled toward "no change" so a
            single odd weekend can't swing it.
  factors   (from calib.json once 300+ graded props carry their factor parts) one multiplier per factor, fit
            the same way; otherwise from the Top 10 picks as described above.

Every adjustment is listed in plain English under "notes" so the app can show what changed and why.
Usage: python tune.py [tuning.json]
"""
import json, math, sys, datetime as dt

OUT = sys.argv[1] if len(sys.argv) > 1 else "tuning.json"
BE = 110 / 210  # 52.4%: the win rate needed to break even at -110
PRIOR = 12
LABEL = {"pyd": "passing yards", "cmp": "completions", "att": "pass attempts", "ptd": "passing TDs", "ryd": "rushing yards",
         "car": "rush attempts", "rec": "receptions", "recyd": "receiving yards", "rry": "rush + rec yards",
         "kpts": "kicking points", "fgm": "field goals", "pat": "extra points", "tkl": "tackles", "sck": "sacks",
         "td": "anytime TDs", "pts": "points", "reb": "rebounds", "ast": "assists", "3pm": "threes", "pra": "PRA",
         "pr": "pts + reb", "pa": "pts + ast", "ra": "reb + ast"}
FXNAME = {"form": "recent form", "matchup": "matchup", "game": "game script", "minutes": "minutes trend",
          "news": "injury news", "weather": "wind", "market": "Kalshi market", "research": "research"}
DEFAULT_CONF = {"high": 1.2, "medium": 1.0, "low": .6}


def shrunk(w, l):
    return (w + PRIOR * BE) / (w + l + PRIOR)


CAL_EDGES = [.5, .55, .6, .65, .7, 1.01]


def buckets(rows, key):
    """[[low, high, graded, average predicted chance, actual hit rate], ...] for each chance band with any picks"""
    res = []
    for lo, hi in zip(CAL_EDGES, CAL_EDGES[1:]):
        b = [e for e in rows if lo <= (e.get(key) or 0) < hi]
        if b:
            res.append([lo, min(hi, 1), len(b), round(sum(e[key] for e in b) / len(b), 3),
                        round(sum(e["status"] == "win" for e in b) / len(b), 3)])
    return res


def solve(A, v):
    """A x = v for a small dense system (Gaussian elimination with partial pivoting)"""
    n = len(v)
    M = [row[:] + [v[i]] for i, row in enumerate(A)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        if abs(M[i][i]) < 1e-12:
            return [0.0] * n
        for r in range(n):
            if r != i:
                f = M[r][i] / M[i][i]
                M[r] = [a - f * b for a, b in zip(M[r], M[i])]
    return [M[i][n] / M[i][i] for i in range(n)]


def ridge_logit(X, y, prior, lam, off=None, iters=25):
    """logistic regression y ~ sig(off + X.w), penalised by lam * |w - prior|^2 (Newton's method)"""
    w = list(prior)
    k = len(w)
    off = off or [0.0] * len(y)
    for _ in range(iters):
        g = [2 * lam * (w[j] - prior[j]) for j in range(k)]
        H = [[2 * lam * (i == j) for j in range(k)] for i in range(k)]
        for x, t, o in zip(X, y, off):
            z = o + sum(a * b for a, b in zip(w, x))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            for i in range(k):
                g[i] += (p - t) * x[i]
                for j in range(k):
                    H[i][j] += p * (1 - p) * x[i] * x[j]
        step = solve(H, g)
        w = [a - b for a, b in zip(w, step)]
        if max(abs(b) for b in step) < 1e-6:
            break
    return w


def lg(p):
    p = min(.995, max(.005, p))
    return math.log(p / (1 - p))


def learn(cal, out):
    """self-correction from every graded slate prop: shrink over-confident chances, fix an over/under lean,
    per-prop-type corrections and factor weights"""
    rows = []
    for e in cal:
        x = e.get("x")
        if x is None:  # older entries: the app's chance for its side, before any calibration existed
            x = lg(e["prob"]) * (1 if e["side"] == "over" else -1)
        y = 1.0 if (e["side"] == "over") == (e["status"] == "win") else 0.0
        rows.append((e, x, y))
    n = len(rows)
    if n < 150:
        return
    ys = [y for _, _, y in rows]
    # props on the same day share weather, game scripts and late news, so one big Sunday is worth far less than
    # its prop count: only trust the fit in proportion to how many separate game days it has seen
    days = sum(1 for v in __import__("collections").Counter(e["t"][:10] for e, _, _ in rows).values() if v >= 20)
    trust = days / (days + 2)
    c, b = ridge_logit([[1.0, x] for _, x, _ in rows], ys, [0.0, 1.0], 25.0)
    c, b = c * trust, 1 + (b - 1) * trust
    b = max(.35, min(1.2, b))
    c = max(-.4, min(.4, c))
    base = [c + b * x for _, x, _ in rows]
    mk = {}
    for i, (e, x, y) in enumerate(rows):
        mk.setdefault(f"{e['lg']}|{e['market']}", []).append(i)
    per = {}
    for m, idx in sorted(mk.items()):
        if len(idx) < 30:
            continue
        cm, bm = ridge_logit([[1.0, b * rows[i][1]] for i in idx], [ys[i] for i in idx], [0.0, 1.0], 15.0, [c for _ in idx])
        cm, bm = cm * trust, 1 + (bm - 1) * trust
        cm, bm = max(-.5, min(.5, cm)), max(.3, min(1.5, bm))
        if abs(cm) >= .03 or abs(bm - 1) >= .05:
            per[m] = [round(cm, 3), round(bm, 3)]
            for i in idx:
                base[i] = c + cm + b * bm * rows[i][1]
    out["calibration"] = {"n": n, "days": days, "trust": round(trust, 2), "c": round(c, 3), "b": round(b, 3), "per": per}
    # what the app would have said with these corrections, side by side with what it said
    pred_old = sum(e["prob"] for e, _, _ in rows) / n
    hit = sum(e["status"] == "win" for e, _, _ in rows) / n
    if b < .97:
        out["notes"].append(f"Across {n} graded props the app's chances averaged {pred_old:.0%} but {hit:.0%} hit: "
                            f"its percentages are now pulled toward 50% (confidence x{b:.2f})")
    elif b > 1.03:
        out["notes"].append(f"Across {n} graded props the app was too cautious ({pred_old:.0%} predicted, {hit:.0%} hit): "
                            f"its percentages now spread out more (x{b:.2f})")
    ov = [y for e, _, y in rows if e["side"] == "over"]
    un = [1 - y for e, _, y in rows if e["side"] == "under"]
    if abs(c) >= .03 and ov and un:
        out["notes"].append(f"Overs it backed hit {sum(ov) / len(ov):.0%}, unders {sum(un) / len(un):.0%}: every prop now gets a "
                            f"{'small' if abs(c) < .1 else 'firm'} nudge toward the {'over' if c > 0 else 'under'} before a side is picked")
    for m, (cm, bm) in sorted(per.items(), key=lambda kv: -abs(kv[1][0]) - abs(kv[1][1] - 1)):
        lgn, mid = m.split("|")
        bits = []
        if abs(cm) >= .05:
            bits.append(f"an extra nudge toward the {'over' if cm > 0 else 'under'}")
        if bm <= .9:
            bits.append(f"trusted less (x{bm:.2f}): its edges have played out smaller than predicted")
        elif bm >= 1.1:
            bits.append(f"trusted more (x{bm:.2f})")
        if bits:
            out["notes"].append(f"{lgn} {LABEL.get(mid, mid)}: " + ", ".join(bits))
    # factor weights: needs the factor parts stored with each prop (picks.py since pt-v60)
    fx = [(i, e["f"]) for i, (e, _, _) in enumerate(rows) if isinstance(e.get("f"), dict)]
    names = [f for f in FXNAME if sum(1 for _, d in fx if abs(d.get(f) or 0) > .02) >= 60]
    if len(fx) >= 300 and names:
        pm = {}
        for i, d in fx:
            e = rows[i][0]
            pm[i] = (per.get(f"{e['lg']}|{e['market']}") or [0.0, 1.0])
        X = [[b * pm[i][1] * (d.get(f) or 0) for f in names] for i, d in fx]
        rest = [c + pm[i][0] + b * pm[i][1] * sum(v for f, v in d.items() if f not in names) for i, d in fx]
        w = ridge_logit(X, [ys[i] for i, _ in fx], [1.0] * len(names), 40.0, rest)
        for f, m in zip(names, w):
            m = 1 + (m - 1) * trust
            m = round(max(.5, min(1.5, m)), 3)
            if abs(m - 1) >= .05:
                out["factors"][f] = m
                out["notes"].append(f"{FXNAME[f].capitalize()} has been {'over' if m < 1 else 'under'}-weighted across "
                                    f"{len(fx)} graded props: weighted x{m}")


def main():
    try:
        rec = json.load(open("record.json"))
    except Exception:
        rec = {}
    graded = lambda a: [e for e in a if e.get("status") in ("win", "loss")]
    picks = graded(rec.get("picks", []))
    research = graded(rec.get("research", []))
    out = {"built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
           "graded_picks": len(picks), "graded_research": len(research), "market": {}, "factors": {}, "research_conf": {}, "notes": []}
    # 1. prop type + side
    groups = {}
    for e in picks:
        groups.setdefault(f"{e['lg']}|{e['market']}|{e['side']}", []).append(e["status"] == "win")
    for k, res in sorted(groups.items()):
        w, n = sum(res), len(res)
        if n < 8:
            continue
        mult = round(max(.6, min(1.25, 1 + (shrunk(w, n - w) - BE) * 3)), 3)
        if abs(mult - 1) >= .03:
            out["market"][k] = mult
            lg, m, side = k.split("|")
            out["notes"].append(f"{lg} {LABEL.get(m, m)} {side}s are {w}-{n - w}: ranked {'higher' if mult > 1 else 'lower'} (x{mult})")
    # 2. factors: did picks win more when the factor backed them?
    with_fx = [e for e in picks if isinstance(e.get("factors"), dict)]
    for f in FXNAME:
        sup = [e["status"] == "win" for e in with_fx if (e["factors"].get(f) or 0) > .05]
        ag = [e["status"] == "win" for e in with_fx if (e["factors"].get(f) or 0) < -.05]
        if len(sup) < 25 or len(ag) < 25:
            continue
        diff = shrunk(sum(sup), len(sup) - sum(sup)) - shrunk(sum(ag), len(ag) - sum(ag))
        mult = round(max(.5, min(1.5, 1 + diff * 2)), 3)
        if abs(mult - 1) >= .05:
            out["factors"][f] = mult
            out["notes"].append(f"When {FXNAME[f]} backed a pick it went {sum(sup)}-{len(sup) - sum(sup)}, vs "
                                f"{sum(ag)}-{len(ag) - sum(ag)} when it didn't: weighted x{mult}")
    # 3. research confidence
    for c, base in DEFAULT_CONF.items():
        res = [e["status"] == "win" for e in research if e.get("conf") == c]
        if len(res) < 10:
            continue
        mult = round(max(.2, min(1.6, base * (1 + (shrunk(sum(res), len(res) - sum(res)) - BE) * 3))), 3)
        if abs(mult - base) >= .05:
            out["research_conf"][c] = mult
            out["notes"].append(f"{c.capitalize()}-confidence research calls are {sum(res)}-{len(res) - sum(res)}: "
                                f"their weight goes from {base} to {mult}")
    # 4. self-correction from every graded slate prop (replaces the Top-10-only factor weights when there's enough)
    try:
        cal = [e for e in json.load(open("calib.json")).get("props", []) if e.get("status") in ("win", "loss")]
    except Exception:
        cal = []
    learn(cal, out)
    # 5. probability check: when the app says 60%, does it hit about 60%? (every slate prop, plus Kalshi's own odds)
    out["calib"] = {"n": len(cal), "since": min((e["t"][:10] for e in cal), default=None),
                    "app": buckets(cal, "prob"), "kalshi": buckets([e for e in cal if e.get("kal") is not None], "kal"),
                    "top": buckets([e for e in picks if e.get("prob") is not None], "prob")}
    # a dated log of what changed, for the app's weekly report card ("what the app changed about itself")
    try:
        hist = json.load(open(OUT)).get("history") or []
    except Exception:
        hist = []
    today = out["built"][:10]
    shape = lambda n: __import__("re").sub(r"[\d.]+", "#", n)  # the same adjustment with updated numbers isn't news
    seen = {shape(n) for h in hist for n in h["notes"]}
    new = [n for n in out["notes"] if shape(n) not in seen]
    if new:
        hist = [h for h in hist if h["d"] != today] + [{"d": today, "notes": new}]
    out["history"] = hist[-40:]
    json.dump(out, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}: {len(picks)} graded picks, {len(research)} graded research calls, {len(out['notes'])} adjustments")
    for n in out["notes"]:
        print("  " + n)


if __name__ == "__main__":
    main()
