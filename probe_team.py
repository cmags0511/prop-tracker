import json, subprocess, sys, urllib.request
out = subprocess.run([sys.executable, "soccer_team.py", "probe_st.json"], capture_output=True, text=True, timeout=1500)
print(out.stdout[-6000:]); print(out.stderr[-3000:])
r = urllib.request.urlopen(urllib.request.Request("https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates=20261018", headers={"User-Agent": "Mozilla/5.0"}), timeout=30)
d = json.loads(r.read()); e = d["events"][0]; c = e["competitions"][0]
s = json.loads(urllib.request.urlopen(urllib.request.Request("https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary?event=" + e["id"], headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
hc = s["header"]["competitions"][0]
print("SUMMARY", [(x["homeAway"], x.get("score"), x.get("linescores")) for x in hc["competitors"]])
print("KEYS", list(s.keys()), [k for k in (s.get("keyEvents") or [])[:3]])
print("ESPN", e["name"], c["status"]["type"], [(x["homeAway"], x["score"], x.get("linescores")) for x in c["competitors"]])
