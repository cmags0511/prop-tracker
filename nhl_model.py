"""NHL chances from the box-score history (nhl_data.py): a stats-only model for shots on goal, points, assists,
anytime goals and goalie saves.

Each player's per-game rate is a weighted average of his recent games (every game back counts 0.5^(1/HALF) as much
as the one after it, so last season still counts a little), shrunk toward his position's average with K games' worth of
prior. Shots are then scaled by how many shots the opponent allows and goals/points/assists by how many goals it
allows (each team's last 15 games, shrunk toward the league and softened by an exponent). Counts are modelled as
Poisson (points, assists, goals) or negative binomial (shots, saves), whose extra spread comes from nhl_backtest.py.
A goalie's saves = the shots his team is expected to face (the opponent's shots for against his team's shots allowed)
times his save percentage, shrunk toward the league's.

The chance of "over" a line L is P(count >= floor(L) + 1).
"""
import datetime as dt
import math

HALF = {"s": 10.0, "g": 40.0, "a": 40.0}      # games for a game's weight to halve, per stat (shots, goals, assists); from nhl_backtest.py
K_PRIOR = {"s": 30.0, "g": 30.0, "a": 5.0}    # games' worth of position-average prior mixed into each rate
OPP_N, OPP_EXP = 10.0, .7
R_SHOTS, R_SAVES = 14.0, 90.0   # negative-binomial size (bigger = closer to Poisson); set from nhl_backtest.py
SV_PRIOR_SHOTS = 300.0          # shots' worth of league-average save percentage mixed into a goalie's own

MARKETS = {"sog": "Shots on goal", "pts": "Points", "ast": "Assists", "goal": "Anytime goal", "sv": "Saves"}


def pois_tail(k, mu):
    """P(X >= k), X ~ Poisson(mu)"""
    if k <= 0:
        return 1.0
    mu = max(mu, 1e-6)
    p, c = math.exp(-mu), 0.0
    for i in range(k):
        c += p
        p *= mu / (i + 1)
    return max(0.0, 1 - c)


def nb_tail(k, mu, r):
    """P(X >= k), X ~ negative binomial with mean mu and size r"""
    if k <= 0:
        return 1.0
    mu = max(mu, 1e-6)
    q = mu / (r + mu)
    p, c = (1 - q) ** r, 0.0
    for i in range(k):
        c += p
        p *= (i + r) / (i + 1) * q
    return max(0.0, 1 - c)


def p_over(market, mu, line):
    k = int(math.floor(line)) + 1
    if market in ("sog", "sv"):
        return nb_tail(k, mu, R_SHOTS if market == "sog" else R_SAVES)
    return pois_tail(k, mu)


class Hist:
    def __init__(self, h):
        self.p, self.g, self.t = h["players"], h["goalies"], h["teams"]
        self.names = h.get("names", {})
        self.upcoming = h.get("upcoming", [])
        agg = {"F": [0, 0, 0, 0, 0], "D": [0, 0, 0, 0, 0]}   # games, goals, assists, shots, toi
        for p in self.p.values():
            a = agg["D" if p["p"] == "D" else "F"]
            for r in p["g"]:
                a[0] += 1
                a[1] += r[5]
                a[2] += r[6]
                a[3] += r[7]
                a[4] += r[3]
        self.lg = {k: {"g": v[1] / max(1, v[0]), "a": v[2] / max(1, v[0]), "s": v[3] / max(1, v[0]), "toi": v[4] / max(1, v[0])} for k, v in agg.items()}
        tg = [r for rows in self.t.values() for r in rows]
        n = max(1, len(tg))
        self.lg_sf = sum(r[3] for r in tg) / n      # shots a team takes per game
        self.lg_gf = sum(r[5] for r in tg) / n
        gs = [r for p in self.g.values() for r in p["g"]]
        self.lg_sv = sum(r[5] for r in gs) / max(1, sum(r[4] for r in gs))

    @staticmethod
    def _before(rows, date):
        return [r for r in rows if r[0] < date]

    def rate(self, pid, date):
        """weighted per-game rates (goals, assists, shots, toi) shrunk toward the position average, and games used"""
        p = self.p.get(pid)
        if not p:
            return None
        rows = self._before(p["g"], date)
        if not rows:
            return None
        pr = self.lg["D" if p["p"] == "D" else "F"]
        n = len(rows)
        out = {"n": n}
        for key, ix, nm in (("s", 7, "s"), ("g", 5, "g"), ("a", 6, "a")):
            w = [0.5 ** (i / HALF[key]) for i in range(n)][::-1]
            sw = sum(w)
            v = sum(wi * r[ix] for wi, r in zip(w, rows)) / sw
            out[key] = (sw * v + K_PRIOR[key] * pr[nm]) / (sw + K_PRIOR[key])
            out["raw_" + key] = v
        out["toi"] = sum(r[3] for r in rows[-10:]) / len(rows[-10:])
        return out

    def team_factor(self, team, date, kind):
        """how many shots ('sa') or goals ('ga') `team` allows vs the league, shrunk and softened"""
        rows = self._before(self.t.get(team, []), date)[-15:]
        if not rows:
            return 1.0
        ix, lgv = (4, self.lg_sf) if kind == "sa" else (6, self.lg_gf)
        v = sum(r[ix] for r in rows) / len(rows)
        v = (len(rows) * v + OPP_N * lgv) / (len(rows) + OPP_N)
        return (v / lgv) ** OPP_EXP

    def team_for(self, team, date, kind):
        rows = self._before(self.t.get(team, []), date)[-15:]
        if not rows:
            return 1.0
        ix, lgv = (3, self.lg_sf) if kind == "sf" else (5, self.lg_gf)
        v = sum(r[ix] for r in rows) / len(rows)
        v = (len(rows) * v + OPP_N * lgv) / (len(rows) + OPP_N)
        return v / lgv

    def skater_mu(self, pid, market, opp, date):
        r = self.rate(pid, date)
        if not r or r["n"] < 3:
            return None
        if market == "sog":
            return r["s"] * self.team_factor(opp, date, "sa")
        gf = self.team_factor(opp, date, "ga")
        if market == "goal":
            return r["g"] * gf
        if market == "ast":
            return r["a"] * gf
        if market == "pts":
            return (r["g"] + r["a"]) * gf
        return None

    def goalie_mu(self, gid, team, opp, date):
        """expected saves for goalie `gid` of `team` against `opp`"""
        g = self.g.get(gid)
        if not g:
            return None
        rows = self._before(g["g"], date)
        if len(rows) < 3:
            return None
        sa, sv = sum(r[4] for r in rows[-20:]), sum(r[5] for r in rows[-20:])
        svp = (sv + SV_PRIOR_SHOTS * self.lg_sv) / (sa + SV_PRIOR_SHOTS)
        shots = self.lg_sf * self.team_for(opp, date, "sf") * self.team_factor(team, date, "sa")
        return shots * svp

    def mu(self, pid, market, team, opp, date):
        return self.goalie_mu(pid, team, opp, date) if market == "sv" else self.skater_mu(pid, market, opp, date)
