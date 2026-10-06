# Prop Tracker

An installable phone app (PWA) and website for NBA and NFL player props.

NBA and NFL player prop tracker built on free, open data (nflverse and sportsdataverse).
GitHub Actions rebuilds `props_data.json` every 3 hours and GitHub Pages serves the site.

## One-time setup (about 5 minutes)

1. **Create a repository.** Sign in at github.com, click **New repository**, name it `prop-tracker`, set it to **Public**, and click **Create repository**.
2. **Upload the files.** On the new repo page, click **uploading an existing file**. Drag in everything from this folder, including the hidden `.github` folder and `.nojekyll` (on a Mac press Cmd+Shift+. in Finder to show hidden files). Click **Commit changes**.
   - If the `.github` folder won't upload by dragging, create it by hand: **Add file > Create new file**, type `.github/workflows/update.yml` as the name, and paste in the contents of that file.
3. **Turn on the website.** Go to **Settings > Pages**. Under *Build and deployment*, pick **Deploy from a branch**, branch **main**, folder **/ (root)**, and click **Save**. After a minute your site is live at `https://YOUR-USERNAME.github.io/prop-tracker/`.
4. **Turn on automatic updates.** Go to the **Actions** tab and click **I understand my workflows, go ahead and enable them** if asked. Open **Update prop data** and click **Run workflow** once to test it. After that it runs every 3 hours by itself.

## Changing how often it updates

Edit the `cron` line in `.github/workflows/update.yml`. Times are in UTC. Examples:
- `"17 */3 * * *"`: every 3 hours (the default)
- `"0 10 * * *"`: once a day at 6 AM Eastern

GitHub may delay scheduled runs by a few minutes at busy times. It also pauses scheduled workflows on repositories with no activity for 60 days; the automatic data commits normally count as activity, and you can re-enable the workflow from the Actions tab if it ever stops.

## Files

- `index.html`: the site
- `props_data.json`: the data the site reads (rebuilt automatically)
- `build_data.py`: downloads the free datasets and builds `props_data.json`
- `.github/workflows/update.yml`: the schedule

## Installing it on a phone

Once the site is live, open `https://YOUR-USERNAME.github.io/prop-tracker/` on the phone.

- **iPhone (Safari):** tap the Share button, then **Add to Home Screen**. The site also shows this tip the first time.
- **Android (Chrome):** tap **Install app** at the top of the page, or use the menu > **Install app**.

It then opens full screen from its own icon, works offline with the last data it loaded, and pulls fresh numbers whenever it's opened. Share the link and anyone can install it the same way.

After you change `index.html` or other app files, bump `VERSION` in `sw.js` (for example `pt-v2`) so installed copies pick up the new version. Data updates don't need this.

## DraftKings and BetMGM odds

The app shows each player's DraftKings and BetMGM line and odds when an Odds API key is set up.

1. Sign up at https://the-odds-api.com and copy your API key.
2. In this repository go to **Settings > Secrets and variables > Actions > New repository secret**. Name it `ODDS_API_KEY` and paste the key.

That's it: the next scheduled update pulls lines for games starting in the next 36 hours (every 6 hours), for these props by default:
- NFL: passing yards, rushing yards, receiving yards, receptions, anytime TD
- NBA: points, rebounds, assists, 3-pointers, points + rebounds + assists

Each game costs roughly one credit per prop type, so about 5 credits per game per fetch. Rough monthly use with the defaults is 6,000-9,000 credits once both seasons are running, which fits The Odds API's 20K plan. The free plan (500 credits a month) is enough to test it. The script stops before your credits run below 25.

To change the defaults, add repository **variables** (same page, Variables tab): `ODDS_WINDOW_HOURS`, `ODDS_EVERY_HOURS`, `ODDS_MARKETS_NFL`, `ODDS_MARKETS_NBA` (comma-separated market keys, listed at the top of `fetch_odds.py`).
