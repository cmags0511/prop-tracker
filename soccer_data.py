"""Soccer player props: match history, upcoming matches, DraftKings prices (via ESPN) and the app's model.

Every league ESPN carries DraftKings soccer props for. For each upcoming match (next 3 days) it reads the
priced player props (anytime goalscorer, shots, shots on target, assists, keeper saves, fouls, cards), estimates
each player's chance from his recent matches, and works out the expected profit at DraftKings' price.

Files
  soccer_hist.json.gz  match-by-match player stats (all competitions), built up run by run
  soccer.json          what the app shows: upcoming matches, priced props with the model's chance and expected
                       profit, the Top 10 lists, and recent results for grading tracked picks

Model (see backtest_soccer.py): each stat is a Poisson count per appearance. His rate as a starter and as a sub
come from his last 12 appearances (shrunk toward his position's average), mixed by how often he's started his
team's recent matches (or the confirmed lineup, when ESPN has it). Goals, assists, shots and shots on target are
scaled by his team's expected goals from DraftKings' match total and moneylines; keeper saves by the opponent's.
The model's chance is then blended with DraftKings' price (log-odds, MKT_W), because the book knows things the box
scores don't (injuries, rotation), and a tiny edge from a model alone is mostly noise.

Usage: python soccer_data.py [--light] [--days-back N]
  --light   prices and lineups only (no new history), for the hourly refresh
"""
import gzip, json, math, sys, time, datetime as dt
import urllib.request
from concurrent.futures import ThreadPoolExecutor

LEAGUES = {
    "eng.1": "Premier League", "esp.1": "La Liga", "ita.1": "Serie A", "ger.1": "Bundesliga", "fra.1": "Ligue 1",
    "usa.1": "MLS", "uefa.champions": "Champions League", "uefa.europa": "Europa League",
    "uefa.europa.conf": "Conference League", "mex.1": "Liga MX", "ned.1": "Eredivisie", "por.1": "Primeira Liga",
    "eng.2": "Championship", "bra.1": "Brasileirão", "arg.1": "Argentina", "sco.1": "Scottish Prem",
    "tur.1": "Süper Lig", "bel.1": "Belgian Pro League", "aut.1": "Austria", "sui.1": "Switzerland",
    "den.1": "Denmark", "gre.1": "Greece", "nor.1": "Norway", "swe.1": "Sweden", "jpn.1": "J1 League",
    "ksa.1": "Saudi Pro League", "aus.1": "A-League", "eng.3": "League One", "esp.2": "La Liga 2",
    "ita.2": "Serie B", "ger.2": "2. Bundesliga", "fra.2": "Ligue 2", "eng.fa": "FA Cup",
    "eng.league_cup": "Carabao Cup", "esp.copa_del_rey": "Copa del Rey", "ger.dfb_pokal": "DFB-Pokal",
    "ita.coppa_italia": "Coppa Italia", "fra.coupe_de_france": "Coupe de France", "usa.open": "US Open Cup",
    "concacaf.champions": "CONCACAF Champions Cup", "conmebol.libertadores": "Libertadores",
    "conmebol.sudamericana": "Sudamericana", "uefa.nations": "Nations League", "fifa.worldq.uefa": "WC Qual (UEFA)",
    "fifa.worldq.conmebol": "WC Qual (CONMEBOL)", "fifa.worldq.concacaf": "WC Qual (CONCACAF)",
    "fifa.friendly": "Friendlies", "fifa.world": "World Cup", "usa.nwsl": "NWSL", "eng.w.1": "WSL",
}
SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
CORE = "https://sports.core.api.espn.com/v2/sports/soccer/leagues"
H = {"User-Agent": "Mozilla/5.0 (prop-tracker)", "Accept": "application/json"}
HIST = "soccer_hist.json.gz"
NATIONAL = ("fifa.", "uefa.nations", "uefa.euro", "conmebol.america", "concacaf.gold", "concacaf.nations")
OUT = "soccer.json"
CLOSE = "soccer_close.json"  # the last DraftKings price seen before each kickoff (closing line value)
AHEAD_DAYS = 3
KEEP_DAYS = 400          # history kept per player
MAX_ROWS = 30            # matches kept per player
# row layout in soccer_hist players[aid]["g"]
COLS = ["date", "lg", "ev", "team", "opp", "home", "start", "sub", "g", "a", "sh", "sot", "fc", "yc", "rc", "sv", "gc"]
# DraftKings markets read from ESPN, and the stat each one settles on
MARKETS = {"Anytime Goalscorer": "g", "To Score 2+ Goals": "g2", "Shots Milestones": "sh",
           "Shots on Target Milestones": "sot", "Assists Milestones": "a", "Goalkeeper Saves Milestones": "sv",
           "Fouls Committed Milestones": "fc", "To Receive a Card": "card"}
