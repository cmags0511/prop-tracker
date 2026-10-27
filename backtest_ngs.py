"""Next Gen Stats backtest: do NGS metrics (player's own recent ones and what the opponent allows) predict NFL prop
results beyond the app's existing features? Rows = /tmp/claude-0/nfl/rows.pkl (synthetic line = weighted recent
average, y = went over), same as the usage and weather backtests."""
import numpy as np, pandas as pd

import sys
N = (sys.argv[1] if len(sys.argv) > 1 else ".").rstrip("/") + "/"  # folder with nflverse ngs_{receiving,rushing,passing}.csv.gz
D = (sys.argv[2] if len(sys.argv) > 2 else N).rstrip("/") + "/"  # folder with rows.pkl and stw_<yr>.csv (usage backtest)
BASE = ["pf", "z", "mu", "imp", "upj", "snap_tr"]
r = pd.read_pickle(D + "rows.pkl")
stw = pd.concat([pd.read_csv(f"{D}stw_{y}.csv", low_memory=False) for y in (2023, 2024, 2025, 2026)])
stw = stw[stw.season_type.isin(["REG", "POST"])]
opp = stw.drop_duplicates(["player_id", "season", "week"]).set_index(["player_id", "season", "week"]).opponent_team
r["opp"] = [opp.get((p, s, w)) for p, s, w in zip(r.pid, r.season, r.week)]


def prior_avg(df, idcol, cols, wcol=None, k=4, min_g=2):
    """{(id, season, week): mean of cols over the id's previous k games (same season, earlier weeks)}"""
    df = df.sort_values([idcol, "season", "week"])
    out = {}
    for (i, s), g in df.groupby([idcol, "season"]):
        rows = g[cols].values
        wts = g[wcol].values if wcol else np.ones(len(g))
        weeks = g.week.values
        for j in range(len(g)):
            lo = max(0, j - k)
            if j - lo < min_g:
                continue
            w = wts[lo:j]
            out[(i, s, weeks[j])] = (rows[lo:j] * w[:, None]).sum(0) / max(w.sum(), 1e-9)
    return out


def ngs(t):
    d = pd.read_csv(f"{N}ngs_{t}.csv.gz")
    return d[(d.week > 0) & d.season.isin([2023, 2024, 2025, 2026])]


rec, rush, pas = ngs("receiving"), ngs("rushing"), ngs("passing")
rec["sep_x"] = rec.avg_separation
FEATS = {
    "rec": (rec, ["avg_separation", "avg_cushion", "percent_share_of_intended_air_yards", "avg_yac_above_expectation",
                  "avg_intended_air_yards", "catch_percentage"], "targets"),
    "rush": (rush, ["rush_yards_over_expected_per_att", "efficiency", "percent_attempts_gte_eight_defenders", "avg_time_to_los"], "rush_attempts"),
    "pass": (pas, ["completion_percentage_above_expectation", "avg_time_to_throw", "aggressiveness", "avg_intended_air_yards",
                   "avg_air_yards_to_sticks"], "attempts"),
}
GROUP = {"rec": ["rec", "recyd"], "rush": ["car", "ryd", "rry"], "pass": ["pyd", "cmp", "att"]}


def logit(X, y, lam=1.0, it=40):
    X = np.column_stack([np.ones(len(X)), X]); b = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ b)); W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + lam * np.eye(len(b)); H[0, 0] -= lam
        b += np.linalg.solve(H, X.T @ (y - p) - lam * np.r_[0, b[1:]])
    return b


def pred(X, b):
    return 1 / (1 + np.exp(-np.column_stack([np.ones(len(X)), X]) @ b))


def ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))


def top_hit(p, y, q=.2):
    """hit rate of the model's most confident 20% (taking its side)"""
    c = np.abs(p - .5); cut = np.quantile(c, 1 - q); m = c >= cut
    return np.mean((p[m] >= .5) == (y[m] == 1)), m.sum()


summary = []
for kind, (df, cols, wcol) in FEATS.items():
    own = prior_avg(df, "player_gsis_id", cols, wcol)
    # the opponent's defense: what it allowed (mean of the NGS metrics of players facing it, weighted), previous 4 games
    gm = stw.drop_duplicates(["player_id", "season", "week"])[["player_id", "season", "week", "opponent_team"]]
    dd = df.merge(gm, left_on=["player_gsis_id", "season", "week"], right_on=["player_id", "season", "week"], how="inner")
    dd = dd.groupby(["opponent_team", "season", "week"]).apply(
        lambda g: pd.Series(np.average(g[cols].values, axis=0, weights=np.maximum(g[wcol].values, 1e-9)), index=cols)).reset_index()
    dfa = prior_avg(dd, "opponent_team", cols, None, k=5, min_g=2)
    s = r[r.m.isin(GROUP[kind])].copy()
    O = np.array([own.get((p, se, w), [np.nan] * len(cols)) for p, se, w in zip(s.pid, s.season, s.week)], dtype=float)
    A = np.array([dfa.get((o, se, w), [np.nan] * len(cols)) for o, se, w in zip(s.opp, s.season, s.week)], dtype=float)
    for i, c in enumerate(cols):
        s["o_" + c] = O[:, i]
        s["d_" + c] = A[:, i]
    for m in GROUP[kind]:
        sm = s[s.m == m]
        print(f"\n=== {kind} / {m}: {len(sm)} rows")
        for pre in ("o_", "d_"):
            for c in cols:
                f = pre + c
                d = sm.dropna(subset=[f])
                if len(d) < 400:
                    continue
                # standardise on the training years only
                tr, te = d[d.season <= 2024], d[d.season >= 2025]
                if len(tr) < 200 or len(te) < 200:
                    continue
                mu_, sd_ = tr[f].mean(), tr[f].std() or 1
                ztr, zte = ((tr[f] - mu_) / sd_).clip(-3, 3).values, ((te[f] - mu_) / sd_).clip(-3, 3).values
                ytr, yte = tr.y.values.astype(float), te.y.values.astype(float)
                b0 = logit(tr[BASE].values, ytr); b1 = logit(np.column_stack([tr[BASE].values, ztr]), ytr)
                p0 = pred(te[BASE].values, b0); p1 = pred(np.column_stack([te[BASE].values, zte]), b1)
                dll = ll(p1, yte) - ll(p0, yte)
                h0, n = top_hit(p0, yte); h1, _ = top_hit(p1, yte)
                # does the coefficient hold in the test years too (refit there)?
                bt = logit(np.column_stack([te[BASE].values, zte]), yte)
                summary.append((kind, m, f, len(te), b1[-1], bt[-1], dll * 1e4, h0, h1))
                flag = " <==" if dll > 0 and np.sign(b1[-1]) == np.sign(bt[-1]) and abs(b1[-1]) > .03 else ""
                print(f"  {f:48s} train coef {b1[-1]:+.3f} test coef {bt[-1]:+.3f}  out-of-sample dLL x1e4 {dll*1e4:+6.2f}"
                      f"  top20% hit {h0:.3f} -> {h1:.3f} (n={n}){flag}")

S = pd.DataFrame(summary, columns=["kind", "m", "feat", "n_test", "coef_tr", "coef_te", "dll_e4", "top_base", "top_new"])
S.to_csv(N + "summary.csv", index=False)
print("\nBest out-of-sample gains:")
print(S.sort_values("dll_e4", ascending=False).head(15).to_string(index=False))
