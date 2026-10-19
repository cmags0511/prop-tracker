"""Billy Walters' game factors and bet sizing, as printed in his book (Gambler, 2023, ch. 22: his values at the end of
the 2022 season), worked out for every NFL game from the nflverse schedule. Used by walters.py.

Factors are in his units: 5 factor points = 1 point of spread (0.2 each). Each one goes to the side it helps:
  S (situations)  turf, division, conference, prime time, coming off Monday night / overtime, 3rd road game in 4, byes
                  (by team strength), playoff byes, Super Bowl winner and loser next season, 2000+ mile trips,
                  short-trip rivalries, body clock (10 a.m. and night kickoffs by home time zone), 2nd straight game
                  2+ time zones away, bounce-back after a 19+ / 29+ point loss
  W (weather)     warm-weather team or cold-climate dome team visiting an outdoor game in the cold, rain
  E (emotional)   0.2 each: a team on a 2-game losing streak (when the other isn't), lost the last meeting, coach or
                  starting QB facing his old team
Left out because they need judgment, not schedule data: matchup / "variable" factors, snow and heavy wind on the
side, each QB's personal weather record, and a team's playoff stakes.

Key numbers: his table of how often NFL games land on each margin. A bet's strength is the share of games landing
between his number and the line (whole numbers count half, a price off -110 shifts the line ~1/8 point per 5 cents,
and a pick that crosses 0 loses one side of 1). Under 5.5% is no play; 5.5% is half a star, up to 3 stars at 15%.
"""
import math, collections as C

# raw nflverse abbreviation -> (lat, lon, time zone: 0 east .. 3 pacific, conference, division)
TEAMS = {
    "BUF": (42.77, -78.79, 0, "AFC", "E"), "MIA": (25.96, -80.24, 0, "AFC", "E"), "NE": (42.09, -71.26, 0, "AFC", "E"),
    "NYJ": (40.81, -74.07, 0, "AFC", "E"), "BAL": (39.28, -76.62, 0, "AFC", "N"), "CIN": (39.10, -84.52, 0, "AFC", "N"),
    "CLE": (41.51, -81.70, 0, "AFC", "N"), "PIT": (40.45, -80.02, 0, "AFC", "N"), "HOU": (29.68, -95.41, 1, "AFC", "S"),
    "IND": (39.76, -86.16, 0, "AFC", "S"), "JAX": (30.32, -81.64, 0, "AFC", "S"), "TEN": (36.17, -86.77, 1, "AFC", "S"),
    "DEN": (39.74, -105.02, 2, "AFC", "W"), "KC": (39.05, -94.48, 1, "AFC", "W"), "LV": (36.09, -115.18, 3, "AFC", "W"),
    "OAK": (37.75, -122.20, 3, "AFC", "W"), "LAC": (33.95, -118.34, 3, "AFC", "W"), "SD": (32.78, -117.12, 3, "AFC", "W"),
    "DAL": (32.75, -97.09, 1, "NFC", "E"), "NYG": (40.81, -74.07, 0, "NFC", "E"), "PHI": (39.90, -75.17, 0, "NFC", "E"),
    "WAS": (38.91, -76.86, 0, "NFC", "E"), "CHI": (41.86, -87.62, 1, "NFC", "N"), "DET": (42.34, -83.05, 0, "NFC", "N"),
    "GB": (44.50, -88.06, 1, "NFC", "N"), "MIN": (44.97, -93.26, 1, "NFC", "N"), "ATL": (33.76, -84.40, 0, "NFC", "S"),
    "CAR": (35.23, -80.85, 0, "NFC", "S"), "NO": (29.95, -90.08, 1, "NFC", "S"), "TB": (27.98, -82.50, 0, "NFC", "S"),
    "ARI": (33.53, -112.26, 2, "NFC", "W"), "LA": (33.95, -118.34, 3, "NFC", "W"), "STL": (38.63, -90.19, 1, "NFC", "W"),
    "SF": (37.40, -121.97, 3, "NFC", "W"), "SEA": (47.60, -122.33, 3, "NFC", "W"),
}
# international sites by nflverse stadium_id prefix: (lat, lon, time zones east (-) / west (+) of US Eastern)
ABROAD = {"LON": (51.56, -0.28, -5), "GER": (48.22, 11.62, -6), "FRA": (50.07, 8.65, -6), "MAD": (40.45, -3.69, -6),
          "MEX": (19.30, -99.15, 1), "SAO": (-23.55, -46.63, -1), "MEL": (-37.82, 144.98, -15), "DUB": (53.34, -6.23, -5),
          "TOR": (43.64, -79.39, 0), "RIO": (-22.91, -43.23, -1)}