LABEL = {"g": "Anytime goal", "sh": "Shots", "sot": "Shots on target", "a": "Assists", "sv": "Saves",
         "fc": "Fouls", "card": "Booked"}
ATTACK = {"g", "a", "sh", "sot"}
MKT_W = .5               # log-odds weight on DraftKings' price (margin removed) in the final chance
MARGIN = {"g": .10, "sh": .07, "sot": .08, "a": .10, "sv": .07, "fc": .07, "card": .10}  # typical book margin
K_START, K_SUB = 4, 3    # shrinkage (pseudo-appearances) toward the position average


FAILED = "failed"  # marker: the request didn't go through (rate limit, timeout), unlike a real "no data"


def get(url, tries=4):
    """JSON, None when ESPN has nothing (400/404), or FAILED when it never answered properly"""
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
        except Exception:
            pass
        time.sleep(2 ** (i + 1))
    return FAILED


def pmap(fn, items, workers=6):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def scoreboards(days):
    """{lg: [event, ...]} for the given dates"""
    jobs = [(lg, d) for lg in LEAGUES for d in days]
    res = pmap(lambda j: (j, get(f"{SITE}/{j[0]}/scoreboard?dates={j[1]:%Y%m%d}")), jobs)
    out = {}
    scoreboards.failed = [[j[0], j[1].isoformat()] for j, d in res if d == FAILED]
    for (lg, _), d in res:
        if d == FAILED:
            continue
        for e in (d or {}).get("events", []):
            out.setdefault(lg, {})[e["id"]] = e
    return {lg: list(v.values()) for lg, v in out.items()}


def pos_group(p):
    p = (p or "").upper()
    if p.startswith("G"):
        return "G"
    if p in ("D", "CD", "CB", "LB", "RB", "WB", "LWB", "RWB", "CD-L", "CD-R", "SW") or p.startswith("D") or p.endswith("B"):
        return "D"
    if p in ("F", "CF", "ST", "LF", "RF", "LW", "RW", "SS") or p.startswith("F") or p.endswith("W"):
        return "F"
    return "M"


