"""Build usage.json: how each NFL player is being used, from nflverse's free play-by-play, snap counts and
weekly stats. The picks use it for two signals that held up in a backtest on 2025-26 games (trained on 2023-24):

  proj     a usage projection per prop: his target / carry share (last 6 games) x his team's dropbacks /
           rushes (last 6) x his efficiency (last 16 games, shrunk toward league norms). Results swing week to
           week; usage is steadier, so a projection well above or below the line is a real signal.
  snap_tr  his snap share in his last 2 games minus the 4 before: a role that's growing (or shrinking).
  rz, gl   red-zone (inside the 10) carries + targets, and goal-line (inside the 5) carries, per game over his
           last 6: the anytime-TD model's strongest addition.

Also kept, for context only (they did not improve the backtest, so they carry no weight): each team's pace and
pass rate over expected.

Usage: python build_usage.py [usage.json]
"""
import io, json, sys, time, datetime as dt
import urllib.request
import pandas as pd
from usage_lib import read_pbp, team_games, player_games

OUT = sys.argv[1] if len(sys.argv) > 1 else "usage.json"
NFLV = "https://github.com/nflverse/nflverse-data/releases/download"
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.astimezone(dt.timezone(dt.timedelta(hours=-4))).date()
CUR = TODAY.year if TODAY.month >= 8 else TODAY.year - 1


def fetch(url, required=True):
    for attempt in range(2):
        for u in ([url, url[:-4] + ".csv.gz"] if url.endswith(".csv") else [url]):
            try:
                with urllib.request.urlopen(u, timeout=180) as r:
                    raw = io.BytesIO(r.read())
                return raw
            except Exception as e:
                last = e
        time.sleep(15)
    if required:
        raise RuntimeError(f"could not download {url}: {last}")
    print(f"skip {url}: {last}")
    return None


def csv(url, required=True, **kw):
    raw = fetch(url, required)
    if raw is None:
        return None
    gz = raw.getvalue()[:2] == b"\x1f\x8b"
    return pd.read_csv(raw, low_memory=False, compression="gzip" if gz else None, **kw)


def main():
    pbp, stats, snaps = [], [], []
    for y in (CUR - 1, CUR):
        raw = fetch(f"{NFLV}/pbp/play_by_play_{y}.csv.gz", required=(y == CUR - 1))
        if raw is not None:
            pbp.append(read_pbp(raw))
        s = csv(f"{NFLV}/stats_player/stats_player_week_{y}.csv", required=(y == CUR - 1))
        if s is not None:
            stats.append(s)
        n = csv(f"{NFLV}/snap_counts/snap_counts_{y}.csv", required=False)
        if n is not None:
            snaps.append(n)
    pbp, stats, snaps = pd.concat(pbp), pd.concat(stats), pd.concat(snaps)
    stats = stats[stats.season_type.isin(["REG", "POST"])].copy()
    for c in ["completions", "attempts", "passing_yards", "carries", "rushing_yards", "receptions", "targets", "receiving_yards"]:
        stats[c] = pd.to_numeric(stats[c], errors="coerce").fillna(0)
    pl = csv(f"{NFLV}/players/players.csv")
    pfr2gsis = dict(zip(pl.pfr_id, pl.gsis_id))
    sch = csv(f"{NFLV}/schedules/games.csv")
    order = {g: i for i, g in enumerate(sch.sort_values(["gameday", "gametime"]).game_id)}
    tg = team_games(pbp)
    tg["o"] = tg.game_id.map(order)
    tg = tg.dropna(subset=["o"]).sort_values("o")
    pg = player_games(pbp, stats, snaps, pfr2gsis)
    pg["o"] = pg.game_id.map(order)
    pg = pg.dropna(subset=["o"]).sort_values("o")
    stats["o"] = stats.game_id.map(order)
    stats = stats.dropna(subset=["o"]).sort_values("o")

    teams = {}
    lg_plays = tg.groupby("team").tail(6).plays.mean()
    for t, d in tg.groupby("team"):
        d = d.tail(6)
        teams[t] = {"drop": round(d["drop"].mean(), 1), "rush": round(d.rush.mean(), 1), "plays": round(d.plays.mean(), 1),
                    "proe": round(float(d.proe.mean()), 3) if d.proe.notna().any() else None}
    players = {}
    sh = {p: d for p, d in stats.groupby("player_id")}
    for pid, u in pg.groupby("player_id"):
        pos = u.position.iloc[-1]
        if pos not in ("QB", "RB", "WR", "TE", "FB"):
            continue
        u = u.tail(6)
        if len(u) < 3 or u.season.iloc[-1] < CUR - 1:
            continue
        team = u.team.iloc[-1]
        t = teams.get(team)
        if not t:
            continue
        past = sh[pid].tail(16)
        tgt, rec, ryds, cyd, car = past.targets.sum(), past.receptions.sum(), past.receiving_yards.sum(), past.rushing_yards.sum(), past.carries.sum()
        ypt = (ryds + 8.0 * 20) / (tgt + 20)
        cr = (rec + .65 * 20) / (tgt + 20)
        ypc = (cyd + 4.3 * 30) / (car + 30)
        tsh, csh = float(u.target_share.mean()), float(u.carry_share.mean())
        pt = t["drop"] * .93 * tsh
        proj = {"rec": pt * cr, "recyd": pt * ypt, "ryd": t["rush"] * csh * ypc, "car": t["rush"] * csh}
        proj["rry"] = proj["ryd"] + proj["recyd"]
        if pos == "QB":
            pa = past[past.attempts > 0]
            att = t["drop"] * .93
            proj = {"att": att, "cmp": att * (pa.completions.sum() + .64 * 60) / (pa.attempts.sum() + 60),
                    "pyd": att * (pa.passing_yards.sum() + 6.8 * 60) / (pa.attempts.sum() + 60)}
        snap = u.snap.dropna()
        snap_tr = float(snap.tail(2).mean() - snap.head(max(1, len(snap) - 2)).mean()) if len(snap) >= 4 else 0.0
        players[pid] = {"team": team, "pos": pos, "proj": {k: round(v, 1) for k, v in proj.items()},
                        "snap": round(float(snap.iloc[-1]), 2) if len(snap) else None, "snap_tr": round(snap_tr, 3),
                        "tsh": round(tsh, 3), "csh": round(csh, 3), "rz": round(float(u.rz.mean()), 2), "gl": round(float(u.gl.mean()), 2),
                        "last": str(u.game_id.iloc[-1])}
    out = {"built": NOW.isoformat(timespec="minutes"), "season": CUR, "league_plays": round(float(lg_plays), 1),
           "teams": teams, "players": players}
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(players)} players, {len(teams)} teams")


if __name__ == "__main__":
    main()