# warm-weather teams (outdoors or dome) and dome teams from cold places, for his cold-weather W-factors
WARM = {"ARI", "ATL", "DAL", "HOU", "JAX", "LA", "LAC", "SD", "LV", "MIA", "NO", "TB", "SF", "OAK"}
COLD_DOME = {"DET", "MIN", "IND", "STL"}
# short trips: the visitor gets these points (any Mid-Atlantic/Northeast pair not listed separately is +1)
RIVAL = [({"TB", "JAX", "MIA"}, 1), ({"DAL", "HOU"}, 1), ({"ATL", "CAR"}, 1), ({"LA", "LAC"}, 2), ({"LV", "LA", "LAC"}, 1),
         ({"IND", "CIN"}, 1), ({"NYG", "NYJ"}, 2), ({"BAL", "WAS"}, 2), ({"CHI", "GB"}, 1),
         ({"PHI", "NYG", "NYJ", "WAS", "NE", "BAL", "BUF"}, 1)]
# chance of the final margin landing on each number (his table, rounded %)
KEY = {1: 3, 2: 3, 3: 8, 4: 3, 5: 3, 6: 5, 7: 6, 8: 3, 9: 2, 10: 4, 11: 2, 12: 2, 13: 2, 14: 5, 15: 2, 16: 3, 17: 3, 18: 3}
STARS = [(15, 3), (13, 2.5), (11, 2), (9, 1.5), (7, 1), (5.5, .5)]
PER = .2           # points per factor point
QB_W = .15         # (not used: needs each QB's weather splits)


def grass(s):
    s = (s or "").strip()
    return None if not s else s in ("grass", "dessograss")


def miles(p, q):
    la1, lo1, la2, lo2 = map(math.radians, (p[0], p[1], q[0], q[1]))
    x = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3959 * 2 * math.asin(math.sqrt(x))


def site(g):
    """(lat, lon, time zone) where the game is played"""
    pre = (g.get("stadium_id") or "")[:3]
    if g.get("neutral") and pre in ABROAD:
        return ABROAD[pre]
    t = TEAMS.get(pre) if g.get("neutral") else None
    t = t or TEAMS.get(g.get("rh", g["h"])) or (0, 0, 0)
    return t[0], t[1], t[2]


def hour(g):
    try:
        h, m = g["time"].split(":")
        return int(h) + int(m) / 60
    except Exception:
        return 13.0


