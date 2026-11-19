"""Fit current authored race lines with the production native body/wall solver.
Run after profile-routes.py, before rebuilding events and city street cuts.
The probe is a locally compiled race-course-probe.c using native/src/world.c + physics.c.
"""
from pathlib import Path
import argparse,json,math,subprocess,tempfile,heapq,hashlib
import shapely
from city_road_clearance import areas,road_width
import numpy as np
from shapely.geometry import LineString
ap=argparse.ArgumentParser();ap.add_argument('--probe',type=Path,required=True);ap.add_argument('--town',type=Path);ap.add_argument('--events',type=int,nargs='*');args=ap.parse_args()
root=Path(__file__).resolve().parent;town=args.town or root.parent/'build/custom-city/PL01.town';origin=np.array(json.loads((root/'roi.json').read_text())['originEPSG2180'][:2])
_,_,buildings=areas(root,road_width,with_buildings=True)
obstacle=buildings.buffer(.95)
def detour(segment):
 line=LineString(segment);allowed=line.buffer(20).difference(obstacle)
 xmin,ymin,xmax,ymax=allowed.bounds;step=.5
 nx=int(math.ceil((xmax-xmin)/step))+1;ny=int(math.ceil((ymax-ymin)/step))+1
 yy,xx=np.mgrid[:ny,:nx];coordinates=np.column_stack((xmin+xx.ravel()*step,ymin+yy.ravel()*step))
 valid=shapely.contains_xy(allowed,coordinates[:,0],coordinates[:,1]).reshape(ny,nx)
 def node(p):
  ix=int(round((p[0]-xmin)/step));iy=int(round((p[1]-ymin)/step))
  candidates=[(math.hypot(xmin+x*step-p[0],ymin+y*step-p[1]),(y,x))for y in range(max(0,iy-3),min(ny,iy+4))for x in range(max(0,ix-3),min(nx,ix+4))if valid[y,x]]
  if not candidates:raise RuntimeError('No free car-width anchor for local detour')
  return min(candidates)[1]
 start,end=node(segment[0]),node(segment[-1]);q=[(0.,start)];distance={start:0.};previous={}
 local=obstacle.intersection(shapely.box(xmin,ymin,xmax,ymax));clearance=shapely.distance(shapely.points(coordinates),local).reshape(ny,nx)
 while q:
  _,at=heapq.heappop(q)
  if at==end:break
  y,x=at
  for dy,dx in [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]:
   yy,xx=y+dy,x+dx
   if not(0<=yy<ny and 0<=xx<nx and valid[yy,xx]):continue
   if dy and dx and not(valid[y,xx]and valid[yy,x]):continue
   cost=distance[at]+math.hypot(dx,dy)*step*(1+.6/(.3+clearance[yy,xx]));nxt=(yy,xx)
   if cost<distance.get(nxt,1e30):distance[nxt]=cost;previous[nxt]=at;heapq.heappush(q,(cost+math.hypot(yy-end[0],xx-end[1])*step,nxt))
 if end not in distance:raise RuntimeError('No connected car-width detour around the building')
 chain=[end]
 while chain[-1]!=start:chain.append(previous[chain[-1]])
 points=np.array([segment[0],*[(xmin+x*step,ymin+y*step)for y,x in chain[::-1]],segment[-1]])
 for _ in range(60):
  candidates=(points[:-2]+2*points[1:-1]+points[2:])/4;ok=shapely.contains_xy(allowed,candidates[:,0],candidates[:,1]);points[1:-1][ok]=candidates[ok]
 return points
for path in sorted(root.glob('route-7*.json')):
 r=json.loads(path.read_text());
 if args.events and r['id']not in args.events:continue
 p=np.array(r.setdefault('unfittedCourse',r['course']))[:-1]-origin;worst=0
 with tempfile.TemporaryDirectory(prefix='race-body-fit-')as td:
  td=Path(td)
  for iteration in range(24):
   t=np.roll(p,-1,axis=0)-np.roll(p,1,axis=0);heading=np.arctan2(t[:,1],t[:,0]);probes=td/'input.txt';output=td/'output.txt'
   probes.write_text(''.join(f"{r['id']} {x} {y} 0 {h}\n"for (x,y),h in zip(p,heading)))
   result=subprocess.run([str(args.probe),str(town),str(probes),str(r['id']),str(output)],capture_output=True,text=True,check=True)
   projected=np.loadtxt(output);push=projected[:,2];worst=max(worst,float(push.max()))
   print(r['id'],'iteration',iteration,'maximum native body correction',round(float(push.max()),3),'m',flush=True)
   if push.max()<.08:break
   if push.max()>.3:
    i=int(push.argmax());a=max(0,i-12);b=min(len(p)-1,i+12)
    replacement=detour(p[a:b+1]);line=LineString([*p[:a],*replacement,*p[b+1:],p[0]])
    p=np.array([line.interpolate(d).coords[0]for d in np.arange(0,line.length,3)])
    continue
   d=projected[:,:2]-p;weights=(push>.04).astype(float);smooth=np.zeros_like(d);total=np.zeros(len(p))
   for k in range(-7,8):
    w=math.exp(-.5*(k/3)**2);smooth+=np.roll(d,k,axis=0)*w;total+=np.roll(weights,k)*w
   p+=smooth/np.maximum(1,total)[:,None]*1.1

  else:raise RuntimeError(f"{r['id']}: physical course fit did not converge")
 line=LineString([*p,p[0]]);course=[list(np.array(line.interpolate(d).coords[0])+origin)for d in np.arange(0,line.length,3)]+[list(p[0]+origin)]
 tol=12
 while len(line.simplify(tol,preserve_topology=False).coords)>33:tol+=2
 r.update(course=course,outline=[list(np.array(q)+origin)for q in line.simplify(tol,preserve_topology=False).coords],lengthM=line.length,simplifyToleranceM=tol,physicalFit={'solver':'native/src physics.c collide_body_walls_preview','bodyEnvelopeM':[5.6,3.1,1.5],'iterations':iteration+1,'maximumInitialCorrectionM':worst,'localDetourLimitM':20})
 r['physicalFit']['courseSHA256']=hashlib.sha256(json.dumps(r['course'],separators=(',',':')).encode()).hexdigest()
 r['physicalFit']['collisionTownSHA256']=hashlib.sha256(town.read_bytes()).hexdigest()
 path.write_text(json.dumps(r,ensure_ascii=False,separators=(',',':')))
