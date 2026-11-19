"""Authored PL01 circuits 7002-7005 on the OSM road graph (road-graph.json).
Shortest paths between named anchors; edges with <1.2 m to an invisible collision wall
(from the shipped PL01.town) are effectively banned, and re-using an edge costs 20x so
loops do not double back. Building passages (Brama Krakowska) are inserted explicitly.
Writes route-<id>.json in the same shape as route-7001.json."""
from pathlib import Path
import json,math,heapq,collections,struct,zlib,argparse
import numpy as np
from shapely.geometry import LineString
from shapely import STRtree
ap=argparse.ArgumentParser();ap.add_argument('--events',type=int,nargs='*');args=ap.parse_args()
root=Path(__file__).resolve().parent;OX,OY,OZ=json.loads((root/'roi.json').read_text())['originEPSG2180']
raw=(root.parent/'build/custom-city/PL01.town').read_bytes();b=zlib.decompress(raw[12:]);nt,nm,no=struct.unpack_from('<III',b,0);o=12
for _ in range(nt):w,h=struct.unpack_from('<II',b,o);o+=8+w*h*3
segs=[]
for i in range(nm):
 cat,tex,nv,ni=struct.unpack_from('<IIII',b,o);o+=16;v=np.frombuffer(b,'<f4',nv*5,o).reshape(nv,5);o+=nv*20;idx=np.frombuffer(b,'<u2',ni,o);o+=ni*2+nv*4
 if cat!=(2|256|512):continue
 for t in idx.reshape(-1,3)[::2]:
  p=v[t,:2];i0,i1=np.unravel_index(np.argmax(((p[:,None]-p[None])**2).sum(-1)),(3,3))
  if np.hypot(*(p[i0]-p[i1]))>.2:segs.append(LineString([p[i0],p[i1]]))
tree=STRtree(segs)
def clearance(a,c):
 # middle 20-80 % of the edge: a wall corner touching a junction node is not an obstruction
 A=np.array([a[0]-OX,a[1]-OY]);C=np.array([c[0]-OX,c[1]-OY])
 if np.linalg.norm(C-A)<.5:return 9
 L=LineString([A+(C-A)*.2,A+(C-A)*.8]);near=tree.query(L.buffer(1.3))
 return min([segs[k].distance(L)for k in near],default=9)
data=json.loads((root/'road-graph.json').read_text());g=collections.defaultdict(list)
for a,c,d,n in data['edges']:g[tuple(a)].append((tuple(c),d,n));g[tuple(c)].append((tuple(a),d,n))   # race closes the streets: one-way restrictions do not apply
# Weld dead ends of a named street to the nearest node of the same street within 20 m
# (OSM splits e.g. Krakowskie Przedmiescie at Plac Litewski without a shared node).
welds=0
for a in [a for a,es in list(g.items())if len(es)==1]:
 name=g[a][0][2]
 if not name:continue
 best=None
 for c,es in g.items():
  if c==a or any(nb==a for nb,_,_ in es)or not any(n==name for _,_,n in es):continue
  d=math.dist(a,c)
  if d<20 and(best is None or d<best[0]):best=(d,c)
 if best:g[a].append((best[1],best[0],name));g[best[1]].append((a,best[0],name));welds+=1
print('welded dead ends',welds)
def near(p,name):
 cand=[a for a,es in g.items()if name is None or any(name in n for _,_,n in es)]
 return min(cand,key=lambda a:math.dist(a,(p[0]+OX,p[1]+OY)))
ROI=json.loads((root/'roi.json').read_text())['boundsEPSG2180']
# Junction corners the race AI cannot take (bots stop there; verified in bots-test runs).
AVOID=[]
def inside(p,margin=60):
 if any(math.dist((p[0]-OX,p[1]-OY),a)<12 for a in AVOID):return False
 return ROI[0]+margin<p[0]<ROI[2]-margin and ROI[1]+margin<p[1]<ROI[3]-margin
