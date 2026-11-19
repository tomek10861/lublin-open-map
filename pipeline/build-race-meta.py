"""Names, lengths and main streets of the authored PL01 circuits for the race picker."""
from pathlib import Path
import json
root=Path(__file__).resolve().parent;web=root.parent/'web/src'
OX,OY,_=json.loads((root/'roi.json').read_text())['originEPSG2180']
cat=json.loads((web/'catalog.json').read_text());det=json.loads((web/'race-details.json').read_text())
for p in sorted(root.glob('route-7*.json')):
 r=json.loads(p.read_text());eid=r['id']
 streets=[n for n,m in r['streets'].items()if n and m>=80][:6]
 pts=[[round(x-OX,2),round(y-OY,2)]for x,y in r['outline']];xs=[q[0]for q in pts];ys=[q[1]for q in pts]
 name=r['name'].replace('Lublin · ','')
 for e in cat['events']:
  if e['id']==eid:e.update(name=name,lengthM=round(r['lengthM']),streets=streets,outlinePoints=len(pts))
 import math
 olen=sum(math.dist(a,b)for a,b in zip(pts,pts[1:]))
 entry={'outlineLengthM':round(olen,2),'id':eid,'region':'PL01','kind':'Circuit','name':name,'streets':streets,'points':pts,'closed':True,'lengthM':round(r['lengthM']),
  'widthM':round(max(xs)-min(xs)),'heightM':round(max(ys)-min(ys)),'source':f'custom-city/Paths{eid}.bin','recordOffset':8+272*0,
  'lengthSource':'Authored circuit measured along profiled OSM-derived race line','outlineSource':'Simplified authored course'}
 det['events']=[e for e in det['events']if e['id']!=eid]+[entry]
 print(eid,name,round(r['lengthM']),'m:',', '.join(streets))
(web/'catalog.json').write_text(json.dumps(cat,ensure_ascii=False,indent=1));(web/'race-details.json').write_text(json.dumps(det,ensure_ascii=False))
# Street-name HUD (web/public/street-hud.js): named OSM streets of PL01 as local polylines.
_streets={}
for _road in json.loads((root/'terrain-build/roads-with-ground-heights.json').read_text())['roads']:
 _t=_road['properties'];_name=_t.get('name')
 if not _name or _t.get('highway') in (None,'footway','path','steps','cycleway','corridor','elevator','platform','proposed','construction'):continue
 for _part in _road['parts']:
  if len(_part)>1:_streets.setdefault(_name,[]).append([[round(q[0]-OX,1),round(q[1]-OY,1)]for q in _part])
(root.parent/'build/custom-city/streets.json').write_text(json.dumps({'about':'OSM street names (ODbL), PL01 local metres','streets':_streets},ensure_ascii=False,separators=(',',':')))
print('street names:',len(_streets))
# Free-roam traffic lanes (city_traffic): RoutesFreeRoam.bin for the authored city.
from city_traffic import lanes as _lanes, write as _write_lanes
_n=_write_lanes(root.parent/'build/custom-city/RoutesFreeRoam.bin',_lanes(root,(OX,OY,180)))
print('traffic lanes:',_n)
