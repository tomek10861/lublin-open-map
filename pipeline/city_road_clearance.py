"""Own the photographic street cut: drivable roads, protected buildings, exact XY clipping.
Footpaths are not carriageways. No expanded roadside band may erase building facades.
"""
import json
import numpy as np
import shapely
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union
from pyproj import Transformer
import xml.etree.ElementTree as ET
DRIVABLE={'motorway','trunk','primary','secondary','tertiary','unclassified','residential','service','living_street','pedestrian','motorway_link','trunk_link','primary_link','secondary_link','tertiary_link'}
def areas(root,road_width,*,with_buildings=False):
 origin=json.loads((root/'roi.json').read_text())['originEPSG2180'];ox,oy=origin[:2]
 roads=json.loads((root/'terrain-build/roads-with-ground-heights.json').read_text())['roads']
 protected=[]
 for b in json.loads((root/'lublin-buildings-clipped.json').read_text())['buildings']:
  for s in b['surfaces']:
   if s['surface']=='GroundSurface' and len(s['coordinates'])>=3:
    p=Polygon([(v[0]-ox,v[1]-oy)for v in s['coordinates']]).buffer(0)
    if not p.is_empty:protected.append(p)
 nodes={};ways=[];transform=Transformer.from_crs(4326,2180,always_xy=True)
 for path in sorted((root/'osm-tiles').glob('*.osm')):
  tree=ET.parse(path).getroot()
  for n in tree.findall('node'):nodes[n.get('id')]=(float(n.get('lon')),float(n.get('lat')))
  for w in tree.findall('way'):
   if any(t.get('k')=='building'for t in w.findall('tag')):ways.append([n.get('ref')for n in w.findall('nd')])
 for refs in ways:
  if len(refs)<4 or not all(r in nodes for r in refs):continue
  xy=[transform.transform(*nodes[r])for r in refs]
  p=Polygon([(x-ox,y-oy)for x,y in xy]).buffer(0)
  if not p.is_empty:protected.append(p)
 buildings=unary_union(protected).buffer(.6)
 strips=[];passages=[]
 for road in roads:
  tags=road['properties']
  tagged_passage=tags.get('tunnel')=='building_passage' or tags.get('covered')=='yes'
  if tags.get('highway')not in DRIVABLE and not tagged_passage:continue
  for part in road['parts']:
   if len(part)<2:continue
   line=LineString([(q[0]-ox,q[1]-oy)for q in part])
   if tagged_passage:passages.append(line.buffer(1.8))
   else:strips.append(line.buffer(road_width(tags)/2,cap_style='flat'))
 for path in sorted(root.glob('route-7*.json')):
  course=json.loads(path.read_text())['course']
  strips.append(LineString([(x-ox,y-oy)for x,y in course]).buffer(8.0,join_style='round'))
 street=unary_union(strips).difference(buildings)
 return (street,unary_union(passages),buildings)if with_buildings else (street,unary_union(passages))
LOCAL_LEAF_COORDS,LOCAL_LEAF_M=4000,96.0
_local_index={}   # id(area) -> (area, leaf boxes STRtree, leaf pieces); the area ref pins the id
def local(area,bounds):
 """area ∩ bounds. A city-wide clearance area is split once into a quadtree of box-aligned pieces
 (one overlay per level instead of one full-city overlay per mesh chunk); the result equals the
 direct intersection, with extra collinear vertices at leaf seams only."""
 ax0,ay0,ax1,ay1=area.bounds if not area.is_empty else (0,0,0,0);bx0,by0,bx1,by1=bounds.bounds
 if area.is_empty or shapely.get_num_coordinates(area)<=LOCAL_LEAF_COORDS or (ax1-ax0)*(ay1-ay0)<=16*max(1e-9,(bx1-bx0)*(by1-by0)):return area.intersection(bounds)   # chunk-sized: direct
 entry=_local_index.get(id(area))
 if entry is None or entry[0] is not area:
  boxes=[];pieces=[]
  def split(g,box):
   if g.is_empty:return
   x0,y0,x1,y1=box
   if shapely.get_num_coordinates(g)<=LOCAL_LEAF_COORDS or max(x1-x0,y1-y0)<=LOCAL_LEAF_M:boxes.append(shapely.box(*box));pieces.append(g);return
   xm,ym=(x0+x1)/2,(y0+y1)/2
   for q in((x0,y0,xm,ym),(xm,y0,x1,ym),(x0,ym,xm,y1),(xm,ym,x1,y1)):split(g.intersection(shapely.box(*q)),q)
  split(area,area.bounds)
  if len(_local_index)>=8:_local_index.clear()   # a few long-lived city areas per build
  entry=_local_index[id(area)]=(area,shapely.STRtree(boxes),np.array(pieces,dtype=object))
 _,tree,pieces=entry;hit=tree.query(bounds,predicate='intersects')
 if not len(hit):return Polygon()
 parts=shapely.get_parts(shapely.intersection(pieces[hit],bounds));parts=parts[shapely.get_type_id(parts)==3]   # seam-touching leaves add bare edges
 return unary_union(parts) if len(parts) else Polygon()
