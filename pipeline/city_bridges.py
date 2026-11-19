"""Observed upper-road profiles; topology keeps crossing lower roads on their own level."""
from pathlib import Path
import json,hashlib
import numpy as np
from shapely.geometry import LineString,Polygon
from shapely.ops import unary_union
from city_road_clearance import road_width,DRIVABLE
from fetch_bridge_surfaces import read_grid

APPROACH_M=220.   # connected approach road followed on each side
MAX_GRADE=.065    # ramp grade limit (urban viaducts: about 5-7 %)
def profiles(root,ground):
 origin=np.array(json.loads((root/'roi.json').read_text())['originEPSG2180']);roads=json.loads((root/'terrain-build/roads-with-ground-heights.json').read_text())['roads'];ordinary=[]
 for road in roads:
  if road['properties'].get('bridge')in ['yes','viaduct'] or road['properties'].get('highway')not in DRIVABLE:continue
  for part in road['parts']:
   if len(part)>1:ordinary.append(np.array(part)[:,:2]-origin[:2])
 def approach(endpoint,previous):
  points=[endpoint];used=set();remaining=APPROACH_M
  for _ in range(40):
   direction=points[-1]-previous;direction/=np.linalg.norm(direction);choices=[]
   for i,p in enumerate(ordinary):
    if i in used:continue
    for q in (p,p[::-1]):
     if np.linalg.norm(q[0]-points[-1])>.3:continue
     step=q[1]-q[0];length=np.linalg.norm(step)
     if length and direction@step/length>.45:choices.append((direction@step/length,i,q))
   if not choices:break
   _,i,q=max(choices,key=lambda x:x[0]);used.add(i);line=LineString(q);length=min(remaining,line.length)
   q=np.array([line.interpolate(s).coords[0]for s in np.arange(2,length,2)]+[line.interpolate(length).coords[0]]);previous=points[-1];points.extend(q);remaining-=length
   if remaining<=.01:break
   previous=points[-2]
  return np.array(points)
 records=[]
 for road in roads:
  if road['properties'].get('bridge')not in ['yes','viaduct']:continue
  for part,p in enumerate(road['parts']):
   missing=not(root/f'bridge-audit/extended-patches/way-{road["id"]}-{part}.asc').exists()
   p=np.array(p)[:,:2]-origin[:2];before=approach(p[0],p[1]);after=approach(p[-1],p[-2]);
   if missing:before=p[:1];after=p[-1:]
   path=np.concatenate((before[:0:-1],p,after[1:]));axis=LineString(path);s=np.linspace(0,axis.length,int(np.ceil(axis.length/2))+1);xy=np.array([axis.interpolate(t).coords[0]for t in s]);tan=np.array([np.array(axis.interpolate(min(axis.length,t+1)).coords[0])-axis.interpolate(max(0,t-1)).coords[0]for t in s]);normal=np.column_stack((-tan[:,1],tan[:,0]));normal/=np.linalg.norm(normal,axis=1)[:,None];width=road_width(road['properties']);sample=xy[:,None,:]+origin[:2]+normal[:,None,:]*np.linspace(-min(width/4,2),min(width/4,2),7)[None,:,None];asc=root/f'bridge-audit/extended-patches/way-{road["id"]}-{part}.asc';
   if missing:asc=root/f'bridge-audit/patches/way-{road["id"]}-{part}.asc'
   head,data=read_grid(asc);ix=np.floor((sample[:,:,0]-head['xllcorner'])/head['cellsize']).astype(int);iy=int(head['nrows'])-1-np.floor((sample[:,:,1]-head['yllcorner'])/head['cellsize']).astype(int)
   # Longer approaches may leave the captured NMPT patch: there the terrain is the observation.
   inside=(ix>=0)&(iy>=0)&(ix<data.shape[1])&(iy<data.shape[0]);g0=ground(xy[:,0],xy[:,1])
   samples=np.where(inside,data[np.clip(iy,0,data.shape[0]-1),np.clip(ix,0,data.shape[1]-1)]-origin[2],g0[:,None]);raw=np.quantile(samples,.2,axis=1);z=np.array([np.median(raw[max(0,i-2):min(len(raw),i+3)])for i in range(len(raw))]);# NMPT sees bridge-gate roofs and tree crowns; remove positive features shorter than 30 m.
   width_samples=min(15,(len(z)//2)*2-1);width_samples=max(1,width_samples);pad=width_samples//2
   z=np.min(np.lib.stride_tricks.sliding_window_view(np.pad(z,pad,mode='edge'),width_samples),axis=1)
   z=np.max(np.lib.stride_tricks.sliding_window_view(np.pad(z,pad,mode='edge'),width_samples),axis=1)
   g=ground(xy[:,0],xy[:,1]);start=LineString(before).length if len(before)>1 else 0;end=axis.length-(LineString(after).length if len(after)>1 else 0)
   # Preserve surveyed decks. Only far ends of actual connected approach roads blend to old terrain.
   weight=np.ones(len(s))
   if start:weight*=np.minimum(1,s/min(25,start))
   if end<axis.length:weight*=np.minimum(1,(axis.length-s)/min(25,axis.length-end))
   z=g+(z-g)*weight
   for _ in range(8):z[1:-1]=.25*z[:-2]+.5*z[1:-1]+.25*z[2:]
   # Real viaduct ramps stay below MAX_GRADE: keep the observed deck crest and lengthen the
   # ramps outward along the connected approach roads instead of a short 20%+ jump.
   deck=(s>=start)&(s<=end)
   if deck.any() and not deck.all():
    # Approaches: the terrain, raised only where a ramp from the observed deck (<= MAX_GRADE)
    # stands above it. Terrain hills are never treated as deck, NMPT trees/roofs never as road.
    ramp=np.max(z[deck][None,:]-MAX_GRADE*np.abs(s[:,None]-s[deck][None,:]),axis=1)
    z=np.where(deck,z,np.maximum(g,ramp))
   suspicious=bool(np.max(np.abs(np.diff(z)/np.diff(s)))>.30)
   if suspicious or missing:

    # Thin, obscured pedestrian crossings are not enough evidence for an inferred elevated roadway.
    z=g.copy();mask=(s>=start)&(s<=end);z[mask]=np.interp(s[mask],[start,end],[np.interp(start,s,g),np.interp(end,s,g)]);status='legacy approach interpolation retained; NMPT obscured, implausible or extended capture unavailable'
   else:status='NMPT deck and connected approaches'
   records.append({'way':road['id'],'part':part,'name':road['properties'].get('name'),'status':status,'widthM':width,'xy':xy.tolist(),'z':z.tolist(),'stationM':s.tolist(),'deckStationM':[start,end],'sourceSHA256':hashlib.sha256(asc.read_bytes()).hexdigest(),'heightDatum':'PL-KRON86-NH','acquisitionDate':None,'maxGrade':float(np.max(np.abs(np.diff(z)/np.diff(s)))),'maxLiftM':float(np.max(z-g)),'endLiftM':[float(z[0]-g[0]),float(z[-1]-g[-1])]})
 for r in records:r.update({'originEPSG2180': [746600, 381750, 180], 'coordinates': 'local metres relative to origin; z is source-datum elevation minus originZ', 'profileMethod': '20th percentile of seven cross-section samples; 30m positive-feature opening; 8 binomial smoothing steps', 'widthSource': 'OSM width or lanes, otherwise road-class fallback; not surveyed structure width', 'approachBlend': f'up to {APPROACH_M:.0f}m of connected source roads; far 25m blend to original NMT terrain; ramps limited to {MAX_GRADE:.1%}'})
 return records

def footprint(records):return unary_union([LineString(r['xy']).buffer(r['widthM']/2,cap_style='flat')for r in records])
def chunks(records,offset=.04):
 for r in records:
  xy=np.array(r['xy']);delta=np.roll(xy,-1,axis=0)-np.roll(xy,1,axis=0);delta[0]=xy[1]-xy[0];delta[-1]=xy[-1]-xy[-2];normal=np.column_stack((-delta[:,1],delta[:,0]));normal/=np.linalg.norm(normal,axis=1)[:,None];v=np.zeros((len(xy)*2,5),dtype='<f4');v[::2,:2]=xy-normal*r['widthM']/2;v[1::2,:2]=xy+normal*r['widthM']/2;v[:,2]=np.repeat(r['z'],2)+offset;v[:,3:]=v[:,:2]/8;idx=np.array([[2*i,2*i+2,2*i+1,2*i+1,2*i+2,2*i+3]for i in range(len(xy)-1)],dtype='<u2').reshape(-1);yield v,idx

def surface_sampler(ground,records):
 import shapely
 prepared=[(LineString(r['xy']),LineString(r['xy']).buffer(r['widthM']/2,cap_style='flat'),np.array(r['stationM']),np.array(r['z']))for r in records]
 def sample(x,y):
  x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float));flatx=x.reshape(-1);flaty=y.reshape(-1);result=np.asarray(ground(flatx,flaty)).copy();assigned=np.zeros(len(flatx),bool)
  for line,polygon,stations,z in prepared:
   mask=shapely.covers(polygon,shapely.points(flatx,flaty))
   if not mask.any():continue
   along=shapely.line_locate_point(line,shapely.points(flatx[mask],flaty[mask]));heights=np.interp(along,stations,z);result[mask]=np.where(assigned[mask],np.maximum(result[mask],heights),heights);assigned[mask]=True
  return result.reshape(x.shape)
 return sample

