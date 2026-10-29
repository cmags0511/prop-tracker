"""Soccer team bets: every match bet FanDuel (and DraftKings, through ESPN) prices off the score, checked against
Pinnacle's sharp prices.

Player props can't be beaten at DraftKings or FanDuel (their cut is 25-45%), but team markets carry a much smaller
cut, and Pinnacle prices them sharply. For each match:
  1. Read Pinnacle's prices: 3-way moneyline, every Asian handicap and total line, team totals, for the full match
     and the first half. Remove Pinnacle's margin.
  2. Fit a scoreline model (Dixon-Coles: two Poisson means plus a low-score correction) that reproduces those
     prices. That gives a fair chance for every final (and half-time) score.
  3. Price every FanDuel market that is settled by the score - moneyline, draw no bet, double chance, spreads,
     totals, team totals, both teams to score, result + total, win to nil, exact team goals, winning margin, goal
     bands, the same for the first half - plus DraftKings' moneyline and total from ESPN.
  4. List the bets that pay more than their fair price: 2% expected return or more on markets Pinnacle prices
     itself (result, double chance, draw no bet, spreads, totals, team totals), 5% on ones only the model prices
     (both teams to score, combos, exact goals, margins; nothing longer than +300 there). At most 2 per match.
On the first full run FanDuel's prices averaged 3.5-7% below fair on the main markets and more on the combos, so
most matches have nothing; the list is the few exceptions.
Picks lock at kickoff and are graded from ESPN's final (and half-time) score at the saved price, 1 unit each.
Corners, cards, shots and first-scorer bets aren't covered: there's no sharp price to check them against.
Not betting advice; a paper record.

usage: python soccer_team.py [soccer_team.json]"""
import json, math, os, re, sys, time, datetime as dt, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor

PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_KEY = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"  # the public guest key pinnacle.com's own pages send
FD = "https://sbapi.nj.sportsbook.fanduel.com/api"
FD_KEY = "FhMFpcPWXMeyZxOx"  # the public app key sportsbook.fanduel.com's own pages send
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0", "Accept": "application/json"}
# Pinnacle league -> ESPN league (league games only: cup ties can go to extra time, which these bets don't count)
LEAGUES = {
    "England - Premier League": "eng.1", "Spain - La Liga": "esp.1", "Italy - Serie A": "ita.1",
    "Germany - Bundesliga": "ger.1", "France - Ligue 1": "fra.1", "UEFA - Champions League": "uefa.champions",
    "UEFA - Europa League": "uefa.europa", "UEFA - Conference League": "uefa.europa.conf",
    "USA - Major League Soccer": "usa.1", "England - Championship": "eng.2", "Netherlands - Eredivisie": "ned.1",
    "Portugal - Primeira Liga": "por.1", "Portugal - Liga Portugal": "por.1", "Scotland - Premiership": "sco.1",
    "Mexico - Liga MX": "mex.1", "Mexico - Primera Division": "mex.1", "Brazil - Serie A": "bra.1",
    "Turkey - Super Lig": "tur.1", "Turkey - Süper Lig": "tur.1", "Belgium - Pro League": "bel.1",
    "Belgium - First Division A": "bel.1", "Germany - 2. Bundesliga": "ger.2", "Spain - Segunda Division": "esp.2",
    "Italy - Serie B": "ita.2", "France - Ligue 2": "fra.2", "England - League 1": "eng.3",
    "Saudi Arabia - Pro League": "ksa.1", "Argentina - Liga Pro": "arg.1", "Japan - J1 League": "jpn.1",
}
FD_TABS = ("popular", "goals", "team-props", "half")
AHEAD = dt.timedelta(days=3)
EV_MAIN, EV_MODEL = .02, .05     # expected return needed: markets Pinnacle prices / markets only the model prices
EV_MAX_MAIN = .06                # above this the "edge" is usually a stale price or a data slip: on 24,600 matches, claimed edges of 5%+
                                 # at the best price lost money (5-10%: -3% to -7%; 10%+: -10% to -17%)
MIN_DEC, MAX_DEC, MAX_DEC_MODEL = 1.25, 6.0, 4.0  # draws run to +500; the model's long shots (0-0 etc.) are its least sure
PER_MATCH, TOP_N = 2, 25
FIT_MAX = .02                    # skip a match when the model can't reproduce Pinnacle's prices this closely
G = 11                           # scores 0-10 per team


def get(url, headers=None, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=dict(UA, **(headers or {})))
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if i == tries - 1:
                print(f"  failed {url[:90]}: {e}")
                return None
            time.sleep(1.5 * (i + 1))