class Schedule:
    """every game in kickoff order, so each game's factors look only at what came before it"""

    def __init__(self, games):
        self.games = sorted(games, key=lambda g: (g["day"], g["time"] or ""))
        self.before = {}           # game id -> {team: [earlier games this season ... ]}
        self.turf = {}             # (team, season) -> home surface is grass (from its home games so far)
        self.dome = C.defaultdict(lambda: C.Counter())
        self.sb = {}               # season -> (winner, loser) of that season's Super Bowl
        for g in self.games:
            if g["type"] == "SB" and g.get("margin") is not None:
                w, l = (g["h"], g["a"]) if g["margin"] > 0 else (g["a"], g["h"])
                self.sb[g["season"]] = (w, l)

    def prep(self):
        hist = C.defaultdict(list)    # team -> all its earlier games
        surf = {}
        for g in self.games:
            self.before[g["id"]] = {t: hist[t][-6:] for t in (g["h"], g["a"])}
            self.before[g["id"]]["_meet"] = [x for x in hist[g["h"]][-40:] if g["a"] in (x["h"], x["a"])]
            self.before[g["id"]]["_coach"] = {t: [x for x in hist[t][-60:]] for t in (g["h"], g["a"])}
            for t in (g["h"], g["a"]):
                if (t, g["season"]) not in self.turf and t in surf:
                    self.turf[(t, g["season"])] = surf[t]
            if not g.get("neutral") and grass(g.get("surface")) is not None:
                surf[g["h"]] = grass(g.get("surface"))
                self.turf.setdefault((g["h"], g["season"]), surf[g["h"]])
            if not g.get("neutral"):
                self.dome[g["h"]][g.get("roof") in ("dome", "closed")] += 1
            if g.get("margin") is not None:
                hist[g["h"]].append(g)
                hist[g["a"]].append(g)

    def factors(self, g, rating=lambda t: 0.0, temp=None, rain=None):
        """[(side 'h'/'a', points in his units, label)] for game g; rating(team) sizes byes; temp/rain override the
        schedule's kickoff weather (forecasts for coming games)"""
        h, a, out = g["h"], g["a"], []
        rh, ra = g.get("rh", h), g.get("ra", a)    # the abbreviation at the time, for where the team played
        prev = self.before.get(g["id"], {})
        add = lambda side, v, why: out.append((side, v, why)) if v else None
        other = lambda s: "a" if s == "h" else "h"
        team = {"h": h, "a": a}
        # turf: the visitor's home surface vs this field
        tv, th = self.turf.get((a, g["season"])), grass(g.get("surface"))
        if th is None:
            th = self.turf.get((h, g["season"]))
        if tv is not None and th is not None and not g.get("neutral"):
            add("a", 1, "same turf") if tv == th else add("h", 1, "turf change for visitor")
        ta, tb = TEAMS.get(rh), TEAMS.get(ra)
        if ta and tb:
            if ta[3] == tb[3] and ta[4] == tb[4]:
                add("a", 1, "division visitor")
            if ta[3] != tb[3]:
                add("h", 1, "other conference")
        # prime time and the week before
        wd, hr = g.get("weekday"), hour(g)
        night = hr >= 19
        if not g.get("neutral"):
            add("h", 2 if wd == "Thursday" and night else 4 if wd == "Sunday" and night else 2 if wd == "Monday" else 0,
                f"home {wd} night")
        for s in ("h", "a"):
            p = (prev.get(team[s]) or [None])[-1]
            if not p or p["season"] != g["season"]:
                continue
            was_home = p["h"] == team[s]
            if p.get("weekday") == "Monday":
                v = {("h", True): 0, ("h", False): 4, ("a", True): 6, ("a", False): 8}[(s, was_home)]
                add(other(s), v, f"{team[s]} off Monday night")
            if p.get("ot"):
                add(other(s), 4 if was_home else 2, f"{team[s]} off overtime")
            m = p["margin"] if was_home else -p["margin"]
            if m <= -29:
                add(s, 4, f"{team[s]} lost by {int(-m)}")
            elif m <= -19:
                add(s, 2, f"{team[s]} lost by {int(-m)}")
            # bye: 13+ days off, worth more to better teams and on the road
            rest = g.get("rest_" + s)
            if rest and rest >= 13 and g["type"] == "REG":
                r = rating(team[s])
                v = (4 if r < -2 else 5 if r < 4 else 7) + (s == "a")
                add(s, v, f"{team[s]} off a bye")
            if rest and rest >= 13 and g["type"] == "DIV":
                add(s, 1, f"{team[s]} playoff bye")
        # road trips: 3rd away game in 4, 2nd straight game 2+ time zones from home
        pa = [x for x in prev.get(a) or [] if x["season"] == g["season"]][-3:]
        if len(pa) == 3 and sum(x["a"] == a and not x.get("neutral") for x in pa) >= 2 and not g.get("neutral"):
            add("h", 2, f"{a} 3rd road game in 4")
        here = site(g)
        if tb and pa:
            p = pa[-1]
            if p["h"] != a and abs(site(p)[2] - tb[2]) >= 2 and abs(here[2] - tb[2]) >= 2:
                add("h", 2, f"{a} 2nd straight trip 2+ time zones")
        if tb and miles(tb, here) >= 2000:
            add("h", 1, f"{a} 2000+ miles")
        for pair, v in RIVAL:
            if rh in pair and ra in pair:
                add("a", v, "short trip")
                break
        # body clock: early kickoffs hurt western teams, night games hurt eastern ones (both sides, so it nets out
        # for teams from the same zone)
        if not (g.get("neutral") and (g.get("stadium_id") or "")[:3] in ABROAD):
            for s, t in (("h", ta), ("a", tb)):
                if not t:
                    continue
                if hr < 14:
                    add(other(s), {3: 2, 2: 1}.get(t[2], 0), f"{team[s]} early body clock")
                if night:
                    add(other(s), {0: 6, 1: 3, 2: 1}.get(t[2], 0), f"{team[s]} night body clock")
        # Super Bowl teams the next season
        sb = self.sb.get(g["season"] - 1)
        if sb and g["type"] == "REG":
            for s in ("h", "a"):
                n = len([x for x in prev.get(team[s]) or [] if x["season"] == g["season"]])
                if team[s] == sb[0] and n < 4:
                    add(s, 4 if n == 0 else 2, f"{team[s]} Super Bowl winner")
                if team[s] == sb[1] and n < 4:
                    add(other(s), 4 if n == 0 else 2, f"{team[s]} Super Bowl loser")
        # weather: cold for warm-weather and cold-climate dome visitors at outdoor games, rain helps the visitor
        t_ = temp if temp is not None else g.get("temp")
        outdoor = g.get("roof") in ("outdoors", "open") if temp is None else True
        if t_ is not None and outdoor:
            d = self.dome[a]
            dome_team = d[True] > d[False]
            if ra in WARM:
                v = next((v for lim, v in ((10, 1.75), (15, 1.25), (20, 1), (25, .75), (30, .5), (35, .25)) if t_ <= lim), 0)
                add("h", v, f"{a} warm team in the cold ({t_:.0f}F)")
            elif ra in COLD_DOME and dome_team:
                v = next((v for lim, v in ((10, .75), (20, .5), (30, .25)) if t_ <= lim), 0)
                add("h", v, f"{a} dome team in the cold ({t_:.0f}F)")
        if rain is not None and rain >= 60:
            add("a", .25, "rain")
        # E-factors (1 each = 0.2 points)
        streak = {}
        for s in ("h", "a"):
            ps = [x for x in prev.get(team[s]) or [] if x["season"] == g["season"]][-2:]
            streak[s] = len(ps) == 2 and all((x["margin"] if x["h"] == team[s] else -x["margin"]) < 0 for x in ps)
        if streak["h"] != streak["a"]:
            s = "h" if streak["h"] else "a"
            add(s, 1, f"{team[s]} lost 2 straight")
        meet = [x for x in prev.get("_meet") or [] if g["season"] - x["season"] <= 1]
        if meet and meet[-1]["margin"]:
            x = meet[-1]
            loser = x["a"] if x["margin"] > 0 else x["h"]
            add("h" if loser == h else "a", 1, f"{loser} lost the last meeting")
        for s in ("h", "a"):
            me, opp = team[s], team[other(s)]
            ck, qb = g.get("coach_" + s), g.get("qb_" + s)
            past = [x for x in (prev.get("_coach") or {}).get(opp, []) if g["season"] - x["season"] <= 3]
            side_of = lambda x: "h" if x["h"] == opp else "a"
            if ck and any(x.get("coach_" + side_of(x)) == ck for x in past):
                add(s, 1, f"{me} coach vs his old team")
            if qb and any(x.get("qb_" + side_of(x)) == qb for x in past):
                add(s, 1, f"{me} QB vs his old team")
        return out