def structure(records,ground,avoid,min_lift=1.5,collision=None,rail_lift=3.0):
 """Visible viaduct body under/around each elevated deck (visual only; the deck ribbon from
 chunks() stays the drivable surface): 1.2 m deck slab underside, side fascias, 1 m parapets
 and piers every ~25 m where the deck is >4 m up. Piers never stand on `avoid` (lower roads)."""
 import shapely
 from shapely.geometry import box
 from shapely import affinity
 shapely.prepare(avoid)
 for r in records:
  xy=np.array(r['xy']);z=np.array(r['z']);st=np.array(r['stationM'])
  if len(xy)<2:continue
  g=ground(xy[:,0],xy[:,1]);lift=z-g;up=lift>min_lift
  if not up.any():continue
  d=np.gradient(xy,axis=0);d/=np.linalg.norm(d,axis=1)[:,None]+1e-9;nrm=np.column_stack((-d[:,1],d[:,0]));half=r['widthM']/2
  L=xy-nrm*half;R=xy+nrm*half;V=[];I=[]
  def quad(a,b,c,e,u0,u1,v0,v1,inside):
   # One winding only: the engine never culls and accumulates face normals per vertex, so a
   # double-sided quad would cancel its own normal (black stripes). Face away from `inside`.
   a,b,c,e=(np.asarray(q,float)for q in(a,b,c,e));n=np.cross(b-a,c-a)
   base=len(V);V.extend([[*a,u0,v0],[*b,u1,v0],[*c,u1,v1],[*e,u0,v1]])
   I.extend([base,base+1,base+2,base,base+2,base+3]if n@((a+c)/2-np.asarray(inside,float))>=0 else[base,base+2,base+1,base,base+3,base+2])
  for i in range(len(xy)-1):
   if not(up[i]or up[i+1]):continue
   u0,u1=st[i]/4,st[i+1]/4;zt0,zt1=z[i],z[i+1];zb0,zb1=zt0-1.2,zt1-1.2
   mid=(*((xy[i]+xy[i+1])/2),(zt0+zt1)/2-.6)
   for E in(L,R):
    quad((*E[i],zb0),(*E[i+1],zb1),(*E[i+1],zt1+1.0),(*E[i],zt0+1.0),u0,u1,0,.55,mid)   # fascia + parapet, outer face
    inner=E+(xy-E)*.04   # parapet inner face (towards the carriageway)
    quad((*inner[i],zt0),(*inner[i+1],zt1),(*inner[i+1],zt1+1.0),(*inner[i],zt0+1.0),u0,u1,0,.25,(*E[i],zt0+.5))
   quad((*L[i],zb0),(*L[i+1],zb1),(*R[i+1],zb1),(*R[i],zb0),u0,u1,0,half/2,(mid[0],mid[1],zt0+5))   # underside faces down
  CV=[];CI=[]
  def wall(a,b,z0a,z0b,z1a,z1b):   # invisible collision face (engine walls are >= 2.5 m tall)
   k=len(CV);CV.extend([[*a,z0a,0,0],[*b,z0b,0,0],[*b,z1b,0,0],[*a,z1a,0,0]]);CI.extend([k,k+1,k+2,k,k+2,k+3,k,k+2,k+1,k,k+3,k+2])   # both sides, like the race barriers (never drawn)
  def column(cx,cy,w,top,ref):   # square column from below the terrain up to `top`
   sq=np.array([[-w,-w],[w,-w],[w,w],[-w,w]])/2+[cx,cy];gb=float(np.min(ground(sq[:,0],sq[:,1])))-.5
   for j in range(4):
    a,b=sq[j],sq[(j+1)%4];quad((*a,gb),(*b,gb),(*b,top),(*a,top),0,w/4,0,(top-gb)/4,(cx,cy,(gb+top)/2))
    wall(a,b,gb,gb,max(top,gb+3),max(top,gb+3))
  if collision is not None:   # parapets hold the car on the deck wherever it is clearly elevated
   for i in range(len(xy)-1):
    if lift[i]<rail_lift or lift[i+1]<rail_lift:continue
    for E in(L,R):wall(E[i],E[i+1],z[i]-.5,z[i+1]-.5,z[i]+3,z[i+1]+3)
  # Piers: a pair of columns under the deck edges with a cap beam, every ~25 m where the deck is
  # >4 m up. Each column must stand off every lower carriageway (avoid); if the nominal station is
  # on a road, the pier slides along the deck (up to 12 m) to the nearest clear spot.
  last=-1e9
  for t in np.arange(12.5,st[-1],25.):
   for off in (0,2,-2,4,-4,6,-6,8,-8,10,-10,12,-12):
    if t+off<=last+12:continue
    k=min(int(np.searchsorted(st,t+off)),len(st)-1)
    if lift[k]<4:continue
    cols=[]
    for side in(-1,1):
     cx,cy=xy[k]+nrm[k]*side*max(.6,half-.9)
     if not avoid.intersects(box(cx-.6,cy-.6,cx+.6,cy+.6)):cols.append((cx,cy))
    if not cols:continue
    top=z[k]-1.2
    for cx,cy in cols:column(cx,cy,1.1,top,None)
    a_,b_=xy[k]-nrm[k]*(half-.3),xy[k]+nrm[k]*(half-.3);dd=d[k]*.55   # cap beam across the deck
    cap=[a_-dd,b_-dd,b_+dd,a_+dd];mid=(*xy[k],top-.5)
    for j in range(4):
     a,b=cap[j],cap[(j+1)%4];quad((*a,top-1.0),(*b,top-1.0),(*b,top),(*a,top),0,np.linalg.norm(b-a)/4,0,.25,mid)
    quad((*cap[0],top-1.0),(*cap[3],top-1.0),(*cap[2],top-1.0),(*cap[1],top-1.0),0,.3,0,half/2,(*xy[k],top+3))
    last=t+off;break
  if collision is not None and CV:
   CV_=np.asarray(CV,'<f4');CI_=np.asarray(CI,np.int64)
   for s0 in range(0,len(CI_),60000):   # 60000 = whole 12-index walls
    part=CI_[s0:s0+60000];used,inv=np.unique(part,return_inverse=True);collision.append((CV_[used],inv.astype('<u2')))
  if V:
   V=np.asarray(V,dtype='<f4');I=np.asarray(I,dtype=np.int64)
   for start in range(0,len(I),60000):   # 16-bit indices: split on whole quads (6 indices each)
    part=I[start:start+60000];used,inv=np.unique(part,return_inverse=True);yield V[used],inv.astype('<u2')

