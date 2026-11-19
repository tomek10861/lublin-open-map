"""Capture official NMPT patches around the map's bridge ways; preserve URL, datum and digests."""
from pathlib import Path
import json,math,subprocess,hashlib,io,concurrent.futures
from urllib.parse import urlencode
import numpy as np
from datetime import datetime,timezone
root=Path(__file__).resolve().parent;out=root/'bridge-audit/extended-patches';out.mkdir(parents=True,exist_ok=True)
roads=json.loads((root/'terrain-build/roads-with-ground-heights.json').read_text())['roads'];tasks=[]
for road in roads:
 if road['properties'].get('bridge')not in ['yes','viaduct']:continue
 for part,points in enumerate(road['parts']):
  if len(points)<2:continue
  xy=np.array(points)[:,:2];lo=np.floor(xy.min(0)-120).astype(int);hi=np.ceil(xy.max(0)+120).astype(int)
  params={'SERVICE':'WCS','VERSION':'1.0.0','REQUEST':'GetCoverage','COVERAGE':'DSM_PL-KRON86-NH','CRS':'EPSG:2180','RESPONSE_CRS':'EPSG:2180','BBOX':','.join(map(str,[*lo,*hi])),'WIDTH':int(hi[0]-lo[0]),'HEIGHT':int(hi[1]-lo[1]),'FORMAT':'image/x-aaigrid'}
  url='https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMPT/GRID1/WCS/DigitalSurfaceModel?'+urlencode(params);tasks.append((road['id'],part,road['properties'],url))
def read_grid(path):
 head={};data=[]
 with path.open()as f:
  for line in f:
   fields=line.split()
   if not fields:continue
   if fields[0].lower()in {'ncols','nrows','xllcorner','yllcorner','xllcenter','yllcenter','cellsize','nodata_value'}:head[fields[0].lower()]=float(fields[1])
   else:data.append(line);break
  data.extend(f.readlines())
 if not all(k in head for k in ['ncols','nrows','cellsize']):raise ValueError('Response is not an ASCII height grid')
 values=np.loadtxt(io.StringIO(''.join(data)),dtype=np.float32)
 if values.shape!=(int(head['nrows']),int(head['ncols'])):raise ValueError('Height-grid dimensions mismatch')
 return head,values

def fetch(task):
 identity,part,tags,url=task
 if not str(identity).isdigit():raise ValueError('Expected an OSM numeric way identity')
 path=out/f'way-{identity}-{part}.asc';meta=path.with_suffix('.json');record={'way':identity,'part':part,'tags':tags,'url':url,'heightDatum':'PL-KRON86-NH','captureDate':datetime.now(timezone.utc).date().isoformat(),'capturedAtUTC':datetime.now(timezone.utc).isoformat(),'acquisitionDate':None}
 try:
  cached=json.loads(meta.read_text())if meta.exists()else None
  if not(path.exists()and cached and cached.get('url')==url and cached.get('sha256')==hashlib.sha256(path.read_bytes()).hexdigest()):
   temp=path.with_suffix('.download');p=subprocess.run(['/usr/bin/curl','--fail','--location','--retry','1','--max-time','35','--silent','--show-error','-o',str(temp),'-w','%{http_code}\n%{url_effective}',url],capture_output=True,text=True,check=True);record['transport']=p.stdout;read_grid(temp);temp.replace(path)
  if cached and cached.get('url')==url and cached.get('sha256')==hashlib.sha256(path.read_bytes()).hexdigest():record=cached.copy()
  head,values=read_grid(path);valid=np.isfinite(values)
  if 'nodata_value'in head:valid&=values!=head['nodata_value']
  record.update(status='captured',file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),header=head,validSamples=int(valid.sum()),totalSamples=int(values.size))
 except Exception as e:record.update(status='unavailable',reason=str(e))
 meta.write_text(json.dumps(record,indent=2,ensure_ascii=False));print(identity,record['status'],flush=True);return record
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:records=list(pool.map(fetch,tasks))
 (root/'bridge-audit/nmpt-extended-captures.json').write_text(json.dumps(records,indent=2,ensure_ascii=False));print('captured',sum(r['status']=='captured'for r in records),'of',len(records))
