"""Kickoff weather for the Walters page: what fell at past games (backtests) and the forecast for coming ones.

Both come from Open-Meteo (free, no key) at the stadium, summed over kickoff and the next 3 hours: temperature (F,
average), wind (mph, highest hour), rain (mm) and snow (cm). Past games are kept in walters_wx.json (game id ->
{temp, wind, rain, snow}), filled in a few days after each game once the archive has it.

What the backtest (every outdoor game since 2009, against closing lines) found, which decides how each is used:
  rain under   2mm+ of rain at kickoff: the under went 59% (53% in 2009-17, 64% since). A totals pick, 1 unit
  rain factor  Walters' +0.25 for the visitor: no effect on the side, kept at his value
  snow         ~40 games, no effect: shown on the card, 0 points
  wind x pass  15+ mph wind against the pass-heavier team: the closing line already has it. Shown, 0 points
  QB weather   each QB's cover record in the cold, heat, wind, wet and domes (Walters' 0.15-point QB W-factors)
               didn't predict his next game in those conditions. Shown, 0 points
The rain under was the best of a few cutoffs tried (2, 4, 6mm), and live picks run on a forecast rather than what
fell, so expect it to do somewhat worse than the backtest.
"""
import csv, io, json, time, datetime as dt, collections as C
import urllib.request
from zoneinfo import ZoneInfo
import walters_book as B

CACHE = "walters_wx.json"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
HOURLY = "hourly=temperature_2m,rain,snowfall,wind_speed_10m&wind_speed_unit=mph&temperature_unit=fahrenheit&timezone=UTC"
TEAM_STATS = "https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_{}.csv"
ET = ZoneInfo("America/New_York")
RAIN_MM = 2.0           # the rain under: 2mm+ over kickoff and the next 3 hours
SNOW_CM, WIND_SIDE = .5, 15
COND = {"cold": "the cold (35F or less)", "hot": "the heat (80F+)", "wind": "15+ mph wind", "wet": "rain or snow",
        "dome": "domes"}


def _get(url):
    for k in range(3):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "prop-tracker"}),
                                                     timeout=60).read())
        except Exception as e:
            err = e
            time.sleep(5 * (k + 1))
    raise err


def kickoff(g):
    """kickoff in UTC from nflverse's Eastern date and time"""
    return dt.datetime.fromisoformat(f'{g["day"]}T{g.get("time") or "13:00"}').replace(tzinfo=ET).astimezone(dt.timezone.utc)


def outdoor(g):
    return (g.get("roof") or "") in ("outdoors", "open", "")


def _sum(h, k0):
    """kickoff + 3 hours from Open-Meteo's hourly arrays"""
    idx = {t: i for i, t in enumerate(h["time"])}
    ii = [idx.get((k0 + dt.timedelta(hours=j)).strftime("%Y-%m-%dT%H:00")) for j in range(4)]
    ii = [i for i in ii if i is not None]
    v = lambda k: [h[k][i] for i in ii if h[k][i] is not None]
    if not v("temperature_2m"):
        return None
    return {"temp": round(sum(v("temperature_2m")) / len(v("temperature_2m")), 1), "wind": round(max(v("wind_speed_10m") or [0]), 1),
            "rain": round(sum(v("rain")), 1), "snow": round(sum(v("snowfall")), 2)}


def history(games, now):
    """walters_wx.json, topped up with outdoor games from 6+ days ago that it doesn't have yet"""
    try:
        wx = json.load(open(CACHE))
    except Exception:
        wx = {}
    todo = C.defaultdict(list)
    for g in games:
        if g["season"] >= 2009 and g["margin"] is not None and outdoor(g) and g["id"] not in wx \
                and kickoff(g) < now - dt.timedelta(days=6):
            la, lo, _ = B.site(g)
            todo[(round(la, 2), round(lo, 2))].append(g)
    for (la, lo), gs in todo.items():
        d0, d1 = min(g["day"] for g in gs), max(g["day"] for g in gs)
        d1 = (dt.date.fromisoformat(d1) + dt.timedelta(days=1)).isoformat()
        try:
            h = _get(f"{ARCHIVE}?latitude={la}&longitude={lo}&start_date={d0}&end_date={d1}&{HOURLY}")["hourly"]
        except Exception as e:
            print(f"weather archive {la},{lo} failed: {e}")
            continue
        for g in gs:
            w = _sum(h, kickoff(g))
            if w:
                wx[g["id"]] = w
    if todo:
        json.dump(dict(sorted(wx.items())), open(CACHE, "w"), separators=(",", ":"))
    return wx


