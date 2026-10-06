"""Pull DraftKings player prop lines from ESPN's public data feed into lines.json.

ESPN's scoreboard and odds feeds are free and need no key, but they are not an official,
documented API: ESPN can change or remove them at any time. If a fetch fails, the existing
lines.json is kept so the app keeps showing the last good lines.

What ESPN provides: the current DraftKings line and the opening line for each player prop.
It does not include the odds (prices) for player props.

Optional settings (environment variables):
  LINES_DAYS_NFL   look this many days ahead for NFL games (default 7)
  LINES_DAYS_NBA   look this many days ahead for NBA games (default 2)

Usage: python fetch_lines.py [lines.json]
"""
import json, os, re, sys, time, datetime as dt
import urllib.request, urllib.error

OUT = sys.argv[1] if len(sys.argv) > 1 else "lines.json"
DK = "100"  # ESPN's provider id for DraftKings
LEAGUES = {
    "NFL": ("football", "nfl", int(os.environ.get("LINES_DAYS_NFL") or 7)),
    "NBA": ("basketball", "nba", int(os.environ.get("LINES_DAYS_NBA") or 2)),
}
SKIP = re.compile(r"half|quarter|\b1st\b|\b2nd\b|first|longest|double|triple|steal|block|turnover|interception|scorer|or more|milestone")


def market(lg, name):
    """Map ESPN's prop name (e.g. 'Total Passing Yards (incl. overtime)') to the app's prop id."""
    n = name.lower()
    if SKIP.search(n):
        return None
    if lg == "NFL":
        if "rushing" in n and "receiving" in n and "yards" in n:
            return "rry"
        if "plus" in n or "+" in n:
            return None
        for key, prop in [("passing yards", "pyd"), ("pass completions", "cmp"), ("completions", "cmp"),
                          ("passing attempts", "att"), ("pass attempts", "att"), ("passing touchdowns", "ptd"),
                          ("rushing yards", "ryd"), ("carries", "car"), ("rushing attempts", "car"),
                          ("receiving yards", "recyd"), ("receptions", "rec")]:
            if key in n:
                return prop
        return None
    pts, reb, ast = "point" in n and "3" not in n and "three" not in n, "rebound" in n, "assist" in n
    if pts and reb and ast:
        return "pra"
    if pts and reb:
        return "pr"
    if pts and ast:
        return "pa"
    if reb and ast:
        return "ra"
    if "three" in n or "3-point" in n or "3 point" in n or "3pt" in n:
        return "3pm"
    if pts:
        return "pts"
    if reb:
        return "reb"
    if ast:
        return "ast"
    return None


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (prop-tracker)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    out = {"fetched": now.isoformat(timespec="minutes"), "book": "DraftKings", "NFL": {}, "NBA": {}}
    any_ok = False
    for lg, (sport, league, days) in LEAGUES.items():
        start = now.astimezone(dt.timezone(dt.timedelta(hours=-5))).date()
        end = start + dt.timedelta(days=days)
        try:
            sb = get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
                     f"?dates={start:%Y%m%d}-{end:%Y%m%d}&limit=200")
        except Exception as e:
            print(f"{lg}: scoreboard failed ({e}); keeping previous {lg} lines")
            out[lg] = old.get(lg, {})
            continue
        any_ok = True
        events = [e for e in sb.get("events", []) if e.get("status", {}).get("type", {}).get("state") == "pre"]
        got = 0
        for ev in events:
            base = (f"https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}"
                    f"/events/{ev['id']}/competitions/{ev['id']}/odds/{DK}/propBets")
            page, pages, items = 1, 1, []
            try:
                while page <= pages:
                    d = get(f"{base}?limit=1000&page={page}")
                    items += d.get("items", [])
                    pages = d.get("pageCount", 1) or 1
                    page += 1
            except urllib.error.HTTPError as e:
                if e.code != 404:  # 404 = no props posted yet for this game
                    print(f"{lg} {ev.get('shortName')}: props failed ({e.code})")
                continue
            except Exception as e:
                print(f"{lg} {ev.get('shortName')}: props failed ({e})")
                continue
            for it in items:
                ref = (it.get("athlete") or {}).get("$ref", "")
                m = re.search(r"/athletes/(\d+)", ref)
                prop = market(lg, (it.get("type") or {}).get("name", ""))
                cur = ((it.get("current") or {}).get("target") or {}).get("value")
                if not m or not prop or cur is None:
                    continue
                opn = ((it.get("open") or {}).get("target") or {}).get("value")
                rec = out[lg].setdefault(m.group(1), {})
                prev = rec.get(prop)
                upd = it.get("lastUpdated", "")
                if prev is None or upd > prev.get("u", ""):
                    rec[prop] = {"line": cur, "open": opn, "u": upd, "g": ev.get("shortName", "")}
                    got += prev is None
            time.sleep(0.2)
        print(f"{lg}: {len(events)} upcoming games, {got} player lines")
    if not any_ok:
        print("ESPN unreachable; keeping previous lines.json")
        return
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
