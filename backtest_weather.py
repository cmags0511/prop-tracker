"""Weather backtest: does kickoff wind / cold / rain move NFL prop results beyond the existing model features?
Prop rows from rows.pkl (synthetic line = weighted recent average); kicker rows built here."""
import math, sys, numpy as np, pandas as pd
D = (sys.argv[1] if len(sys.argv) > 1 else ".").rstrip("/") + "/"  # folder with nflverse games.csv, stw_<yr>.csv and the usage backtest rows.pkl
YRS = [2023, 2024, 2025, 2026]
g = pd.read_csv(D + "games.csv")
g = g[g.season.isin(YRS)].set_index("game_id")
out = g.roof.isin(["outdoors", "open"])
stats = pd.concat([pd.read_csv(f"{D}stw_{y}.csv", low_memory=False) for y in YRS])
stats = stats[stats.season_type.isin(["REG", "POST"])]
key = stats.set_index(["player_id", "season", "week"]).game_id
key = key[~key.index.duplicated()]

r = pd.read_pickle(D + "rows.pkl")
r["gid"] = [key.get((p, s, w)) for p, s, w in zip(r.pid, r.season, r.week)]
r = r.dropna(subset=["gid"])
r["outd"] = r.gid.map(out).fillna(False).astype(bool)
r["wind"] = r.gid.map(g.wind)
r["temp"] = r.gid.map(g.temp)
r = r[r.outd & r.wind.notna()]
print("outdoor prop rows with weather:", len(r))

BASE = ["pf", "z", "mu", "imp", "upj", "snap_tr"]


def logit(X, y, lam=1.0, it=50):
    X = np.column_stack([np.ones(len(X)), X]); b = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ b)); W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + lam * np.eye(len(b)); H[0, 0] -= lam
        b += np.linalg.solve(H, X.T @ (y - p) - lam * np.r_[0, b[1:]])
    return b


def ll(X, y, b):
    X = np.column_stack([np.ones(len(X)), X]); p = np.clip(1 / (1 + np.exp(-X @ b)), 1e-6, 1 - 1e-6)
    return np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))


def test(df, name, feats):
    df = df.copy()
    y = df.y.values.astype(float)
    print(f"\n== {name}: n={len(df)}, over rate {y.mean():.3f}")
    # bucket view
    for lo, hi in [(0, 8), (8, 12), (12, 16), (16, 20), (20, 99)]:
        s = df[(df.wind >= lo) & (df.wind < hi)]
        if len(s) > 30:
            print(f"  wind {lo:>2}-{hi:<2}: n={len(s):5d} over {s.y.mean():.3f}")
    for lo, hi in [(-50, 32), (32, 45), (45, 200)]:
        s = df[(df.temp >= lo) & (df.temp < hi)]
        if len(s) > 30:
            print(f"  temp {lo:>3}-{hi:<3}: n={len(s):5d} over {s.y.mean():.3f}")
    # model with and without, coefficient in each half (by season)
    for half, mask in [("all", df.season > 0), ("2023-24", df.season <= 2024), ("2025-26", df.season >= 2025)]:
        d = df[mask]; yy = d.y.values.astype(float)
        X0 = d[BASE].values if set(BASE) <= set(d.columns) else np.zeros((len(d), 0))
        X1 = np.column_stack([X0] + [d[f].values for f in feats])
        b0, b1 = logit(X0, yy), logit(X1, yy)
        print(f"  {half:8s} n={len(d):5d} " + " ".join(f"{f}={c:+.3f}" for f, c in zip(feats, b1[-len(feats):]))
              + f"  dLL/row={ll(X1, yy, b1) - ll(X0, yy, b0):+.5f}")


r["w12"] = np.maximum(0, r.wind - 12) / 5
r["cold"] = np.maximum(0, 40 - r.temp) / 10
for grp, ms in [("passing (QB yds/cmp/att)", ["pyd", "cmp", "att"]), ("receiving", ["rec", "recyd"]),
                ("rushing", ["ryd", "car", "rry"])]:
    test(r[r.m.isin(ms)], grp, ["w12", "cold"])

# kickers: FG made and kicking points vs a synthetic line from his last 8 games
k = stats[stats.position == "K"].copy()
for c in ["fg_made", "fg_att", "pat_made"]:
    k[c] = pd.to_numeric(k[c], errors="coerce").fillna(0)
k["kp"] = 3 * k.fg_made + k.pat_made
k = k.sort_values(["season", "week"])
rows = []
for pid, d in k.groupby("player_id"):
    d = d.reset_index(drop=True)
    for i in range(6, len(d)):
        prev = d.iloc[max(0, i - 8):i]; cur = d.iloc[i]
        gid = cur.game_id
        if gid not in g.index or not out.get(gid, False) or pd.isna(g.wind.get(gid)):
            continue
        hg = g.loc[gid]
        home = hg.home_team == cur.team
        sp = hg.spread_line; spt = (-sp if home else sp) if sp == sp else 0
        imp = (hg.total_line / 2 - spt / 2) if hg.total_line == hg.total_line else 22
        for m in ["fg_made", "kp"]:
            L = math.floor(prev[m].mean()) + .5
            v = prev[m].values
            rows.append(dict(season=cur.season, m=m, y=int(cur[m] > L), wind=hg.wind, temp=hg.temp,
                             pf=(np.sum(v > L) + 1) / (len(v) + 2) - .5, imp=(imp - 22.5) / 4))
kd = pd.DataFrame(rows)
kd["w12"] = np.maximum(0, kd.wind - 12) / 5
kd["cold"] = np.maximum(0, 40 - kd.temp) / 10
BASE = ["pf", "imp"]
for m in ["fg_made", "kp"]:
    test(kd[kd.m == m], "kicker " + m, ["w12", "cold"])
