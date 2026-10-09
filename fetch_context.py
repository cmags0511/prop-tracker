"""Pull the non-stat context the picks use into context.json: injury reports and game-day weather.

  injuries  ESPN's public injury reports (NFL, NBA, college): status (Out, Doubtful, Questionable,
            Day-To-Day, Injured Reserve...), injury and ESPN's short note, keyed by ESPN athlete id.
  weather   for every upcoming outdoor football game (NFL and college): wind, temperature and chance of
            rain at kickoff from Open-Meteo's free forecast. Stadium towns are looked up once with
            Open-Meteo's geocoder and cached in context.json. Indoor stadiums are marked indoor.

Both sources are free and need no key; neither is an official, documented API. If a source fails, the
previous values are kept so the picks still have something to work with.

Usage: python fetch_context.py [context.json]
"""
import json, sys, time, datetime as dt
import urllib.request, urllib.parse

OUT = sys.argv[1] if len(sys.argv) > 1 else "context.json"
H = {"User-Agent": "Mozilla/5.0 (prop-tracker)"}
ESPN = "https://site.api.espn.com/apis/site/v2/sports"
LEAGUES = {"NFL": "football/nfl", "NBA": "basketball/nba", "CFB": "football/college-football"}
ROOFED = {"SoFi Stadium"}  # covered stadiums ESPN doesn't mark as indoor
FIX = {"NFL": {"LAR": "LA", "WSH": "WAS"}}  # ESPN abbreviation -> the app's (nflverse) abbreviation
STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
          "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
          "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
          "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
          "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
          "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
          "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
          "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
          "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
          "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def team(lg, abbr):
    return FIX.get(lg, {}).get(abbr, abbr)


def injuries(lg, path):
    d = get(f"{ESPN}/{path}/injuries")
    out = {}
    for t in d.get("injuries", []):
        for i in t.get("injuries", []):
            a = i.get("athlete") or {}
            aid = next((l["href"].split("/id/")[1].split("/")[0] for l in a.get("links", []) if "/id/" in l.get("href", "")), None)
            if not aid or i.get("status") in (None, "Active"):
                continue
            det = i.get("details") or {}
            # skip stale entries (ESPN's college feed carries years-old ones); IR stays, it's long-term by nature
            try:
                age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat((i.get("date") or "").replace("Z", "+00:00"))
                if age > dt.timedelta(days=30) and i["status"] != "Injured Reserve":
                    continue
            except ValueError:
                pass
            out[aid] = {"n": a.get("displayName", ""), "t": team(lg, (a.get("team") or {}).get("abbreviation", "")),
                        "pos": (a.get("position") or {}).get("abbreviation", ""), "s": i["status"],
                        "inj": det.get("type") or "", "ret": det.get("returnDate") or "",
                        "c": (i.get("shortComment") or "")[:220], "d": i.get("date", "")}
    return out


def geocode(city, state, country, cache):
    key = f"{city}|{state}|{country}"
    if key in cache:
        return cache[key]
    res = None
    try:
        d = get("https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": city, "count": 10, "language": "en"}))
        rs = d.get("results") or []
        want = STATES.get(state)
        pick = [r for r in rs if want and r.get("admin1") == want] or \
               [r for r in rs if country in ("USA", "United States") and r.get("country_code") == "US"] or rs
        if pick:
            res = [round(pick[0]["latitude"], 3), round(pick[0]["longitude"], 3)]
    except Exception as e:
        print(f"geocode {key} failed: {e}")
        return None
    cache[key] = res
    return res


