"""Usage, red-zone, pace, pass-rate-over-expected and defender data from nflverse (free, public).

Shared by build_usage.py (the live usage.json the picks read) and backtest_usage.py (which checks each signal
against past seasons before it gets any weight).

  team_games(pbp)     one row per team per game: plays, dropbacks, rushes, pass rate over expected (PROE)
  player_games(...)   one row per player per game: snap %, targets, target share, air-yards share, carries,
                      carry share, red-zone (inside the 10) carries + targets, goal-line (inside the 5) carries
  defender_games(...) one row per defender per game: defensive snap %, position group (CB, S, LB, DL)
"""
import pandas as pd

PBP_COLS = ["game_id", "season_type", "week", "posteam", "defteam", "play_type", "yardline_100", "qb_dropback",
            "rush_attempt", "pass_attempt", "xpass", "pass_oe", "rusher_player_id", "receiver_player_id",
            "passer_player_id", "qb_kneel", "qb_spike", "two_point_attempt"]
DEF_GROUP = {"CB": "CB", "DB": "CB", "S": "S", "FS": "S", "SS": "S", "LB": "LB", "ILB": "LB", "OLB": "LB",
             "MLB": "LB", "DE": "DL", "DT": "DL", "DL": "DL", "NT": "DL", "EDGE": "DL"}


def read_pbp(path):
    p = pd.read_csv(path, usecols=lambda c: c in PBP_COLS, low_memory=False, compression="gzip")
    p = p[p.play_type.isin(["pass", "run"]) & (p.qb_kneel != 1) & (p.qb_spike != 1) & (p.two_point_attempt != 1)]
    return p


def team_games(pbp):
    g = pbp.groupby(["game_id", "posteam"])
    t = pd.DataFrame({"plays": g.size(), "drop": g.qb_dropback.sum(), "rush": g.rush_attempt.sum(),
                      "proe": g.pass_oe.mean() / 100.0}).reset_index().rename(columns={"posteam": "team"})
    return t


def player_games(pbp, stats, snaps, pfr2gsis):
    """per player per game usage; `stats` is nflverse stats_player_week, `snaps` is snap_counts"""
    rz = pbp[pbp.yardline_100 <= 10]
    rzc = rz[rz.rush_attempt == 1].groupby(["game_id", "rusher_player_id"]).size()
    rzt = rz[rz.pass_attempt == 1].groupby(["game_id", "receiver_player_id"]).size()
    glc = pbp[(pbp.yardline_100 <= 5) & (pbp.rush_attempt == 1)].groupby(["game_id", "rusher_player_id"]).size()
    tc = pbp[pbp.rush_attempt == 1].groupby(["game_id", "posteam"]).size()
    trz = rz.groupby(["game_id", "posteam"]).size()
    s = stats[["player_id", "game_id", "team", "position", "season", "week", "targets", "target_share",
               "air_yards_share", "carries", "attempts"]].copy()
    s["rz"] = [rzc.get((g, p), 0) + rzt.get((g, p), 0) for g, p in zip(s.game_id, s.player_id)]
    s["gl"] = [glc.get((g, p), 0) for g, p in zip(s.game_id, s.player_id)]
    s["team_rush"] = [tc.get((g, t), 0) for g, t in zip(s.game_id, s.team)]
    s["team_rz"] = [trz.get((g, t), 0) for g, t in zip(s.game_id, s.team)]
    s["carry_share"] = s.carries / s.team_rush.where(s.team_rush > 0)
    s["rz_share"] = s.rz / s.team_rz.where(s.team_rz > 0)
    sn = snaps[snaps.offense_snaps > 0][["game_id", "pfr_player_id", "offense_pct"]].copy()
    sn["player_id"] = sn.pfr_player_id.map(pfr2gsis)
    sn = sn.dropna(subset=["player_id"]).drop_duplicates(["game_id", "player_id"])
    s = s.merge(sn[["game_id", "player_id", "offense_pct"]], on=["game_id", "player_id"], how="left")
    for c in ("target_share", "air_yards_share", "carry_share", "rz_share"):
        s[c] = pd.to_numeric(s[c], errors="coerce").fillna(0.0)
    return s.rename(columns={"offense_pct": "snap"})


def defender_games(snaps):
    d = snaps[(snaps.defense_snaps > 0)][["game_id", "season", "week", "pfr_player_id", "player", "position",
                                          "team", "opponent", "defense_pct"]].copy()
    d["grp"] = d.position.map(DEF_GROUP)
    return d.dropna(subset=["grp"])
