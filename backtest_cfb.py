"""College football signal backtest (Oct 30): does CollegeFootballData.com data (betting lines, last year's SP+ ratings,
team pace and pass rate) predict prop results beyond recent form?
Rows = every FBS player game 2022-26 for 7 prop types; synthetic line = weighted average of his last 10 games (nearest x.5),
y = went over. Base features: recent form z, last-10 mean vs line, hit rate vs the line, opponent allowed (5 games). Each new
feature is added alone; train 2022-24, test 2025-26 (features use only earlier games). Reports the out-of-sample log-loss gain,
a t-statistic on it, and the hit rate of the most confident 20% of picks. Also prints the over rate of the synthetic lines.
Needs a free key from collegefootballdata.com in the CFBD_API_KEY environment variable (a GitHub Actions secret in the
"CFB backtest" workflow). Usage: python backtest_cfb.py [data_dir]   (about 350 API calls on a cold cache; cached in data_dir)
"""
import os, sys, json, math, time, collections, datetime as dt, urllib.request, urllib.parse, urllib.error
import numpy as np

KEY = os.environ.get("CFBD_API_KEY", "").strip()
D = (sys.argv[1] if len(sys.argv) > 1 else "backtest_data").rstrip("/") + "/cfbd/"
os.makedirs(D, exist_ok=True)
YEARS = [2022, 2023, 2024, 2025, 2026]
WEEKS = range(1, 16)
THIS_YEAR = 2026
BASE = "https://api.collegefootballdata.com"
calls = 0


def api(path, **params):
    """GET one endpoint (cached in D). Plain requests with the key; empty results for the current year aren't cached."""
    global calls
    q = urllib.parse.urlencode(params)
    f = D + path.strip("/").replace("/", "_") + "_" + q.replace("&", "_").replace("=", "-") + ".json"
    if os.path.exists(f):
        return json.load(open(f))
    for i in range(4):
        try:
            req = urllib.request.Request(f"{BASE}{path}?{q}", headers={"Authorization": "Bearer " + KEY, "Accept": "application/json", "User-Agent": "prop-tracker-backtest"})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
            calls += 1
            if data or params.get("year") != THIS_YEAR:
                json.dump(data, open(f, "w"))
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(20 * (i + 1)); continue
            print(f"  {path} {q}: HTTP {e.code}"); return []
        except Exception as e:
            print(f"  {path} {q}: {str(e)[:80]}"); time.sleep(3)
    return []


def g(d, *names, default=None):
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None:
            return d[n]
    return default


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---- 1. games (dates, scores), lines, last year's SP+ ----
games = {}
for y in YEARS:
    for gm in api("/games", year=y, seasonType="regular"):
        games[g(gm, "id")] = dict(year=y, week=g(gm, "week"), date=(g(gm, "startDate", "start_date") or "")[:10],
                                  home=g(gm, "homeTeam", "home_team"), away=g(gm, "awayTeam", "away_team"))
print(f"games: {len(games)}  ({collections.Counter(v['year'] for v in games.values())})")
if not games:
    print("no games came back: is the CFBD_API_KEY secret set and valid?"); sys.exit(1)
first = next(iter(games.values()))
print("sample game:", first)

spread, total = {}, {}
for y in YEARS:
    for ln in api("/lines", year=y, seasonType="regular"):
        gid = g(ln, "id")
        sp = [num(l.get("spread")) for l in (ln.get("lines") or [])]; ou = [num(l.get("overUnder")) for l in (ln.get("lines") or [])]
        sp = [x for x in sp if x is not None]; ou = [x for x in ou if x is not None]
        if sp: spread[gid] = float(np.mean(sp))      # home team's spread: negative = home favored
        if ou: total[gid] = float(np.mean(ou))
print(f"lines: {len(spread)} spreads, {len(total)} totals")

sp_off, sp_def = {}, {}
for y in [YEARS[0] - 1] + YEARS:
    for r in api("/ratings/sp", year=y):
        t = g(r, "team")
        sp_off[(y, t)] = num((r.get("offense") or {}).get("rating")); sp_def[(y, t)] = num((r.get("defense") or {}).get("rating"))
print(f"SP+ ratings: {len(sp_off)} team-years")