def add_match(hist, lg, ev, s):
    """store each player's line from a finished match summary"""
    try:
        comp = s["header"]["competitions"][0]
        date = comp["date"][:10]
        cs = comp["competitors"]
        sc = {c["team"]["id"]: int(float(c.get("score") or 0)) for c in cs}
        ab = {c["team"]["id"]: c["team"].get("abbreviation") or c["team"].get("displayName", "")[:3].upper() for c in cs}
        nm = {c["team"]["id"]: c["team"].get("displayName", "") for c in cs}
        ha = {c["team"]["id"]: c.get("homeAway") == "home" for c in cs}
    except Exception:
        return False
    ids = list(sc)
    if len(ids) != 2:
        return False
    for tid in ids:
        opp = ids[1] if tid == ids[0] else ids[0]
        t = hist["teams"].setdefault(tid, {"a": ab[tid], "n": nm[tid], "g": []})
        t["a"], t["n"] = ab[tid], nm[tid]
        if not any(r[1] == ev for r in t["g"]):
            t["g"].append([date, ev, sc[tid], sc[opp], lg])
            t["g"] = sorted(t["g"])[-40:]
    for r in s.get("rosters", []):
        tid = (r.get("team") or {}).get("id")
        if tid not in sc:
            continue
        opp = ids[1] if tid == ids[0] else ids[0]
        for x in r.get("roster", []):
            st = {k["name"]: k.get("value") for k in x.get("stats", [])}
            if not st.get("appearances"):
                continue
            a = x.get("athlete") or {}
            aid = a.get("id")
            if not aid:
                continue
            pos = ((x.get("position") or {}).get("abbreviation")) or ""
            sv = st.get("saves")
            if sv is None and pos_group(pos) == "G" and st.get("shotsFaced") is not None:
                sv = max(0, (st.get("shotsFaced") or 0) - (st.get("goalsConceded") or 0))
            row = [date, lg, ev, ab[tid], ab[opp], 1 if ha[tid] else 0, 1 if x.get("starter") else 0,
                   1 if x.get("subbedIn") else 0, st.get("totalGoals") or 0, st.get("goalAssists") or 0,
                   st.get("totalShots") or 0, st.get("shotsOnTarget") or 0, st.get("foulsCommitted") or 0,
                   st.get("yellowCards") or 0, st.get("redCards") or 0, sv or 0, st.get("goalsConceded") or 0]
            row = [int(v) if isinstance(v, float) and v.is_integer() else v for v in row]
            p = hist["players"].setdefault(aid, {"n": a.get("displayName") or a.get("fullName", ""), "pos": pos, "g": []})
            p["n"] = a.get("displayName") or p["n"]
            if pos and pos != "SUB":
                p["pos"] = pos
            if not lg.startswith(NATIONAL):  # his club (international matches don't change it)
                p["tid"], p["t"] = tid, ab[tid]
            else:
                p["ntid"] = tid
            if not any(g[2] == ev for g in p["g"]):
                p["g"].append(row)
                p["g"] = sorted(p["g"])[-MAX_ROWS:]
    return True


def update_history(hist, days_back, now):
    """add every finished match from the last `days_back` days, plus anything an earlier run couldn't fetch
    (ESPN sometimes rate-limits; a missed day or match is retried on the next runs until it comes through)"""
    done = hist.setdefault("events", {})
    days = [(now - dt.timedelta(days=k)).date() for k in range(0, days_back + 1)]
    sb = scoreboards(days)
    # league-days that failed before: retry them too
    old_fail = [(lg, dt.date.fromisoformat(d)) for lg, d in hist.get("retry_days", []) if lg in LEAGUES and dt.date.fromisoformat(d) not in days]
    failed_days = list(scoreboards.failed)
    for lg, d in old_fail:
        r = get(f"{SITE}/{lg}/scoreboard?dates={d:%Y%m%d}")
        if r == FAILED:
            failed_days.append([lg, d.isoformat()])
        else:
            sb.setdefault(lg, []).extend((r or {}).get("events", []))
    hist["retry_days"] = failed_days[-2000:]
    todo = {(lg, e["id"]) for lg, evs in sb.items() for e in evs
            if e["status"]["type"].get("state") == "post" and e["id"] not in done}
    todo |= {(lg, ev) for ev, lg in hist.get("retry_ev", {}).items() if ev not in done}
    todo = sorted(todo)
    print(f"history: {len(todo)} finished matches to add; {len(failed_days)} league-days to retry")
    res = pmap(lambda j: (j, get(f"{SITE}/{j[0]}/summary?event={j[1]}")), todo)
    n = 0
    retry = {}
    for (lg, ev), s in res:
        if s == FAILED or not s:
            if s == FAILED:
                retry[ev] = lg
            continue
        if add_match(hist, lg, ev, s):
            done[ev] = (now.date()).isoformat()
            n += 1
    hist["retry_ev"] = retry
    # forget old events / rows
    cut = (now - dt.timedelta(days=KEEP_DAYS)).date().isoformat()
    hist["events"] = {k: v for k, v in done.items() if v >= (now - dt.timedelta(days=30)).date().isoformat() or v >= cut}
    for aid in list(hist["players"]):
        p = hist["players"][aid]
        p["g"] = [g for g in p["g"] if g[0] >= cut]
        if not p["g"]:
            del hist["players"][aid]
    print(f"history: added {n} matches; {len(hist['players'])} players")
    return sb