def clip(v,idx,street,passages,ground):
 """Return chunks (vertices, indices), preserving UV/Z by barycentric interpolation."""
 bounds=shapely.box(float(v[:,0].min())-.01,float(v[:,1].min())-.01,float(v[:,0].max())+.01,float(v[:,1].max())+.01)
 street=local(street,bounds);passages=local(passages,bounds)
 shapely.prepare(street);shapely.prepare(passages)
 tri=idx.reshape(-1,3);xyz=v[tri];c=xyz[:,:,:3].mean(1)
 if ground is None:low=np.ones(len(tri),bool);portal=np.zeros(len(tri),bool)
 else:
  above=xyz[:,:,2]-ground(xyz[:,:,0],xyz[:,:,1])
  low=above.max(1)<5.;portal=above.max(1)<2.8
 candidates=low|portal
 polys=shapely.polygons(xyz[:,:,:2]);hit=np.zeros(len(tri),bool)
 if low.any():hit[low]=shapely.intersects(polys[low],street)
 if portal.any():hit[portal]|=shapely.intersects(polys[portal],passages)
 fully=np.zeros(len(tri),bool)
 if low.any():fully[low]=shapely.covers(street,polys[low])
 if portal.any():fully[portal]|=shapely.covers(passages,polys[portal])
 keep=~hit;extra=[];combined=street.union(passages)
 for i in np.flatnonzero(hit&~fully):
  points=xyz[i];p=polys[i];cut=combined if portal[i] else street
  if p.area<1e-8:
   # Vertical faces have no 2D area; only remove those inside the clear road.
   if not cut.covers(shapely.Point(*c[i,:2])):keep[i]=True
   continue
  remainder=p.difference(cut)
  if remainder.is_empty:continue
  if abs(remainder.area-p.area)<1e-9:keep[i]=True;continue
  matrix=np.column_stack((points[1,:2]-points[0,:2],points[2,:2]-points[0,:2]))
  for piece in getattr(remainder,'geoms',[remainder]):
   if piece.geom_type!='Polygon' or piece.area<1e-8:continue
   triangles=shapely.constrained_delaunay_triangles(piece)
   for t in triangles.geoms:
    xy=np.asarray(t.exterior.coords)[:3];uv=np.linalg.solve(matrix,(xy-points[0,:2]).T).T
    q=points[0]+uv[:,0,None]*(points[1]-points[0])+uv[:,1,None]*(points[2]-points[0])
    # Preserve the source triangle's winding.
    if np.linalg.det(matrix)*np.linalg.det(np.column_stack((xy[1]-xy[0],xy[2]-xy[0])))<0:q=q[[0,2,1]]
    extra.extend(q)
 result=[]
 if keep.any():result.append((v,tri[keep].reshape(-1).astype('<u2')))
 for start in range(0,len(extra),63000):
  vv=np.array(extra[start:start+63000],dtype='<f4');result.append((vv,np.arange(len(vv),dtype='<u2')))
 return result,int(hit.sum())

