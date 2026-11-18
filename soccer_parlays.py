"""Soccer parlays -> soccer_parlays.json (rebuilt every run, after soccer_data.py).

Same shape as parlays.json so the record (record.py) and the app treat them like the NFL/NBA parlays. Legs are the
Soccer tab's leg pool (soccer.json "legs": starters in goals / shots / shots on target props, best value first).

  * every leg's chance is pulled 5% toward 50% first (the app's chances run a little high)
  * the parlay's chance is the legs' chances multiplied. Two players in the SAME match move together only a little
    (backtest on 8,800 team-games of the app's history: two teammates both hit 1+ shots 2.9% more often than their
    own rates imply, 1+ shots on target 4.4% more, 1+ goals 1.0% more; a player on each side hit together LESS than
    chance: 0.975, 0.952 and 0.883), so same-game legs get those small factors, not a big correlation edge
  * the price is the legs' prices multiplied (an estimate: the book's own parlay price will differ). For same-game
    legs it assumes the book gives back half of a correlation edge
  * parlays are built per ET match day for today and the next three days (all legs of a parlay on the same day); at most ONE same-game parlay per match; a handful of
    different-game parlays; a leg appears in at most REUSE of the listed parlays

Usage: python soccer_parlays.py [soccer_parlays.json]
"""
import datetime as dt
import itertools
import json
import math
import sys
from zoneinfo import ZoneInfo

OUT = sys.argv[1] if len(sys.argv) > 1 else "soccer_parlays.json"
ET = ZoneInfo("America/New_York")
SHRINK = .95
BOOK_GIVES = .5
MIN_EV = -.12      # soccer legs rarely beat their price (the model sees little value at DraftKings' prices), so the bar is "closest to
                   # fair", not a real edge: the page says so and the record shows how they do
MIN_P = {2: .08, 3: .03}   # soccer legs are often long shots (anytime goal), so the chance floor is low; the payout is what they are for
KEEP = {"same": 6, "cross": 6}
SGP_PER_GAME = 1
REUSE = 2
POOL = 24          # best-value legs that are combined
# how often two players of one match hit together vs their own rates multiplied (soccer_hist backtest, see above)
TEAMMATE = {"g": 1.010, "sh": 1.029, "sot": 1.044}
OPPONENT = {"g": .883, "sh": .975, "sot": .952}


def dec_of(price):
    return 1 + (price / 100 if price > 0 else 100 / -price)


def amer(dec):
    return round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))


def pair_factor(a, b):
    mk = a["m"] if a["m"] == b["m"] else min(a["m"], b["m"], key=lambda m: ("g", "sh", "sot").index(m) if m in ("g", "sh", "sot") else 9)
    tab = TEAMMATE if a["team"] == b["team"] else OPPONENT
    return tab.get(mk, 1.0)


def why(a, b, f):
    last = lambda c: c["name"].split()[-1]
    if a["team"] == b["team"]:
        return f"{last(a)} and {last(b)} play for the same team: teammates hit together about {abs(f - 1) * 100:.0f}% more often than chance"
    return f"{last(a)} and {last(b)} are on opposite sides: they hit together about {abs(1 - f) * 100:.0f}% less often than chance"