# ---- 2. player stats per game ----
CATS = {"passing": ("pyd", "att", "cmp"), "rushing": ("ryd", "car"), "receiving": ("recyd", "rec")}
pg = {}                                  # (market, pid, gid) -> value
pinfo = {}                               # (pid, gid) -> (team, opp, home)
teamvol = collections.defaultdict(lambda: collections.defaultdict(float))   # (team, gid) -> att / car
allowed = collections.defaultdict(lambda: collections.defaultdict(float))   # (defense team, market) gid -> total allowed
shown = False
for y in YEARS:
    for wk in WEEKS:
        for cat in CATS:
            for gm in api("/games/players", year=y, week=wk, seasonType="regular", category=cat):
                gid = g(gm, "id"); teams = gm.get("teams") or []
                if len(teams) != 2:
                    continue
                if gid not in games:
                    continue
                for ti, t in enumerate(teams):
                    school = g(t, "school", "team"); opp = g(teams[1 - ti], "school", "team"); home = g(t, "homeAway") == "home"
                    for c in t.get("categories") or []:
                        if c.get("name") != cat:
                            continue
                        for ty in c.get("types") or []:
                            tn = ty.get("name")
                            for a in ty.get("athletes") or []:
                                pid, st = a.get("id"), a.get("stat")
                                if pid is None:
                                    continue
                                pinfo[(pid, gid)] = (school, opp, home)
                                if cat == "passing" and tn == "C/ATT" and isinstance(st, str) and "/" in st:
                                    cm, at = st.split("/")[:2]
                                    cm, at = num(cm), num(at)
                                    if at is not None:
                                        pg[("att", pid, gid)] = at; teamvol[(school, gid)]["att"] += at
                                        allowed[(opp, "att")][gid] += at
                                    if cm is not None:
                                        pg[("cmp", pid, gid)] = cm; allowed[(opp, "cmp")][gid] += cm
                                elif cat == "passing" and tn == "YDS":
                                    v = num(st)
                                    if v is not None: pg[("pyd", pid, gid)] = v; allowed[(opp, "pyd")][gid] += v
                                elif cat == "rushing" and tn in ("YDS", "CAR"):
                                    v = num(st); m = "ryd" if tn == "YDS" else "car"
                                    if v is not None:
                                        pg[(m, pid, gid)] = v; allowed[(opp, m)][gid] += v
                                        if m == "car": teamvol[(school, gid)]["car"] += v
                                elif cat == "receiving" and tn in ("YDS", "REC"):
                                    v = num(st); m = "recyd" if tn == "YDS" else "rec"
                                    if v is not None: pg[(m, pid, gid)] = v; allowed[(opp, m)][gid] += v
                if not shown:
                    print("sample games/players team keys:", list(teams[0].keys())); shown = True
print(f"player-game stats: {len(pg)}; API calls this run: {calls}")

# ---- 3. rows ----
hist = collections.defaultdict(list)     # (market, pid) -> [(date, gid, value)]
for (m, pid, gid), v in pg.items():
    hist[(m, pid)].append((games[gid]["date"], gid, v))
for k in hist:
    hist[k].sort()
tgames = collections.defaultdict(list)   # team -> [(date, gid)]
for (school, gid) in teamvol:
    tgames[school].append((games[gid]["date"], gid))
for k in tgames:
    tgames[k].sort()
alist = {k: sorted((games[gid]["date"], gid, v) for gid, v in d.items()) for k, d in allowed.items()}
MINLINE = {"pyd": 100, "att": 15, "cmp": 8, "ryd": 25, "car": 8, "recyd": 25, "rec": 2}
W = np.array([.15, .14, .13, .12, .11, .10, .09, .07, .05, .04])   # newest first


def prior(lst, date, n):
    out = [x for x in lst if x[0] < date]
    return out[-n:]


def rnd(x):
    return math.floor(x) + .5 if x - math.floor(x) < .5 else math.floor(x) + 1.5 if x - math.floor(x) > .5 else x + .5


rows = collections.defaultdict(list)
for (m, pid), lst in hist.items():
    for i, (date, gid, val) in enumerate(lst):
        p = lst[max(0, i - 10):i]
        if len(p) < 6 or games[gid]["year"] < 2022:
            continue
        v10 = np.array([x[2] for x in p][::-1])                     # newest first
        w = W[:len(v10)] / W[:len(v10)].sum()
        wavg = float((v10 * w).sum()); line = math.floor(wavg) + .5
        if wavg < MINLINE[m] * .8 or line < MINLINE[m]:
            continue
        info = pinfo.get((pid, gid))
        if not info:
            continue
        team, opp, home = info
        sd = float(v10.std()) or 1.0
        f = {"z_form": (v10[:3].mean() - line) / sd, "m10_gap": (v10.mean() - line) / sd,
             "hr10": float((v10 > line).mean()) - .5}
        al = [x[2] for x in prior(alist.get((opp, m), []), date, 5)]
        row = dict(y=int(val > line), year=games[gid]["year"], date=date, f=f, new={}, _al=float(np.mean(al)) if al else None)
        sp, tot = spread.get(gid), total.get(gid)
        if sp is not None and tot is not None:
            tsp = sp if home else -sp
            row["new"]["imp_pts"] = tot / 2 - tsp / 2
            row["new"]["team_spread"] = tsp
            row["new"]["abs_spread"] = abs(sp)
            row["new"]["total"] = tot
        row["new"]["home"] = 1.0 if home else 0.0
        row["new"]["week"] = float(games[gid]["week"] or 0)
        yy = games[gid]["year"]
        for nm, tbl, tm in (("opp_def_sp", sp_def, opp), ("team_off_sp", sp_off, team), ("opp_off_sp", sp_off, opp), ("team_def_sp", sp_def, team)):
            v = tbl.get((yy - 1, tm))
            if v is not None:
                row["new"][nm] = v
        tg = prior(tgames.get(team, []), date, 5)
        if len(tg) >= 3:
            at = np.mean([teamvol[(team, x[1])]["att"] for x in tg]); cr = np.mean([teamvol[(team, x[1])]["car"] for x in tg])
            row["new"]["team_plays"] = at + cr
            row["new"]["team_passrate"] = at / (at + cr) if at + cr else .5
        rows[m].append(row)
