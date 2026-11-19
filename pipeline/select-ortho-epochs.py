"""Compare cached GUGiK epochs for low-detail tiles. Selection is a sharpness
heuristic, not recovered detail; all source images/time requests remain retained."""
from pathlib import Path
from urllib.parse import urlencode
import argparse,json,hashlib,subprocess,concurrent.futures
from PIL import Image
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=0,help='0=all low-detail candidates');p.add_argument('--years',default='2025,2022,2019,2017');a=p.parse_args()
r=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'/ortho-high');baseCache=r/'cache';cache=r/'epochs';cache.mkdir(exist_ok=True);base=json.loads((r/'tiles.json').read_text());service='https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolutionTime'
def score(path):
 with Image.open(path)as im:
  im=im.convert('L');im.thumbnail((512,512));g=np.asarray(im,dtype=float)
 if g.std()<2 or np.mean(g>250)>.985:return None
 lap=-4*g[1:-1,1:-1]+g[:-2,1:-1]+g[2:,1:-1]+g[1:-1,:-2]+g[1:-1,2:];return float(lap.var())
for tile in base:tile['sharpness']=score(baseCache/tile['file'])
valid=[x['sharpness']for x in base if x['sharpness']is not None];threshold=float(np.percentile(valid,25));candidates=sorted([x for x in base if x['sharpness']is None or x['sharpness']<=threshold],key=lambda x:x['sharpness']or -1)
if a.limit:candidates=candidates[:a.limit]
def compare(tile):
 choices=[{'file':str(baseCache/tile['file']),'url':tile['url'],'requestedTime':None,'acquisitionYear':None,'sharpness':tile['sharpness'],'source':'GUGiK HighResolution current mosaic','sha256':tile['sha256']}];failures=[]
 for year in a.years.split(','):
  time=year+'-01-01';params={'SERVICE':'WMS','VERSION':'1.1.1','REQUEST':'GetMap','LAYERS':'Raster','STYLES':'','SRS':'EPSG:2180','BBOX':','.join(map(str,tile['bboxEPSG2180'])),'WIDTH':tile['width'],'HEIGHT':tile['height'],'FORMAT':'image/jpeg','TIME':time};url=service+'?'+urlencode(params);path=cache/(hashlib.sha256(url.encode()).hexdigest()+'.jpg')
  try:
   if not path.exists():subprocess.run(['/usr/bin/curl','-sSfL','--max-time','20',url,'-o',str(path)],check=True,capture_output=True)
   value=score(path)
   with Image.open(path)as im:assert im.size==(tile['width'],tile['height'])
   choices.append({'file':str(path),'url':url,'requestedTime':time,'acquisitionYear':None,'sharpness':value,'source':'GUGiK StandardResolutionTime','sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
  except Exception as e:failures.append({'requestedTime':time,'error':str(e)})
 usable=[x for x in choices if x['sharpness']is not None];best=max(usable,key=lambda x:x['sharpness'])if usable else choices[0]
 # Never label requested TIME as verified acquisition year. Keep metadata unknown
 # until GetFeatureInfo/PZGiK index confirms actual source capture date.
 return{'tile':tile['file'],'bboxEPSG2180':tile['bboxEPSG2180'],'selected':best,'candidates':choices,'failures':failures,'yearVerification':'TIME request is logged; actual acquisitionYear is not yet verified'}
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
 for result in pool.map(compare,candidates):
  results.append(result);(r/'epoch-selection.json').write_text(json.dumps({'heuristic':'variance of Laplacian at max512px, blank/no-data rejected','lowDetailThreshold':threshold,'candidateTiles':len(candidates),'completed':len(results),'tiles':results,'status':'selection manifest only; not yet applied to GDAL mosaic'},ensure_ascii=False,indent=2));print(json.dumps({'tile':result['tile'],'selectedTime':result['selected']['requestedTime'],'sharpness':result['selected']['sharpness']}),flush=True)