def load(f, d):
    try:
        return json.load(open(f))
    except (OSError, ValueError):
        return d


def dec(a):
    return 1 + (a / 100 if a > 0 else 100 / -a)


def am(d):
    return round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1))


def norm(n):
    n = unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[.'\-&]", " ", n).split())


STOP = {"fc", "cf", "afc", "sc", "ac", "as", "ss", "us", "cd", "ud", "rc", "rcd", "club", "de", "the", "city", "united",
        "real", "sporting", "athletic", "atletico", "inter", "1", "04", "05", "fk", "sk", "bk", "if", "ca", "cr"}


def words(n):
    return {w for w in norm(n).split() if len(w) > 2 and w not in STOP}


def same_team(a, b):
    wa, wb = words(a), words(b)
    if wa & wb:
        return True
    na, nb = norm(a).replace(" ", ""), norm(b).replace(" ", "")
    return bool(na and nb) and (na in nb or nb in na)


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------- the scoreline model ----------------
def pois(lam):
    p = [math.exp(-lam)]
    for k in range(1, G):
        p.append(p[-1] * lam / k)
    return p


def matrix(lh, la, rho):
    """P[h][a]: Dixon-Coles (Poisson scores, with 0-0, 1-0, 0-1 and 1-1 corrected by rho), normalised"""
    ph, pa = pois(lh), pois(la)
    P = [[ph[h] * pa[a] for a in range(G)] for h in range(G)]
    P[0][0] *= max(0, 1 - lh * la * rho)
    P[0][1] *= max(0, 1 + lh * rho)
    P[1][0] *= max(0, 1 + la * rho)
    P[1][1] *= max(0, 1 - rho)
    s = sum(map(sum, P))
    return [[x / s for x in r] for r in P]


def dists(P):
    diff, tot, hm, aw = {}, {}, [0] * G, [0] * G
    for h in range(G):
        for a in range(G):
            x = P[h][a]
            diff[h - a] = diff.get(h - a, 0) + x
            tot[h + a] = tot.get(h + a, 0) + x
            hm[h] += x
            aw[a] += x
    return diff, tot, dict(enumerate(hm)), dict(enumerate(aw))


def asian_ev(dist, line, d, sign=1):
    """expected return of a bet at decimal d on (X*sign + line > 0), X ~ dist; quarter lines split in two"""
    halves = [line - .25, line + .25] if abs(line * 4 - round(line * 4)) < 1e-9 and round(line * 4) % 2 else [line]
    ev = 0
    for L in halves:
        for x, p in dist.items():
            m = sign * x + L
            ev += p * ((d - 1) if m > 1e-9 else (-1 if m < -1e-9 else 0)) / len(halves)
    return ev


def shin(inv):
    """margin-free chances from the books' implied chances (1/odds), by Shin's method: it takes more of the margin
    off the long shots than the favourites, which matches how they actually win (24,600 matches, 2021-26: outcomes
    priced under 20% win about 11% less often than the proportional method says; Shin cuts that gap by about half)"""
    tot = sum(inv)
    if tot <= 1:
        return [x / tot for x in inv]
    lo, hi = 0.0, .4
    for _ in range(50):
        z = (lo + hi) / 2
        p = [(math.sqrt(z * z + 4 * (1 - z) * x * x / tot) - z) / (2 * (1 - z)) for x in inv]
        if sum(p) > 1:
            lo = z
        else:
            hi = z
    s = sum(p)
    return [x / s for x in p]


def novig2(a, b):
    pa, pb = shin([1 / dec(a), 1 / dec(b)])
    return 1 / pa, 1 / pb  # fair decimals


def targets(mk, period):
    """Pinnacle's margin-free prices for one match and period, as fitting targets"""
    T = {"ml": None, "lines": []}
    for m in mk:
        if m.get("period") != period or m.get("status") != "open":
            continue
        pr = {p.get("designation"): p for p in m.get("prices") or []}
        ty = m.get("type")
        if ty == "moneyline" and {"home", "away", "draw"} <= set(pr):
            ks = ("home", "draw", "away")
            T["ml"] = dict(zip(ks, shin([1 / dec(pr[k]["price"]) for k in ks])))
        elif ty == "spread" and {"home", "away"} <= set(pr):
            dh, da = novig2(pr["home"]["price"], pr["away"]["price"])
            T["lines"].append(("diff", pr["home"]["points"], dh, 1))
            T["lines"].append(("diff", pr["away"]["points"], da, -1))
        elif ty == "total" and {"over", "under"} <= set(pr):
            do, du = novig2(pr["over"]["price"], pr["under"]["price"])
            L = pr["over"]["points"]
            T["lines"].append(("tot", -L, do, 1))
            T["lines"].append(("tot", L, du, -1))
        elif ty == "team_total" and {"over", "under"} <= set(pr):
            do, du = novig2(pr["over"]["price"], pr["under"]["price"])
            L, side = pr["over"]["points"], m.get("side")
            k = "hm" if side == "home" else "aw"
            T["lines"].append((k, -L, do, 1))
            T["lines"].append((k, L, du, -1))
    return T


def fit(T):
    """(lh, la, rho, rms error) reproducing Pinnacle's prices; None without a moneyline"""
    if not T["ml"]:
        return None
    ml = T["ml"]

    def loss(x):
        lh, la, rho = math.exp(x[0]), math.exp(x[1]), max(-.25, min(.15, x[2]))
        P = matrix(lh, la, rho)
        D = dict(zip(("diff", "tot", "hm", "aw"), dists(P)))
        pd = sum(P[i][i] for i in range(G))
        ph = sum(p for k, p in D["diff"].items() if k > 0)
        err = [(ph - ml["home"]) * 2, (pd - ml["draw"]) * 2, (1 - ph - pd - ml["away"]) * 2]
        for k, L, d, s in T["lines"]:
            err.append(asian_ev(D[k], L, d, s) / d)  # ~ the error in the chance
        return sum(e * e for e in err) / len(err)

    # start: goals from the favourite's edge, total near 2.6
    edge = ml["home"] - ml["away"]
    x = [math.log(max(.2, 1.3 + .95 * edge)), math.log(max(.2, 1.3 - .95 * edge)), -.05]
    best = nelder(loss, x)
    lh, la, rho = math.exp(best[0]), math.exp(best[1]), max(-.25, min(.15, best[2]))
    return lh, la, rho, math.sqrt(loss(best))


def nelder(f, x0, steps=(.15, .15, .05), iters=160):
    pts = [list(x0)] + [[x0[j] + (steps[j] if j == i else 0) for j in range(3)] for i in range(3)]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        o = sorted(range(4), key=lambda i: vals[i])
        pts, vals = [pts[i] for i in o], [vals[i] for i in o]
        if vals[-1] - vals[0] < 1e-10:
            break
        c = [sum(p[j] for p in pts[:3]) / 3 for j in range(3)]
        xr = [c[j] + (c[j] - pts[3][j]) for j in range(3)]
        fr = f(xr)
        if fr < vals[0]:
            xe = [c[j] + 2 * (c[j] - pts[3][j]) for j in range(3)]
            fe = f(xe)
            pts[3], vals[3] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[2]:
            pts[3], vals[3] = xr, fr
        else:
            xc = [c[j] + .5 * (pts[3][j] - c[j]) for j in range(3)]
            fc = f(xc)
            if fc < vals[3]:
                pts[3], vals[3] = xc, fc
            else:
                for i in (1, 2, 3):
                    pts[i] = [pts[0][j] + .5 * (pts[i][j] - pts[0][j]) for j in range(3)]
                    vals[i] = f(pts[i])
    return pts[min(range(4), key=lambda i: vals[i])]


# ---------------- what each bet needs from the score ----------------
def num_in(s):
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def who(runner, home, away):
    r = norm(runner)
    if r in ("draw", "tie"):
        return "draw"
    if r == norm(home) or r == norm(away):
        return "home" if r == norm(home) else "away"
    hit_h, hit_a = same_team(runner, home), same_team(runner, away)
    if hit_h and not hit_a:
        return "home"
    if hit_a and not hit_h:
        return "away"
    return None


def ou(x, line, side):
    return "win" if (x > line) == (side == "over") else "loss"


def settle(mtype, runner, home, away, h, a):
    """'win' / 'loss' / 'push' for this FanDuel bet at final score h-a (or the half-time score for first-half
    markets); None if the bet isn't one this file can price"""
    t, r = mtype, " ".join(re.sub(r"&", " ", (runner or "").lower()).split())
    res = "home" if h > a else "away" if a > h else "draw"
    t1 = t.replace("1ST_HALF_", "").replace("FIRST_HALF_", "").replace("_IN_THE_FIRST_HALF", "").replace("_-_1ST_HALF", "")
    if t in ("WIN-DRAW-WIN", "HALF-TIME_RESULT"):
        w = who(runner, home, away)
        return None if w is None else ("win" if w == res else "loss")
    if t == "DRAW_NO_BET":
        w = who(runner, home, away)
        return None if w is None or w == "draw" else ("push" if res == "draw" else "win" if w == res else "loss")
    if t == "DOUBLE_CHANCE":
        parts = re.split(r"\s+(?:and|or)\s+", runner, flags=re.I)
        if len(parts) != 2:
            return None
        ws = {who(p, home, away) for p in parts}
        return None if None in ws or len(ws) != 2 else ("win" if res in ws else "loss")
    m = re.fullmatch(r"OVER_UNDER_(\d)(\d)", t1)
    if m:
        L = float(f"{m.group(1)}.{m.group(2)}")
        side = "over" if r.startswith("over") else "under" if r.startswith("under") else None
        return side and ou(h + a, L, side)
    m = re.fullmatch(r"OVER/UNDER_(\d+\.5)_GOALS", t1)
    if m:
        side = "over" if "over" in r else "under" if "under" in r else None
        return side and ou(h + a, float(m.group(1)), side)
    m = re.fullmatch(r"(HOME|AWAY)_TEAM_OVER/UNDER_(\d+\.5)", t1)
    if m:
        x = h if m.group(1) == "HOME" else a
        side = "over" if r.startswith("over") else "under" if r.startswith("under") else None
        return side and ou(x, float(m.group(2)), side)
    if t1 == "BOTH_TEAMS_TO_SCORE":
        b = h > 0 and a > 0
        return "win" if (r == "yes") == b else "loss" if r in ("yes", "no") else None
    m = re.fullmatch(r"BOTH_TEAMS_TO_SCORE_&_O/U_(\d\.5)_GOALS", t)
    if m:
        mm = re.fullmatch(r"(yes|no) over (\d\.5)|(yes|no) under (\d\.5)", r)
        if not mm:
            return None
        yes = (mm.group(1) or mm.group(3)) == "yes"
        over = mm.group(1) is not None
        return "win" if ((h > 0 and a > 0) == yes and (h + a > float(m.group(1))) == over) else "loss"
    m = re.fullmatch(r"WDW_&_O/U_(\d\.5)_GOALS", t)
    if m:
        mm = re.fullmatch(r"(.+?) and (over|under) \d\.5", r)
        w = mm and who(mm.group(1), home, away)
        return None if not w else ("win" if w == res and ou(h + a, float(m.group(1)), mm.group(2)) == "win" else "loss")
    if t == "TO_WIN_TO_NIL":
        w = who(runner, home, away)
        return None if w not in ("home", "away") else ("win" if (w == "home" and h > 0 and a == 0) or (w == "away" and a > 0 and h == 0) else "loss")
    m = re.fullmatch(r"(HOME|AWAY)_TEAM_-(\d)\.5_GOALS", t)
    if m:
        mm = re.fullmatch(r"(.+?) ([+-]\d\.5) goals", r)
        w = mm and who(mm.group(1), home, away)
        if not w or w == "draw":
            return None
        x = (h - a if w == "home" else a - h) + float(mm.group(2))
        return "win" if x > 0 else "loss"
    if t1 in ("NUMBER_OF_TEAM_GOALS", "TEAM_GOALS"):
        mm = re.fullmatch(r"(.+?) to score (no|exactly (\d)|(\d) or more) (?:first half )?goals?", r)
        w = mm and who(mm.group(1), home, away)
        if not w or w == "draw":
            return None
        x = h if w == "home" else a
        if mm.group(2) == "no":
            return "win" if x == 0 else "loss"
        if mm.group(3):
            return "win" if x == int(mm.group(3)) else "loss"
        return "win" if x >= int(mm.group(4)) else "loss"
    if t == "WINNING_MARGIN":
        if r == "score draw":
            return "win" if res == "draw" and h > 0 else "loss"
        if r in ("no goal", "no goals", "0 0"):
            return "win" if h == a == 0 else "loss"
        mm = re.fullmatch(r"(.+?) to win by (?:exactly )?(\d+)( or more)? goals?", r)
        w = mm and who(mm.group(1), home, away)
        if not w or w == "draw":
            return None
        x, k = (h - a if w == "home" else a - h), int(mm.group(2))
        return "win" if (x >= k if mm.group(3) else x == k) else "loss"
    if t.startswith("MULTIGOL"):
        if "2ND_HALF" in t:
            return None
        x = h if t.endswith("HOME") else a if t.endswith("AWAY") else h + a
        mm = re.fullmatch(r"(\d+)(?: (\d+))?(\+)?", r.replace("-", " "))
        if not mm:
            return None
        lo = int(mm.group(1))
        hi = 99 if mm.group(3) else int(mm.group(2) or lo)
        return "win" if lo <= x <= hi else "loss"
    if t == "RESULT_&_BOTH_TO_SCORE":
        w = who(runner, home, away)
        return None if w is None else ("win" if w == res and h > 0 and a > 0 else "loss")
    return None


FIRST_HALF = re.compile(r"1ST_HALF|FIRST_HALF|HALF-TIME_RESULT|IN_THE_FIRST_HALF")
MAIN_TYPES = re.compile(r"^(WIN-DRAW-WIN|HALF-TIME_RESULT|DRAW_NO_BET|DOUBLE_CHANCE|OVER_UNDER_\d\d|1ST_HALF_OVER/UNDER_\d\.5_GOALS|"
                        r"(HOME|AWAY)_TEAM_(FIRST_HALF_)?OVER/UNDER_\d\.5|(HOME|AWAY)_TEAM_-\d\.5_GOALS)$")
SKIP = re.compile(r"2ND_HALF|CORNER|CARD|BOOKING|SHOT|PENALTY|SCORER|ASSIST|CORRECT_SCORE|HALF-TIME/FULL-TIME|EACH_HALF|BOTH_HALVES|"
                  r"EITHER_HALF|MOST_GOALS|FIRST_GOAL|LEAD_AT|2_UP|EARLY_PAYOUT|HAT-TRICK|PLAYER|MINUTE")


def chance(P, mtype, runner, home, away):
    """(win, push) chance for one bet; None if it can't be priced"""
    w = pu = 0
    for h in range(G):
        for a in range(G):
            s = settle(mtype, runner, home, away, h, a)
            if s is None:
                return None
            if s == "win":
                w += P[h][a]
            elif s == "push":
                pu += P[h][a]
    return w, pu


def nice(mname, runner, home, away):
    r = runner.strip()
    mname = mname.replace("Home Team", home).replace("Away Team", away)
    m = re.fullmatch(r"(.+?) (First Half )?Over/Under (\d\.5)(?: Goals)?", mname)
    if m and norm(r) in ("over", "under") and m.group(1) not in ("1st Half",):
        return f"{m.group(1)} {r.lower()} {m.group(3)} goals{' (1st half)' if m.group(2) else ''}"
    if norm(r) in ("yes", "no", "over", "under") or re.fullmatch(r"[\d\-+ ]+", r):
        return f"{mname}: {r}"
    if mname.startswith("1st Half") and "1st half" not in r.lower() or mname.startswith("Half-Time"):
        if mname.startswith("Half-Time"):
            return "Level at half-time" if norm(r) == "draw" else f"{r} leading at half-time"
        return f"{r} (1st half)"
    if mname in ("Tie No Bet",):
        return f"{r} (draw no bet)"
    if mname == "Double Chance":
        return f"{r.replace(' And ', ' or ')} (double chance)"
    if mname == "To Win to Nil":
        return f"{r} to win to nil"
    if mname == "Moneyline (3-way)":
        return "Draw" if norm(r) == "draw" else f"{r} to win"
    if mname == "Result & Both to Score":
        return ("Score draw" if norm(r) == "draw" else f"{r} to win") + ", both teams score"
    return r


# ---------------- data ----------------
def pinnacle(now):
    head = {"X-API-Key": PIN_KEY}
    lgs = get(f"{PIN}/sports/29/leagues?all=false", head) or []
    use = [(l["id"], l["name"]) for l in lgs if l.get("name") in LEAGUES and l.get("matchupCount")]
    print(f"Pinnacle: {len(use)} leagues ({', '.join(n for _, n in use)})")

    def one(lg):
        mus = get(f"{PIN}/leagues/{lg[0]}/matchups", head) or []
        mk = get(f"{PIN}/leagues/{lg[0]}/markets/straight", head) or []
        by = {}
        for m in mk:
            by.setdefault(m.get("matchupId"), []).append(m)
        out = []
        for m in mus:
            if m.get("type") != "matchup" or m.get("special") or m.get("units") not in (None, "Regular") or m.get("isLive"):
                continue
            t = ts(m["startTime"])
            if not now < t < now + AHEAD:
                continue
            ps = {p.get("alignment"): p.get("name") for p in m.get("participants") or []}
            if not ps.get("home") or not ps.get("away"):
                continue
            out.append({"id": m["id"], "t": t, "home": ps["home"], "away": ps["away"], "lg": LEAGUES[lg[1]],
                        "league": lg[1].split(" - ", 1)[-1], "mk": by.get(m["id"], [])})
        return out

    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, use))
    return [m for r in res for m in r]


