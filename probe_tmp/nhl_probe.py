"""TEMPORARY probe (nhl-probe branch only): what do ESPN, FanDuel, Pinnacle and The Odds API carry for NHL?"""
import json, os, sys, datetime as dt, urllib.request, urllib.error
sys.path.insert(0, ".")
from fetch_prices import FD, FD_KEY, PIN, PIN_KEY, get
out = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}
def safe(label, fn):
    try:
        out[label] = fn()
    except Exception as e:
        out[label] = f"ERR {e}"
# --- FanDuel
def fd():
    r = {}
    page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId=nhl&_ak={FD_KEY}&timezone=America%2FNew_York")
    evs = (page.get("attachments") or {}).get("events", {})
    now = dt.datetime.now(dt.timezone.utc)
    ups = sorted([e for e in evs.values() if " @ " in e["name"] and dt.datetime.fromisoformat(e["openDate"].replace("Z", "+00:00")) > now], key=lambda e: e["openDate"])
    r["events"] = [(e["name"], e["openDate"], e["eventId"]) for e in ups[:8]]
    if not ups:
        return r
    ev = ups[0]
    r["tabs"] = {}
    for tab in ("", "player-props", "shots-on-goal", "player-shots-on-goal", "goalscorer", "goal-scorer", "goalscorer-props", "points", "player-points", "assists", "player-assists", "saves", "goalie-props", "player-saves", "player-goals", "popular", "goals", "points-assists", "shots", "points-assists-props", "shots-props", "goals-props", "period-player-props", "quick-hits", "player-props-shots", "shots-on-goal-props", "goalie-saves", "player-shots", "any-time-goal-scorer", "points-assists-goals"):
        try:
            d = get(f"{FD}/event-page?_ak={FD_KEY}&eventId={ev['eventId']}" + (f"&tab={tab}" if tab else ""))
            ms = (d.get("attachments") or {}).get("markets", {}).values()
            names = sorted({m.get("marketName") for m in ms})
            r["tabs"][tab or "(none)"] = {"n": len(names), "names": names[:40]}
            if tab == "popular":
                samp = []
                for m in (d.get("attachments") or {}).get("markets", {}).values():
                    if m.get("marketName") in ("2+ Shots on Goal", "Any Time Goal Scorer", "1+ Points", "Alt Total Goals"):
                        samp.append({"name": m["marketName"], "n": len(m.get("runners") or []), "first": [(x.get("runnerName"), x.get("handicap"), (x.get("winRunnerOdds") or {}).get("americanDisplayOdds", {}).get("americanOdds")) for x in (m.get("runners") or [])[:4]]})
                r["popular_sample"] = samp
                r["popular_names_all"] = sorted({m.get("marketName") for m in (d.get("attachments") or {}).get("markets", {}).values()})
            if tab == "" :
                r["layout"] = json.dumps(d.get("layout"))[:1500]
        except Exception as e:
            r["tabs"][tab or "(none)"] = f"ERR {e}"
    return r
safe("fanduel", fd)
# --- Pinnacle
def pin():
    head = {"X-API-Key": PIN_KEY}
    leagues = get(f"{PIN}/sports/4/leagues?all=false", **head)
    nhl = [l for l in leagues if "NHL" in (l.get("name") or "")]
    r = {"leagues": [(l["id"], l["name"], l.get("matchupCount")) for l in nhl]}
    if nhl:
        lid = nhl[0]["id"]
        mu = get(f"{PIN}/leagues/{lid}/matchups", **head)
        cats = {}
        for m in mu:
            sp = m.get("special") or {}
            if sp:
                cats.setdefault(sp.get("category"), []).append(sp.get("description"))
        r["special_categories"] = {k: (len(v), v[:12]) for k, v in cats.items()}
        r["n_matchups"] = len(mu)
    return r
safe("pinnacle", pin)
# --- ESPN box score
def espn():
    r = {}
    day = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).strftime("%Y%m%d")
    sb = get(f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={day}")
    done = [e for e in sb["events"] if e["status"]["type"].get("completed")]
    r["completed_yesterday"] = len(done)
    if done:
        s = get(f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event={done[0]['id']}")
        r["summary_keys"] = list(s.keys())
        bp = (s.get("boxscore") or {}).get("players") or []
        r["teams"] = len(bp)
        if bp:
            t = bp[0]
            r["stat_groups"] = [(g.get("name"), g.get("labels"), g.get("keys"), (g.get("athletes") or [None])[0]) for g in t.get("statistics", [])]
            r["team_keys"] = list(t.keys())
    return r
safe("espn", espn)
# --- The Odds API (1 credit)
def oddsapi():
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        return "no key"
    u = f"https://api.the-odds-api.com/v4/sports/icehockey_nhl/events?apiKey={key}"
    evs = json.loads(urllib.request.urlopen(u, timeout=40).read())
    r = {"events": len(evs)}
    if evs:
        u2 = f"https://api.the-odds-api.com/v4/sports/icehockey_nhl/events/{evs[0]['id']}/odds?apiKey={key}&regions=us&markets=player_shots_on_goal,player_assists,player_total_saves&bookmakers=draftkings,fanduel&oddsFormat=american"
        resp = urllib.request.urlopen(u2, timeout=40)
        d = json.loads(resp.read())
        r["remaining"] = resp.headers.get("x-requests-remaining")
        r["books"] = [(b["key"], [(m["key"], len(m["outcomes"])) for m in b["markets"]]) for b in d.get("bookmakers", [])]
        r["game"] = d.get("home_team"), d.get("away_team")
        r["sample"] = {}
        for b in d.get("bookmakers", []):
            for m in b["markets"]:
                r["sample"][b["key"] + "|" + m["key"]] = [(o.get("name"), o.get("description"), o.get("point"), o.get("price")) for o in m["outcomes"][:6]]
    return r
safe("oddsapi", oddsapi)
json.dump(out, open("probe_tmp/nhl_probe_out.json", "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str)[:6000])
