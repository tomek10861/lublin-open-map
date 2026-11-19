from pathlib import Path
import json,math
import numpy as np
import rasterio
r=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'');out=r/'terrain-build';meta=json.loads((out/'terrain.json').read_text());a=np.fromfile(out/'terrain-5m.f32',dtype='<f4').reshape(meta['rows'],meta['columns']);rng=np.random.default_rng(7001);checks=0;maxError=0
for source in meta['sources']:
 with rasterio.open(r/'nmt-original'/source['file'])as d:
  for row,col in zip(rng.integers(0,a.shape[0],250),rng.integers(0,a.shape[1],250)):
   e=744500+col*5;n=383500-row*5
   if d.bounds.left<=e<d.bounds.right and d.bounds.bottom<n<=d.bounds.top:
    z=float(next(d.sample([(e,n)]))[0])
    if z==d.nodata:continue
    error=abs(z-float(a[row,col]));assert error<.002,(source['file'],e,n,z,float(a[row,col]));maxError=max(maxError,error);checks+=1
assert checks>=80
# Cross-source alignment check, independent of mesh coordinate origin.
buildings=json.loads((r/'lublin-buildings-clipped.json').read_text())['buildings'];delta=[]
for b in buildings:
 p=[p for s in b['surfaces']if s['surface']=='GroundSurface'for p in s['coordinates']]
 if not p:continue
 e,n,z=np.mean(np.array(p),axis=0);row=int(round((383500-n)/5));col=int(round((e-744500)/5))
 if 0<=row<a.shape[0]and 0<=col<a.shape[1]:delta.append(abs(float(z)-float(a[row,col])))
proof={'independentGDALSourceSamples':checks,'maxHeightDifferenceM':maxError,'allGridFinite':bool(np.isfinite(a).all()),'gridShape':list(a.shape),'buildingsCompared':len(delta),'buildingGroundMedianAbsoluteDifferenceM':float(np.median(delta)),'buildingGroundP95AbsoluteDifferenceM':float(np.percentile(delta,95)),'rasterioGDAL':rasterio.__gdal_version__}
(out/'verification.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof,indent=2))