def espn_events(lgs_days):
    def one(j):
        d = get(f"{ESPN}/{j[0]}/scoreboard?dates={j[1]:%Y%m%d}")
        return j[0], (d or {}).get("events", [])
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, lgs_days))
    out = {}
    for lg, evs in res:
        for e in evs:
            out[(lg, e["id"])] = e
    return out


def espn_teams(e):
    c = (e.get("competitions") or [{}])[0]
    t = {x.get("homeAway"): x for x in c.get("competitors") or []}
    return t.get("home") or {}, t.get("away") or {}, c


def dk_offers(e, home, away):
    """DraftKings' 3-way moneyline and match total from ESPN's odds block, as FanDuel-style bets"""
    _, _, c = espn_teams(e)
    o = ((c.get("odds") or [{}])[0]) or {}
    cur = lambda d: ((d or {}).get("close") or {}).get("odds") or ((d or {}).get("open") or {}).get("odds")

    def p(v):
        try:
            return int(str(v).replace("+", "")) if v not in (None, "", "OFF") else (100 if str(v).upper() == "EVEN" else None)
        except ValueError:
            return 100 if str(v).upper() == "EVEN" else None
    out = []
    ml = o.get("moneyline") or {}
    for k, name in (("home", home), ("draw", "Draw"), ("away", away)):
        v = p(cur(ml.get(k)))
        if v:
            out.append(("Moneyline (3-way)", "WIN-DRAW-WIN", name, v))
    tot = o.get("total") or {}
    try:
        L = float(str(((tot.get("over") or {}).get("close") or (tot.get("over") or {}).get("open") or {}).get("line") or "").lstrip("ou"))
    except ValueError:
        L = None
    if L and abs(L * 2 - round(L * 2)) < 1e-9 and round(L * 2) % 2:
        code = f"OVER_UNDER_{int(L)}{int(round(L * 10)) % 10}"
        for k in ("over", "under"):
            v = p(cur(tot.get(k)))
            if v:
                out.append((f"Over/Under {L} Goals", code, f"{k.title()} {L} Goals", v))
    return out


