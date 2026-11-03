"""NHL game history from ESPN's public box scores -> nhl_hist.json.gz.

For every finished NHL game (regular season and playoffs) it stores each skater's ice time, power-play time, goals,
assists, shots on goal, blocks and hits, each goalie's shots faced and saves, and each team's shots for and against.
That is the history the NHL tab's chances are built from (nhl_model.py).

It crawls ESPN's scoreboard day by day, newest first, and caps the number of new games per run (MAX_NEW) so the
first runs fill in this season and then work back through last season; later runs only add the last few days.

Output: nhl_hist.json.gz
  {"built", "done_days": [...], "events": {espn event id: ET date},
   "players": {id: {"n": name, "t": team, "p": position, "g": [[date, opp, home, toi, pptoi, g, a, s, blk, hit], ...]}},
   "goalies": {id: {"n", "t", "g": [[date, opp, home, toi, shots against, saves, goals against], ...]}},
   "teams": {abbr: [[date, opp, home, shots for, shots against, goals for, goals against], ...]},
   "names": {abbr: full team name}, "upcoming": [{"id", "t", "away", "home"}]}

Usage: python nhl_data.py [nhl_hist.json.gz]
"""
import datetime as dt
import gzip
import json
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

OUT = sys.argv[1] if len(sys.argv) > 1 else "nhl_hist.json.gz"
ET = ZoneInfo("America/New_York")
START = dt.date(2025, 10, 4)   # last season's opening week: the crawl works back to here
MAX_NEW = 350                  # new games per run
BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0",
                                               "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))


def num(v):
    """'15:16' -> 15.27 (minutes); '2' -> 2.0; anything else -> None"""
    if v is None:
        return None
    s = str(v).strip()
    try:
        if ":" in s:
            m, _, sec = s.partition(":")
            return int(m) + int(sec) / 60
        return float(s)
    except ValueError:
        return None


def load(path):
    try:
        return json.load(gzip.open(path, "rt"))
    except Exception:
        return {"done_days": [], "events": {}, "players": {}, "goalies": {}, "teams": {}, "names": {}, "upcoming": []}


def et_date(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET).date()


def add_game(h, ev):
    """parse one finished game's box score into the history; returns False if there was nothing usable"""
    comp = ev["competitions"][0]
    cs = {c["homeAway"]: c for c in comp["competitors"]}
    date = str(et_date(ev["date"]))
    abbr = {k: c["team"]["abbreviation"] for k, c in cs.items()}
    for k, c in cs.items():
        h["names"][abbr[k]] = c["team"].get("displayName") or abbr[k]
    sm = get(f"{BASE}/summary?event={ev['id']}")
    teams = (sm.get("boxscore") or {}).get("players") or []
    if len(teams) != 2:
        return False
    shots = {}
    rows = []
    for t in teams:
        ta = t["team"]["abbreviation"]
        home = 1 if ta == abbr["home"] else 0
        opp = abbr["away"] if home else abbr["home"]
        sf = 0
        for grp in t.get("statistics", []):
            keys = grp.get("keys") or []
            for a in grp.get("athletes") or []:
                st = {k: num(v) for k, v in zip(keys, a.get("stats") or [])}
                at = a["athlete"]
                pid = str(at["id"])
                toi = st.get("timeOnIce") or 0
                if grp.get("name") == "goalies":
                    sa, sv, ga = st.get("shotsAgainst"), st.get("saves"), st.get("goalsAgainst")
                    if toi <= 0 or sa is None:
                        continue
                    if sv is None:
                        sv = sa - (ga or 0)
                    g = h["goalies"].setdefault(pid, {"n": at.get("displayName"), "t": ta, "g": []})
                    g["n"], g["t"] = at.get("displayName"), ta
                    rows.append(("g", pid, [date, opp, home, round(toi, 1), int(sa), int(sv), int(ga or 0)]))
                else:
                    if toi <= 0:
                        continue
                    pos = ((at.get("position") or {}).get("abbreviation")) or ""
                    s = int(st.get("shotsTotal") or 0)
                    sf += s
                    p = h["players"].setdefault(pid, {"n": at.get("displayName"), "t": ta, "p": pos, "g": []})
                    p["n"], p["t"], p["p"] = at.get("displayName"), ta, pos or p["p"]
                    rows.append(("p", pid, [date, opp, home, round(toi, 1), round(st.get("powerPlayTimeOnIce") or 0, 1),
                                            int(st.get("goals") or 0), int(st.get("assists") or 0), s,
                                            int(st.get("blockedShots") or 0), int(st.get("hits") or 0)]))
        shots[ta] = sf
    if not rows:
        return False
    for kind, pid, r in rows:
        (h["players"] if kind == "p" else h["goalies"])[pid]["g"].append(r)
    for k in ("home", "away"):
        o = "away" if k == "home" else "home"
        h["teams"].setdefault(abbr[k], []).append([date, abbr[o], 1 if k == "home" else 0, shots.get(abbr[k], 0), shots.get(abbr[o], 0),
                                                   int(num(cs[k].get("score")) or 0), int(num(cs[o].get("score")) or 0)])
    h["events"][str(ev["id"])] = date
    return True


