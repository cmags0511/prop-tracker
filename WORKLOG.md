# Work log

Newest first. One entry per change: date, who, what, and anything the other person should know.
Mark unfinished work **IN PROGRESS** (with the files it touches) and update the entry when it's done.

## 2026-10-17
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