used=collections.Counter();clr={}
def path(s,e):
 q=[(0,s)];dist={s:0};par={}
 while q:
  c,a=heapq.heappop(q)
  if a==e:break
  if c!=dist[a]:continue
  for nb,d,n in g[a]:
   if not inside(nb):continue   # keep circuits 60 m clear of the map boundary walls
   k=(a,nb)
   if k not in clr:clr[k]=clearance(a,nb)
   cc=c+d*(20 if used[k]or used[(nb,a)]else 1)+(1e5 if clr[k]<1.2 else 0)
   if cc<dist.get(nb,1e18):dist[nb]=cc;par[nb]=(a,n);heapq.heappush(q,(cc,nb))
 if e not in dist:raise SystemExit(f'disconnected {s}->{e}')
 ch=[e];names=collections.Counter()
 while ch[-1]!=s:a,n=par[ch[-1]];names[n]+=math.dist(a,ch[-1]);ch.append(a)
 ch=ch[::-1]
 for a,c in zip(ch,ch[1:]):used[(a,c)]+=1
 return ch,names,dist[e]
BRAMA=[(2197,-61.5),(2201.3,-60.4),(2203.9,-59.1),(2210.4,-56.4),(2214.9,-54.4),(2219.5,-52.4)]   # Bramowa building passage axis
LOOPS={
 7001:('Lublin · pętla od Bramy Krakowskiej',[((2120,-62),'Krakowskie'),((850,150),'Racławick'),((304,-450),'Głęboka'),((1300,-500),'Narutowicza'),((2200,-105),'Królewska')]),
 7002:('Lublin · Stare Miasto przez bramy',[((2150,-63),'Krakowskie'),'BRAMA',((2310,0),'Rynek'),((2400,140),'Grodzka'),((2520,260),None),((2350,380),'Tysiąclecia'),((2215,150),'Lubartowska')]),
 7003:('Lublin · deptak Krakowskie Przedmieście',[((2150,-63),'Krakowskie'),((1830,-40),'Krakowskie'),((1300,-75),'Krakowskie'),((1300,-320),'Lipowa'),((1500,-360),'Okopowa'),((1750,-190),'Peowiaków'),((2270,-120),'Królewska')]),
 7004:('Lublin · Zamek i Podzamcze',[((2560,290),'Zamkowa'),((2650,400),'Tysiąclecia'),((2600,560),'Ruska'),((2400,520),'Lubartowska'),((2350,380),'Tysiąclecia')]),
 7005:('Lublin · Ogród Saski',[((700,120),'Racławickie'),((1200,60),'Wieniawska'),((1340,250),'Spokojna'),((1478,200),'Ogrodowa'),((1500,-62),'Krakowskie'),((1100,-60),'Racławickie')]),
}
for rid,(title,anchors) in LOOPS.items():
 if args.events and rid not in args.events:continue
 if not args.events and not (root/f'route-{rid}.json').exists():continue
 used.clear();pts=[];streets=collections.Counter();seq=[]
 for a in anchors:seq.append(a)
 seq.append(seq[0])
 cur=None
 for a in seq:
  if a=='BRAMA':
   brama=[(x+OX,y+OY)for x,y in BRAMA]
   if cur is not None:
    ch,nm_,c=path(cur,near(BRAMA[0],'Krakowskie')if True else None);pts+=ch[1:]if pts else ch;streets.update(nm_)
   pts+=brama;streets['Bramowa (Brama Krakowska)']+=25;cur=near(BRAMA[-1],'Bramowa');continue
  node=near(*a)
  if cur is None:pts=[node];cur=node;continue
  ch,nm_,c=path(cur,node)
  if c>=1e5:print(rid,'WARNING tight edge on leg to',a)
  pts+=ch[1:];streets.update(nm_);cur=node
