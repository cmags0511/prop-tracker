
## How the Top 10 is ranked

`picks.py` scores every prop that has a DraftKings line using:
- **Form**: weighted hit rate vs the line (last 10, season, last 5) and how far his average sits from it. Lines far from his recent numbers are trusted less, since that usually reflects news, and players who sat out their team's latest game are weighted down.
- **Matchup**: what players at his position have done against the opponent over its last 10 games.
- **Game script** (football): the team's implied points from the spread and total.
- **Minutes** (NBA): last 3 games vs last 15.
- **Injuries** (every 3 hours, `fetch_context.py` → `context.json`, from ESPN's injury reports): players listed Out, Doubtful, IR or suspended are dropped; Questionable/Day-To-Day players are weighted down slightly and flagged. In the NBA, when regulars who held part of the team's recent scoring, rebounding, assists or minutes are ruled out, his teammates' overs get a boost (backtest: overs hit about 58% when 20%+ of the team's production sat, vs 52% when nobody did). NFL teammate absences are shown but not weighted, since the backtest found no reliable effect.
- **Weather** (football, Open-Meteo forecast at kickoff): wind above about 12 mph weighs on passing and receiving props, more as it rises (backtest: no drop at 10-15 mph, but passing overs hit about 39% with 15+ mph wind). Indoor stadiums are skipped.
- **Research** (see `RESEARCH.md`): twice a day (7:34 AM and 4:34 PM ET), plus a light Sunday 11:34 AM inactives check, a scheduled Claude task researches the props the app shows (Top 10s, game Top 5s, Kalshi gaps): `research_packets.py` groups the games into at most 4 batches, one researcher per batch, looking past the numbers (availability, role and usage, matchup and scheme, game script, conditions, market, expert views); `merge_notes.py` validates the write-ups into `notes.json`, and each prop card shows the findings and sources. A college researcher finds published prop lines for the week's biggest college games (DraftKings college props aren't in the free feed) and the app ranks them with its own numbers. Kalshi game-winner odds appear on NFL and college game cards.

- **Prediction market** (`fetch_markets.py` → `markets.json`, every 3 hours): Kalshi lists ladder markets for NFL and NBA players ("250+ passing yards" priced 0-100 cents = the crowd's probability). The app reads the ladder at DraftKings' line to get the market's chance of the over and adds it to the score (weight 0.8 in log-odds, capped). Wide bid/ask quotes are skipped, and only pre-game prices for the same game are used. Kalshi's market data API is public and free.
- **Starters vs backups** (ESPN depth charts in `context.json`, NFL and NBA): backups rank at half strength unless the research check says his role grew; a player whose starter is ruled out moves up.
- **Prop-type checks** (backtest by prop type): yardage overs (receiving, rushing, rush+rec) were close to a coin flip even when the form score was confident, so their form signal is shrunk 30% on the over side. Lines of 0.5/1.5 on count props usually carry heavy juice that a hit rate can't see, so they rank lower and get a "Check odds" tag. The Best-overall Top 10 takes at most 3 picks of any one prop type.

The app shows overs by default ("Overs" / "Overs + unders" switch); `picks.json` has `picksOver`, `byMarketOver` and `gamesOver` lists for that, and `record.json` grades both Top 10s (each entry's `sets`).

Weights for form, matchup, game script and minutes come from a walk-forward backtest on 2025 NFL and 2025-26 NBA games: favorable matchups hit about 57.5% vs about 51-54% for unfavorable ones.
