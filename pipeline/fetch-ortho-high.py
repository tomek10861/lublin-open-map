"""GUGiK WMS-only cache -> GDAL-backed tiled GeoTIFF -> bounded runtime atlas."""
from pathlib import Path
from urllib.parse import urlencode
import json,math,hashlib,subprocess,time,concurrent.futures,os,sys
from PIL import Image
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window
from rasterio.enums import Resampling
root=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'/ortho-high');cache=root/'cache';runtime=root/'runtime';cache.mkdir(parents=True,exist_ok=True);runtime.mkdir(exist_ok=True)
base='https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/HighResolution';xmin,ymin,xmax,ymax=json.loads((Path(__file__).resolve().parent/'roi.json').read_text())['boundsEPSG2180'];res=.1
# Request grid anchored at the original west edge (744500, 2048 px = 204.8 m columns): an ROI
# extension only fetches the new columns; cached tiles keep their exact URLs.
GRID_X0=744500.0;gx=GRID_X0-math.ceil(max(0,GRID_X0-xmin)/204.8)*204.8
width,height=round((xmax-gx)/res),round((ymax-ymin)/res)
requests=[]
for row in range(math.ceil(height/2048)):
 for col in range(math.ceil(width/2048)):
  w,h=min(2048,width-col*2048),min(2048,height-row*2048);x=gx+col*2048*res;top=ymax-row*2048*res
  params={'SERVICE':'WMS','VERSION':'1.1.1','REQUEST':'GetMap','LAYERS':'Raster','STYLES':'','SRS':'EPSG:2180','BBOX':f'{x:.3f},{top-h*res:.3f},{x+w*res:.3f},{top:.3f}','WIDTH':w,'HEIGHT':h,'FORMAT':'image/jpeg'}
  url=base+'?'+urlencode(params);key=hashlib.sha256(url.encode()).hexdigest();requests.append({'row':row,'col':col,'width':w,'height':h,'url':url,'file':key+'.jpg','bboxEPSG2180':[x,top-h*res,x+w*res,top]})
def fetch(spec):
 p=cache/spec['file'];side=p.with_suffix('.json')
 if p.exists()and side.exists():
  record=json.loads(side.read_text());im=Image.open(p)
  if im.size==(spec['width'],spec['height'])and record['url']==spec['url']and record['sha256']==hashlib.sha256(p.read_bytes()).hexdigest():return record
 temp=p.with_suffix('.part')
 for attempt in range(3):
  t=subprocess.run(['/usr/bin/curl','-sSfL','--max-time','35',spec['url'],'-o',str(temp)],capture_output=True)
  try:
   if t.returncode:raise RuntimeError(t.stderr.decode())
   with Image.open(temp)as im:im.load();assert im.format=='JPEG' and im.size==(spec['width'],spec['height'])
   record={**spec,'sha256':hashlib.sha256(temp.read_bytes()).hexdigest(),'bytes':temp.stat().st_size,'source':'GUGiK, geoportal.gov.pl','resolutionMPerPixel':res};os.replace(temp,p);side.write_text(json.dumps(record,indent=2));return record
  except Exception:
   if attempt==2:raise
   time.sleep(1+attempt)
if '--runtime-only' not in sys.argv:
 results=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:
  for i,record in enumerate(pool.map(fetch,requests),1):
   results.append(record)
   if i%12==0 or i==len(requests):print(f'Cached {i}/{len(requests)} GUGiK tiles',flush=True)
 (root/'tiles.json').write_text(json.dumps(results,indent=2))
# Streaming tile windows: never allocate the full1.47Gpixel mosaic in RAM.
mosaic=root/'lublin-ortho-0.1m.tif'
with rasterio.Env(GDAL_CACHEMAX=64):
 if '--runtime-only' not in sys.argv:
  with rasterio.open(mosaic,'w',driver='GTiff',width=width,height=height,count=3,dtype='uint8',crs='EPSG:2180',transform=from_origin(gx,ymax,res,res),tiled=True,blockxsize=512,blockysize=512,compress='JPEG',jpeg_quality=90,photometric='YCBCR',BIGTIFF='IF_SAFER',num_threads=2)as dst:
   for record in results:
    with Image.open(cache/record['file'])as im:a=np.asarray(im.convert('RGB'))
    dst.write(a.transpose(2,0,1),window=Window(record['col']*2048,record['row']*2048,record['width'],record['height']))
   dst.update_tags(SOURCE='GUGiK, geoportal.gov.pl',WMS_SERVICE=base,WMS_LAYER='Raster',REQUESTED_RESOLUTION_M='.1',NOTE='Requested raster spacing does not prove native acquisition resolution; source blur/redaction retained.')
   dst.build_overviews([2,4,8,16,32,64],Resampling.average);dst.update_tags(ns='rio_overview',resampling='average')
  print('GDAL GeoTIFF mosaic and overviews written',flush=True)
 atlas=[]
 with rasterio.open(mosaic)as src:
  for row in range(2):
   for col in range(3):
    x=xmin+col*2032;top=ymax-row*2032;w=min(2032,xmax-x);h=min(2032,top-ymin)
    if w<=0 or h<=0:continue
    #0.5m runtime texels; max4000pixels per texture, native mipmaps at upload.
    a=src.read(window=Window(round((x-gx)/res),round((ymax-top)/res),round(w/res),round(h/res)),out_shape=(3,round(h/.5),round(w/.5)),resampling=Resampling.average)
    contentH,contentW=a.shape[1:];tw=1;th=1
    while tw<contentW+32:tw*=2
    while th<contentH+32:th*=2
    padded=np.pad(a.transpose(1,2,0),((16,th-contentH-16),(16,tw-contentW-16),(0,0)),mode='edge')
    filename=f'ortho-{col}-{row}.png';im=Image.fromarray(padded);im.save(runtime/filename)
    atlas.append({'file':filename,'boundsEPSG2180':[x,top-h,x+w,top],'width':im.width,'height':im.height,'contentWidth':contentW,'contentHeight':contentH,'gutterPx':16,'uvRect':[16/tw,16/th,(16+contentW)/tw,(16+contentH)/th],'runtimeMPerPixel':.5,'source':'GUGiK, geoportal.gov.pl','sha256':hashlib.sha256((runtime/filename).read_bytes()).hexdigest()})
(root/'atlas.json').write_text(json.dumps({'source':base,'layer':'Raster','crs':'EPSG:2180','cacheResolutionM':.1,'runtimeResolutionM':.5,'gutterPx':16,'sampler':'clamp_to_edge; anisotropy16x capped by GPU','tiles':atlas,'mipmaps':'native upload_tex -> rhi_texture_generate_mips; trilinear sampler','attribution':'Źródło: GUGiK, geoportal.gov.pl'},ensure_ascii=False,indent=2))
print(json.dumps({'cacheTiles':len(requests),'gdal':rasterio.__gdal_version__,'mosaic':str(mosaic),'runtimeTextures':len(atlas)},ensure_ascii=False),flush=True)