# opponent-allowed, standardized within each market
for m, rs in rows.items():
    vals = [r["_al"] for r in rs if r["_al"] is not None]
    mu, sd_ = (np.mean(vals), np.std(vals) or 1.0) if vals else (0, 1)
    for r in rs:
        r["f"]["opp_allow"] = ((r["_al"] - mu) / sd_) if r["_al"] is not None else 0.0
print("rows:", {m: len(r) for m, r in rows.items()})
print("over rate of the synthetic line (rows, all years):", {m: round(float(np.mean([r["y"] for r in rs])), 3) for m, rs in rows.items()})
print("over rate by year:", {y: round(float(np.mean([r["y"] for rs in rows.values() for r in rs if r["year"] == y])), 3) for y in YEARS if any(r["year"] == y for rs in rows.values() for r in rs)})

# ---- 4. tests ----


def fit(X, y, l2=1.0, it=40):
    w = np.zeros(X.shape[1])
    for _ in range(it):
        z = np.clip(X @ w, -30, 30); p = 1 / (1 + np.exp(-z))
        gr = X.T @ (p - y) + l2 * np.r_[0, w[1:]]
        H = (X.T * (p * (1 - p))) @ X + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= np.linalg.solve(H + 1e-6 * np.eye(len(w)), gr)
    return w


def rowloss(y, p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


BASE = ["z_form", "m10_gap", "hr10", "opp_allow"]
NEW = ["imp_pts", "team_spread", "abs_spread", "total", "home", "week", "opp_def_sp", "team_off_sp", "opp_off_sp", "team_def_sp", "team_plays", "team_passrate"]
res = []
print(f"\n{'market':6s} {'feature':13s} {'n_train':>7s} {'n_test':>6s} {'gain':>8s} {'t':>6s} {'top20 new':>9s} {'top20 base':>10s}")
for m, rs in rows.items():
    tr_all = [r for r in rs if r["year"] <= 2024]; te_all = [r for r in rs if r["year"] >= 2025]
    if len(tr_all) < 300 or len(te_all) < 150:
        print(m, "too few rows", len(tr_all), len(te_all)); continue
    for nf in NEW:
        tr = [r for r in tr_all if nf in r["new"]]; te = [r for r in te_all if nf in r["new"]]
        if len(tr) < 300 or len(te) < 150:
            continue
        def X(rr, feats):
            return np.array([[1.0] + [(r["f"][k] if k in r["f"] else r["new"][k]) for k in feats] for r in rr])
        Xb_tr, Xn_tr = X(tr, BASE), X(tr, BASE + [nf]); mu, sdv = Xn_tr[:, 1:].mean(0), Xn_tr[:, 1:].std(0) + 1e-9
        st = lambda A: np.c_[A[:, :1], (A[:, 1:] - mu[:A.shape[1] - 1]) / sdv[:A.shape[1] - 1]]
        yt = np.array([r["y"] for r in tr]); ye = np.array([r["y"] for r in te])
        wb = fit(st(Xb_tr), yt); wn = fit(st(Xn_tr), yt)
        pb = 1 / (1 + np.exp(-st(X(te, BASE)) @ wb)); pn = 1 / (1 + np.exp(-st(X(te, BASE + [nf])) @ wn))
        d = rowloss(ye, pb) - rowloss(ye, pn); gain = d.mean(); t = gain / (d.std(ddof=1) / math.sqrt(len(d)) + 1e-12)
        k = max(1, len(te) // 5); topn = np.argsort(-np.abs(pn - .5))[:k]; topb = np.argsort(-np.abs(pb - .5))[:k]
        hit = lambda p, idx: float(np.mean((ye[idx] == 1) == (p[idx] > .5)))
        res.append((m, nf, gain, t))
        print(f"{m:6s} {nf:13s} {len(tr):7d} {len(te):6d} {gain:+8.5f} {t:+6.2f} {hit(pn, topn):9.3f} {hit(pb, topb):10.3f}")
big = [r for r in res if r[3] >= 2]
print(f"\n{len(res)} tests; {len(big)} improve the base with t >= 2 (about {max(1, round(len(res) * .025))} expected by chance in that direction):")
for r in sorted(big, key=lambda r: -r[3]): print(f"  {r[0]} {r[1]}: gain {r[2]:+.5f} t={r[3]:+.2f}")
worse = [r for r in res if r[3] <= -2]
print(f"{len(worse)} make it worse with t <= -2 (overfit)")