FOOTBRIDGE_CLEARANCE_M=5.5   # walkway above the carriageway it spans
FOOTBRIDGE_RAMP=.12          # end ramps/stairs down to the terrain
def footbridges(root,ground,carriageway,min_length=15.):
 """Pedestrian bridges (OSM footway/path/cycleway/steps, bridge=*, layer>=1) that span a
 carriageway. The roads file holds only drivable roads, so these come from the OSM tiles.
 Height is inferred (no NMPT capture): clearance above the spanned carriageway, ramps at the
 ends. Visual only; returns records shaped like profiles() for chunks()/structure()."""
 import xml.etree.ElementTree as ET,shapely
 from pyproj import Transformer
 origin=np.array(json.loads((root/'roi.json').read_text())['originEPSG2180'][:2]);tr=Transformer.from_crs(4326,2180,always_xy=True)
 nodes={};ways={}
 for path in sorted((root/'osm-tiles').glob('*.osm')):
  t=ET.parse(path).getroot()
  for n in t.findall('node'):nodes[n.get('id')]=(float(n.get('lon')),float(n.get('lat')))
  for w in t.findall('way'):
   tags={x.get('k'):x.get('v')for x in w.findall('tag')}
   try:layer=int(tags.get('layer','0'))
   except ValueError:layer=0
   if tags.get('bridge')in(None,'no')or tags.get('highway')not in('footway','path','cycleway','steps')or layer<1:continue   # pedestrian streets are drivable bridges (profiles)
   ways[w.get('id')]=(tags,[x.get('ref')for x in w.findall('nd')])
 shapely.prepare(carriageway);records=[]
 for wid,(tags,refs) in sorted(ways.items()):
  if len(refs)<2 or not all(r in nodes for r in refs):continue
  line=LineString([np.array(tr.transform(*nodes[r]))-origin for r in refs])
  if line.length<min_length or not carriageway.intersects(line):continue
  s=np.linspace(0,line.length,max(2,int(np.ceil(line.length/1.0))+1));xy=np.array([line.interpolate(t).coords[0]for t in s])
  g=np.asarray(ground(xy[:,0],xy[:,1]),float);over=shapely.contains_xy(carriageway,xy[:,0],xy[:,1])
  if not over.any():continue
  crest=float(g[over].max())+FOOTBRIDGE_CLEARANCE_M;lo,hi=s[over].min()-2,s[over].max()+2
  dist=np.maximum(0,np.maximum(lo-s,s-hi));z=np.maximum(g,crest-FOOTBRIDGE_RAMP*dist)
  width=float(tags.get('width','3').split()[0])if str(tags.get('width','3')).split()[0].replace('.','',1).isdigit()else 3.
  records.append({'way':wid,'part':0,'name':tags.get('name'),'status':'OSM footbridge, inferred height','widthM':max(2.,min(6.,width)),'xy':xy.tolist(),'z':z.tolist(),'stationM':s.tolist()})
 return records
