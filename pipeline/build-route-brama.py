from pathlib import Path
import json,math,heapq,collections
from shapely.geometry import LineString
r=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'');data=json.loads((r/'road-graph.json').read_text());g=collections.defaultdict(list)
for a,b,d,n in data['edges']:g[tuple(a)].append((tuple(b),d,n))
def near(p,name):return min((a for a,es in g.items()if any(name.lower()in n.lower()for _,_,n in es)),key=lambda a:math.dist(a,p))
anchors=[near((748720,381688),'Krakowskie'),near((747450,381900),'Racławick'),near((746904,381300),'Głęboka'),near((747900,381250),'Narutowicza')];anchors.append(anchors[0])  # loop from Brama Krakowska
points=[];streets=collections.Counter()
for start,end in zip(anchors,anchors[1:]):
 q=[(0,start)];dist={start:0};parent={}
 while q:
  cost,a=heapq.heappop(q)
  if cost!=dist[a]:continue
  if a==end:break
  for b,d,n in g[a]:
   value=cost+d
   if value<dist.get(b,math.inf):dist[b]=value;parent[b]=(a,n,d);heapq.heappush(q,(value,b))
 assert end in dist,('Disconnected road graph',start,end)
 chain=[];p=end
 while p!=start:
  chain.append(p);a,n,d=parent[p];streets[n]+=d;p=a
 chain.append(start);chain.reverse();points.extend(chain if not points else chain[1:])
assert points[0]==points[-1];line=LineString(points);tol=12
while len(line.simplify(tol).coords)>33:tol+=2
outline=list(line.simplify(tol).coords)
# Exact5m course samples retain intermediate street geometry, distinct from coarse HUD outline.
course=[list(line.interpolate(i).coords[0])for i in range(0,math.ceil(line.length),5)];course.append(list(points[0]))
result={'id':7001,'name':'Lublin · pętla od Bramy Krakowskiej','lengthM':line.length,'source':'OpenStreetMap directed motor-road graph; authored checkpoint outline','origin':[746600,381750,180],'anchors':anchors,'streets':streets,'outline':outline,'course':course,'rawPoints':points,'simplifyToleranceM':tol}
(r/'route-7001.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')));print(json.dumps({k:v for k,v in result.items()if k not in['course','rawPoints','outline']},ensure_ascii=False,indent=2));print('outline',len(outline),'course',len(course))