_fc = {}


def forecast(g, k0):
    """the kickoff forecast for a coming outdoor game (Open-Meteo forecasts 16 days out), or None"""
    la, lo, _ = B.site(g)
    key = (round(la, 2), round(lo, 2))
    if key not in _fc:
        try:
            _fc[key] = _get(f"{FORECAST}?latitude={key[0]}&longitude={key[1]}&forecast_days=16&{HOURLY}")["hourly"]
        except Exception as e:
            print(f"weather forecast {key} failed: {e}")
            _fc[key] = None
    return _sum(_fc[key], k0) if _fc[key] else None


def conds(w, indoor):
    """the conditions Walters rates each QB in"""
    if indoor:
        return {"dome"}
    c = set()
    if w:
        if w["temp"] <= 35:
            c.add("cold")
        if w["temp"] >= 80:
            c.add("hot")
        if w["wind"] >= WIND_SIDE:
            c.add("wind")
        if w["rain"] >= RAIN_MM or w["snow"] >= SNOW_CM:
            c.add("wet")
    return c


def qb_records(done, wx):
    """QB id -> condition -> [covers, non-covers], from every finished game since 2009"""
    rec = C.defaultdict(lambda: C.defaultdict(lambda: [0, 0]))
    for g in done:
        if g["season"] < 2009 or g["spread"] is None:
            continue
        r = g["margin"] - g["spread"]    # home cover margin
        if not r:
            continue
        for c in conds(wx.get(g["id"]), not outdoor(g)):
            for q, won in ((g["qb_h"], r > 0), (g["qb_a"], r < 0)):
                if q:
                    rec[q][c][0 if won else 1] += 1
    return rec


def pass_rates(season):
    """team -> share of plays that are dropbacks (passes + sacks) this season, from nflverse team stats"""
    try:
        rows = csv.DictReader(io.StringIO(urllib.request.urlopen(TEAM_STATS.format(season), timeout=60).read().decode()))
    except Exception as e:
        print(f"team stats {season} failed: {e}")
        return {}
    t = C.defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        db = float(r["attempts"] or 0) + float(r["sacks_suffered"] or 0)
        t[r["team"]][0] += db
        t[r["team"]][1] += db + float(r["carries"] or 0)
    return {k: v[0] / v[1] for k, v in t.items() if v[1] >= 100}


def notes(g, w, indoor, qbs, prate, tm):
    """the weather things Walters weighs that tested at zero: shown on the card, 0 points"""
    out = []
    if w and not indoor and w["snow"] >= SNOW_CM:
        out.append(f"snow in the forecast ({w['snow']:.1f} cm)")
    if w and not indoor and w["wind"] >= WIND_SIDE:
        ph, pa = prate.get(g["rh"]), prate.get(g["ra"])
        if ph is not None and pa is not None:
            out.append(f"{w['wind']:.0f} mph wind: {tm(g['ra'])} pass {pa:.0%} of plays, {tm(g['rh'])} {ph:.0%}")
    for c in sorted(conds(w, indoor)):
        for s in ("a", "h"):
            r = qbs.get(g.get("qb_" + s), {}).get(c)
            if r and sum(r) >= 3:
                out.append(f"{g.get('qbn_' + s) or 'QB'} in {COND[c]}: {r[0]}–{r[1]} ATS")
    return out