FD_COMPS = re.compile(r"premier league|la liga|serie a|bundesliga|ligue [12]|champions league|europa|conference|mls|"
                      r"championship|eredivisie|primeira liga|scottish premiership|liga mx|mexic|belgian pro|segunda|serie b|"
                      r"league 1|saudi|argentin|j1 league|turkish super", re.I)


def fanduel(now):
    """FanDuel's soccer matches: the sport page, plus the league pages for the leagues Pinnacle is read for"""
    page = get(f"{FD}/content-managed-page?page=SPORT&eventTypeId=1&_ak={FD_KEY}&timezone=America%2FNew_York") or {}
    att = page.get("attachments") or {}
    allev = dict(att.get("events") or {})
    comps = [k for k, v in (att.get("competitions") or {}).items()
             if FD_COMPS.search(v.get("name", "")) and not re.search(r"women|u21|u19|u23|cup|trophy|copa", v.get("name", ""), re.I)]

    def one(cid):
        d = get(f"{FD}/competition-page?competitionId={cid}&eventTypeId=1&_ak={FD_KEY}") or {}
        return (d.get("attachments") or {}).get("events") or {}
    with ThreadPoolExecutor(4) as ex:
        for evs in ex.map(one, comps):
            allev.update(evs)
    evs = [e for e in allev.values() if " v " in e.get("name", "") and now < ts(e["openDate"]) < now + AHEAD]
    print(f"FanDuel: {len(comps)} league pages")
    print(f"FanDuel: {len(evs)} soccer matches in the next {AHEAD.days} days")
    return evs


