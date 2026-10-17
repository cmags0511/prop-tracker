# Work log

Newest first. One entry per change: date, who, what, and anything the other person should know.
Mark unfinished work **IN PROGRESS** (with the files it touches) and update the entry when it's done.

## 2026-10-17
- **rmolnar10**: Walters-style NFL game lines (PR): `walters.py` → `walters.json`, new hourly step `walters`
  in `lines.yml`, hidden page `view-walt` behind the "poopy?" link at the bottom of the Record tab. Data:
  nflverse schedule (games.csv), ESPN scoreboard (DK spread + prices, finals), context.json injuries. Backtest
  440-349 (55.8%) since 2012 vs closing lines at a 4+ point edge.
- **rmolnar10**: Redesign merged (PR #3): Inter type, neutral light/dark palette, bottom tabs Props · Games ·
  My picks · Record (Record = the app's graded Top 10, moved out of My picks), Soccer in the sport switch,
  Props split into Top picks / Touchdowns / Trends / All props. Light/dark switch in the header (PR #4,
  `ptTheme` in localStorage; follows the phone until picked).
- **rmolnar10** — **IN PROGRESS** (touches `index.html`, possibly `record.py`): Record tab overhaul that tracks
  Top 10 and soccer bets at real prices. Note `index.html` changes here so we can fold them in.
- **cmags0511**: slate.json and calib.json now keep each prop's sportsbook prices (`po`/`pu` over/under, `pb` book,
  `pe` estimated) so PR #2 can be judged on real results. PR #2 stays open until ~Oct 27 (two more NFL weekends).
- **cmags0511**: Navigation redesign mockup tried and dropped; the app keeps its current layout. Nothing in
  `index.html` changed, so layout work there is open again.
- **rmolnar10**: Sportsbook prices from Pinnacle and FanDuel (`fetch_prices.py`, step `fetch_prices` in both
  workflows) into `odds.json`; the record grades units at the price saved with each pick (PR #1).
- **cmags0511**: Workflows on checkout v5 / setup-python v6 (Node 24), runner pinned to ubuntu-24.04.
- **cmags0511**: Audit fixes. `build_data.py` writes `box_recent.json` (every NFL player's last 3 weeks, incl.
  snap-only zero lines) and `record.py` grades from it, so picks on fringe players are no longer voided
  (7 past voids re-graded). Soccer team strength now reads ESPN's `moneyline`/`total` blocks. Goalkeeper saves
  lean harder on the book (`MKT_W_M`). Step health files + header warning. Research notes stay usable 72h.
- **cmags0511**: College Top 5 on the CFB board (`renderCfbTop` in index.html).

## 2026-10-15
- **cmags0511**: Usage signals (`build_usage.py`, `usage_lib.py`, `usage.json`): usage projection, snap trend,
  red-zone looks in the TD model, NBA pace. Tested and not used: NFL pace/PROE, opponent missing defenders,
  backup QB, rest.
