from pathlib import Path
import json,math,heapq,collections
r=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'');roads=json.loads((r/'roads-clipped.geojson').read_text());g=collections.defaultdict(list);names=collections.defaultdict(set)
def key(p):return tuple(round(v,3)for v in p)
for f in roads['features']:
 t=f['properties'];ps=[f['geometry']['coordinates']]if f['geometry']['type']=='LineString'else f['geometry']['coordinates'];name=t.get('name','')
 for line in ps:
  for a,b in zip(line,line[1:]):
   a,b=key(a),key(b);length=math.dist(a,b)
   if length<.01:continue
   oneway=t.get('oneway')
   if oneway!='-1':g[a].append((b,length,name))
   if oneway not in['yes','1','true']:g[b].append((a,length,name))
   names[a].add(name);names[b].add(name)
labels=['Kraśnick','Racławick','Solidarno','Głęboka','Sikorsk','Poniatowsk','Sowińsk']
for a,ns in names.items():
 hits=[p for p in labels if any(p.lower()in n.lower()for n in ns)]
 if len(hits)>1:print(a,','.join(hits))
(r/'road-graph.json').write_text(json.dumps({'edges':[[list(a),list(b),d,n]for a,es in g.items()for b,d,n in es]},ensure_ascii=False,separators=(',',':')))