def fd_markets(eid):
    seen, out = set(), []
    for tab in FD_TABS:
        d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={eid}&tab={tab}") or {}
        for m in ((d.get("attachments") or {}).get("markets") or {}).values():
            if m.get("marketId") in seen or m.get("marketStatus", "OPEN") != "OPEN":
                continue
            seen.add(m.get("marketId"))
            for r in m.get("runners") or []:
                a = ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")
                if a is not None and r.get("runnerStatus", "ACTIVE") == "ACTIVE":
                    out.append((m.get("marketName", ""), m.get("marketType", ""), r.get("runnerName", ""), int(a)))
        time.sleep(.1)
    return out


# ---------------- picks ----------------
def build(now):
    pin = pinnacle(now)
    fds = fanduel(now)
    days = sorted({(m["lg"], (m["t"] - dt.timedelta(hours=6)).date()) for m in pin} |
                  {(m["lg"], (m["t"] + dt.timedelta(hours=6)).date()) for m in pin} | {(m["lg"], m["t"].date()) for m in pin})
    es = espn_events(days)
    cands, fitted, games, todo = [], 0, [], []
    for m in pin:
        fe = [e for e in fds if abs(ts(e["openDate"]) - m["t"]) <= dt.timedelta(minutes=20)
              and " v " in e["name"] and same_team(e["name"].split(" v ")[0], m["home"]) and same_team(e["name"].split(" v ")[1], m["away"])]
        ee = [e for (lg, _), e in es.items() if lg == m["lg"] and abs(ts(e["date"]) - m["t"]) <= dt.timedelta(minutes=20)
              and same_team(espn_teams(e)[0].get("team", {}).get("displayName", ""), m["home"])
              and same_team(espn_teams(e)[1].get("team", {}).get("displayName", ""), m["away"])]
        if len(ee) != 1:
            continue  # can't be graded without ESPN's score
        fit_ft, fit_1h = fit(targets(m["mk"], 0)), fit(targets(m["mk"], 1))
        if not fit_ft or fit_ft[3] > FIT_MAX:
            continue
        fitted += 1
        todo.append((m, ee[0], fe[0] if len(fe) == 1 else None, fit_ft, fit_1h))
    with ThreadPoolExecutor(4) as ex:
        fdm = list(ex.map(lambda j: fd_markets(j[2]["eventId"]) if j[2] else [], todo))
    matched = sum(1 for j in todo if j[2])
    for (m, ev, fe, fit_ft, fit_1h), fdo in zip(todo, fdm):
        P = {0: matrix(*fit_ft[:3]), 1: matrix(*fit_1h[:3]) if fit_1h and fit_1h[3] <= FIT_MAX else None}
        offers = []
        if fe:
            fhome, faway = fe["name"].split(" v ", 1)
            offers += [("FanDuel", fhome, faway) + o for o in fdo]
        offers += [("DraftKings", m["home"], m["away"]) + o for o in dk_offers(ev, m["home"], m["away"])]
        games.append({"t": m["t"].isoformat(timespec="minutes"), "home": m["home"], "away": m["away"], "league": m["league"],
                      "xg": [round(fit_ft[0], 2), round(fit_ft[1], 2)], "fit": round(fit_ft[3], 4), "fd": bool(fe),
                      "n": len(offers)})
        for book, home, away, mname, mtype, runner, price in offers:
            if SKIP.search(mtype):
                continue
            period = 1 if FIRST_HALF.search(mtype) else 0
            if P[period] is None:
                continue
            c = chance(P[period], mtype, runner, home, away)
            if c is None:
                continue
            w, pu = c
            d = dec(price)
            src = "main" if MAIN_TYPES.match(mtype) else "model"
            evr = w * d + pu - 1
            fair_d = (1 - pu) / w if w > 0 else 99
            cands.append({"key": f"{m['id']}|{book}|{mtype}|{norm(runner)}", "t": m["t"].isoformat(timespec="minutes"),
                          "lg": m["lg"], "league": m["league"], "espn": ev["id"], "pin": m["id"], "home": m["home"], "away": m["away"],
                          "fdhome": home, "fdaway": away, "book": book, "market": mname, "mtype": mtype, "runner": runner,
                          "bet": nice(mname, runner, m["home"] if book == "DraftKings" else home, m["away"] if book == "DraftKings" else away),
                          "period": period, "price": price, "prob": round(w, 4), "push": round(pu, 4), "fair": am(fair_d) if fair_d < 99 else None,
                          "ev": round(evr, 4), "src": src, "side": who(runner, home, away) or norm(runner)})
    print(f"{len(pin)} Pinnacle matches, {fitted} fitted and on ESPN, {matched} on FanDuel; {len(cands)} bets priced")
    return cands, games


