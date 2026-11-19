"""Profile authored race lines cyclically, retaining the source for repeatable rebuilds."""
from pathlib import Path
import json,math,argparse
import numpy as np
from shapely.geometry import LineString
ap=argparse.ArgumentParser();ap.add_argument('--events',type=int,nargs='*');args=ap.parse_args()
root=Path(__file__).resolve().parent
from shapely import STRtree,points as make_points
import struct,zlib
body=zlib.decompress((root.parent/'build/custom-city/PL01.town').read_bytes()[12:]);nt,nm,_=struct.unpack_from('<III',body);o=12
for _ in range(nt):w,h=struct.unpack_from('<II',body,o);o+=8+w*h*3
walls=[]
for _ in range(nm):
 cat,tex,nv,ni=struct.unpack_from('<IIII',body,o);o+=16
 vv=np.frombuffer(body,'<f4',nv*5,o).reshape(nv,5);o+=nv*20
 ii=np.frombuffer(body,'<u2',ni,o);o+=ni*2+nv*4
 if cat!=770:continue
 for tri in ii.reshape(-1,3)[::2]:
  xy=vv[tri,:2];a,b=np.unravel_index(np.argmax(((xy[:,None]-xy[None])**2).sum(-1)),(3,3))
  if np.linalg.norm(xy[a]-xy[b])>.2:walls.append(LineString([xy[a],xy[b]]))
tree=STRtree(walls)
def clearance(p):return tree.query_nearest(make_points(p-[746600,381750]),return_distance=True,all_matches=False)[1]

for path in sorted(root.glob('route-7*.json')):
 r=json.loads(path.read_text());
 if args.events and r['id']not in args.events:continue
 r.pop('physicalFit',None);r.pop('unfittedCourse',None)
 source=r.setdefault('unprofiledCourse',r['course'])
 line=LineString(source);n=math.ceil(line.length/2)
 original=np.array([line.interpolate(i*line.length/n).coords[0]for i in range(n)])
 p=original.copy();minimum=np.minimum(2.0,np.maximum(0,clearance(original)-.01))
 for _ in range(240):
  q=(np.roll(p,1,0)+2*p+np.roll(p,-1,0))/4
  ok=clearance(q)>=minimum;p[ok]=q[ok]
 line=LineString([*p,p[0]])
 r['course']=[list(line.interpolate(d).coords[0])for d in np.arange(0,line.length,3)]+[list(p[0])]
 # Authored broad arcs give the native pursuit controller room to turn; body-fit verifies them.
 profiles=root/'race-corner-profiles.json'
 if profiles.exists():
  points=np.array(r['course'])[:-1]-[746600,381750]
  for corner in json.loads(profiles.read_text())['corners']:
   if r['id']not in corner['events']:continue
   angles=np.radians(np.linspace(*corner['anglesDegrees'],max(8,math.ceil(abs(corner['anglesDegrees'][1]-corner['anglesDegrees'][0])*math.pi/180*corner['radiusM']))))
   arc=np.array(corner['centre'])+corner['radiusM']*np.column_stack((np.cos(angles),np.sin(angles)))
   a=int(np.linalg.norm(points-arc[0],axis=1).argmin());b=int(np.linalg.norm(points-arc[-1],axis=1).argmin())
   if max(np.linalg.norm(points[a]-arc[0]),np.linalg.norm(points[b]-arc[-1]))>12:raise ValueError(f"{r['id']}: authored corner no longer matches this course")
   if a>b:a,b=b,a;arc=arc[::-1]
   points=np.concatenate((points[:a],arc,points[b+1:]))
  line=LineString([*(points+[746600,381750]),points[0]+[746600,381750]])
  r['course']=[list(line.interpolate(d).coords[0])for d in np.arange(0,line.length,3)]+[list(line.coords[0])]
 tol=12
 while len(line.simplify(tol,preserve_topology=False).coords)>33:tol+=2
 r.update(outline=list(line.simplify(tol,preserve_topology=False).coords),lengthM=line.length,simplifyToleranceM=tol,profiling={'method':'cyclic diffusion, 2m samples, 240 iterations, physical wall clearance constrained','maxShiftM':float(np.linalg.norm(p-original,axis=1).max())})
 def turns(points):
  v=np.diff(np.array(points),axis=0);v=v/np.maximum(np.linalg.norm(v,axis=1,keepdims=True),1e-9)
  return float(np.degrees(np.arccos(np.clip((v*np.roll(v,1,0)).sum(1),-1,1))).max())
 print(r['id'],'max local heading change',round(turns(source),1),'->',round(turns(r['course']),1),'degrees; length',round(line.length))
 path.write_text(json.dumps(r,ensure_ascii=False,separators=(',',':')))
