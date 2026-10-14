import json, urllib.request
def get(u):
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
    except Exception as e:
        return {"ERR": str(e)}
out = {}
# Kalshi: every sports series whose ticker or title mentions college football
ser = get("https://api.elections.kalshi.com/trade-api/v2/series?category=Sports")
L = ser.get("series") or []
out["n_series"] = len(L)
out["ncaaf_series"] = [(s.get("ticker"), s.get("title")) for s in L if "NCAAF" in (s.get("ticker") or "").upper() or "college football" in (s.get("title") or "").lower()]
for t in ["KXNCAAFPASSYDS", "KXNCAAFRSHYDS", "KXNCAAFRECYDS", "KXNCAAFTD", "KXCFBPASSYDS"]:
    m = get(f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={t}&status=open&limit=5")
    out[t] = {"n": len(m.get("markets") or []), "sample": [x.get("title") for x in (m.get("markets") or [])[:3]], "err": m.get("ERR")}
# ESPN: odds providers on a big upcoming CFB game
sb = get("https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&limit=400&dates=20261017")
evs = [e for e in sb.get("events", [])][:6]
out["games"] = []
for e in evs:
    eid = e["id"]
    od = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{eid}/competitions/{eid}/odds")
    provs = [(i.get("provider", {}).get("id"), i.get("provider", {}).get("name")) for i in od.get("items", [])]
    pb = {}
    for pid, _ in provs:
        r = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{eid}/competitions/{eid}/odds/{pid}/propBets?limit=5")
        pb[pid] = r.get("count", r.get("ERR"))
    out["games"].append({"name": e.get("shortName"), "providers": provs, "propBets": pb})
json.dump(out, open("out/probe.json", "w"), indent=1)