def weather(lg, path, days, geo, now):
    out = {}
    today = now.astimezone(dt.timezone(dt.timedelta(hours=-5))).date()
    fc = {}
    for k in range(days + 1):
        try:
            sb = get(f"{ESPN}/{path}/scoreboard?dates={today + dt.timedelta(days=k):%Y%m%d}" + ("&groups=80&limit=400" if lg == "CFB" else ""))
        except Exception as e:
            print(f"{lg} scoreboard failed: {e}")
            continue
        for e in sb.get("events", []):
            if e.get("status", {}).get("type", {}).get("state") != "pre":
                continue
            c = e["competitions"][0]
            tm = {x["homeAway"]: team(lg, (x.get("team") or {}).get("abbreviation", "")) for x in c["competitors"]}
            if not tm.get("home") or not tm.get("away"):
                continue
            v = c.get("venue") or {}
            ad = v.get("address") or {}
            t = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            key = f"{tm.get('away')}@{tm.get('home')}|{t:%Y-%m-%d}"
            rec = {"venue": v.get("fullName", ""), "indoor": bool(v.get("indoor")) or v.get("fullName") in ROOFED, "t": t.isoformat()}
            if not rec["indoor"] and ad.get("city"):
                ll = geocode(ad["city"], ad.get("state", ""), ad.get("country", "USA"), geo)
                if ll and (t - now) < dt.timedelta(days=15):
                    try:
                        lk = tuple(ll)
                        if lk not in fc:
                            fc[lk] = get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
                                "latitude": ll[0], "longitude": ll[1], "hourly": "wind_speed_10m,wind_gusts_10m,precipitation_probability,temperature_2m",
                                "wind_speed_unit": "mph", "temperature_unit": "fahrenheit", "timezone": "UTC", "forecast_days": 16}))
                            time.sleep(.1)
                        h = fc[lk]["hourly"]
                        want = t.strftime("%Y-%m-%dT%H:00")
                        if want in h["time"]:
                            # average over the game's first three hours
                            i = h["time"].index(want)
                            sl = lambda k: [x for x in h[k][i:i + 3] if x is not None]
                            avg = lambda k: round(sum(sl(k)) / len(sl(k)), 1) if sl(k) else None
                            rec.update(wind=avg("wind_speed_10m"), gust=avg("wind_gusts_10m"),
                                       rain=max(sl("precipitation_probability") or [0]), temp=avg("temperature_2m"))
                    except Exception as ex:
                        print(f"forecast {key} failed: {ex}")
            out[key] = rec
    return out


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    geo = old.get("geo", {})
    stamp = now.isoformat(timespec="minutes")
    # "fetched" = when each league's injury report was last pulled successfully; the picks ignore
    # a league's report once it's more than 30 hours old, so a broken feed can't keep stale news alive
    ctx = {"built": stamp, "fetched": dict(old.get("fetched") or {}), "injuries": {}, "weather": {}, "geo": geo}
    for lg, path in LEAGUES.items():
        try:
            ctx["injuries"][lg] = injuries(lg, path)
            ctx["fetched"][lg] = stamp
        except Exception as e:
            print(f"{lg} injuries failed ({e}); keeping previous")
            ctx["injuries"][lg] = (old.get("injuries") or {}).get(lg, {})
            ctx["fetched"].setdefault(lg, old.get("built", "2000-01-01T00:00+00:00"))
    for lg, days in (("NFL", 7), ("CFB", 4)):
        try:
            w = weather(lg, LEAGUES[lg], days, geo, now)
            # keep last run's forecast for upcoming games a failed scoreboard request skipped
            for k, v in (old.get("weather") or {}).items():
                if k.startswith(lg + "|") and k[len(lg) + 1:] not in w and v.get("t") and dt.datetime.fromisoformat(v["t"]) > now:
                    ctx["weather"][k] = v
            ctx["weather"].update({f"{lg}|{k}": v for k, v in w.items()})
        except Exception as e:
            print(f"{lg} weather failed ({e}); keeping previous")
            ctx["weather"].update({k: v for k, v in (old.get("weather") or {}).items() if k.startswith(lg + "|")})
    json.dump(ctx, open(OUT, "w"), separators=(",", ":"))
    from collections import Counter
    print(f"wrote {OUT}: " + ", ".join(f"{lg} {len(v)} injuries {dict(Counter(x['s'] for x in v.values()))}" for lg, v in ctx["injuries"].items())
          + f"; weather for {len(ctx['weather'])} games, {sum(1 for w in ctx['weather'].values() if w.get('wind') is not None)} with forecasts")


if __name__ == "__main__":
    main()
