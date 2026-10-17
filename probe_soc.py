import json, urllib.request
def get(u):
    try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
    except Exception as e: return {"ERR": str(e)}
out = {}
for lg in ["eng.1", "esp.1", "fra.1", "usa.1"]:
    sb = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard")
    ev = [e for e in sb.get("events", []) if e["status"]["type"]["state"] == "pre"][:1]
    for e in ev:
        o = (e["competitions"][0].get("odds") or [None])[0]
        out[lg] = o
json.dump(out, open("out/probe.json", "w"), indent=1)
