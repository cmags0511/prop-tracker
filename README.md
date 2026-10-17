
## How the Top 10 is ranked

`picks.py` scores every prop that has a DraftKings line using:
- **Form**: weighted hit rate vs the line (last 10, season, last 5) and how far his average sits from it. Lines far from his recent numbers are trusted less, since that usually reflects news, and players who sat out their team's latest game are weighted down.
- **Matchup**: what players at his position have done against the opponent over its last 10 games.
- **Game script** (football): the team's implied points from the spread and total.
- **Minutes** (NBA): last 3 games vs last 15.
- **Injuries** (every 3 hours, `fetch_context.py` → `context.json`, from ESPN's injury reports): players listed Out, Doubtful, IR or suspended are dropped; Questionable/Day-To-Day players are weighted down slightly and flagged. In the NBA, when regulars who held part of the team's recent scoring, rebounding, assists or minutes are ruled out, his teammates' overs get a boost (backtest: overs hit about 58% when 20%+ of the team's production sat, vs 52% when nobody did). NFL teammate absences are shown but not weighted, since the backtest found no reliable effect.
- **Weather** (football, Open-Meteo forecast at kickoff): wind above about 12 mph weighs on passing and receiving props, more as it rises (backtest: no drop at 10-15 mph, but passing overs hit about 39% with 15+ mph wind). Indoor stadiums are skipped.
- **Research** (see `RESEARCH.md`): once a day in full (7:34 AM ET), plus a quick 4:34 PM news check and a Sunday 11:34 AM inactives check, a scheduled Claude task researches the props the app shows (Top 10s, game Top 5s, Kalshi gaps): `research_packets.py` groups the games into at most 4 batches, one researcher per batch, looking past the numbers (availability, role and usage, matchup and scheme, game script, conditions, market, expert views); `merge_notes.py` validates the write-ups into `notes.json`, and each prop card shows the findings and sources. A college researcher finds published prop lines for the week's biggest college games (DraftKings college props aren't in the free feed) and the app ranks them with its own numbers. Kalshi game-winner odds appear on NFL and college game cards.

- **Prediction market** (`fetch_markets.py` → `markets.json`, every 3 hours): Kalshi lists ladder markets for NFL and NBA players ("250+ passing yards" priced 0-100 cents = the crowd's probability). The app reads the ladder at DraftKings' line to get the market's chance of the over and adds it to the score (weight 0.8 in log-odds, capped). Wide bid/ask quotes are skipped, and only pre-game prices for the same game are used. Kalshi's market data API is public and free.
- **Starters vs backups** (ESPN depth charts in `context.json`, NFL and NBA): backups rank at half strength unless the research check says his role grew; a player whose starter is ruled out moves up.
- **Prop-type checks** (backtest by prop type): yardage overs (receiving, rushing, rush+rec) were close to a coin flip even when the form score was confident, so their form signal is shrunk 30% on the over side. Lines of 0.5/1.5 on count props usually carry heavy juice that a hit rate can't see, so they rank lower and get a "Check odds" tag. The Best-overall Top 10 takes at most 3 picks of any one prop type.

The app shows overs by default ("Overs" / "Overs + unders" switch); `picks.json` has `picksOver`, `byMarketOver` and `gamesOver` lists for that, and `record.json` grades both Top 10s (each entry's `sets`).

Weights for form, matchup, game script and minutes come from a walk-forward backtest on 2025 NFL and 2025-26 NBA games: favorable matchups hit about 57.5% vs about 51-54% for unfavorable ones.

## Research notes: how they're read

Every note says which side the evidence **favors** (`side`) and how firmly (`adj` +1 lean, +2 strong, 0 nothing clear).
`merge_notes.py` stores "against the over" as "for the under", so every note reads one way; `picks.py` (`research_dir`),
`record.py` and the app all use the same rule. `caution` means the outlook is uncertain (questionable, role in flux),
not a direction: it ranks the pick a bit lower. A pick the research firmly favors the other side of is dropped; one the
research only leans against ranks much lower. `audit_top.py` flags any Top 10 pick that's unresearched or disagrees.

## Touchdowns

`picks.py` → `tdTop`: a backtested anytime-TD model (TD rate, touches, TDs per touch, team implied points, position;
calibrated on 2025-26 games) blended with Kalshi's "1+ TD" price and the research. Two Top 10s: likeliest and plus
money. `tdAll` feeds the "most profitable plus-money TDs" section: expected profit from real prices (The Odds API, when a
key is set) or odds typed into the app.

## Soccer

`soccer_data.py` (every 3 hours, prices hourly with `--light`): every league ESPN carries DraftKings soccer props for.
It keeps four months of player match stats (`soccer_hist.json.gz`), reads each upcoming match's priced props (goals,
shots, shots on target, assists, saves, fouls, cards), and estimates each chance with a Poisson model (recent starts and
sub appearances, shrunk toward the position average, scaled by the team's expected goals from DraftKings' total and
moneylines). `backtest_soccer.py` checks it against every past appearance; the per-stat calibration and per-position
corrections in `soccer_data.py` come from it. The chance is blended with DraftKings' price, and expected profit =
chance × payout. Club and international form are kept apart. The daily research checks availability and rotation for
the soccer Top 10s. `soccer_close.json` holds the last price before kickoff (closing line value).

## Records and tracking

`record.json` locks every Top 10 (props, TDs, soccer, the research's own calls) at kickoff and grades it from the box
score; `calib.json` grades every slate prop for the Probability check; `closing.json` keeps kickoff lines. Units use the sportsbook price saved with each pick: `fetch_prices.py` reads
Pinnacle's public odds (no key) for every NFL, NBA and college prop it lists, and FanDuel's for what Pinnacle doesn't
price (rush + rec yards, kicking points from FanDuel's team ladders) or prices at a different line. Prices are always
for DraftKings' line: when a book's line differs, usually by a yard or two on yardage props, its price is moved to
DraftKings' line and marked ≈. The record
counts from `priced_from`, the first run with real prices, so units never mix real prices with an assumed -110. My picks and
parlays live on the device, update live from ESPN box scores during games, and grade themselves at the final.

## Usage signals (build_usage.py)

From nflverse's free play-by-play, snap counts and weekly stats, every update builds `usage.json`: each NFL
player's snap share and its trend, target and carry share, red-zone (inside the 10) and goal-line looks, and a
usage projection per prop (share x team volume x efficiency). Backtested on 2025-26 games with a model fit on
2023-24: the usage projection, snap-share trend and red-zone looks (anytime TDs) improved the predictions and
are used, at half their backtested weight. Team pace, pass rate over expected, opponents' missing defenders, a
backup QB starting, and rest / short weeks did not improve them and carry no weight. NBA: team pace helped
slightly and is used; back-to-backs, blowout risk and usage-rate trends did not. tune.py re-weights the usage
factor from real graded results like every other factor.