def choose(cands):
    ok = [c for c in cands if MIN_DEC <= dec(c["price"]) <= (MAX_DEC if c["src"] == "main" else MAX_DEC_MODEL)
          and (EV_MAIN <= c["ev"] <= EV_MAX_MAIN if c["src"] == "main" else c["ev"] >= EV_MODEL)]
    # the same bet at both books: keep the better price
    best = {}
    for c in sorted(ok, key=lambda c: -c["ev"]):
        k = (c["pin"], c["mtype"], c["period"], c["side"])
        best.setdefault(k, c)
    per, out = {}, []
    for c in sorted(best.values(), key=lambda c: -c["ev"]):
        if per.get(c["pin"], 0) >= PER_MATCH:
            continue
        per[c["pin"]] = per.get(c["pin"], 0) + 1
        out.append(c)
    return out[:TOP_N]


def grade(record, now):
    need = [e for e in record if e["status"] == "pending" and now - dt.datetime.fromisoformat(e["t"]) > dt.timedelta(hours=2, minutes=30)]
    if not need:
        return
    days = sorted({(e["lg"], d) for e in need for d in (dt.datetime.fromisoformat(e["t"]).date(),
                                                         (dt.datetime.fromisoformat(e["t"]) - dt.timedelta(hours=8)).date())})
    es = espn_events(days)
    for e in need:
        ev = es.get((e["lg"], e["espn"]))
        if not ev:
            if now - dt.datetime.fromisoformat(e["t"]) > dt.timedelta(days=3):
                e["status"] = "void"
            continue
        h, a, c = espn_teams(ev)
        st = ((c.get("status") or {}).get("type") or {})
        if not st.get("completed"):
            if st.get("state") == "post" or now - dt.datetime.fromisoformat(e["t"]) > dt.timedelta(days=2):
                e["status"] = "void"  # postponed or abandoned
            continue
        if re.search(r"AET|PEN|Extra", (st.get("detail") or "") + (st.get("shortDetail") or "") + st.get("name", ""), re.I):
            e["status"] = "void"  # these bets count the 90 minutes only; ESPN's score includes extra time
            continue
        if e["period"] == 1:  # the half-time score is on the match summary, not the scoreboard
            sm = get(f"{ESPN}/{e['lg']}/summary?event={e['espn']}") or {}
            hc = {x.get("homeAway"): x for x in (((sm.get("header") or {}).get("competitions") or [{}])[0].get("competitors") or [])}
            try:
                sh = int(float(hc["home"]["linescores"][0]["displayValue"]))
                sa = int(float(hc["away"]["linescores"][0]["displayValue"]))
            except (KeyError, IndexError, TypeError, ValueError):
                if now - dt.datetime.fromisoformat(e["t"]) > dt.timedelta(days=3):
                    e["status"] = "void"
                continue  # try again next hour
        else:
            sh, sa = int(h.get("score") or 0), int(a.get("score") or 0)
        s = settle(e["mtype"], e["runner"], e["fdhome"], e["fdaway"], sh, sa)
        e["status"] = s or "void"
        e["result"] = f"{sh}-{sa}"


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "soccer_team.json"
    now = dt.datetime.now(dt.timezone.utc)
    old = load(out, {})
    cands, games = build(now)
    top = choose(cands)
    if not cands and old.get("picks"):
        print("no prices this run; keeping the previous list")
        top = [c for c in old["picks"] if dt.datetime.fromisoformat(c["t"]) > now]
        games = old.get("games", [])
    rec = {(e["key"], e["t"]): e for e in old.get("record", [])}
    for k, e in list(rec.items()):  # not started: replaced by the current list; started: locked
        if e["status"] == "pending" and dt.datetime.fromisoformat(e["t"]) > now:
            del rec[k]
    for c in top:
        rec[(c["key"], c["t"])] = dict(c, status="pending", result=None)
    record = sorted(rec.values(), key=lambda e: (e["t"], -e["ev"]))
    grade(record, now)
    done = [e for e in record if e["status"] in ("win", "loss")]
    units = sum(dec(e["price"]) - 1 if e["status"] == "win" else -1 for e in done)
    print(f"{len(top)} picks; record {sum(e['status'] == 'win' for e in done)}-{sum(e['status'] == 'loss' for e in done)} ({units:+.2f}u)")
    for c in top[:8]:
        print(f"  {c['home']} v {c['away']}: {c['bet']} {c['book']} {c['price']:+d} fair {c['fair']} chance {c['prob']} ev {c['ev']:+.3f} {c['src']}")
    if os.environ.get("ST_DEBUG"):
        json.dump(cands, open("st_cands.json", "w"), separators=(",", ":"))
    json.dump({"built": now.isoformat(timespec="minutes"), "started": old.get("started") or now.date().isoformat(),
               "picks": top, "games": games, "record": record}, open(out, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
