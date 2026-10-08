
## How the Top 10 is ranked

`picks.py` scores every prop that has a DraftKings line using:
- **Form**: weighted hit rate vs the line (last 10, season, last 5) and how far his average sits from it. Lines far from his recent numbers are trusted less, since that usually reflects news, and players who sat out their team's latest game are weighted down.
- **Matchup**: what players at his position have done against the opponent over its last 10 games.
- **Game script** (football): the team's implied points from the spread and total.
- **Minutes** (NBA): last 3 games vs last 15.
- **Research**: twice a day (7:54 AM and 4:54 PM ET) a scheduled Claude task researches the top candidates (injuries, role, game plan, opposing team stats, expert and bettor views) and writes `notes.json`; each pick gets a -2..+2 adjustment, and ruled-out players are dropped.

Weights for form, matchup, game script and minutes come from a walk-forward backtest on 2025 NFL and 2025-26 NBA games: favorable matchups hit about 57.5% vs about 51-54% for unfavorable ones.
