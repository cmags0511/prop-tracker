"""Best parlays for NFL and NBA -> parlays.json (rebuilt every run, after the last picks.py).

A parlay's expected profit is the product of every leg's (chance x price) minus 1, so a leg that is a bad price by
itself is still a bad price inside a parlay. The one real edge is correlation: two legs that tend to hit together
(a QB's passing yards and his receiver's yards) hit together more often than the product of their chances. So:

  * legs come from picks.json "legs": upcoming NFL/NBA props graded C or better at a real sportsbook quote
  * the parlay's chance is the legs' chances multiplied, bumped (or cut) for each pair in the same game by how those
    two players' stat lines actually moved together in games they both played, blended with a small prior
  * the price is the legs' prices multiplied (an estimate: DraftKings' own parlay price will differ). For
    same-game legs it assumes the book gives back half of the correlation edge, since same-game parlays are priced
    with correlation in mind
  * every leg's chance is pulled 5% toward 50% first (the app's chances run a little high), so each extra leg
    doesn't compound the error

Only combos with a clear edge are kept; the best few per sport go to the app, one leg per player.

Usage: python parlays.py [parlays.json]
"""
import datetime as dt
import itertools
import json
import math
import sys
from zoneinfo import ZoneInfo

from picks import OUT_STATUS, stat

OUT = sys.argv[1] if len(sys.argv) > 1 else "parlays.json"
ET = ZoneInfo("America/New_York")
POOL = 30          # legs per sport that are combined (best edge first)
SHRINK = .95       # each leg's chance is pulled this much toward 50%
SHRINK_LG = {"NFL": .85}   # the app's NFL chances above 60% have run too high, so a harder pull there
PARTNERS = 20      # near-fair unders, and as many overs again (see OVER_PARTNERS), that may join a parlay
OVER_PARTNERS = 15

PARTNER_LINK = 1.03   # a partner must lift the parlay's chance by this much through a same-game pair with another leg
BOOK_GIVES = .5    # share of a same-game correlation edge the book prices in
MIN_EV = {2: .03, 3: .04}
MIN_P = {2: .30, 3: .18}
KEEP = {"same": 4, "cross": 5}   # per sport and kind
REUSE = 2          # a leg may appear in at most this many of the listed parlays
PRIOR_W = 25       # the prior counts as this many shared games
MIN_SHARED = 8

PASS, RECV, RUSH = {"pyd", "cmp", "att", "ptd"}, {"rec", "recyd"}, {"ryd", "car"}


def amer(dec):
    return round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))


def dec_of(price):
    return 1 + (price / 100 if price > 0 else 100 / -price)


def prior(a, b):
    """correlation of two legs' OVERS in the same game (an under flips the sign), from how football works"""
    if a["lg"] != "NFL":
        return 0.0 if a["team"] != b["team"] else -0.03
    ma, mb = a["market"], b["market"]
    same = a["team"] == b["team"]
    if same:
        if (ma in PASS and mb in RECV) or (ma in RECV and mb in PASS):
            return .25
        if (ma in PASS and mb in RUSH) or (ma in RUSH and mb in PASS):
            return -.12
        if ma in RECV and mb in RECV:
            return -.05
        return 0.0
    if ma in PASS and mb in PASS:
        return .08
    return 0.0


def hit(v, line, side):
    if v == line:
        return None
    return (v > line) == (side == "over")


def pair_rho(a, b, rows):
    """(rho, shared games, games both hit): empirical correlation of the two legs' outcomes in games both
    players played, shrunk toward the prior"""
    ra, rb = rows.get(a["id"]), rows.get(b["id"])
    n = both = 0
    xs, ys = [], []
    if ra and rb:
        by = {(r["date"], r["opp"]): r for r in ra}
        for r2 in rb:
            r1 = by.get((r2["date"], r2["opp"]))
            if r1 is None:
                continue
            try:
                h1 = hit(stat(r1, a["market"]), a["line"], a["side"])
                h2 = hit(stat(r2, b["market"]), b["line"], b["side"])
            except Exception:
                continue
            if h1 is None or h2 is None:
                continue
            xs.append(1 if h1 else 0)
            ys.append(1 if h2 else 0)
            both += h1 and h2
    n = len(xs)
    sgn = (1 if a["side"] == "over" else -1) * (1 if b["side"] == "over" else -1)
    pr = prior(a, b) * sgn
    phi = 0.0
    if n >= MIN_SHARED:
        mx, my = sum(xs) / n, sum(ys) / n
        vx, vy = mx * (1 - mx), my * (1 - my)
        if vx > 0 and vy > 0:
            phi = (sum(x * y for x, y in zip(xs, ys)) / n - mx * my) / math.sqrt(vx * vy)
        else:
            n = 0
    else:
        n = 0
    rho = (n * phi + PRIOR_W * pr) / (n + PRIOR_W)
    return max(-.35, min(.5, rho)), n, both


def joint2(pa, pb, rho):
    j = pa * pb + rho * math.sqrt(pa * (1 - pa) * pb * (1 - pb))
    return max(max(0.0, pa + pb - 1) + 1e-6, min(min(pa, pb) - 1e-6, j))