# remove spurs: an anchor beside the road makes the path go to it and straight back
 def despike(q):
  changed=True
  while changed and len(q)>3:
   changed=False
   for i in range(1,len(q)-1):
    a_,b_,c_=np.array(q[i-1]),np.array(q[i]),np.array(q[i+1]);u=b_-a_;w=c_-b_
    if np.linalg.norm(u)<1e-6 or np.linalg.norm(w)<1e-6:del q[i];changed=True;break
    turn=math.degrees(math.acos(max(-1,min(1,(u@w)/np.linalg.norm(u)/np.linalg.norm(w)))))
    if turn>150 and np.linalg.norm(c_-a_)<12:del q[i];changed=True;break
  return q
 before=len(pts);ring=[tuple(p)for p in pts]
 if ring[0]==ring[-1]:ring=ring[:-1]
 for _ in range(len(ring)):   # cyclic despike: also catches a U-turn at the start/finish join
  n0=len(ring);ring=despike(ring+ring[:2])[:-2]if len(ring)>4 else ring;ring=ring[1:]+ring[:1]
  if len(ring)==n0 and _>len(ring):break
 # start/finish on the straightest 120 m of the loop (grid slots then stand on a straight)
 Lr=LineString(ring+[ring[0]]);samp=[np.array(Lr.interpolate(d).coords[0])for d in np.arange(0,Lr.length,5)]
 hd=np.unwrap([math.atan2(*(samp[(i+1)%len(samp)]-samp[i])[::-1])for i in range(len(samp))])
 best=min(range(len(samp)),key=lambda i:np.ptp([hd[(i+j)%len(samp)]+(2*math.pi*((i+j)//len(samp)))*0 for j in range(-12,13)]))
 sp=samp[best];k0=min(range(len(ring)),key=lambda i:math.dist(ring[i],sp));ring=ring[k0:]+ring[:k0];pts=ring+[ring[0]]
 print(rid,'despiked',before-len(pts),'points; start moved to',[round(sp[0]-OX),round(sp[1]-OY)])
# fillet sharp corners (>60 deg) with a <=10 m arc: the race AI stops at tight junction turns
 def fillet(q,R=10.0):
  out=[q[0]]
  for i in range(1,len(q)-1):
   a_,b_,c_=np.array(q[i-1]),np.array(q[i]),np.array(q[i+1]);u=a_-b_;w=c_-b_;lu,lw=np.linalg.norm(u),np.linalg.norm(w)
   if lu<1e-6 or lw<1e-6:continue
   ang=math.acos(max(-1,min(1,(u@w)/lu/lw)))   # interior angle
   if math.degrees(math.pi-ang)<=60:out.append(tuple(b_));continue
   t=min(R/math.tan(ang/2),lu*.45,lw*.45);p0=b_+u/lu*t;p1=b_+w/lw*t
   for f in np.linspace(0,1,7):out.append(tuple((1-f)**2*p0+2*(1-f)*f*b_+f*f*p1))   # quadratic arc through the corner
  out.append(q[-1]);return out
 pts=fillet(pts)
 # dense resample, cut dead-end excursions (path returns within 5 m after <=80 m), then
 # cyclic smoothing clipped to 3 m from the real road: turns the race AI can actually take
 Lr=LineString(pts);P=np.array([Lr.interpolate(d).coords[0]for d in np.arange(0,Lr.length,2.0)])
 changed=True
 while changed:
  changed=False
  for i in range(len(P)):
   j_hi=min(len(P),i+101)   # excursions up to 200 m
   if j_hi<=i+5:continue
   d=np.linalg.norm(P[i+5:j_hi]-P[i],axis=1)
   if len(d) and d.min()<5:
    j=i+5+int(np.argmin(d));P=np.concatenate([P[:i+1],P[j:]]);changed=True;break
 O=P.copy()
 for _ in range(12):
  Q=(np.roll(P,1,0)+2*P+np.roll(P,-1,0))/4;off=Q-O;nr=np.linalg.norm(off,axis=1,keepdims=True)
  P=O+off*np.minimum(1,3.0/np.maximum(nr,1e-9))
 pts=[tuple(p)for p in P]+[tuple(P[0])]
 line=LineString(pts);course=[list(line.interpolate(i).coords[0])for i in range(0,math.ceil(line.length),5)];course.append(list(pts[0]))
 tol=12
 # outline only drives HUD gates: topology-free simplify always shrinks (a self-touching
 # filleted loop never does with preserve_topology), bounded in case of degenerate input
 while len(line.simplify(tol,preserve_topology=False).coords)>33 and tol<400:tol+=2
 outline=list(line.simplify(tol,preserve_topology=False).coords)
 res={'id':rid,'name':title,'lengthM':line.length,'source':'OpenStreetMap road graph; clearance-aware authored loop','origin':[OX,OY,OZ],'streets':{k:round(v)for k,v in streets.most_common()},'outline':outline,'course':course,'rawPoints':[list(p)for p in pts],'simplifyToleranceM':tol}
 (root/f'route-{rid}.json').write_text(json.dumps(res,ensure_ascii=False,separators=(',',':')))
 print(rid,title,round(line.length),'m; outline',len(outline),'; streets',list(res['streets'])[:8])
