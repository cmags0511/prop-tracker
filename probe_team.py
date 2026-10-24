import json, os, subprocess, sys, urllib.request
from fetch_prices import get, FD, FD_KEY
page = get(f"{FD}/content-managed-page?page=SPORT&eventTypeId=1&_ak={FD_KEY}&timezone=America%2FNew_York")
comps = (page.get("attachments") or {}).get("competitions") or {}
print("COMPS", [(k, v.get("name")) for k, v in list(comps.items())[:40]])
for url in [f"{FD}/content-managed-page?page=COMPETITION&competitionId=10932509&eventTypeId=1&_ak={FD_KEY}&timezone=America%2FNew_York",
            f"{FD}/competition-page?competitionId=10932509&eventTypeId=1&_ak={FD_KEY}",
            f"{FD}/content-managed-page?page=CUSTOM&customPageId=premier-league&_ak={FD_KEY}&timezone=America%2FNew_York",
            f"{FD}/content-managed-page?page=CUSTOM&customPageId=soccer&_ak={FD_KEY}&timezone=America%2FNew_York"]:
    try:
        d = get(url); ev = (d.get("attachments") or {}).get("events") or {}
        print("OK", url[:110], len(ev), sorted({e.get("competitionId") for e in ev.values()})[:20])
    except Exception as e:
        print("ERR", url[:110], e)
env = dict(os.environ, ST_DEBUG="1")
out = subprocess.run([sys.executable, "soccer_team.py", "probe_st.json"], capture_output=True, text=True, timeout=1500, env=env)
print(out.stdout[-3000:]); print(out.stderr[-3000:])
