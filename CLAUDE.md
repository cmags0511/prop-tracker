# Working on Prop Tracker (read this first)

Two people work on this repo, each with their own Claude: **cmags0511** (owner) and **rmolnar10**. The Claude
sessions can't talk to each other directly, so this file and `WORKLOG.md` are how they coordinate. Read both
before changing anything, and add to `WORKLOG.md` when you finish.

## Before you change code
1. `git pull --rebase origin main` first. Bots commit data files to main every hour (`Refresh lines`) and every
   3 hours (`Update prop data`), and the scheduled research runs commit `notes.json`, `picks.json` and `slate.json`.
2. Check `WORKLOG.md` for anything **in progress** by the other person. Don't edit the same files they're working
   on until they've pushed; if you need to, say so in the log.
3. Bigger changes (new data sources, model weights, record/grading logic, the workflows): open a pull request
   so the other person can look first. Small fixes can go straight to main.

## When you push
- Never resolve conflicts with `-X theirs` / `-X ours`, never force-push main. Those silently drop the other
  person's work. Resolve conflicts by hand, keeping both sides' changes.
- Conflicts in **generated data files** (everything in the list below) are safe to settle by taking the newest
  version and re-running the script that makes it (usually `python picks.py picks.json`).
- After a front-end change, bump `VERSION` in `sw.js` (otherwise installed apps keep the old page).
- Add a line to `WORKLOG.md`: date, who, what changed, anything the other person needs to know.

## How the app fits together
- `index.html` (the whole app, vanilla JS) + `sw.js`, served by GitHub Pages.
- Workflows: `.github/workflows/update.yml` (every 3h: full rebuild) and `lines.yml` (hourly: lines, prices,
  re-rank, lock and grade). Every step writes its outcome to `health_update.json` / `health_lines.json`; the app
  shows "⚠ Data issue" when a key step failed. Give any new step an `id:` so it's recorded.
- Generated data (don't hand-edit; re-run the script): `props_data.json` + `box_recent.json` (build_data.py),
  `cfb_data.json` (build_cfb.py), `usage.json` (build_usage.py), `context.json` (fetch_context.py),
  `lines.json` (fetch_lines.py), `markets.json` (fetch_markets.py), `odds.json` (fetch_prices.py / fetch_odds.py),
  `picks.json` + `slate.json` (picks.py), `record.json` + `calib.json` + `closing.json` (record.py),
  `tuning.json` (tune.py), `soccer*.json` (soccer_data.py).
- `notes.json` is written by the research runs (RESEARCH.md, merge_notes.py, scheduled tasks on the owner's
  account: daily research 7:34 AM ET, evening news check, game-day inactives checks).
- Model: picks.py (prop ranking; factor parts are re-weighted daily by tune.py from graded results), TD model in
  `td_board`, soccer in soccer_data.py. Any new signal should be backtested before it gets weight
  (see backtest_soccer.py; NFL/NBA backtests are described in README "Usage signals").

## House rules (from the owner)
- No real-money betting features. Don't scrape DraftKings or BetMGM directly (ESPN's feed carries DK lines).
- Research notes are in our own words: facts only, no quotes, usernames or copied picks.
- Keep API keys out of the code: secrets go in GitHub Actions secrets (e.g. `ODDS_API_KEY`).
- Be honest about results: the record, CLV and probability check show losses as plainly as wins.