def priors(hist):
    """average per-appearance rate of each stat by position group, for starts and for sub appearances"""
    acc = {}
    for p in hist["players"].values():
        gp = pos_group(p.get("pos"))
        for r in p["g"][-12:]:
            k = (gp, "s" if r[6] else "b")
            a = acc.setdefault(k, {"n": 0, **{s: 0 for s in ("g", "a", "sh", "sot", "fc", "yc", "sv")}})
            a["n"] += 1
            for s, i in (("g", 8), ("a", 9), ("sh", 10), ("sot", 11), ("fc", 12), ("yc", 13), ("sv", 15)):
                a[s] += r[i] or 0
    out = {}
    for k, a in acc.items():
        out[k] = {s: (a[s] / a["n"] if a["n"] else 0) for s in a if s != "n"}
    return out


def pois_ge(lam, k):
    """P(X >= k) for X ~ Poisson(lam)"""
    if k <= 0:
        return 1.0
    term, cdf = math.exp(-lam), 0.0
    for i in range(k):
        if i:
            term *= lam / i
        cdf += term
    return max(0.0, min(1.0, 1 - cdf))


def team_avg(hist, tid, now):
    rows = [r for r in (hist["teams"].get(tid) or {}).get("g", [])
            if r[0] >= (now - dt.timedelta(days=200)).date().isoformat()][-10:]
    if not rows:
        return 1.35, 1.35
    gf = (sum(r[2] for r in rows) + 1.35 * 3) / (len(rows) + 3)
    ga = (sum(r[3] for r in rows) + 1.35 * 3) / (len(rows) + 3)
    return gf, ga


def implied(ev_odds, home):
    """team expected goals from DraftKings' match total and moneylines"""
    if not ev_odds:
        return None
    tot = num(ev_odds.get("overUnder")) or 2.6
    def p_ml(v):
        v = num(v)
        if v is None or v == 0:
            return None
        return 100 / (v + 100) if v > 0 else -v / (-v + 100)
    ph, pa, pd = p_ml((ev_odds.get("homeTeamOdds") or {}).get("moneyLine")), p_ml((ev_odds.get("awayTeamOdds") or {}).get("moneyLine")), p_ml((ev_odds.get("drawOdds") or {}).get("moneyLine"))
    if ph is None or pa is None:
        return {"home": tot / 2, "away": tot / 2, "total": tot}
    s = ph + pa + (pd or 0)
    ph, pa = ph / s, pa / s
    d = 1.9 * (ph - pa)
    return {"home": max(.2, tot / 2 + d / 2), "away": max(.2, tot / 2 - d / 2), "total": tot}


# per-position correction to the rates (backtest_soccer.py): the shrunken rates overrated defenders' goals and
# shots on target and underrated forwards' goals, because a few big games move a low-volume player's average a lot
POS_ADJ = {'g|D': 0.637, 'a|D': 0.657, 'sh|D': 0.983, 'sot|D': 0.824, 'fc|D': 1.058, 'yc|D': 1.261, 'g|M': 1.022,
           'a|M': 1.071, 'sh|M': 1.012, 'sot|M': 1.04, 'fc|M': 0.971, 'yc|M': 0.869, 'g|F': 1.225, 'a|F': 0.916,
           'sh|F': 0.975, 'sot|F': 1.077, 'fc|F': 0.973, 'yc|F': 0.536}


def lam_for(p, stat, pri, s_start):
    """his expected count of `stat` in this match, before the team adjustment"""
    i = {"g": 8, "a": 9, "sh": 10, "sot": 11, "fc": 12, "yc": 13, "sv": 15}[stat]
    gp = pos_group(p.get("pos"))
    rows = p["g"][-12:]
    st = [r for r in rows if r[6]]
    sb = [r for r in rows if not r[6]]
    ps = (pri.get((gp, "s")) or {}).get(stat, 0)
    pb = (pri.get((gp, "b")) or {}).get(stat, ps * .3)
    l_s = (sum(r[i] or 0 for r in st) + ps * K_START) / (len(st) + K_START)
    l_b = (sum(r[i] or 0 for r in sb) + pb * K_SUB) / (len(sb) + K_SUB)
    return (s_start * l_s + (1 - s_start) * l_b) * POS_ADJ.get(f"{stat}|{gp}", 1.0)


