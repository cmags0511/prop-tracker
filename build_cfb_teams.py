"""ESPN's college team abbreviations -> names, for matching games in the odds feeds (fetch_odds.py, fetch_oddspapi.py).
Writes cfb_teams.json {"ABBR": ["Northwestern Wildcats", "Northwestern"]}. Run when a new season starts or a match fails."""
import json, urllib.request
B = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams"
out = {}
# FBS first, then FCS, then everyone else: the first team to claim an abbreviation keeps it (OSU is Ohio State, not a small school)
for groups in ("80", "81", ""):
    for page in range(1, 6):
        with urllib.request.urlopen(urllib.request.Request(f"{B}?limit=300&page={page}" + (f"&groups={groups}" if groups else ""),
                                                          headers={"User-Agent": "prop-tracker"}), timeout=40) as r:
            teams = json.load(r)["sports"][0]["leagues"][0]["teams"]
        if not teams:
            break
        for t in teams:
            t = t["team"]
            out.setdefault(t["abbreviation"], [t["displayName"], t.get("shortDisplayName") or t.get("location") or t["displayName"]])
json.dump(out, open("cfb_teams.json", "w"), separators=(",", ":"), sort_keys=True)
print(f"wrote cfb_teams.json: {len(out)} teams")
