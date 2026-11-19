"""Resample verified GUGiK ASCII grids, preserving datum/no-data and source provenance."""
from pathlib import Path
import json,math,hashlib,struct
import numpy as np
from PIL import Image
root=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'');out=root/'terrain-build';out.mkdir(exist_ok=True)
bounds=list(json.loads((Path(__file__).resolve().parent/'roi.json').read_text())['boundsEPSG2180']);step=5;x=np.arange(bounds[0],bounds[2]+step,step);y=np.arange(bounds[3],bounds[1]-step,-step);xx,yy=np.meshgrid(x,y);height=np.full(xx.shape,np.nan,dtype=np.float32);coverage=np.zeros(xx.shape,dtype=np.uint8);sources=[];tiles=[]
for p in sorted((root/'nmt-original').glob('*.asc')):
 with p.open()as f:head={k.lower():float(v)for k,v in (f.readline().split() for _ in range(6))}
 cols,rows=int(head['ncols']),int(head['nrows']);a=np.loadtxt(p,skiprows=6,dtype=np.float32);assert a.shape==(rows,cols)
 cell=head['cellsize'];west=head.get('xllcenter',head.get('xllcorner',0)+cell/2);south=head.get('yllcenter',head.get('yllcorner',0)+cell/2);north=south+(rows-1)*cell
 assert cell==1.0;valid=(xx>=west)&(xx<=west+(cols-1)*cell)&(yy>=south)&(yy<=north)
 col=np.clip(np.rint((xx-west)/cell).astype(int),0,cols-1);row=np.clip(np.rint((north-yy)/cell).astype(int),0,rows-1);z=a[row,col];valid&=np.isfinite(z)&(z!=head['nodata_value'])
 overlap=valid&np.isfinite(height)
 if overlap.any():assert float(np.max(np.abs(height[overlap]-z[overlap])))<.11,'Inconsistent duplicate source heights'
 height[valid]=z[valid];coverage[valid]+=1
 src={'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'cellM':cell,'xCenter':west,'yCenter':south,'rows':rows,'columns':cols};sources.append(src);tiles.append((a,west,south,north,cell,head['nodata_value']))
seamRepairs=[]
for row,col in zip(*np.where(~np.isfinite(height))):
 e,n=xx[row,col],yy[row,col];best=None
 for a,w,so,t,c,nodata in tiles:
  ri,ci=round((t-n)/c),round((e-w)/c)
  for di in range(-2,3):
   for dj in range(-2,3):
    i,j=ri+di,ci+dj
    if 0<=i<a.shape[0] and 0<=j<a.shape[1] and a[i,j]!=nodata and np.isfinite(a[i,j]):
     dist=math.hypot(w+j*c-e,t-i*c-n)
     if dist<=2 and (best is None or dist<best[0]):best=(dist,float(a[i,j]))
 if best is not None:
  height[row,col]=best[1];seamRepairs.append({'easting':float(e),'northing':float(n),'nearestSourceDistanceM':best[0],'heightM':best[1]})
assert np.isfinite(height).all(),f'Uncovered samples {np.isnan(height).sum()}'
# Verify independent road-height lookup against the original1m grids, not the resampled mesh.
roadSeamRepairs={}
def sample(e,n):
 for a,w,s,t,c,nodata in tiles:
  row=(t-n)/c;col=(e-w)/c
  if 0<=row<a.shape[0]-1 and 0<=col<a.shape[1]-1:
   i,j=int(row),int(col);v=a[i:i+2,j:j+2]
   if np.isfinite(v).all()and (v!=nodata).all():
    u,f=col-j,row-i;return float((v[0,0]*(1-u)+v[0,1]*u)*(1-f)+(v[1,0]*(1-u)+v[1,1]*u)*f)
 best=None
 for a,w,so,t,c,nodata in tiles:
  ri,ci=round((t-n)/c),round((e-w)/c)
  for di in range(-2,3):
   for dj in range(-2,3):
    i,j=ri+di,ci+dj
    if 0<=i<a.shape[0] and 0<=j<a.shape[1] and a[i,j]!=nodata and np.isfinite(a[i,j]):
     dist=math.hypot(w+j*c-e,t-i*c-n)
     if dist<=2 and (best is None or dist<best[0]):best=(dist,float(a[i,j]))
 if best is not None:
  roadSeamRepairs[f'{e:.3f},{n:.3f}']={'easting':e,'northing':n,'nearestSourceDistanceM':best[0],'heightM':best[1]};return best[1]
 return None
roads=json.loads((root/'roads-clipped.geojson').read_text());profiles=[];missing=0
for feature in roads['features']:
 g=feature['geometry'];parts=[g['coordinates']]if g['type']=='LineString'else g['coordinates'];newparts=[]
 for line in parts:
  points=[]
  for k in range(len(line)-1):
   a,b=line[k],line[k+1];length=math.dist(a,b);count=max(1,math.ceil(length/5))
   for i in range(count):
    t=i/count;e=a[0]+(b[0]-a[0])*t;n=a[1]+(b[1]-a[1])*t;z=sample(e,n)
    if z is None:missing+=1
    points.append([round(e,3),round(n,3),round(z,3)if z is not None else None])
  if line:
   e,n=line[-1];z=sample(e,n);points.append([round(e,3),round(n,3),round(z,3)if z is not None else None]);missing+=z is None
  newparts.append(points)
 profiles.append({'id':feature['id'],'properties':feature['properties'],'parts':newparts})
assert missing==0,f'Missing road heights: {missing}'
(out/'roads-with-ground-heights.json').write_text(json.dumps({'crs':'EPSG:2180','heightDatum':'PL-KRON86-NH','heightMeaning':'NMT bare-earth elevation, not bridge deck height','sourceCellM':1,'roadSampleSpacingM':5,'roads':profiles},ensure_ascii=False,separators=(',',':')))
# Compact regular terrain grid, little endian, north-to-south rows, absolute heights.
(out/'terrain-5m.f32').write_bytes(height.astype('<f4').tobytes())
np.save(out/'terrain-5m.npy',height)
summary={'boundsEPSG2180':bounds,'heightDatum':'PL-KRON86-NH','sourceYear':2017,'sourceCellM':1,'meshCellM':step,'columns':len(x),'rows':len(y),'minHeightM':float(height.min()),'maxHeightM':float(height.max()),'missingSamples':int(np.isnan(height).sum()),'tileSeamNearestSamples':seamRepairs,'roadFeatures':len(profiles),'roadHeightSamples':sum(len(p)for r in profiles for p in r['parts']),'missingRoadSamples':missing,'roadTileSeamNearestSamples':list(roadSeamRepairs.values()),'sources':sources,'notes':['Resampled5m mesh from actual1mNMT; no synthetic flat fallback.','NMT represents bare earth: bridges/viaducts need separate deck reconstruction.','Historical2017data may differ from current roads.']}
(out/'terrain.json').write_text(json.dumps(summary,indent=2))
# Quick relief preview for inspection.
gy,gx=np.gradient(height,step);light=(.6-gx*.6+gy*.45)/np.sqrt(1+gx*gx+gy*gy);light=np.clip(light,.15,1);normal=(height-height.min())/(height.max()-height.min());rgb=np.stack([.25+.5*normal,.42+.35*normal,.22+.35*normal],axis=2)*light[:,:,None];Image.fromarray(np.uint8(np.clip(rgb,0,1)*255)).save(out/'terrain-relief.png')
print(json.dumps({k:v for k,v in summary.items()if k!='sources'},indent=2))