ROAD_WIDTH={'motorway':8,'trunk':8,'primary':8,'secondary':7,'tertiary':7,'residential':6,'service':4.5,'living_street':5,'pedestrian':22}   # facade-to-facade on Krakowskie Przedmiescie
def road_width(tags):
 """OSM width, else lanes x 3.4 m (+ shoulders), else the class default. Covers the whole
 carriageway so parked/moving cars in the orthophoto do not show beside the asphalt."""
 default=ROAD_WIDTH.get(tags.get('highway'),6)
 try:return max(3,min(24,float(str(tags.get('width','')).split()[0])))
 except(ValueError,IndexError):pass
 try:
  lanes=int(str(tags.get('lanes','')).split(';')[0])
  return max(3,min(24,lanes*3.4+(.8 if tags.get('oneway')=='yes' else 1.2)))
 except ValueError:return default

def floor_chunks(v,idx,street):
 """Fill the cleared corridor with the actual collision terrain's interpolated surface."""
 bounds=shapely.box(float(v[:,0].min())-.01,float(v[:,1].min())-.01,float(v[:,0].max())+.01,float(v[:,1].max())+.01)
 if not street.intersects(bounds):return []
 outside=bounds.difference(local(street,bounds))
 floor=v.copy();floor[:,2]+=.04;floor[:,3:5]=floor[:,:2]/8
 return clip(floor,idx,outside,Polygon(),None)[0]

def bridge_shapes(root):
 """Identify retained bridge decks by complete producer-owned XY ribbons, not display names."""
 origin=np.array(json.loads((root/'roi.json').read_text())['originEPSG2180'][:2]);result=[]
 for road in json.loads((root/'terrain-build/roads-with-ground-heights.json').read_text())['roads']:
  if road['properties'].get('bridge')not in ['yes','viaduct']:continue
  width=road_width(road['properties'])
  for part in road['parts']:
   if len(part)<2:continue
   xy=np.array(part)[:,:2];out=[]
   for i,p in enumerate(xy):
    tangent=xy[min(len(xy)-1,i+1)]-xy[max(0,i-1)];length=np.linalg.norm(tangent)
    if length<.001:tangent=np.array([1.,0.]);length=1
    normal=np.array([-tangent[1],tangent[0]])/length*width/2
    out.extend([p-normal-origin,p+normal-origin])
   result.append(np.array(out,dtype='<f4'))
 return result

def is_bridge_ribbon(vertices,shapes):
 return any(len(vertices)==len(shape) and np.allclose(vertices[:,:2],shape,rtol=0,atol=.001)for shape in shapes)

def bridge_deck_area(root):
 """Reserve the deck footprint; retain lower roads only at actual interior crossings."""
 origin=np.array(json.loads((root/'roi.json').read_text())['originEPSG2180'][:2]);roads=[]
 for road in json.loads((root/'terrain-build/roads-with-ground-heights.json').read_text())['roads']:
  if road['properties'].get('bridge')in ['yes','viaduct'] or road['properties'].get('highway')not in DRIVABLE:continue
  for part in road['parts']:
   if len(part)>1:roads.append((LineString(np.asarray(part)[:,:2]-origin),road_width(road['properties'])))
 tree=shapely.STRtree([line for line,w in roads]);decks=[];crossings=[]
 for shape in bridge_shapes(root):
  centres=(shape[::2]+shape[1::2])/2;axis=LineString(centres)
  for k in range(len(centres)-1):decks.append(Polygon([shape[2*k],shape[2*k+1],shape[2*k+3],shape[2*k+2]]).buffer(0))
  for i in tree.query(axis,predicate='intersects'):
   line,width=roads[i];intersection=line.intersection(axis)
   for p in getattr(intersection,'geoms',[intersection]):
    if p.geom_type!='Point':continue
    s=axis.project(p);t=line.project(p)
    if min(s,axis.length-s)<3:continue
    a=np.array(axis.interpolate(min(axis.length,s+1)).coords[0])-np.array(axis.interpolate(max(0,s-1)).coords[0]);b=np.array(line.interpolate(min(line.length,t+1)).coords[0])-np.array(line.interpolate(max(0,t-1)).coords[0]);length=np.linalg.norm(a)*np.linalg.norm(b)
    if length and abs(a@b)/length<.7:crossings.append(line.buffer(width/2))
 return unary_union(decks).difference(unary_union(crossings))