def combos(legs, min_ev=None):
    min_ev = MIN_EV if min_ev is None else min_ev
    found = {}
    for n in (2, 3):
        for combo in itertools.combinations(legs, n):
            games = {c["ev_id"] for c in combo}
            if len(games) == 1:
                kind = "same"
            elif len(games) == n:
                kind = "cross"
            else:
                continue    # a mix of two in one match and one in another isn't built
            p = math.prod(c["p"] for c in combo)
            dec = math.prod(c["dec"] for c in combo)
            notes, factor = [], 1.0
            if kind == "same":
                for a, b in itertools.combinations(combo, 2):
                    f = pair_factor(a, b)
                    factor *= f
                    notes.append(why(a, b, f))
                p *= factor
                if factor > 1:
                    dec /= 1 + BOOK_GIVES * (factor - 1)
            ev = p * dec - 1
            if ev < min_ev or p < MIN_P[n] or p > .9:
                continue
            first = min(combo, key=lambda c: c["t"])
            pid = "|".join(sorted(c["key"] for c in combo)) + "@" + first["t"]
            found[pid] = {"id": pid, "lg": "SOC", "kind": kind, "n": n, "t": first["t"],
                          "legs": [{"key": c["key"], "lg": "SOC", "id": c["pid"], "name": c["name"], "team": c["team"], "pos": c.get("pos"),
                                    "opp": c["opp"], "home": c["home"], "t": c["t"], "market": c["m"], "m": c["m"], "k": c["k"],
                                    "label": c["label"], "side": "over", "line": c["k"] - .5, "price": c["price"], "ev_id": c["ev_id"],
                                    "comp": c.get("lg"), "league": c.get("league"), "p": round(c["p"], 3)}
                                   for c in sorted(combo, key=lambda c: c["t"])],
                          "p": round(p, 3), "fair": amer(1 / p), "dec": round(dec, 3), "price": amer(dec),
                          "ev": round(ev, 3), "pairs": notes}
    return found


def pick(found):
    """per match day: the best same-game parlay of each match and a handful of different-game parlays"""
    result, used, sgp = [], {}, {}
    for kind in ("same", "cross"):
        kept = 0
        for pa in sorted((x for x in found.values() if x["kind"] == kind), key=lambda x: -x["ev"]):
            if kept >= KEEP[kind]:
                break
            if any(used.get(l["key"], 0) >= REUSE for l in pa["legs"]):
                continue
            if kind == "same":
                g = pa["legs"][0]["ev_id"]
                if sgp.get(g, 0) >= SGP_PER_GAME:
                    continue
                sgp[g] = sgp.get(g, 0) + 1
            for l in pa["legs"]:
                used[l["key"]] = used.get(l["key"], 0) + 1
            result.append(pa)
            kept += 1
    return result


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        s = json.load(open("soccer.json"))
    except Exception:
        s = {}
    pool = s.get("legs") or (s.get("top", []) + s.get("value", []))
    result, nlegs, loose = [], 0, {}
    for day in [now.astimezone(ET).date() + dt.timedelta(days=i) for i in range(4)]:
        legs, seen = [], set()
        for c in sorted(pool, key=lambda c: -c["ev"]):
            t = dt.datetime.fromisoformat(c["t"])
            price = c.get("bp") or c["price"]
            if t <= now or t.astimezone(ET).date() != day or c["pid"] in seen or c["m"] not in TEAMMATE:
                continue
            seen.add(c["pid"])
            legs.append(dict(c, price=price, p=.5 + (c["prob"] - .5) * SHRINK, dec=dec_of(price)))
            if len(legs) == POOL:
                break
        nlegs += len(legs)
        result += pick(combos(legs))
        loose.update(combos(legs, min_ev=-1))
    result.sort(key=lambda x: (x["t"], -x["ev"]))
    # when nothing is close enough to fair, the page still shows the few closest combos (not recorded) so the
    # shortfall is visible: the est. EV on each is how far below fair it is
    listed, near, games = {p["id"] for p in result}, [], set()
    for pa in sorted((x for x in loose.values() if x["id"] not in listed), key=lambda x: -x["ev"]):
        if len(near) >= 4:
            break
        if pa["kind"] == "same" and pa["legs"][0]["ev_id"] in games:
            continue
        if pa["kind"] == "same":
            games.add(pa["legs"][0]["ev_id"])
        near.append(pa)
    json.dump({"built": now.isoformat(timespec="minutes"), "parlays": result, "closest": near}, open(OUT, "w"), separators=(",", ":"))
    print(f"soccer parlays: {nlegs} legs, wrote {OUT}: {len(result)} parlays, {len(near)} closest")


if __name__ == "__main__":
    main()
