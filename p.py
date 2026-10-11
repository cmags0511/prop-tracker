import json,urllib.request
H={"User-Agent":"Mozilla/5.0"}
g=lambda u:json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=30).read())
sb=g("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard")
out={}
for e in sb['events'][:3]:
    ev=e['id']
    for prov in (100,):
        try:
            d=g(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{ev}/competitions/{ev}/odds/{prov}/propBets?limit=1000")
        except Exception as x:
            out[f"{ev}-{prov}"]=str(x);continue
        types={}
        for it in d.get('items',[]):
            t=(it.get('type') or {}).get('name');types.setdefault(t,[]).append({k:it[k] for k in it if k not in('$ref',)})
        out[f"{e['name']}-{prov}"]={t:(len(v),v[:2]) for t,v in types.items()}
json.dump(out,open('out/td.json','w'),indent=1)
print({k:(list(v.keys()) if isinstance(v,dict) else v) for k,v in out.items()})
