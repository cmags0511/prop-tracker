import json,urllib.request,urllib.parse,datetime as dt
H={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
def g(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=30).read())
out={}
L=["eng.1","esp.1","ita.1","ger.1","fra.1","usa.1","uefa.champions","uefa.europa","mex.1","ned.1","por.1","eng.2","bra.1","arg.1","sco.1","tur.1","bel.1","fifa.worldq.uefa","uefa.nations","fifa.friendly"]
today=dt.date.today()
rng=f"{today:%Y%m%d}-{today+dt.timedelta(days=10):%Y%m%d}"
for lg in L:
    try:
        sb=g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={rng}")
        evs=sb.get('events',[])
        info={"n":len(evs),"first":[e['name']+" "+e['date'] for e in evs[:2]]}
        for e in evs[:3]:
            try:
                d=g(f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{lg}/events/{e['id']}/competitions/{e['id']}/odds/100/propBets?limit=1000")
                ty={}
                for it in d.get('items',[]):
                    t=(it.get('type') or {}).get('name');ty.setdefault(t,[]).append(it.get('current'))
                info.setdefault("props",{})[e['name']]={t:(len(v),v[:2]) for t,v in ty.items()}
            except Exception as x: info.setdefault("props",{})[e['name']]=str(x)[:80]
            try:
                o=g(f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{lg}/events/{e['id']}/competitions/{e['id']}/odds")
                info.setdefault("odds",[]).append([ (i.get('provider') or {}).get('name') for i in o.get('items',[])])
            except Exception as x: pass
        out[lg]=info
    except Exception as x:
        out[lg]=str(x)[:100]
# finished match player stats sample (EPL)
try:
    sb=g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={today-dt.timedelta(days=30):%Y%m%d}-{today:%Y%m%d}")
    ev=[e for e in sb['events'] if e['status']['type']['state']=='post'][0]
    s=g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary?event={ev['id']}")
    r=s.get('rosters',[])
    out['sample_roster']={"keys":list(s.keys()),"roster0":json.dumps(r[0]['roster'][0])[:1500] if r else None}
    # athlete gamelog
    aid=r[0]['roster'][0]['athlete']['id']
    try:
        gl=g(f"https://site.web.api.espn.com/apis/common/v3/sports/soccer/eng.1/athletes/{aid}/gamelog")
        out['gamelog']=json.dumps(gl)[:1500]
    except Exception as x: out['gamelog']=str(x)[:100]
except Exception as x: out['sample_roster']=str(x)[:200]
# kalshi soccer series
try:
    ser=g("https://api.elections.kalshi.com/trade-api/v2/series?category=Sports")
    names=[ (s['ticker'],s['title']) for s in ser.get('series',[]) if any(w in (s['title']+s['ticker']).lower() for w in ['soccer','epl','premier','la liga','serie a','bundesliga','ligue','mls','champions','goal','uefa'])]
    out['kalshi_series']=names[:200]
except Exception as x: out['kalshi_series']=str(x)[:200]
json.dump(out,open('out/soc.json','w'),indent=1)
print(json.dumps({k:(v if isinstance(v,str) else {kk:(vv if kk!='props' else {e:(list(p.keys()) if isinstance(p,dict) else p) for e,p in vv.items()}) for kk,vv in v.items()} if isinstance(v,dict) else v) for k,v in out.items() if k not in('sample_roster','gamelog','kalshi_series')},indent=0)[:6000])
print('KALSHI',out.get('kalshi_series'))