# recalibration per stat and milestone, fit by backtest_soccer.py --raw: p' = sig(a + b * logit(p)). The raw
# Poisson model was overconfident at the high end (goals said 40% -> 30% happened, assists 25% -> 15%).
CAL = {'sv1': (0.166, 0.726), 'sv2': (0.405, 0.553), 'sv3': (0.098, 0.512), 'sv4': (-0.149, 0.516), 'sv5': (-0.365, 0.556), 'sv6': (-0.35, 0.701), 'g1': (-0.692, 0.631), 'g2': (-0.296, 0.959), 'a1': (-1.002, 0.519), 'sh1': (-0.141, 0.859), 'sh2': (-0.132, 0.866), 'sh3': (-0.168, 0.827), 'sh4': (-0.096, 0.861), 'sot1': (-0.254, 0.756), 'sot2': (-0.411, 0.775), 'sot3': (-0.225, 0.889), 'fc1': (-0.014, 0.793), 'fc2': (-0.259, 0.758), 'fc3': (-0.399, 0.788), 'yc1': (-0.997, 0.376)}


def calibrate(stat, k, p):
    ab = CAL.get(f"{stat}{k}") or CAL.get(f"{stat}{max([int(x[len(stat):]) for x in CAL if x.startswith(stat) and x[len(stat):].isdigit()] or [0])}")
    return sig(ab[0] + ab[1] * logit(p)) if ab else p


def logit(p):
    p = min(.999, max(.001, p))
    return math.log(p / (1 - p))


def sig(z):
    return 1 / (1 + math.exp(-z))


def read_props(lg, ev):
    """[(athlete id, market, target k, american price, decimal)] from ESPN's DraftKings prop bets"""
    out, page, pages = [], 1, 1
    while page <= pages and page <= 5:
        d = get(f"{CORE}/{lg}/events/{ev}/competitions/{ev}/odds/100/propBets?limit=1000&page={page}")
        if not d or d == FAILED:
            break
        pages = d.get("pageCount") or 1
        for it in d.get("items", []):
            m = MARKETS.get((it.get("type") or {}).get("name"))
            if not m:
                continue
            ref = ((it.get("athlete") or {}).get("$ref") or "")
            aid = ref.split("/athletes/")[-1].split("?")[0] if "/athletes/" in ref else None
            cur = it.get("current") or {}
            o = cur.get("over") or {}
            dec = num(o.get("decimal") or o.get("value"))
            am = o.get("american")
            if not aid or not dec or dec <= 1:
                continue
            if m == "g2":
                m, k = "g", 2
            elif m in ("g", "card"):
                k = 1
            else:
                k = int(num((cur.get("target") or {}).get("value")) or 0)
                if k <= 0:
                    continue
            try:
                am = int(str(am).replace("+", "")) if am not in (None, "") else None
            except ValueError:
                am = None
            if am is None:
                am = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))
            out.append((aid, m, k, am, dec))
        page += 1
    return out


def lineups(lg, ev):
    """confirmed starters / bench from the match summary when ESPN has the lineups (about an hour before)"""
    s = get(f"{SITE}/{lg}/summary?event={ev}")
    if s == FAILED:
        s = None
    res = {}
    for r in (s or {}).get("rosters", []) or []:
        for x in r.get("roster", []) or []:
            aid = (x.get("athlete") or {}).get("id")
            if aid:
                res[aid] = "start" if x.get("starter") else "bench"
    return res if sum(1 for v in res.values() if v == "start") >= 18 else {}


