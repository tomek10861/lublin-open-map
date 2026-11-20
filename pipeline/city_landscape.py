"""Clean vegetation at surveyed OSM tree positions; no photographic ground blobs."""
import math,xml.etree.ElementTree as ET
import numpy as np
import shapely
from pyproj import Transformer

def tree_meshes(root,ground,street,buildings,per_tree=False,extra=()):
 """per_tree: one mesh per tree (each a knockdown prop in the engine); else 80 m cells.
 extra: (numeric id, local x, local y, tags) trees placed by another owner (city_cemetery)."""
 transform=Transformer.from_crs(4326,2180,always_xy=True);nodes={}
 for path in sorted((root/'osm-tiles').glob('*.osm')):
  for n in ET.parse(path).getroot().findall('node'):
   tags={t.get('k'):t.get('v')for t in n.findall('tag')}
   if tags.get('natural')=='tree':nodes[n.get('id')]=(float(n.get('lon')),float(n.get('lat')),tags)
 road_clear=street.buffer(1);shapely.prepare(road_clear);shapely.prepare(buildings)
 vv=[];ii=[];col=[];count=0;previous_cell=None;positioned=[]
 for identity,(lon,lat,tags)in nodes.items():
  x,y=transform.transform(lon,lat);x-=746600;y-=381750;positioned.append(((math.floor(x/80),math.floor(y/80)),identity,x,y,tags))
 for identity,x,y,tags in extra:positioned.append(((math.floor(x/80),math.floor(y/80)),identity,x,y,tags))
 for cell,identity,x,y,tags in sorted(positioned):
  if not(-2100<x<2800 and -1750<y<1750)or road_clear.covers(shapely.Point(x,y))or buildings.covers(shapely.Point(x,y)):continue
  try:height=max(3,min(20,float(tags.get('height',8))));radius=max(1,min(6,float(tags.get('diameter_crown',height*.65))/2))
  except ValueError:height=8;radius=2.6
  if vv and cell!=previous_cell:
   yield np.array(vv,dtype='<f4'),np.array(ii,dtype='<u2'),np.array(col,dtype='u1').tobytes(),count;vv=[];ii=[];col=[];count=0
  previous_cell=cell
  z=float(ground(x,y));base=len(vv);segments=10;rings=6
  for ring in range(rings+1):
   angle=math.pi*ring/rings;rr=max(.02,math.sin(angle))*radius;zz=z+height*.65+math.cos(angle)*height*.35
   for k in range(segments):
    a=2*math.pi*k/segments;vv.append([x+rr*math.cos(a),y+rr*math.sin(a),zz,.5,.5]);col.append([70,155+int(identity)%25,60,255])
  for ring in range(rings):
   for k in range(segments):
    a=base+ring*segments+k;b=base+ring*segments+(k+1)%segments;c=a+segments;d=b+segments;ii.extend([a,b,c,b,d,c])
  base=len(vv)
  for zz in [z,z+height*.5]:
   for k in range(segments):a=2*math.pi*k/segments;vv.append([x+.16*math.cos(a),y+.16*math.sin(a),zz,.5,.5]);col.append([115,75,45,255])
  for k in range(segments):a=base+k;b=base+(k+1)%segments;ii.extend([a,b,a+segments,b,b+segments,a+segments])
  count+=1
  if per_tree:yield np.array(vv,dtype='<f4'),np.array(ii,dtype='<u2'),np.array(col,dtype='u1').tobytes(),count;vv=[];ii=[];col=[];count=0;continue
  if len(vv)>30000 or len(ii)>180000:yield np.array(vv,dtype='<f4'),np.array(ii,dtype='<u2'),np.array(col,dtype='u1').tobytes(),count;vv=[];ii=[];col=[];count=0
 if vv:yield np.array(vv,dtype='<f4'),np.array(ii,dtype='<u2'),np.array(col,dtype='u1').tobytes(),count
