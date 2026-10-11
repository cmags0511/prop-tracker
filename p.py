import json,urllib.request
H={"User-Agent":"Mozilla/5.0"}
g=lambda u: json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=30).read())
for lg in ("eng.2","eng.1"):
    for d in ("20260920","20260926","20260927","20260930","20261001","20261003","20261004"):
        sb=g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={d}")
        print(lg,d,[(e['name'][:30],e['status']['type']['state']) for e in sb.get('events',[])][:12])
sb=g("https://site.api.espn.com/apis/site/v2/sports/soccer/eng.2/scoreboard?dates=20260920-20261005")
print('range',len(sb.get('events',[])))