def main():
    light = "--light" in sys.argv
    days_back = int(sys.argv[sys.argv.index("--days-back") + 1]) if "--days-back" in sys.argv else 7
    now = dt.datetime.now(dt.timezone.utc)
    try:
        hist = json.load(gzip.open(HIST, "rt"))
    except Exception:
        hist = {"players": {}, "teams": {}, "events": {}}
        days_back = max(days_back, 60)  # first run: build two months of history
    if not light and hist.get("depth", 0) < 121:
        days_back = max(days_back, 120)  # deepen (and re-check) four months once, so more players have enough matches
        hist["depth"] = 121
    if not light:
        update_history(hist, days_back, now)
        json.dump(hist, gzip.open(HIST, "wt"), separators=(",", ":"))
    pri = priors(hist)
    try:  # first price seen for each prop (from earlier runs), to show how the price has moved
        old = json.load(open(OUT))
        opened = {f"{p['key']}|{m['ev']}": p.get("open", p["price"]) for m in old.get("matches", []) for p in m.get("props", [])}
    except Exception:
        opened = {}
    try:  # the daily research's soccer check (injuries, suspensions, rotation), when it's fresh
        nf = json.load(open("notes.json"))
        fresh = now - dt.datetime.fromisoformat(nf["updated"].replace("Z", "+00:00")) < dt.timedelta(hours=36)
        snotes = {k: v for k, v in (nf.get("notes") or {}).items() if k.startswith("SOC|")} if fresh else {}
    except Exception:
        snotes = {}
    try:
        closing = json.load(open(CLOSE))
    except Exception:
        closing = {}
    # upcoming matches
    sb = scoreboards([(now + dt.timedelta(days=k)).date() for k in range(0, AHEAD_DAYS + 1)])
    ups = []
    for lg, evs in sb.items():
        for e in evs:
            t = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            if e["status"]["type"].get("state") != "pre" or not (now - dt.timedelta(minutes=5) < t < now + dt.timedelta(days=AHEAD_DAYS)):
                continue
            c = e["competitions"][0]
            teams = {x["homeAway"]: x["team"] for x in c["competitors"]}
            if "home" not in teams or "away" not in teams:
                continue
            ups.append({"lg": lg, "ev": e["id"], "t": t, "home": teams["home"], "away": teams["away"],
                        "odds": (c.get("odds") or [None])[0]})
    print(f"upcoming: {len(ups)} matches")
    props = pmap(lambda u: read_props(u["lg"], u["ev"]), ups)
    soon = [i for i, u in enumerate(ups) if u["t"] - now < dt.timedelta(hours=2) and props[i]]
    lus = dict(zip(soon, pmap(lambda i: lineups(ups[i]["lg"], ups[i]["ev"]), soon)))
    players = hist["players"]
    league_last = {}
    for t in hist["teams"].values():
        for r in t["g"]:
            if r[0] > league_last.get(r[4], ""):
                league_last[r[4]] = r[0]
    matches, cands = [], []
    skip = {"history": 0, "team": 0, "absent": 0}
    for i, u in enumerate(ups):
        pr = props[i]
        if not pr:
            continue
        hid, aid_ = u["home"]["id"], u["away"]["id"]
        imp = implied(u["odds"], True) or {}
        tav = {hid: team_avg(hist, hid, now), aid_: team_avg(hist, aid_, now)}
        lu = lus.get(i, {})
        rows = []
        pinfo = {}
        by_player = {}
        for (aid, m, k, am, dec) in pr:
            by_player.setdefault(aid, []).append((m, k, am, dec))
        for aid, bets in by_player.items():
            p = players.get(aid)
            if p:
                # club form for club matches, international form for internationals (different team, different role)
                nat = u["lg"].startswith(NATIONAL)
                same = [r for r in p["g"] if r[1].startswith(NATIONAL) == nat]
                if len(same) >= 3:
                    p = dict(p, g=same)
            if not p or len(p["g"]) < 3:
                skip["history"] += 1
                continue
            tid = p.get("tid") if not u["lg"].startswith(NATIONAL) else p.get("ntid")
            if tid not in (hid, aid_) and {hid, aid_} & {p.get("tid"), p.get("ntid")}:
                tid = ({hid, aid_} & {p.get("tid"), p.get("ntid")}).pop()
            if tid not in (hid, aid_):
                skip["team"] += 1
                continue  # last seen on another team (transfer); skip until he has a match for this one
            home = tid == hid
            opp_id = aid_ if home else hid
            # recent availability: in how many of his team's last 5 matches did he play / start?
            tg = [r[1] for r in (hist["teams"].get(tid) or {}).get("g", [])][-5:]
            mine = {r[2]: r for r in p["g"]}
            apps = [mine[e] for e in tg if e in mine]
            if tg and not any(e in mine for e in tg[-3:]) and lu.get(aid) != "start":
                skip["absent"] += 1
                continue  # not in any of his team's last 3 squads: injured, dropped or away
            status = lu.get(aid)
            if lu and not status:
                continue  # lineups are out and he isn't in the squad
            note = snotes.get(f"SOC|{aid}|{u['ev']}") or {}
            if note.get("flag") == "out":
                skip["research_out"] = skip.get("research_out", 0) + 1
                continue  # the research found he's injured, suspended or left out
            r_adj = {"support": .2, "caution": -.35}.get(note.get("flag"), 0) * {"high": 1.2, "medium": 1.0, "low": .6}.get(note.get("conf"), 1.0)
            s_start = 1.0 if status == "start" else 0.0 if status == "bench" else \
                ((sum(r[6] for r in apps) + .5) / (len(apps) + 1) if apps else .5)
            # his team's matches are missing from the data while the rest of its league kept playing
            last = ((hist["teams"].get(tid) or {}).get("g") or [[""]])[-1][0]
            lg_last = league_last.get(u["lg"])
            # (checked against ESPN's schedules: gaps here have been real breaks in the calendar, so this only flags a
            # team with no match at all in the last 60 days)
            stale = not last or last < (now - dt.timedelta(days=60)).date().isoformat()
            gf, ga = tav[tid]
            ogf, oga = tav[opp_id]
            exp_for = imp.get("home" if home else "away")
            exp_ag = imp.get("away" if home else "home")
            f_att = max(.55, min(1.7, (exp_for or gf) / max(.4, gf)))
            f_def = max(.55, min(1.7, (exp_ag or ga) / max(.4, ga)))
            for (m, k, am, dec) in bets:
                stat = "yc" if m == "card" else m
                lam = lam_for(p, stat, pri, s_start)
                if m in ATTACK:
                    lam *= f_att if m in ("g", "a") else f_att ** .6
                if m == "sv":
                    lam *= f_def ** .6
                p_mod = calibrate(stat, k, pois_ge(lam, k))
                if r_adj and m != "fc":
                    p_mod = sig(logit(p_mod) + r_adj)
                q = 1 / dec
                q_fair = min(.97, q / (1 + MARGIN.get(m, .08)))
                prob = sig((1 - MKT_W) * logit(p_mod) + MKT_W * logit(q_fair))
                ev = prob * dec - 1
                g10 = p["g"][-10:]
                si = {"g": 8, "a": 9, "sh": 10, "sot": 11, "fc": 12, "yc": 13, "sv": 15, "card": 13}[m]
                hits = sum(1 for r in g10 if (r[si] or 0) >= k)
                rows.append({"key": f"SOC|{aid}|{m}|{k}", "pid": aid, "name": p["n"], "pos": pos_group(p.get("pos")),
                             "team": p["t"], "opp": (u["away"] if home else u["home"]).get("abbreviation", ""),
                             "home": home, "m": m, "k": k, "label": (f"{k}+ goals" if m == "g" else f"{k}+ {LABEL[m].lower()}") if m not in ("g", "card") or k > 1 else LABEL[m],
                             "price": am, "dec": round(dec, 3), "prob": round(prob, 3), "model": round(p_mod, 3),
                             "book": round(q, 3), "fair_book": round(q_fair, 3), "ev": round(ev, 3), "hits": [hits, len(g10)],
                             "lineup": status, "start_rate": round(s_start, 2), **({"stale": True} if stale else {}),
                             "open": opened.get(f"SOC|{aid}|{m}|{k}|{u['ev']}", am),
                             **({"research": note.get("note"), "rflag": note.get("flag"), "rconf": note.get("conf")} if note.get("note") else {})})
                if u["t"] > now:
                    closing[f"SOC|{aid}|{m}|{k}|{u['ev']}"] = [round(dec, 3), u["t"].isoformat(timespec="minutes")]
                if aid not in pinfo:
                    pinfo[aid] = {"n": p["n"], "pos": pos_group(p.get("pos")), "team": p["t"], "lineup": status,
                                  "sr": round(s_start, 2), "dates": [r[0][5:] for r in g10], "opp": [r[4] for r in g10],
                                  "comp": [r[1] for r in g10], "home": home, "st": [r[6] for r in g10],
                                  "v": {s_: [r[i_] or 0 for r in g10] for s_, i_ in (("g", 8), ("a", 9), ("sh", 10), ("sot", 11), ("sv", 15), ("fc", 12), ("yc", 13))
                                        if s_ != "sv" or pos_group(p.get("pos")) == "G"},
                                  **({"research": note.get("note"), "rflag": note.get("flag")} if note.get("note") else {})}
        if not rows:
            continue
        rows.sort(key=lambda r: -r["ev"])
        mt = {"lg": u["lg"], "league": LEAGUES.get(u["lg"], u["lg"]), "ev": u["ev"], "t": u["t"].isoformat(timespec="minutes"),
              "home": u["home"].get("abbreviation", ""), "away": u["away"].get("abbreviation", ""),
              "home_n": u["home"].get("displayName", ""), "away_n": u["away"].get("displayName", ""),
              "exp": [round(imp["home"], 2), round(imp["away"], 2)] if imp.get("home") else None,
              "lineups": bool(lus.get(i)), "n_dk": len(pr), "n_pl": [len(pinfo), len(by_player)], "players": pinfo,
              # every prop with at least a 5% chance, compact: [player, market, k, price, first price seen, chance,
              # expected profit, hits, of last n, model chance] (the app rebuilds names and labels from "players")
              "P": [[r["pid"], r["m"], r["k"], r["price"], r["open"], r["prob"], r["ev"], r["hits"][0], r["hits"][1], r["model"]]
                    for r in rows if r["prob"] >= .05]}
        matches.append(mt)
        for r in rows:
            cands.append(dict(r, lg=u["lg"], league=mt["league"], ev_id=u["ev"], t=mt["t"]))
    # Top 10s: best expected profit (one bet per player, at most 2 per match, chance at least 15%), and the
    # likeliest anytime scorers
    def top(pool, key, per_match=2):
        out, seen, pm = [], set(), {}
        for c in sorted(pool, key=key):
            if c["pid"] in seen or pm.get(c["ev_id"], 0) >= per_match:
                continue
            seen.add(c["pid"])
            pm[c["ev_id"]] = pm.get(c["ev_id"], 0) + 1
            out.append(c)
            if len(out) == 10:
                break
        return out
    # a model chance far above the book's (more than 1.75x, or 15+ points) usually means the book knows something the
    # box scores don't (injury, rotation, a different role), so those stay off the Top lists
    sane = lambda c: c["model"] <= 1.75 * c["fair_book"] and c["model"] - c["fair_book"] <= .15 and not c.get("stale")
    value = top([c for c in cands if c["ev"] >= .05 and c["prob"] >= .2 and c["hits"][1] >= 5 and sane(c)], lambda c: -c["ev"])
    plus = top([c for c in cands if c["ev"] >= .05 and c["price"] >= 100 and c["prob"] >= .12 and c["hits"][1] >= 5 and sane(c)], lambda c: -c["ev"])
    scorers = top([c for c in cands if c["m"] == "g" and c["k"] == 1 and not c.get("stale")], lambda c: -c["prob"], per_match=3)
    matches.sort(key=lambda m: m["t"])
    cut = (now - dt.timedelta(days=10)).isoformat(timespec="minutes")
    json.dump({k: v for k, v in closing.items() if v[1] >= cut}, open(CLOSE, "w"), separators=(",", ":"))
    json.dump({"built": now.isoformat(timespec="minutes"), "leagues": LEAGUES, "skipped": skip, "matches": matches,
               "value": value, "plus": plus, "scorers": scorers},
              open(OUT, "w"), separators=(",", ":"))
    print("players skipped:", skip)
    evs = sorted(c["ev"] for c in cands)
    if evs:
        print("EV distribution: median %.3f, 90th %.3f, share above +5%%: %.1f%%" % (evs[len(evs) // 2], evs[int(len(evs) * .9)],
              100 * sum(1 for e in evs if e >= .05) / len(evs)))
    print(f"wrote {OUT}: {len(matches)} matches with props, {len(cands)} priced props, "
          f"top value {[(c['name'], c['label'], c['price'], c['prob'], c['model'], c['ev']) for c in value[:6]]} plus {[(c['name'], c['label'], c['price'], c['ev']) for c in plus[:4]]}")


if __name__ == "__main__":
    main()