def why(a, b, rho, n, both):
    def last(nm):
        w = [x for x in nm.replace(",", "").split() if x.rstrip(".").lower() not in ("jr", "sr", "ii", "iii", "iv", "v")]
        return w[-1] if w else nm
    side = lambda c: f"{last(c['name'])} {c['side']} {c['line']:g} {c['label'].lower()}"
    if n >= MIN_SHARED:
        return f"{side(a)} and {side(b)} both hit in {both} of {n} games they both played"
    return f"{side(a)} and {side(b)}: {'tend to hit together' if rho > .02 else 'tend to pull apart' if rho < -.02 else 'no clear link'} (typical for this kind of pair)"


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        pk = json.load(open("picks.json"))
    except Exception:
        pk = {}
    legs_all = pk.get("legs") or []
    try:
        data = json.load(open("props_data.json"))
    except Exception:
        data = {}
    rows = {}
    for lg in ("NFL", "NBA"):
        d = data.get(lg)
        if not d:
            continue
        cols = d["cols"]
        rows[lg] = {p["id"]: [dict(zip(cols, r)) for r in p["g"]] for p in d["players"]}
    out_players = set()
    try:
        notes = json.load(open("notes.json"))
        if now - dt.datetime.fromisoformat(notes["updated"].replace("Z", "+00:00")) < dt.timedelta(hours=72):
            out_players = {"|".join(k.split("|")[:2]) for k, v in notes.get("notes", {}).items() if v.get("flag") == "out"}
    except Exception:
        pass

    result = []
    for lg in ("NFL", "NBA"):
        legs = [c for c in legs_all if c["lg"] == lg and dt.datetime.fromisoformat(c["t"]) > now
                and f"{lg}|{c['id']}" not in out_players and c.get("status") not in OUT_STATUS
                and c.get("p_cal") is not None]
        anchors = sorted((c for c in legs if not c.get("partner") and (c.get("edge") or 0) >= .01), key=lambda c: -c["edge"])[:POOL]
        by_edge = sorted((c for c in legs if c.get("partner")), key=lambda c: -c["edge"])
        partners = [c for c in by_edge if c["side"] == "under"][:PARTNERS] + [c for c in by_edge if c["side"] == "over"][:OVER_PARTNERS]
        legs = anchors + partners
        for c in legs:
            c["p"] = .5 + (c["p_cal"] - .5) * SHRINK_LG.get(lg, SHRINK)
            c["dec"] = dec_of(c["price"])
        game = lambda c: (c["t"], *sorted((c["team"], c["opp"])))
        day = lambda c: dt.datetime.fromisoformat(c["t"]).astimezone(ET).date()
        pair_cache = {}

        def pr(a, b):
            k = (a["key"], b["key"])
            if k not in pair_cache:
                pair_cache[k] = pair_rho(a, b, rows.get(lg, {}))
            return pair_cache[k]

        found = {}
        for n in (2, 3):
            for combo in itertools.combinations(legs, n):
                if len({c["id"] for c in combo}) < n or len({day(c) for c in combo}) > 1:
                    continue
                if all(c.get("partner") for c in combo):
                    continue
                p = math.prod(c["p"] for c in combo)
                dec = math.prod(c["dec"] for c in combo)
                factor, notes_, same_pairs = 1.0, [], 0
                mixed = set()
                linked = {c["key"] for c in combo if not c.get("partner")}   # partners count as linked once a pair lifts them
                for a, b in itertools.combinations(combo, 2):
                    if game(a) != game(b):
                        continue
                    same_pairs += 1
                    rho, k, both = pr(a, b)
                    f = joint2(a["p"], b["p"], rho) / (a["p"] * b["p"])
                    factor *= f
                    if f >= PARTNER_LINK:
                        linked |= {a["key"], b["key"]}
                        if a["side"] != b["side"]:
                            mixed |= {a["key"], b["key"]}
                    notes_.append(why(a, b, rho, k, both))
                if any(c["key"] not in linked for c in combo):
                    continue
                if any(c.get("partner") and c["side"] == "over" and c["key"] not in mixed for c in combo):
                    continue    # an over only joins when it pairs well with an under in the parlay    # a near-fair leg that isn't pulled up by one of the others
                if same_pairs and not (.97 <= factor <= 1.8):
                    continue  # legs that work against each other, or a pair the numbers don't support
                p *= factor
                if factor > 1:
                    dec /= 1 + BOOK_GIVES * (factor - 1)
                ev = p * dec - 1
                if ev < MIN_EV[n] or p < MIN_P[n] or p > .9:
                    continue
                kind = "same" if len({game(c) for c in combo}) == 1 else "cross"
                first = min(combo, key=lambda c: c["t"])
                pid = "|".join(sorted(c["key"] for c in combo)) + "@" + first["t"]
                found[pid] = {"id": pid, "lg": lg, "kind": kind, "n": n, "t": first["t"],
                              "legs": [{k: c.get(k) for k in ("key", "lg", "id", "name", "team", "pos", "opp", "home", "t", "market",
                                                              "label", "side", "line", "price", "grade", "p_cal", "edge")}
                                       | {"p": round(c["p"], 3)} for c in sorted(combo, key=lambda c: c["t"])],
                              "p": round(p, 3), "fair": amer(1 / p), "dec": round(dec, 3), "price": amer(dec),
                              "ev": round(ev, 3), "pairs": notes_}
        used = {}
        for kind in ("same", "cross"):
            kept = 0
            for pa in sorted((x for x in found.values() if x["kind"] == kind), key=lambda x: -x["ev"]):
                if kept >= KEEP[kind]:
                    break
                if any(used.get(l["key"], 0) >= REUSE for l in pa["legs"]):
                    continue
                for l in pa["legs"]:
                    used[l["key"]] = used.get(l["key"], 0) + 1
                result.append(pa)
                kept += 1
        print(f"{lg}: {len(legs)} legs, {sum(1 for x in result if x['lg'] == lg)} parlays kept")
    result.sort(key=lambda x: (x["lg"], x["t"], -x["ev"]))
    json.dump({"built": now.isoformat(timespec="minutes"), "parlays": result}, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(result)} parlays")


if __name__ == "__main__":
    main()
