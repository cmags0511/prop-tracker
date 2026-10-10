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

Every adjustment is listed in plain English under "notes" so the app can show what changed and why.
Usage: python tune.py [tuning.json]
"""
import json, sys, datetime as dt

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
    # 4. probability check: when the app says 60%, does it hit about 60%? (every slate prop, plus Kalshi's own odds)
    try:
        cal = [e for e in json.load(open("calib.json")).get("props", []) if e.get("status") in ("win", "loss")]
    except Exception:
        cal = []
    out["calib"] = {"n": len(cal), "since": min((e["t"][:10] for e in cal), default=None),
                    "app": buckets(cal, "prob"), "kalshi": buckets([e for e in cal if e.get("kal") is not None], "kal"),
                    "top": buckets([e for e in picks if e.get("prob") is not None], "prob")}
    json.dump(out, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}: {len(picks)} graded picks, {len(research)} graded research calls, {len(out['notes'])} adjustments")
    for n in out["notes"]:
        print("  " + n)


if __name__ == "__main__":
    main()
