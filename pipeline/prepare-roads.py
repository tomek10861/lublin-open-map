from pathlib import Path
import xml.etree.ElementTree as E,json,collections
from pyproj import Transformer
from shapely.geometry import LineString,box,mapping
root=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'');nodes={};ways={};p=Transformer.from_crs(4326,2180,always_xy=True);roi=box(*json.loads((Path(__file__).resolve().parent/'roi.json').read_text())['boundsEPSG2180'])
for file in sorted((root/'osm-tiles').glob('*.osm')):
 t=E.parse(file)
 for n in t.findall('node'):nodes[n.get('id')]=p.transform(float(n.get('lon')),float(n.get('lat')))
 for w in t.findall('way'):
  tags={v.get('k'):v.get('v') for v in w.findall('tag')}
  if tags.get('highway')in['motorway','trunk','primary','secondary','tertiary','residential','unclassified','living_street','service','pedestrian','motorway_link','trunk_link','primary_link','secondary_link','tertiary_link']:ways[w.get('id')]=([n.get('ref')for n in w.findall('nd')],tags)
features=[];names=collections.Counter()
for id,(refs,tags)in ways.items():
 if not all(n in nodes for n in refs)or len(refs)<2:continue
 line=LineString([nodes[n]for n in refs]).intersection(roi)
 if line.is_empty:continue
 features.append({'type':'Feature','id':id,'properties':tags,'geometry':mapping(line)});names[tags.get('name','bez nazwy')]+=line.length
result={'type':'FeatureCollection','crs':{'type':'name','properties':{'name':'EPSG:2180'}},'attribution':'© OpenStreetMap contributors','license':'https://www.openstreetmap.org/copyright','features':features}
(root/'roads-clipped.geojson').write_text(json.dumps(result,separators=(',',':'),ensure_ascii=False));(root/'road-names.json').write_text(json.dumps(names.most_common(),ensure_ascii=False,indent=2))
print('Road features',len(features))
for name,length in names.items():
 if any(s in name.lower() for s in ['kraśnick','solidarno','głęboka','racławick','sikorsk','poniatowsk','sowińsk']):print(name,round(length),'m centerlines (includes separate carriageways)')