def net(fs):
    """home-minus-away factor points, in points of spread"""
    return PER * sum(v if s == "h" else -v for s, v, _ in fs)


def implicit(line, price):
    """the line a -110 price would carry: each 5 cents off -110 moves it about 1/8 point (his table for 3 and 7)"""
    if price is None:
        return line
    cents = (-price - 100) if price < 0 else (100 - price)    # -120 -> 20, +105 -> -5
    return line - (cents - 10) / 5 * .125


def value(fair, line):
    """the share of games that land between our number and the line (both as the side's margin, e.g. -3.5 = laying
    3.5): each whole number counts for the part of [k - .5, k + .5] the gap covers, so a line on the number counts half"""
    lo, hi = sorted((fair, line))
    tot, one = 0.0, []
    for k in range(math.floor(lo), math.ceil(hi) + 1):
        cov = max(0.0, min(hi, k + .5) - max(lo, k - .5))
        if not cov or k == 0:
            continue
        v = KEY.get(abs(k), 1) * cov
        if abs(k) == 1:
            one.append(v)
        else:
            tot += v
    # crossing 0 (an upset pick): only one side of 1 counts
    return tot + (max(one) if lo < 0 < hi and one else sum(one))


def stars(pct):
    return next((s for lim, s in STARS if pct >= lim), 0)