def main():
    h = load(OUT)
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(ET).date()
    done = set(h.get("done_days") or [])
    new = fail = 0
    day = today
    while day >= START and new < MAX_NEW:
        ds = str(day)
        recent = (today - day).days <= 2   # the last few days are always re-read (late stat corrections, games that ended after midnight)
        if ds in done and not recent:
            day -= dt.timedelta(days=1)
            continue
        try:
            sb = get(f"{BASE}/scoreboard?dates={day:%Y%m%d}")
        except Exception as e:
            print(f"{ds}: scoreboard failed ({e})")
            day -= dt.timedelta(days=1)
            continue
        complete = True
        for ev in sb.get("events", []):
            if (ev.get("season") or {}).get("type") not in (2, 3):
                continue
            state = ev["status"]["type"]
            if not state.get("completed"):
                complete = complete and state.get("state") == "post"
                continue
            if str(ev["id"]) in h["events"]:
                continue
            try:
                if add_game(h, ev):
                    new += 1
                time.sleep(.12)
            except Exception as e:
                fail += 1
                complete = False
                print(f"{ds} {ev.get('shortName')}: {e}")
        if complete and day < today:
            done.add(ds)
        day -= dt.timedelta(days=1)
    # upcoming games: the next 3 days
    up = []
    for k in range(0, 4):
        d = today + dt.timedelta(days=k)
        try:
            sb = get(f"{BASE}/scoreboard?dates={d:%Y%m%d}")
        except Exception:
            continue
        for ev in sb.get("events", []):
            if (ev.get("season") or {}).get("type") not in (2, 3) or ev["status"]["type"].get("state") != "pre":
                continue
            cs = {c["homeAway"]: c["team"] for c in ev["competitions"][0]["competitors"]}
            for t in cs.values():
                h["names"][t["abbreviation"]] = t.get("displayName") or t["abbreviation"]
            up.append({"id": str(ev["id"]), "t": ev["date"].replace("Z", "+00:00"), "away": cs["away"]["abbreviation"], "home": cs["home"]["abbreviation"]})
    h["upcoming"] = sorted({u["id"]: u for u in up}.values(), key=lambda u: u["t"])
    h["done_days"] = sorted(done)
    h["built"] = now.isoformat(timespec="minutes")
    for p in list(h["players"].values()) + list(h["goalies"].values()):
        p["g"].sort(key=lambda r: r[0])
    for t in h["teams"].values():
        t.sort(key=lambda r: r[0])
    with gzip.open(OUT, "wt") as f:
        json.dump(h, f, separators=(",", ":"))
    print(f"wrote {OUT}: {new} new games ({fail} failed), {len(h['events'])} total, {len(h['players'])} skaters, {len(h['goalies'])} goalies, "
          f"{len(h['upcoming'])} upcoming; crawled back to {min(done) if done else 'n/a'}")


if __name__ == "__main__":
    main()
