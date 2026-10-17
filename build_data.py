"""Build props_data.json for the Prop Tracker from free, open datasets.

Downloads (all public GitHub releases):
  - nflverse weekly player stats (last season + current season)
  - nflverse schedule (dates, home/away, closing spreads and totals, upcoming games)
  - sportsdataverse NBA player box scores (last season + current season when it exists)
  - sportsdataverse NBA schedule (upcoming games)

Usage: python3 build_data.py [output_path]
"""
import io, json, sys, time, datetime as dt
import urllib.request
import pandas as pd

OUT = sys.argv[1] if len(sys.argv) > 1 else "props_data.json"
NFLV = "https://github.com/nflverse/nflverse-data/releases/download"
SDV = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.astimezone(dt.timezone(dt.timedelta(hours=-4))).date()


def _read(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        raw = io.BytesIO(r.read())
    if url.endswith(".parquet"):
        return pd.read_parquet(raw)
    return pd.read_csv(raw, low_memory=False, compression="gzip" if url.endswith(".gz") else None)


def get_csv(url, required=True):
    """Download a data file. Data publishers sometimes switch formats or briefly remove a file
    while re-uploading it, so try the .csv, .csv.gz and .parquet versions and retry once."""
    base = url[:-4] if url.endswith(".csv") else url
    tries = [url] + ([base + ".csv.gz", base + ".parquet"] if url.endswith(".csv") else [])
    last = None
    for attempt in range(2):
        for u in tries:
            try:
                return _read(u)
            except Exception as e:
                last = e
        time.sleep(20)
    if required:
        raise RuntimeError(f"could not download {url}: {last}")
    print(f"skip {url}: {last}")
    return None


# ---------------- seasons ----------------
# NFL season label = year it starts (Sept). NBA file label = year it ends (2026 = 2025-26).
nfl_cur = TODAY.year if TODAY.month >= 8 else TODAY.year - 1
nba_end = TODAY.year + 1 if TODAY.month >= 8 else TODAY.year  # season that is current or next up

out = {"built": NOW.isoformat(timespec="minutes")}

# players DraftKings has posted a line for are always kept, even if their usage is below the
# cutoffs (e.g. a backup QB who's starting, or a low-target WR with a receptions line)
try:
    _lines = json.load(open("lines.json"))
    POSTED = {lg: set(_lines.get(lg) or {}) for lg in ("NFL", "NBA")}
except Exception:
    POSTED = {"NFL": set(), "NBA": set()}

# ---------------- NBA ----------------
frames = []
for yr in (nba_end - 1, nba_end):
    d = get_csv(f"{SDV}/espn_nba_player_boxscores/player_box_{yr}.csv", required=(yr == nba_end - 1))
    if d is not None and len(d):
        frames.append(d)
n = pd.concat(frames)
n = n[n.season_type.isin([2, 3])]
n = n[(n.did_not_play != True) & (n.minutes.fillna(0) > 0)]
n["game_date"] = pd.to_datetime(n.game_date)
n = n.sort_values("game_date")
has_cur = (n.season == nba_end).any()
cur_nba = nba_end if has_cur else nba_end - 1
recent = n[n.season >= nba_end - 1]
stats = recent.groupby("athlete_id").agg(gp=("minutes", "size"), mpg=("minutes", "mean"))
cur_gp = n[n.season == cur_nba].groupby("athlete_id").size()
keep = set(stats[(stats.gp >= 15) & (stats.mpg >= 16)].index)
if has_cur:
    keep |= set(cur_gp[cur_gp >= 3].index)
keep |= {a for a in n.athlete_id.unique() if str(int(a)) in POSTED["NBA"]}
nba = []
for pid, d in n[n.athlete_id.isin(keep)].groupby("athlete_id"):
    last = d.iloc[-1]
    games = [[r.game_date.strftime("%Y-%m-%d"), r.opponent_team_abbreviation, 1 if r.home_away == "home" else 0,
              int(round(r.minutes)), int(r.points), int(r.rebounds), int(r.assists),
              int(r.three_point_field_goals_made), int(r.season_type == 3)] for r in d.itertuples()]
    nba.append({"id": str(int(pid)), "n": last.athlete_display_name, "t": last.team_abbreviation,
                "p": last.athlete_position_abbreviation, "g": games})
nba_label = lambda end: f"{end-1}-{str(end)[2:]}"
cur_start = n[n.season == cur_nba].game_date.min().strftime("%Y-%m-%d")

sched = get_csv(f"{SDV}/espn_nba_schedules/nba_schedule_{nba_end}.csv", required=False)
nba_up = []
if sched is not None:
    s = sched.copy()
    s["dt"] = pd.to_datetime(s.date, utc=True)
    s = s[(s.dt >= NOW - pd.Timedelta(hours=4)) & (s.dt <= NOW + pd.Timedelta(days=30))].sort_values("dt")
    for r in s.itertuples():
        nba_up.append([r.dt.isoformat(), r.away_abbreviation, r.home_abbreviation, None, None, None])
# each team's pace: possessions per game over its last 10 (this season once it has 5+ games). In the backtest
# (train 2023-25, test 2025-26) a fast matchup nudged every stat over slightly, about +0.07 log-odds per 5 possessions
pace = {}
try:
    tb = pd.concat([x for x in (get_csv(f"{SDV}/espn_nba_team_boxscores/team_box_{yr}.csv", required=False)
                                for yr in (nba_end - 1, nba_end)) if x is not None])
    tb = tb[tb.season_type == 2].copy()
    for c in ["field_goals_attempted", "offensive_rebounds", "turnovers", "free_throws_attempted"]:
        tb[c] = pd.to_numeric(tb[c], errors="coerce").fillna(0)
    tb["poss"] = tb.field_goals_attempted - tb.offensive_rebounds + tb.turnovers + .44 * tb.free_throws_attempted
    tb = tb.sort_values("game_date")
    for t, d in tb.groupby("team_abbreviation"):
        c = d[d.season == cur_nba]
        if len(d) < 20:  # all-star and exhibition teams
            continue
        pace[t] = round(float((c if len(c) >= 5 else d).poss.tail(10).mean()), 1)
except Exception as e:
    print(f"NBA pace skipped: {e}")
out["NBA"] = {"season": nba_label(cur_nba), "curStart": cur_start, "hasCur": bool(has_cur), "pace": pace,
              "cols": ["date", "opp", "home", "min", "pts", "reb", "ast", "3pm", "po"],
              "players": nba, "upcoming": nba_up}

# ---------------- NFL ----------------
weeks = [get_csv(f"{NFLV}/stats_player/stats_player_week_{nfl_cur-1}.csv")]
w = get_csv(f"{NFLV}/stats_player/stats_player_week_{nfl_cur}.csv", required=False)
if w is not None:
    weeks.append(w)
f = pd.concat(weeks)
raw_weeks = f.copy()  # every player's line, before the usage filters below (record.py grades from it)
OFF = ["QB", "RB", "WR", "TE"]
DEF = ["DB", "LB", "DL"]
f = f[(f.position.isin(OFF + ["K"]) | f.position_group.isin(DEF)) & f.season_type.isin(["REG", "POST"])].copy()
for c in ["attempts", "carries", "targets", "completions", "passing_yards", "passing_tds", "rushing_yards",
          "receptions", "receiving_yards", "rushing_tds", "receiving_tds", "fg_made", "fg_att", "pat_made", "pat_att",
          "def_tackles_solo", "def_tackle_assists", "def_sacks", "def_interceptions"]:
    if c not in f:
        f[c] = 0
    f[c] = pd.to_numeric(f[c], errors="coerce").fillna(0)
f["tkl"] = f.def_tackles_solo + f.def_tackle_assists
# keep games where the player actually did something in his role
# any game where he touched the ball or was targeted counts (dropping low-usage games inflated hit rates)
f = f[(f.position.isin(OFF) & (f.attempts + f.carries + f.targets >= 1))
      | ((f.position == "K") & (f.fg_att + f.pat_att > 0))
      | (f.position_group.isin(DEF) & (f.tkl + f.def_sacks + f.def_interceptions > 0))]
sch = get_csv(f"{NFLV}/schedules/games.csv")
f = f.merge(sch[["game_id", "gameday", "home_team", "spread_line", "total_line"]], on="game_id", how="left")
f = f.sort_values(["season", "week"])
pl = get_csv(f"{NFLV}/players/players.csv", required=False)
espn = {}
if pl is not None:
    espn = {g: str(int(e)) for g, e in zip(pl.gsis_id, pl.espn_id) if e == e}
nfl = []
for pid, d in f.groupby("player_id"):
    pos = d.position.iloc[-1]
    if d.position_group.iloc[-1] in DEF:
        pos = d.position_group.iloc[-1]
    cur = d[d.season == nfl_cur]
    if espn.get(pid) in POSTED["NFL"]:
        pass
    elif len(d) < 5 and len(cur) < 2:
        continue
    elif pos == "QB" and d.attempts.mean() < 20: continue
    elif pos == "RB" and (d.carries + d.targets).mean() < 6: continue
    elif pos in ("WR", "TE") and d.targets.mean() < 3: continue
    elif pos in DEF and d.tkl.mean() < 3.5 and d.def_sacks.mean() < .4: continue
    games = []
    for r in d.itertuples():
        sp = None if r.spread_line != r.spread_line else (-float(r.spread_line) if r.home_team == r.team else float(r.spread_line))
        tot = None if r.total_line != r.total_line else float(r.total_line)
        games.append([str(r.gameday), int(r.week), 1 if r.season_type == "POST" else 0, r.opponent_team,
                      1 if r.home_team == r.team else 0, sp, tot,
                      int(r.completions), int(r.attempts), int(r.passing_yards), int(r.passing_tds),
                      int(r.carries), int(r.rushing_yards), int(r.receptions), int(r.receiving_yards),
                      int(r.rushing_tds + r.receiving_tds), int(r.fg_made), int(r.pat_made), int(r.tkl),
                      float(r.def_sacks), int(r.def_interceptions)])
    nfl.append({"id": pid, "e": espn.get(pid), "n": d.player_display_name.iloc[-1], "t": d.team.iloc[-1], "p": pos, "g": games})

up = sch[(sch.season == nfl_cur) & sch.result.isna()].copy()
up = up[pd.to_datetime(up.gameday).dt.date >= TODAY - dt.timedelta(days=1)]
up = up[pd.to_datetime(up.gameday).dt.date <= TODAY + dt.timedelta(days=30)].sort_values(["gameday", "gametime"])
nfl_up = []
for r in up.itertuples():
    # nflverse times are US/Eastern; store with the EDT/EST offset of that date
    day = dt.date.fromisoformat(r.gameday)
    off = "-04:00" if dt.date(day.year, 3, 8) <= day < dt.date(day.year, 11, 1) else "-05:00"
    t = f"{r.gameday}T{r.gametime if isinstance(r.gametime, str) else '13:00'}:00{off}"
    home_sp = None if r.spread_line != r.spread_line else -float(r.spread_line)
    tot = None if r.total_line != r.total_line else float(r.total_line)
    nfl_up.append([t, r.away_team, r.home_team, home_sp, tot, int(r.week)])
out["NFL"] = {"season": str(nfl_cur), "curStart": f"{nfl_cur}-08-01",
              "cols": ["date", "week", "po", "opp", "home", "spread", "total", "cmp", "att", "pyd", "ptd",
                       "car", "ryd", "rec", "recyd", "td", "fgm", "pat", "tkl", "sck", "dint"],
              "players": nfl, "upcoming": nfl_up}

json.dump(out, open(OUT, "w"), separators=(",", ":"))

# ---------------- box_recent.json: every NFL player's stat line from the last 3 weeks ----------------
# The app's player list keeps only regulars, but a Top 10 pick or research call can be on a fringe player; when his
# line comes down after kickoff he drops off that list and his bet could not be graded (it was voided after 3 days).
# This keeps every stat line, plus a 0 line for anyone who took a snap without recording a stat (nflverse snap counts),
# so those bets grade as the win or loss they were.
try:
    cut = (TODAY - dt.timedelta(days=21)).isoformat()
    r = raw_weeks[raw_weeks.season_type.isin(["REG", "POST"])].merge(sch[["game_id", "gameday"]], on="game_id", how="left")
    r = r[r.gameday >= cut].copy()
    for c in ["completions", "attempts", "passing_yards", "passing_tds", "carries", "rushing_yards", "receptions",
              "receiving_yards", "rushing_tds", "receiving_tds", "fg_made", "pat_made", "def_tackles_solo",
              "def_tackle_assists", "def_sacks", "def_interceptions"]:
        r[c] = pd.to_numeric(r.get(c, 0), errors="coerce").fillna(0)
    box = {}
    for x in r.itertuples():
        box.setdefault(x.player_id, []).append([str(x.gameday), x.opponent_team, int(x.completions), int(x.attempts),
            int(x.passing_yards), int(x.passing_tds), int(x.carries), int(x.rushing_yards), int(x.receptions),
            int(x.receiving_yards), int(x.rushing_tds + x.receiving_tds), int(x.fg_made), int(x.pat_made),
            int(x.def_tackles_solo + x.def_tackle_assists), float(x.def_sacks), int(x.def_interceptions)])
    zeros = 0
    sn = get_csv(f"{NFLV}/snap_counts/snap_counts_{nfl_cur}.csv", required=False)
    if sn is not None and pl is not None:
        pfr = dict(zip(pl.pfr_id, pl.gsis_id))
        g = sch.set_index("game_id")
        sn = sn[(sn.offense_snaps + sn.defense_snaps + sn.st_snaps) > 0]
        for x in sn.itertuples():
            gid = pfr.get(x.pfr_player_id)
            if gid is None or x.game_id not in g.index or str(g.gameday[x.game_id]) < cut:
                continue
            day, opp = str(g.gameday[x.game_id]), x.opponent
            if not any(row[0] == day for row in box.get(gid, [])):
                box.setdefault(gid, []).append([day, opp] + [0] * 14)
                zeros += 1
    json.dump({"built": NOW.isoformat(timespec="minutes"),
               "cols": ["date", "opp", "cmp", "att", "pyd", "ptd", "car", "ryd", "rec", "recyd", "td", "fgm", "pat", "tkl", "sck", "dint"],
               "players": box}, open("box_recent.json", "w"), separators=(",", ":"))
    print(f"box_recent.json: {len(box)} players ({zeros} snap-only zero lines)")
except Exception as e:
    print(f"box_recent.json skipped: {e}")
print(f"NBA {len(nba)} players ({out['NBA']['season']}), {len(nba_up)} upcoming | "
      f"NFL {len(nfl)} players ({nfl_cur}), {len(nfl_up)} upcoming -> {OUT}")
