from pathlib import Path
import xml.etree.ElementTree as ET,zipfile,json,hashlib
from pyproj import Transformer
root=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'');bounds=tuple(json.loads((Path(__file__).resolve().parent/'roi.json').read_text())['boundsEPSG2180'])
ns={'g':'http://www.opengis.net/gml','b':'http://www.opengis.net/citygml/building/2.0'}
features=[];count=0;origin=[746600,381750,180]
with zipfile.ZipFile(root/'lublin-buildings-lod2-2017.zip') as z:
 for name in z.namelist():
  if not name.endswith('.gml'):continue
  with z.open(name) as f:
   for _,e in ET.iterparse(f,events=['end']):
    if e.tag!='{'+ns['b']+'}Building':continue
    count+=1;polygons=[];points=[]
    for surface in ['GroundSurface','WallSurface','RoofSurface']:
     for surf in e.findall('.//b:'+surface,ns):
      for ring in surf.findall('.//g:exterior/g:LinearRing',ns):
       pos=ring.find('g:posList',ns)
       if pos is not None:
        a=list(map(float,pos.text.split()));p=[a[i:i+3] for i in range(0,len(a),3)]
       else:p=[list(map(float,v.text.split())) for v in ring.findall('g:pos',ns)]
       points.extend(p);polygons.append({'surface':surface,'coordinates':p})
    if points and any(bounds[0]<=p[0]<=bounds[2] and bounds[1]<=p[1]<=bounds[3] for p in points):
     features.append({'id':e.get('{'+ns['g']+'}id'),'sourceFile':name,'surfaces':polygons})
    e.clear()
report={'crs':'EPSG:2180 (source XYZ easting,northing,height)','heightDatum':'PL-KRON86-NH','bounds':bounds,'origin':origin,'sourceYear':2017,'sourceUrl':'https://opendata.geoportal.gov.pl/InneDane/Budynki3D/LOD2/0663_gml.zip','sourceSha256':hashlib.sha256((root/'lublin-buildings-lod2-2017.zip').read_bytes()).hexdigest(),'attribution':'Główny Urząd Geodezji i Kartografii, modele3D budynków Lublin2017, CC BY4.0; wycięty obszar','license':'https://creativecommons.org/licenses/by/4.0/','totalSourceBuildings':count,'selectedBuildings':len(features),'buildings':features}
(root/'lublin-buildings-clipped.json').write_text(json.dumps(report,separators=(',',':'),ensure_ascii=False));print(json.dumps({k:v for k,v in report.items() if k!='buildings'},ensure_ascii=False,indent=2))
