
## How the Top 10 is ranked

`picks.py` scores every prop that has a DraftKings line using:
- **Form**: weighted hit rate vs the line (last 10, season, last 5) and how far his average sits from it. Lines far from his recent numbers are trusted less, since that usually reflects news, and players who sat out their team's latest game are weighted down.
- **Matchup**: what players at his position have done against the opponent over its last 10 games.
- **Game script** (football): the team's implied points from the spread and total.
- **Minutes** (NBA): last 3 games vs last 15.
- **Injuries** (every 3 hours, `fetch_context.py` → `context.json`, from ESPN's injury reports): players listed Out, Doubtful, IR or suspended are dropped; Questionable/Day-To-Day players are weighted down slightly and flagged. In the NBA, when regulars who held part of the team's recent scoring, rebounding, assists or minutes are ruled out, his teammates' overs get a boost (backtest: overs hit about 58% when 20%+ of the team's production sat, vs 52% when nobody did). NFL teammate absences are shown but not weighted, since the backtest found no reliable effect.
- **Weather** (football, Open-Meteo forecast at kickoff): wind above 10 mph weighs on passing and receiving props (backtest: passing overs hit about 39% with 15+ mph wind). Indoor stadiums are skipped.
- **Research**: twice a day (7:54 AM and 4:54 PM ET) a scheduled Claude task researches the top candidates and scouts the whole slate, mostly for overs (injuries and practice reports, role and usage trends, coaching and game plan, rest and travel, weather, the opposing roster and defense, line movement, expert and bettor views), picks a daily Best bet and writes `notes.json`; each pick gets a -2..+2 adjustment, and ruled-out players are dropped.

The app shows overs by default ("Overs" / "Overs + unders" switch); `picks.json` has `picksOver`, `byMarketOver` and `gamesOver` lists for that, and `record.json` grades both Top 10s (each entry's `sets`).

Weights for form, matchup, game script and minutes come from a walk-forward backtest on 2025 NFL and 2025-26 NBA games: favorable matchups hit about 57.5% vs about 51-54% for unfavorable ones.
