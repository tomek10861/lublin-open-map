from pathlib import Path
import json,math,struct,zlib,hashlib,io,random,collections
import numpy as np
from PIL import Image,ImageDraw
import shapely
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon
root=Path(__file__).resolve().parent;out=root.parent/'build/custom-city';out.mkdir(exist_ok=True)
meta=json.loads((root/'terrain-build/terrain.json').read_text());heights=np.load(root/'terrain-build/terrain-5m.npy');x0,y0,x1,y1=meta['boundsEPSG2180'];ox,oy,oz=746600,381750,180
atlasMeta=json.loads((root/'ortho-high/atlas.json').read_text());atlas=atlasMeta['tiles'];photoCount=len(atlas)
meshes=[]
def store(cat,tex,vertices,indices=None,color=(128,128,128,255)):
 if len(vertices)<3:return
 a=np.asarray(vertices,dtype='<f4');assert a.shape[1]==5 and np.isfinite(a).all();idx=np.arange(len(a),dtype='<u2')if indices is None else np.asarray(indices,dtype='<u2');assert len(a)<65536 and len(idx)%3==0
 if (cat&255)==0:
  triangles=idx.reshape(-1,3).copy();xyz=a[triangles,:3];nz=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0])[:,2];triangles[nz<0]=triangles[nz<0][:,[0,2,1]];idx=triangles[np.abs(nz)>1e-5].reshape(-1).astype('<u2')
 if len(idx)<3:return   # every triangle was degenerate (clip slivers); TOWN requires ni>=3
 vcol=np.asarray(color,dtype='u1');vcol=vcol if vcol.ndim==2 else np.tile(vcol,(len(a),1));assert vcol.shape==(len(a),4);meshes.append((cat,tex,a,idx,vcol))
def clip_plane(poly,axis,bound,lower):
 out=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  insideA=a[axis]>=bound-1e-5 if lower else a[axis]<=bound+1e-5
  insideB=b[axis]>=bound-1e-5 if lower else b[axis]<=bound+1e-5
  if insideA:out.append(a)
  if insideA!=insideB:
   t=(bound-a[axis])/(b[axis]-a[axis]);out.append(a+(b-a)*t)
 return out
def add(cat,tex,vertices,indices=None,color=(128,128,128,255)):
 a=np.asarray(vertices,dtype=float)
 if len(a)<3:return
 idx=np.arange(len(a))if indices is None else np.asarray(indices)
 if tex!=0:
  target=len(textures)-1 if tex==5 else photoCount+{1:0,2:1,3:2,4:3,7:4,8:5,9:6,10:7,11:8,12:9,13:10,14:11,15:12,16:13,17:14,18:15,19:16,20:17,21:18,22:19,6:20}[tex]   # sky is always the last texture
  return store(cat,target,a,idx,color)
 # One projection owner for terrain, road surface and roofs. Clipping at atlas
 # edges prevents wrap/repeat seams or a building borrowing the neighboring tile.
 lo=a[:,:2].min(axis=0);hi=a[:,:2].max(axis=0)
 for slot,tile in enumerate(atlas):
  west,south,east,north=tile['boundsEPSG2180'];low=np.array([west-ox,south-oy]);high=np.array([east-ox,north-oy])
  if np.any(hi<low)or np.any(lo>high):continue
  def project(v):
   v=np.array(v,copy=True);v[:,3]=(tile['gutterPx']+(v[:,0]+ox-west)/(east-west)*tile['contentWidth'])/tile['width'];v[:,4]=(tile['gutterPx']+(north-v[:,1]-oy)/(north-south)*tile['contentHeight'])/tile['height'];return v
  if np.all(lo>=low)and np.all(hi<=high):store(cat,slot,project(a),idx,color);return
  result=[]
  for tri in idx.reshape(-1,3):
   poly=[a[i]for i in tri]
   for axis,bound,lower in[(0,low[0],True),(0,high[0],False),(1,low[1],True),(1,high[1],False)]:
    if not poly:break
    poly=clip_plane(poly,axis,bound,lower)
   for i in range(1,len(poly)-1):
    if np.linalg.norm(np.cross(poly[i][:3]-poly[0][:3],poly[i+1][:3]-poly[0][:3]))>1e-6:result.extend([poly[0],poly[i],poly[i+1]])
  if result:store(cat,slot,project(result),None,color)
# Ground owner: the shipped terrain mesh uses every other 5 m NMT sample (10 m).
# Road ribbons, start markers and physics read THIS surface, so no consumer can
# disagree with the drawn/collided terrain. NMT carries curbs, verges and
# embankments at 1 m; inside road corridors the mesh vertices are replaced by a
# masked Gaussian average along the corridor (sigma 15 m) so carriageways are
# continuous instead of following curb-level noise. Outside corridors: raw NMT.
roads=json.loads((root/'terrain-build/roads-with-ground-heights.json').read_text())['roads']
from city_road_clearance import road_width
def is_bridge(tags):return tags.get('bridge')in['yes','viaduct']
G=heights[::2,::2].astype(np.float64)
assert (G.shape[0]-1)*2==heights.shape[0]-1 and (G.shape[1]-1)*2==heights.shape[1]-1
corridor=np.zeros(G.shape,bool);gr,gc=np.mgrid[0:G.shape[0],0:G.shape[1]]
for road in roads:
 if is_bridge(road['properties']):continue
 reach=road_width(road['properties'])/2+10
 for points in road['parts']:
  for a,b in zip(points,points[1:]):
   for t in np.linspace(0,1,max(2,int(math.dist(a[:2],b[:2])/2)+1)):
    e=a[0]+(b[0]-a[0])*t;n=a[1]+(b[1]-a[1])*t;r=(y1-n)/10;c=(e-x0)/10;k=int(math.ceil(reach/10))
    i0,i1=max(0,int(r)-k),min(G.shape[0],int(r)+k+2);j0,j1=max(0,int(c)-k),min(G.shape[1],int(c)+k+2)
    corridor[i0:i1,j0:j1]|=((gr[i0:i1,j0:j1]-r)**2+(gc[i0:i1,j0:j1]-c)**2)*100<=reach*reach
def blur(a,sigma=1.5,radius=4):
 k=np.exp(-.5*(np.arange(-radius,radius+1)/sigma)**2);k/=k.sum()
 a=np.apply_along_axis(lambda v:np.convolve(np.pad(v,radius,mode='edge'),k,'valid'),0,a)
 return np.apply_along_axis(lambda v:np.convolve(np.pad(v,radius,mode='edge'),k,'valid'),1,a)
weight=blur(corridor.astype(float));smoothed=blur(G*corridor)/np.maximum(weight,1e-9)
G_raw=G.copy();G[corridor]=smoothed[corridor]
groundReport={'meshCellM':10,'corridorVertices':int(corridor.sum()),'corridorReachM':'road half-width + 10','sigmaM':15,
 'corridorChangeM':{'p50':round(float(np.median(np.abs(G-G_raw)[corridor])),3),'p99':round(float(np.percentile(np.abs(G-G_raw)[corridor],99)),3),'max':round(float(np.abs(G-G_raw)[corridor].max()),3)}}
def h(e,n):
 return float(h_vec(e,n))
from city_package import TerrainSurface
h_vec=TerrainSurface(G,x0,y1).sample
def v(e,n,z,u=None,w=None):return[e-ox,n-oy,z-oz,(e-x0)/(x1-x0)if u is None else u,(y1-n)/(y1-y0)if w is None else w]
import sys
from shapely.geometry import LineString
if '--events-only' in sys.argv:
 raw=(out/'PL01.town').read_bytes();data=zlib.decompress(raw[12:]);nt,nm,photoCount=struct.unpack_from('<III',data,0);pos=12;textures=[]
 for _ in range(nt):
  w,hh=struct.unpack_from('<II',data,pos);pos+=8
  textures.append(Image.frombytes('RGB',(w,hh),data[pos:pos+w*hh*3]));pos+=w*hh*3
 for _ in range(nm):
  cat,tex,nv,ni=struct.unpack_from('<IIII',data,pos);pos+=16
  vv=np.frombuffer(data,'<f4',nv*5,pos).reshape(nv,5).copy();pos+=nv*20
  ii=np.frombuffer(data,'<u2',ni,pos).copy();pos+=ni*2
  cc=np.frombuffer(data,'u1',nv*4,pos).reshape(nv,4).copy();pos+=nv*4
  if not cat&2048 and tex!=photoCount+11:meshes.append((cat,tex,vv,ii,cc))   # race meshes and cranes (lattice texture) are rebuilt
 assert pos==len(data)
 previous_report=json.loads((out/'build-report.json').read_text())
 # Cranes from the last full build's jib candidates (city_cranes owns the model).
 _cand=root/'modeled-buildings/crane-candidates.json'
 if _cand.exists():
  from city_cranes import merge as crane_merge,meshes as crane_meshes
  _jibs=json.loads(_cand.read_text())
  for _j in _jibs:_j.setdefault('tri',[_j['t'][0],_j['t'][1]])
  from city_landmarks import crane_free_zone
  _cfz=crane_free_zone(root,(ox,oy,oz));cranes=[c for c in crane_merge(_jibs) if not _cfz.contains(shapely.Point(*c['mast']))]
  for _kind,_cv,_ci in crane_meshes(cranes,lambda x,y:h_vec(x+ox,y+oy)-oz):add(2|256|1024,14,_cv,_ci)
  print('cranes',[{'mast':[round(float(c['mast'][0]),1),round(float(c['mast'][1]),1)],'jibZ':round(c['jibZ'],1),'reachM':round(c['reachM'],1)}for c in cranes],flush=True)
else:
 from city_mesh_finish import wall_planes,finish_chunks
 from city_bridges import chunks as bridge_chunks,footprint as bridge_footprint
 from city_landscape import tree_meshes
 from city_lod2_finish import gable_faces
 from city_road_clearance import areas as road_clearance_areas,clip as clip_street_mesh,floor_chunks as street_floor_chunks,bridge_deck_area
 import shapely
 street_cut,passages,protected_buildings=road_clearance_areas(root,road_width,with_buildings=True)
 _profiles=root/'bridge-audit/road-profiles.json';bridge_profiles=json.loads(_profiles.read_text())if _profiles.exists()else None
 mesh_building_envelope=protected_buildings.buffer(1);photographic_building_shell=protected_buildings.buffer(-.6)
 # Modeled buildings (city_modeled_buildings): their planar LoD2 walls stand exactly on the
 # footprint, so the street floor reaches the wall instead of stopping at the 0.6 m photo buffer.
 from shapely.ops import unary_union
 from city_modeled_buildings import select as modeled_select,bake as modeled_bake,apply as modeled_apply
 _modeled=modeled_select(root,(ox,oy,oz))[0];_modeled_ids={b['id']for b in _modeled};_modeled_fp=unary_union([b['footprint']for b in _modeled])
 if not _modeled_fp.is_empty:
  _ring=_modeled_fp.buffer(.65).difference(_modeled_fp);street_cut=street_cut.union(street_cut.intersection(_ring.buffer(.8)).buffer(.8).intersection(_ring))
 support_area=street_cut.union(passages);floor_area=support_area
 if bridge_profiles:support_area=support_area.union(bridge_footprint(bridge_profiles))
 # City of Lublin 2022 photogrammetric mesh (import-city-mesh.py). Inside its footprint
 # the mesh is what is SEEN; our smoothed ground, road ribbons and LoD2 walls stay as
 # physics only (TOWN cat bit 512 = draw_disabled). LoD2 roofs there are dropped.
 from shapely import contains_xy
 from shapely.ops import unary_union
 from shapely.geometry import Polygon as ShapelyPolygon, Point
 mesh_dir=root/'city-mesh-2022/import'
 mesh_meta=[json.loads(t.read_text())for t in sorted(mesh_dir.glob('Tile-*/A/tile.json'))]if mesh_dir.exists()else[]   # streamed tiles (LOD A + C)
 mesh_zone=unary_union([ShapelyPolygon(m['footprintLocal'])for m in mesh_meta]).buffer(-3.0)if mesh_meta else None
 def in_zone(xy):
  xy=np.asarray(xy,float).reshape(-1,2)
  return contains_xy(mesh_zone,xy[:,0],xy[:,1])if mesh_zone is not None else np.zeros(len(xy),bool)
 hiddenTriangles={'terrain':0,'road':0}
 def add_split(cat,tex,vertices,indices,kind):
  a=np.asarray(vertices,float);tri=np.asarray(indices).reshape(-1,3);inside=in_zone(a[tri][:,:,:2].mean(axis=1))
  if(~inside).any():add(cat,tex,a,tri[~inside].reshape(-1))
  if inside.any():
   add(cat|512,tex,a,tri[inside].reshape(-1));hiddenTriangles[kind]+=int(inside.sum())
   if kind=='terrain':low=a.copy();low[:,2]+=.01;add(cat|256,tex,low,tri[inside].reshape(-1))   # seen only through gaps in the photo mesh
 street_floors=[]
 #10m visual/physics terrain tiles keep collision-query work local.
 for row in range(0,heights.shape[0]-1,32):
  for col in range(0,heights.shape[1]-1,32):
   rows=list(range(row,min(row+32,heights.shape[0]-1)+1,2));cols=list(range(col,min(col+32,heights.shape[1]-1)+1,2));verts=[v(x0+j*5,y1-i*5,float(G[i//2,j//2]))for i in rows for j in cols];idx=[];width=len(cols)
   for i in range(len(rows)-1):
    for j in range(len(cols)-1):
     a=i*width+j;b=a+1;c=a+width;d=c+1;idx.extend([a,c,b,b,c,d])
   for tv,ti in clip_street_mesh(np.asarray(verts,dtype='<f4'),np.asarray(idx,dtype='<u2'),support_area,Polygon(),None)[0]:add_split(1,0,tv,ti,'terrain')
   # The lowered photo fallback stays visual only; road/terrain collision never overlaps.
   street_floors.extend(street_floor_chunks(np.asarray(verts,dtype='<f4'),np.asarray(idx,dtype='<u2'),floor_area))
 # Stock procedural facade materials; geometry remains the actual LoD2 surfaces.
 textures=[Image.open(root/'ortho-high/runtime'/tile['file']).convert('RGB')for tile in atlas]
 for wallcolor in [(172,158,132),(185,180,169),(145,151,151)]:
  im=Image.new('RGB',(256,256),wallcolor);d=ImageDraw.Draw(im)
  for floor in range(4):
   y=floor*64
   d.rectangle((0,y+59,255,y+63),fill=tuple(max(0,a-20)for a in wallcolor))
   for bay in range(4):
    x=bay*64;d.rectangle((x+15,y+10,x+49,y+50),fill=(70,74,77));d.rectangle((x+18,y+12,x+46,y+47),fill=(76,111,130));d.line((x+32,y+12,x+32,y+47),fill=(190,193,189),width=2);d.line((x+18,y+30,x+46,y+30),fill=(190,193,189));d.rectangle((x+12,y+50,x+52,y+53),fill=(218,215,201))
  textures.append(im)
 asphalt=Image.new('RGB',(256,256));pixels=asphalt.load();rng=random.Random(7001)
 for y in range(256):
  for x in range(256):
   shade=56+rng.randrange(-7,8);pixels[x,y]=(shade,shade,shade+1)
 d=ImageDraw.Draw(asphalt);d.rectangle((6,0,9,255),fill=(206,203,185));d.rectangle((246,0,249,255),fill=(206,203,185));d.rectangle((126,12,129,114),fill=(218,213,191));textures.append(asphalt)
 # Street surfaces by OSM class (procedural, original): 7 granite setts for pedestrian
 # streets (one texture = 4 x 4 m), 8 plain residential asphalt, 9 patched service asphalt.
 paving=Image.new('RGB',(512,512),(92,90,86));pd=ImageDraw.Draw(paving);rng=random.Random(9)
 for row in range(0,512,16):
  shift=(row//16%2)*8
  for col in range(-16,528,16):
   base=rng.randrange(118,168);tint=rng.randrange(-8,9);x=col+shift
   pd.rectangle((x+1,row+1,x+14,row+14),fill=(base+tint,base+tint-4,base-10+tint//2))
 for _ in range(9000):
  x,y=rng.randrange(512),rng.randrange(512);c=paving.getpixel((x,y));k=rng.randrange(-14,15);paving.putpixel((x,y),tuple(max(0,min(255,a+k))for a in c))
 textures.append(paving)
 def plain_asphalt(seed,base,patches):
  im=Image.new('RGB',(256,256));px=im.load();r=random.Random(seed)
  for y in range(256):
   for x in range(256):
    g=base+r.randrange(-8,9);px[x,y]=(g,g,g+2)
  dr=ImageDraw.Draw(im)
  for _ in range(patches):
   x,y=r.randrange(256),r.randrange(256);w,hh=r.randrange(20,70),r.randrange(15,50);g=base+r.choice([-14,-9,10,16]);dr.rectangle((x,y,x+w,y+hh),fill=(g,g,g+2))
  return im
 textures.append(plain_asphalt(11,64,0));textures.append(plain_asphalt(12,72,14))
 # 10: race barrier, red/white chevron boards (procedural)
 stripes=Image.new('RGB',(256,64),(235,235,232));sd_=ImageDraw.Draw(stripes)
 for x0_ in range(-64,256,32):sd_.polygon([(x0_,64),(x0_+16,64),(x0_+48,0),(x0_+32,0)],fill=(200,24,28))
 sd_.rectangle((0,0,255,3),fill=(60,60,60));sd_.rectangle((0,60,255,63),fill=(60,60,60));textures.append(stripes)
 textures.append(Image.new('RGB',(16,16),(255,206,20)))   # 11: race chevrons (solid signal yellow)
 # 12: pavement, grey 50 cm concrete slabs (texture repeat = 2.5 x 2.5 m, procedural)
 slabs=Image.new('RGB',(256,256),(112,111,108));sl=ImageDraw.Draw(slabs);rs=random.Random(12)
 for yy in range(0,255,51):
  for xx in range(0,255,51):
   g=rs.randrange(148,170);sl.rectangle((xx+2,yy+2,xx+49,yy+49),fill=(g,g-1,g-5))
 textures.append(slabs)
 # 13: bridge concrete (viaduct slab, fascias, parapets, piers)
 con=Image.new('RGB',(128,128),(150,148,142));cd_=ImageDraw.Draw(con);rc=random.Random(13)
 for _ in range(900):x_,y_=rc.randrange(128),rc.randrange(128);g_=rc.randrange(132,166);cd_.point((x_,y_),fill=(g_,g_-2,g_-6))
 cd_.rectangle((0,0,127,3),fill=(118,116,110));textures.append(con)
 # 14: tower-crane steel lattice (signal yellow, diagonal bracing)
 lat=Image.new('RGB',(64,64),(226,176,22));ld=ImageDraw.Draw(lat)
 for k_ in (0,63):ld.line((k_,0,k_,63),fill=(150,112,10),width=4);ld.line((0,k_,63,k_),fill=(150,112,10),width=4)
 ld.line((0,0,63,63),fill=(170,128,12),width=3);ld.line((0,63,63,0),fill=(170,128,12),width=3);textures.append(lat)
 # 15: concert-shell membrane (white, faint seams); 16: green bench slats; 17: timber cladding
 mem=Image.new('RGB',(128,128),(236,236,232));md=ImageDraw.Draw(mem)
 for k_ in range(0,128,32):md.line((k_,0,k_,127),fill=(214,215,212),width=2)
 textures.append(mem)
 bnc=Image.new('RGB',(64,64),(46,128,92));bd=ImageDraw.Draw(bnc)
 for k_ in range(0,64,16):bd.line((0,k_,63,k_),fill=(30,92,64),width=3)
 textures.append(bnc)
 tim=Image.new('RGB',(64,64),(168,104,52));tdw=ImageDraw.Draw(tim);rt=random.Random(17)
 for k_ in range(0,64,8):tdw.line((k_,0,k_,63),fill=(132,80,38),width=2)
 for _ in range(120):x_,y_=rt.randrange(64),rt.randrange(64);tdw.point((x_,y_),fill=(150,92,46))
 textures.append(tim)
 # 18: Portal Wilno-Lublin screen: a live-camera look at a Vilnius square (procedural, no imagery)
 scr=Image.new('RGB',(256,256));sp=scr.load()
 for y_ in range(256):
  for x_ in range(256):sp[x_,y_]=(150+y_//6,186+y_//10,222) if y_<120 else (128+(x_*7+y_*3)%17,124+(x_*5)%13,118)
 sd2=ImageDraw.Draw(scr);rr=random.Random(18)
 for k_ in range(9):x_=k_*30-10;h_=rr.randrange(40,75);sd2.rectangle((x_,120-h_,x_+30,120),fill=(rr.randrange(200,236),rr.randrange(190,226),rr.randrange(170,205)))
 for k_ in range(9):
  x_=k_*30-10
  for w_ in range(3):sd2.rectangle((x_+5+w_*8,95,x_+9+w_*8,103),fill=(60,70,82))
 sd2.polygon([(118,40),(128,10),(138,40)],fill=(238,232,214));sd2.rectangle((118,40,138,120),fill=(238,232,214))   # cathedral belfry
 for k_ in range(14):x_=rr.randrange(10,246);y_=rr.randrange(150,230);sd2.ellipse((x_-4,y_-26,x_+4,y_-18),fill=(48,44,46));sd2.rectangle((x_-5,y_-18,x_+5,y_),fill=(rr.randrange(40,160),rr.randrange(40,120),rr.randrange(60,160)))
 textures.append(scr)
 # 19: church facade for LoD2 churches outside the photo zone (plaster, tall round-arched windows, plinth; 12 m repeat)
 chu=Image.new('RGB',(256,256),(214,204,182));cdw=ImageDraw.Draw(chu)
 cdw.rectangle((0,226,255,255),fill=(168,156,138));cdw.rectangle((0,0,255,6),fill=(190,180,160))
 for bay in range(4):
  x_=bay*64;cdw.rectangle((x_+2,0,x_+6,226),fill=(198,188,166));cdw.rectangle((x_+22,70,x_+42,190),fill=(64,70,86))
  cdw.ellipse((x_+22,60,x_+42,80),fill=(64,70,86));cdw.line((x_+32,62,x_+32,190),fill=(150,140,120),width=2);cdw.line((x_+22,125,x_+42,125),fill=(150,140,120),width=2)
 textures.append(chu)
 # 20 cast iron, 21 gilt, 22 bronze (monuments)
 for _c in ((46,48,52),(214,176,64),(78,104,84)):
  _im=Image.new('RGB',(32,32),_c);_d=ImageDraw.Draw(_im);_rq=random.Random(sum(_c))
  for _ in range(60):_x,_y=_rq.randrange(32),_rq.randrange(32);_d.point((_x,_y),fill=tuple(min(255,v+_rq.randrange(-14,15)) for v in _c))
  textures.append(_im)
 # Street-name plates (Polish style: white on blue). Names: OSM `name` (ODbL).
 SIGN_W,SIGN_H,SIGN_COLS,SIGN_ATLAS_W=409,64,5,2048   # POT atlas width
 def plate_text(name):
  for full,short in(('Aleja ','al. '),('Aleje ','Al. '),('Plac ','pl. '),('Rondo ','rondo ')):
   if name.startswith(full):return short+name[len(full):]
  return 'ul. '+name
 junction_names={}
 for road in roads:
  name=road['properties'].get('name')
  if name:
   for points in road['parts']:
    for q in points:junction_names.setdefault((round(q[0]*2),round(q[1]*2)),set()).add(name)
 junction_names={k:v for k,v in junction_names.items()if len(v)>1}
 sign_names=sorted(set().union(*junction_names.values())) if junction_names else []
 rows=(len(sign_names)+1+SIGN_COLS-1)//SIGN_COLS;SIGN_H=min(SIGN_H,4096//rows);atlas_h=1   # cell height shrinks to fit every name
 while atlas_h<rows*SIGN_H:atlas_h*=2
 assert atlas_h<=4096,'street-name atlas overflow'
 signs_im=Image.new("RGB",(SIGN_ATLAS_W,atlas_h),(0,61,145));sd=ImageDraw.Draw(signs_im)
 from PIL import ImageFont
 FONT='/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf'
 def sign_cell(k):c,r=k%SIGN_COLS,k//SIGN_COLS;return c*SIGN_W,r*SIGN_H
 for k,name in enumerate(sign_names):
  x,y=sign_cell(k);text=plate_text(name);sd.rectangle((x+3,y+3,x+SIGN_W-4,y+SIGN_H-4),outline=(245,245,245),width=3)
  size=int(SIGN_H*.62)
  while size>14:
   font=ImageFont.truetype(FONT,size);l,t,r,b=sd.textbbox((0,0),text,font=font)
   if r-l<=SIGN_W-24:break
   size-=1
  sd.text((x+SIGN_W/2,y+SIGN_H/2),text,font=font,fill=(250,250,250),anchor='mm')
 pole_cell=sign_cell(len(sign_names));sd.rectangle((pole_cell[0],pole_cell[1],pole_cell[0]+SIGN_W-1,pole_cell[1]+SIGN_H-1),fill=(150,152,150))
 textures.append(signs_im)   # slot 7 (tex code 6)
 # City-mesh textures are NOT in PL01.town: they ship inside the streamed .tmesh tiles.
 sky=Image.new('RGB',(256,256));pix=sky.load()
 for y in range(256):
  t=y/255
  for x in range(256):pix[x,y]=tuple(round(a*(1-t)+b*t)for a,b in zip((20,36,65),(133,151,164)))
 textures.append(sky)
 # Street floor by real use: carriageways asphalt, pedestrian streets setts, the rest of the
 # cleared street band (pavements, race safety buffer) concrete slabs.
 from city_road_clearance import DRIVABLE as _DRIVABLE
 def _strips(classes):
  return unary_union([LineString([(q[0]-ox,q[1]-oy)for q in part]).buffer(road_width(r['properties'])/2,cap_style='flat')
   for r in roads if r['properties'].get('highway')in classes and not is_bridge(r['properties'])for part in r['parts']if len(part)>1])
 _ped_cls={'pedestrian','living_street'};_motor=_strips(_DRIVABLE-_ped_cls);_ped=_strips(_ped_cls).difference(_motor)
 floorKinds={'asphalt':0,'setts':0,'pavement':0}
 def _inside(v_,i_,area):
  b_=shapely.box(float(v_[:,0].min())-.01,float(v_[:,1].min())-.01,float(v_[:,0].max())+.01,float(v_[:,1].max())+.01)
  return clip_street_mesh(v_,i_,b_.difference(area),Polygon(),None)[0]
 for fv,fi in street_floors:
  for av,ai in _inside(fv,fi,_motor):add(0,8,av,ai);floorKinds['asphalt']+=len(ai)//3
  for rv,ri in clip_street_mesh(fv,fi,_motor,Polygon(),None)[0]:
   for pv,pi in _inside(rv,ri,_ped):pv=pv.copy();pv[:,3:5]=pv[:,:2]/4;add(0,7,pv,pi);floorKinds['setts']+=len(pi)//3
   for sv,si in clip_street_mesh(rv,ri,_ped,Polygon(),None)[0]:sv=sv.copy();sv[:,3:5]=sv[:,:2]/2.5;add(0,12,sv,si);floorKinds['pavement']+=len(si)//3
 print('street floor triangles',floorKinds,flush=True)
 street_floors.clear()
 # Road ribbons from actual OSM centerlines; bridge decks use approach interpolation.
 bridges=[]
 SURFACE={'pedestrian':7,'living_street':7,'residential':8,'unclassified':8,'service':9}
 corridor_lines=[]
 for road in roads:
  tags=road['properties'];width=road_width(tags);surface_tex=SURFACE.get(tags.get('highway'),4)
  def surface_uv(side,width,along,tex=surface_tex):
   return ((side+1)/2*width/4,along/4) if tex==7 else ((side+1)/2,along/16)
  for points in road['parts']:
   if len(points)>1 and not is_bridge(tags):corridor_lines.append(([(q[0]-ox,q[1]-oy)for q in points],width))
  for points in road['parts']:
   if len(points)<2:continue
   if tags.get('bridge')in['yes','viaduct']:
    cumulative=[0]
    for a,b in zip(points,points[1:]):cumulative.append(cumulative[-1]+math.dist(a[:2],b[:2]))
    if cumulative[-1]>0:
     start,end=h(*points[0][:2]),h(*points[-1][:2])
     for i,p in enumerate(points):p[2]=start+(end-start)*cumulative[i]/cumulative[-1]
     bridges.append({'id':road['id'],'name':tags.get('name'),'lengthM':cumulative[-1],'method':'linear deck between NMT approach elevations; requires verification'})
   verts=[];idx=[];along=0
   for i,p in enumerate(points):
    prev=points[max(0,i-1)];nxt=points[min(len(points)-1,i+1)];dx,dy=nxt[0]-prev[0],nxt[1]-prev[1];length=math.hypot(dx,dy)
    if length<.001:dx,dy,length=1,0,1
    nx,ny=-dy/length*width/2,dx/length*width/2
    if i:along+=math.dist(p[:2],points[i-1][:2])
    # Keep road and visual terrain at identical sampled heights, lifting only a small surface layer.
    for side in[-1,1]:
     e,n=p[0]+nx*side,p[1]+ny*side;z=p[2]if is_bridge(tags)else h(e,n);verts.append(v(e,n,z+.08,*surface_uv(side,width,along)))
    if i:a=(i-1)*2;idx.extend([a,a+2,a+1,a+1,a+2,a+3])
   if is_bridge(tags) and not bridge_profiles:add(0,surface_tex,verts,idx)   # bridge decks retain their separate authored height layer
 if bridge_profiles:
  for vv,ii in bridge_chunks(bridge_profiles):store(0,photoCount+5,vv,ii)
  from city_bridges import structure as bridge_structure
  _bridge_walls=[]
  for vv,ii in bridge_structure(bridge_profiles,lambda x,y:h_vec(x+ox,y+oy)-oz,_motor.buffer(1.0),collision=_bridge_walls):add(2|256|1024,13,vv,ii)
  # Pedestrian footbridges over carriageways (visual only: walkway, slab, railings, piers).
  from city_bridges import footbridges
  _foot=footbridges(root,lambda x,y:h_vec(x+ox,y+oy)-oz,_motor)
  for vv,ii in bridge_chunks(_foot,offset=0):add(2|256|1024,13,vv,ii)
  for vv,ii in bridge_structure(_foot,lambda x,y:h_vec(x+ox,y+oy)-oz,_motor.buffer(1.0),min_lift=1.0,collision=_bridge_walls,rail_lift=1e9):add(2|256|1024,13,vv,ii)
  # invisible: parapets and piers are solid. The engine ignores collision meshes wider than
  # WALL_MAX_SPAN (300 m), so long viaducts are split into 80 m cells.
  for vv,ii in _bridge_walls:
   _t=ii.reshape(-1,3);_cell=np.floor(vv[_t,:2].mean(1)/80).astype(int);_keys={tuple(k) for k in _cell}
   for _k in _keys:
    _sel=_t[(_cell==_k).all(1)].reshape(-1);_u,_inv=np.unique(_sel,return_inverse=True);add(2|256|512,1,vv[_u],_inv.astype('<u2'))
  print('bridge collision faces',sum(len(i)//6 for v,i in _bridge_walls),flush=True)
  print('footbridges',[(r['way'],round(max(r['z'])-min(r['z']),1),round(r['stationM'][-1]))for r in _foot],flush=True)
 tree_count=0
 # One mesh per tree: cat 4096 makes it a knockdown prop (falls when hit), 256 no drive surface.
 for vv,ii,colors,n in tree_meshes(root,lambda x,y:h_vec(x+ox,y+oy)-oz,street_cut,protected_buildings,per_tree=True):
  store(2|256|4096,photoCount+3,vv,ii,np.frombuffer(colors,dtype='u1').reshape(-1,4));tree_count+=n
 # One plate per (street, junction): 9 m into the street from the junction, 1.5 m
 # beyond its kerb, parallel to the street it names (readable from the crossing).
 def walk(points,start,step,dist):
  i=start
  while 0<=i+step<len(points):
   a,b=np.array(points[i][:2]),np.array(points[i+step][:2]);d=float(np.linalg.norm(b-a))
   if d>=dist and d>1e-6:return a+(b-a)*dist/d,(b-a)/d
   dist-=d;i+=step
  return None,None
 sign_index={n:k for k,n in enumerate(sign_names)};placed=set();sign_chunks={};signCount=0
 au,av=SIGN_ATLAS_W,atlas_h
 for road in roads:
  tags=road['properties'];name=tags.get('name')
  if not name or name not in sign_index or is_bridge(tags):continue
  half=road_width(tags)/2
  for points in road['parts']:
   for i,q in enumerate(points):
    key=(round(q[0]*2),round(q[1]*2))
    if key not in junction_names:continue
    dedupe=(name,round(q[0]/30),round(q[1]/30))
    if dedupe in placed:continue
    for step in(1,-1):
     pos,t=walk(points,i,step,9.0)
     if pos is not None:break
    if pos is None:continue
    placed.add(dedupe);signCount+=1
    right=np.array([t[1],-t[0]]);c=pos+right*(half+1.5);g=h(*c)
    x,y=sign_cell(sign_index[name]);u0,u1=(x+2)/au,(x+SIGN_W-2)/au;v0,v1=(y+2)/av,(y+SIGN_H-2)/av
    chunk=sign_chunks.setdefault(('sign',signCount),([],[]));verts,idx=chunk   # one mesh per sign: knockdown prop
    for normal in(right,-right):
     r=np.array([-normal[1],normal[0]])   # viewer's right when facing the plate from the `normal` side
     base=len(verts);n3=np.array([normal[0],normal[1]])*.03*(1 if normal is right else 1)
     for du,dz,uu,vv in((-1.1,2.8,u0,v1),(1.1,2.8,u1,v1),(1.1,3.2,u1,v0),(-1.1,3.2,u0,v0)):
      e,n=c+r*du+n3;verts.append(v(e,n,g+dz,uu,vv))
     idx.extend([base,base+1,base+2,base,base+2,base+3])
    pu,pv=(pole_cell[0]+SIGN_W/2)/au,(pole_cell[1]+SIGN_H/2)/av;post=c-right*.08
    for a_,b_ in(((-1,-1),(1,-1)),((1,-1),(1,1)),((1,1),(-1,1)),((-1,1),(-1,-1))):
     base=len(verts)
     for (sx,sy),z in((a_,-.3),(b_,-.3),(b_,3.25),(a_,3.25)):
      e,n=post+t*sx*.04+right*sy*.04;verts.append(v(e,n,g+z,pu,pv))
     idx.extend([base,base+1,base+2,base,base+2,base+3])
 for verts,idx in sign_chunks.values():add(2|256|4096|16384,6,verts,idx,(160,160,160,255))   # sign + post: knocked over (light debris) when hit
 # Triangulate source3D polygons on their own plane, preserving pitched roofs.
 buildings=json.loads((root/'lublin-buildings-clipped.json').read_text())['buildings'];roofTriangles=wallTriangles=0;skipped=0
 replacedBuildings=0
 # Building passages (gates such as Brama Krakowska / Grodzka): a wall that a road centreline
 # crosses is the passage opening, not a solid face. Applies to city-mesh buildings only
 # (their walls are invisible physics); visible LoD2 facades elsewhere are untouched.
 from shapely import STRtree
 from shapely.geometry import LineString as _Line
 road_lines=[_Line([(q[0]-ox,q[1]-oy)for q in part])for road in roads for part in road['parts']if len(part)>1]
 road_tagged=[road['properties'].get('tunnel')in('building_passage','yes')or road['properties'].get('covered')=='yes' for road in roads for part in road['parts']if len(part)>1]
 road_tree=STRtree(road_lines);passageWalls=0;passage_parts=[]
 # OSM tunnel=building_passage ways: a 3.8 m clear corridor (axis +-1.9 m, round ends) in which
 # no collision wall (LoD2 or OSM) may stand and photo geometry below 3.2 m is cut.
 passage_clear=unary_union([_Line([(q[0]-ox,q[1]-oy)for q in part]).buffer(1.9)for road in roads if road['properties'].get('tunnel')=='building_passage' for part in road['parts']if len(part)>1])
 passageClearAreaM2=round(passage_clear.area)
 # A road that runs THROUGH a building (>4 m inside its footprint) is a passage too; a road that
 # only clips a corner (OSM/LoD2 misregistration) is not, and the wall there stays solid.
 for building in buildings:
  for surf in building['surfaces']:
   if surf['surface']!='GroundSurface':continue
   gp=[(q[0]-ox,q[1]-oy)for q in surf['coordinates']]
   if len(gp)<3 or not in_zone([np.mean(gp,axis=0)])[0]:continue
   fp=ShapelyPolygon(gp).buffer(0)
   for k in road_tree.query(fp,predicate='intersects'):
    piece=road_lines[k].intersection(fp)
    if piece.is_empty or piece.length<=.5:continue
    depth=max(fp.exterior.distance(piece.interpolate(t,normalized=True))for t in np.linspace(0,1,21))
    # tagged passages always; untagged only a short pass-through (4-25 m, >1.5 m deep):
    # corner clips stay solid, long internal roads of merged LoD2 blocks stay solid.
    if road_tagged[k] or(4<piece.length<=25 and depth>1.5):passage_parts.append(piece)
 deep_cross=unary_union([g.buffer(1.9)for g in passage_parts if not g.is_empty]+[passage_clear])
 def wall_segment(coords):
  q=np.array(coords,float)[:,:2]-[ox,oy];c=q.mean(axis=0);d=q-c;u,sv,vt=np.linalg.svd(d,full_matrices=False);axis=vt[0];t_=d@axis
  return _Line([c+axis*t_.min(),c+axis*t_.max()]),c
 from city_landmarks import church_lod2_ids
 _churches=church_lod2_ids(root,(ox,oy,oz));print('church LoD2 buildings',len(_churches),flush=True)
 for building in buildings:
  wall=[];roof=[]
  for surf in building['surfaces']:
   if surf['surface']=='GroundSurface':
    gp=[(q[0]-ox,q[1]-oy)for q in surf['coordinates']]
    continue
   if surf['surface']=='WallSurface' and mesh_zone is not None and len(surf['coordinates'])>=3:
    seg,c=wall_segment(surf['coordinates'])
    if in_zone([c])[0] and seg.length>.3 and seg.intersects(deep_cross):passageWalls+=1;continue
   p=np.array(surf['coordinates'],dtype=float)
   if len(p)>1 and np.linalg.norm(p[0]-p[-1])<.001:p=p[:-1]
   if len(p)<3:continue
   normal=np.zeros(3)
   for i in range(1,len(p)-1):
    normal=np.cross(p[i]-p[0],p[i+1]-p[0])
    if np.linalg.norm(normal)>.0001:break
   if np.linalg.norm(normal)<.0001:skipped+=1;continue
   drop=int(np.argmax(np.abs(normal)));axes=[k for k in range(3)if k!=drop];polygon=Polygon(p[:,axes])
   if not polygon.is_valid:skipped+=1;continue
   triangles=constrained_delaunay_triangles(polygon)
   for triangle in triangles.geoms:
    coords=list(triangle.exterior.coords)[:3];q=[]
    for ab in coords:
     xyz=p[0].copy();xyz[axes]=ab;xyz[drop]=p[0,drop]-sum(normal[k]*(xyz[k]-p[0,k])for k in axes)/normal[drop];q.append(xyz)
    if np.dot(np.cross(q[1]-q[0],q[2]-q[0]),normal)<0:q.reverse()
    target=wall if surf['surface']=='WallSurface'else roof
    for xyz in q:
     if surf['surface']=='WallSurface':
      horizontal=xyz[0]if abs(normal[1])>abs(normal[0])else xyz[1];target.append(v(*xyz,horizontal/12,xyz[2]/12))
     else:target.append(v(*xyz))
  replaced=bool(wall)and(building['id']in _modeled_ids or bool(in_zone([np.mean([q[0]for q in wall]),np.mean([q[1]for q in wall])])[0]))   # modeled buildings never keep visible LoD2 too
  if replaced:replacedBuildings+=1;roof=[]
  if wall:
   # LoD2 bases and the road-smoothed ground differ by decimetres; sink each
   # building's lowest ring 0.3 m into the shipped ground so no facade floats.
   base=min(q[2] for q in wall)
   for q in wall:
    if q[2]<=base+.05:q[2]=min(q[2],h(q[0]+ox,q[1]+oy)-oz-.3)
   add((2|256|512) if replaced else 257,   # replaced: invisible OTHER walls = collision obstacles
       19 if building['id'] in _churches else 1+int(hashlib.sha256(building['id'].encode()).hexdigest()[:4],16)%3,wall);wallTriangles+=len(wall)//3
  if roof:
   add(2,0,roof);roofTriangles+=len(roof)//3
   if wall and not replaced:
    cap=gable_faces((np.asarray(wall,dtype='<f4'),np.arange(len(wall),dtype='<u2')),[(np.asarray(roof,dtype='<f4'),np.arange(len(roof),dtype='<u2'))])
    if len(cap):store(1281,photoCount+16 if building['id'] in _churches else photoCount+int(hashlib.sha256(building['id'].encode()).hexdigest()[:4],16)%3,cap)
 # ---- Streamed city-mesh tiles (engine: stream_tiles.h). One .tmesh per tile and LOD:
 #  "TMSHv001" u32 unpacked | zlib( u32 ntex u32 nchunk | ntex*(u32 w,h, rgb) | nchunk*(u32 tex,nv,ni, f32 v[nv*5], u16 i[ni]) )
 # Shared map rules applied HERE, once: measured street-height offset and street-level cut.
 def load_lod(tile,lod):
  d=mesh_dir/tile/lod;z=np.load(d/'mesh.npz');meta=json.loads((d/'tile.json').read_text())
  chunks=[(int(z[f'm{i}']),z[f'v{i}'].copy(),z[f'i{i}'])for i in range(int(z['count']))]
  return meta,chunks
 road_pts=[]
 for road in roads:
  for points in road['parts']:road_pts.extend((q[0]-ox,q[1]-oy)for q in points)
 road_pts=np.array(road_pts);road_cells=set(map(tuple,np.floor(road_pts[in_zone(road_pts)]/2).astype(int)))if len(road_pts)else set()
 streetDiff=[]
 for m in mesh_meta:
  for _,vv,ii in load_lod(m['tile'],'A')[1]:
   t=vv[ii.reshape(-1,3).astype(int),:3];nrm=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);l=np.linalg.norm(nrm,axis=1);c=t[(l>1e-6)&(np.abs(nrm[:,2])>.95*l)].mean(axis=1)[::3]
   keep=np.array([tuple(k)in road_cells for k in np.floor(c[:,:2]/2).astype(int)],bool)if len(c)else np.zeros(0,bool)
   if keep.any():streetDiff.extend((c[keep,2]-(h_vec(c[keep,0]+ox,c[keep,1]+oy)-oz)).tolist())
 streetDiff=np.array(streetDiff)
 meshZOffset=-float(np.median(streetDiff))if len(streetDiff)>=100 else 0.0   # measured, not assumed
 from shapely.geometry import LineString
 modeledReport=modeled_bake(root,(ox,oy,oz),meshZOffset)
 from city_mesh_finish import drop_loose;looseReport={};_jibs=[]
 from city_modeled_buildings import drop_leftovers as modeled_leftovers,osm_only_footprints
 _osm_only=osm_only_footprints(root,(ox,oy,oz))
 from city_landmarks import zone as landmark_zone,meshes as landmark_meshes,collision as landmark_collision
 from city_landmarks import photo_clear_zone
 from city_landmarks import portal_zone,portal_meshes,portal_collision
 _landmark=landmark_zone().union(photo_clear_zone(root,(ox,oy,oz))).union(portal_zone());shapely.prepare(_landmark)
 # Support height for loose photo pieces: terrain, or the LoD2 roof top over a footprint (2 m grid).
 import rasterio.features,rasterio.transform
 _sx0,_sy0,_sx1,_sy1=x0-ox-50,y0-oy-50,x1-ox+50,y1-oy+50
 _sw,_sh=int((_sx1-_sx0)/2)+1,int((_sy1-_sy0)/2)+1;_st=rasterio.transform.from_origin(_sx0,_sy1,2,2);_tops=[]
 for _b in json.loads((root/'lublin-buildings-clipped.json').read_text())['buildings']:
  _top=max((q[2]for _s in _b['surfaces']if _s['surface']=='RoofSurface'for q in _s['coordinates']),default=None)
  for _s in _b['surfaces']:
   if _top is not None and _s['surface']=='GroundSurface'and len(_s['coordinates'])>=3:_tops.append((Polygon([(q[0]-ox,q[1]-oy)for q in _s['coordinates']]).buffer(1.0),_top-oz))
 _roof=rasterio.features.rasterize(sorted(_tops,key=lambda t:t[1]),out_shape=(_sh,_sw),transform=_st,fill=-1e9,dtype='float32')
 def support_height(x,y):
  c=np.clip(((x-_sx0)/2).astype(int),0,_sw-1);r=np.clip(((_sy1-y)/2).astype(int),0,_sh-1)
  return np.maximum(h_vec(x+ox,y+oy)-oz,_roof[r,c])
 finish_planes=wall_planes(root);mesh_finish={}
 stream_dir=out/'stream';stream_dir.mkdir(exist_ok=True)
 for old in stream_dir.glob('*.tmesh'):old.unlink()
 streamIndex=[];meshTriangles={'A':0,'C':0};clippedStreetTriangles={'A':0,'C':0}
 for m in mesh_meta:
  entry={'tile':m['tile'],'bbox':[float(v)for v in m['boundsLocal'][:2]+m['boundsLocal'][3:5]]}
  for lod in('A','C'):
   meta,chunks=load_lod(m['tile'],lod);body=io.BytesIO();texs=sorted(meta['textures'],key=int);slot={int(k):i for i,k in enumerate(texs)}
   kept=[]
   for _,vv,_ in chunks:vv[:,2]+=meshZOffset
   finished,mesh_finish[f"{m['tile']}-{lod}"],count=finish_chunks(chunks,meta,finish_planes,mesh_building_envelope,street_cut,passages,lambda x,y:h_vec(x+ox,y+oy)-oz,photographic_building_shell)
   clippedStreetTriangles[lod]+=count
   for tex,vertices,indices in finished:
    kept.append((slot[tex],vertices.astype('<f4'),indices.astype('<u2')));meshTriangles[lod]+=len(indices)//3
   ims=[]
   for k in texs:
    im=Image.open(mesh_dir/m['tile']/lod/f'tex-{k}.png').convert('RGB')
    pot=lambda n:1<<max(0,round(math.log2(n)))
    if im.size!=(pot(im.width),pot(im.height)):im=im.resize((pot(im.width),pot(im.height)),Image.LANCZOS)   # WebGL1 mipmaps need POT
    ims.append(im)
   _photo_slots=len(ims);kept,ims,_removed=modeled_apply(root,m['tile'],lod,kept,ims)
   kept,_left=modeled_leftovers(root,kept,_photo_slots,_osm_only);looseReport.setdefault(lod,{}).setdefault('modeledLeftovers',0);looseReport[lod]['modeledLeftovers']+=_left
   _photo,_loose=drop_loose([k for k in kept if k[0]<_photo_slots],lambda x,y:h_vec(x+ox,y+oy)-oz,protected_buildings,support_height,found=_jibs if lod=='A' else None);kept=_photo+[k for k in kept if k[0]>=_photo_slots]
   for _k,_n in _loose.items():looseReport.setdefault(lod,{}).setdefault(_k,0);looseReport[lod][_k]+=_n
   _lm=[]   # hand-modeled landmarks own their spot: drop the photo mesh there
   for _t,_v,_i in kept:
    if _t>=_photo_slots:_lm.append((_t,_v,_i));continue
    _tri=_i.reshape(-1,3).astype(np.int64);_c=_v[_tri,:2].mean(1);_in=shapely.contains_xy(_landmark,_c[:,0],_c[:,1])
    if not _in.all():_lm.append((_t,_v,_tri[~_in].reshape(-1).astype('<u2')))
   kept=_lm
   modeledReport.setdefault('photoTrianglesReplaced',{}).setdefault(lod,0);modeledReport['photoTrianglesReplaced'][lod]+=_removed
   if lod=='A':
    # TMSHj001 (network form of LOD A): JPEG textures + deflated meshes. The page's tile worker
    # decodes it into the engine's uncompressed body (TMSHr001); textures are ~8x smaller.
    head=io.BytesIO();head.write(struct.pack('<I',len(ims)))
    for im in ims:
     jb=io.BytesIO();im.save(jb,'JPEG',quality=90,subsampling=0 if im.width<=2048 else 2,optimize=True);jb=jb.getvalue()
     head.write(struct.pack('<III',*im.size,len(jb)));head.write(jb)
    meshes_=io.BytesIO();meshes_.write(struct.pack('<I',len(kept)))
    for tex,vv,ii in kept:meshes_.write(struct.pack('<III',tex,len(vv),len(ii)));meshes_.write(vv.tobytes());meshes_.write(ii.tobytes())
    mraw=meshes_.getvalue();mz=zlib.compress(mraw,6);name=f"{m['tile']}-{lod}.tmesh"
    (stream_dir/name).write_bytes(b'TMSHj001'+head.getvalue()+struct.pack('<II',len(mraw),len(mz))+mz)
    entry[lod]={'file':name,'bytes':(stream_dir/name).stat().st_size,'format':'TMSHj001'}
    continue
   body.write(struct.pack('<II',len(ims),len(kept)))
   for im in ims:body.write(struct.pack('<II',*im.size));body.write(im.tobytes())
   for tex,vv,ii in kept:body.write(struct.pack('<III',tex,len(vv),len(ii)));body.write(vv.tobytes());body.write(ii.tobytes())
   raw=body.getvalue();name=f"{m['tile']}-{lod}.tmesh";(stream_dir/name).write_bytes(b'TMSHv001'+struct.pack('<I',len(raw))+zlib.compress(raw,6))
   entry[lod]={'file':name,'bytes':(stream_dir/name).stat().st_size}
  streamIndex.append(entry)
 # Tower cranes where the photo mesh shows only a floating jib (city_cranes owns the model).
 from city_cranes import merge as crane_merge,meshes as crane_meshes
 (root/'modeled-buildings/crane-candidates.json').write_text(json.dumps([{k:(v.tolist() if hasattr(v,'tolist') else v) for k,v in j.items()} for j in _jibs]))
 from city_landmarks import crane_free_zone
 _cfz=crane_free_zone(root,(ox,oy,oz));cranes=[c for c in crane_merge(_jibs) if not _cfz.contains(shapely.Point(*c['mast']))]
 for _kind,_cv,_ci in crane_meshes(cranes,lambda x,y:h_vec(x+ox,y+oy)-oz):add(2|256|1024,14,_cv,_ci)   # lattice texture marks crane meshes
 craneReport=[{'mast':[round(float(c['mast'][0]),1),round(float(c['mast'][1]),1)],'jibZ':round(c['jibZ'],1),'reachM':round(c['reachM'],1)}for c in cranes]
 print('cranes',craneReport,flush=True)
 # Landmarks (city_landmarks): Muszla Koncertowa in Ogrod Saski — visual meshes + invisible 3 m collision wall.
 for _kind,_lv,_li in landmark_meshes(lambda x,y:h_vec(x+ox,y+oy)-oz):
  add(2|256|1024,{'membrane':15,'rib':13,'stone':13,'wood':17,'bench':16}[_kind],_lv,_li)
 for _kind,_lv,_li in portal_meshes(lambda x,y:h_vec(x+ox,y+oy)-oz):add(2|256|1024,{'concrete':13,'screen':18}[_kind],_lv,_li)
 from city_landmarks import monument_meshes
 for _kind,_lv,_li in monument_meshes(lambda x,y:h_vec(x+ox,y+oy)-oz):add(2|256,{'granite':13,'iron':20,'gilt':21,'bronze':22}[_kind],_lv,_li)   # visible and solid
 for _poly in [*landmark_collision(),portal_collision()]:   # one collision mesh per outline (engine span limit 300 m)
  _cv=[];_ci=[];_ring=list(_poly.exterior.coords)
  for (_ax,_ay),(_bx,_by) in zip(_ring[:-1],_ring[1:]):
   _ga=h(_ax+ox,_ay+oy);_gb=h(_bx+ox,_by+oy);_k=len(_cv)
   _cv+=[v(_ax+ox,_ay+oy,_ga-1),v(_bx+ox,_by+oy,_gb-1),v(_bx+ox,_by+oy,_gb+3),v(_ax+ox,_ay+oy,_ga+3)];_ci+=[_k,_k+1,_k+2,_k,_k+2,_k+3,_k,_k+2,_k+1,_k,_k+3,_k+2]
  add(2|256|512,1,_cv,_ci)
 # Engine index: "PL01STREAM 1" then one line per tile: name minx miny maxx maxy fileA fileC
 (out/'PL01-stream.idx').write_text('PL01STREAM 1\n'+''.join(f"{e['tile']} {e['bbox'][0]:.2f} {e['bbox'][1]:.2f} {e['bbox'][2]:.2f} {e['bbox'][3]:.2f} {e['A']['file']} {e['C']['file']}\n"for e in streamIndex))
 (out/'stream-manifest.json').write_text(json.dumps(streamIndex,indent=1))
 cityMeshReport={'tiles':[m['tile']for m in mesh_meta],'streamed':True,'geometryProcessing':'bounded facade-plane regularization, seam-pinned Taubin smoothing, exact road clipping','regularization':mesh_finish,'triangles':meshTriangles,'zoneAreaM2':round(mesh_zone.area)if mesh_zone is not None else 0,
  'meshZOffsetAppliedM':round(meshZOffset,3),'modeledBuildings':modeledReport,'photoLooseRemoved':looseReport,'cranes':craneReport,'streetTrianglesClipped':clippedStreetTriangles,'streetCutAreaM2':round(street_cut.area) if street_cut is not None else 0,'hiddenPhysicsTriangles':hiddenTriangles,'replacedLoD2Buildings':replacedBuildings,
  'streamBytes':{lod:sum(e[lod]['bytes']for e in streamIndex)for lod in('A','C')},
  'meshStreetMinusGroundM':{'samples':len(streetDiff),**({'p10':round(float(np.percentile(streetDiff,10)),3),'p50':round(float(np.median(streetDiff)),3),'p90':round(float(np.percentile(streetDiff,90)),3)}if len(streetDiff)else{})},
  'source':'Urząd Miasta Lublin, model mesh 3D 2022 (gis.lublin.eu/pobierzdane/mesh/2022)'}
 # Second collision layer for the city-mesh zone: every OSM building outline (ODbL) becomes
 # invisible 9 m walls, except edges a road centreline crosses (gate passages). Fills LoD2
 # gaps (skipped/invalid polygons) and doubles thin walls against high-speed tunnelling.
 import xml.etree.ElementTree as _ET,glob as _glob
 from pyproj import Transformer as _T
 _to=_T.from_crs(4326,2180,always_xy=True);_nodes={};_bways={}
 for _f in sorted(_glob.glob(str(root/'osm-tiles/*.osm'))):
  _r=_ET.parse(_f).getroot()
  for _n in _r.findall('node'):_nodes[_n.get('id')]=(float(_n.get('lon')),float(_n.get('lat')))
  for _w in _r.findall('way'):
   if any(_t.get('k')=='building' for _t in _w.findall('tag')):_bways[_w.get('id')]=[_nd.get('ref')for _nd in _w.findall('nd')]
 osmWallBuildings=0;osmWallEdges=0;osmPassageEdges=0
 # Ogród Saski fence: OSM leisure=park outline; gaps wherever any OSM highway (incl. park
 # footways) crosses it. Visible posts + rails (visual only) and an invisible 3 m wall.
 _hw=[];_park=[]
 for _f in sorted(_glob.glob(str(root/'osm-tiles/*.osm'))):
  for _w in _ET.parse(_f).getroot().findall('way'):
   _tg={_t.get('k'):_t.get('v')for _t in _w.findall('tag')};_rf=[_nd.get('ref')for _nd in _w.findall('nd')]
   if 'highway' in _tg:_hw.append(_rf)
   if _tg.get('leisure')=='park' and 'Saski' in _tg.get('name',''):_park.append(_rf)
 def _xy(refs):return[(_to.transform(*_nodes[r])[0]-ox,_to.transform(*_nodes[r])[1]-oy)for r in refs if r in _nodes]
 _hw_tree=STRtree([_Line(_xy(r))for r in _hw if len(_xy(r))>1])
 fencePosts=0;fenceGaps=0
 for _rf in _park:
  ring=_xy(_rf);pv=[];pi=[];cv=[];ci=[]
  for (ax_,ay_),(bx_,by_) in zip(ring,ring[1:]):
   L_=math.dist((ax_,ay_),(bx_,by_));n_=max(1,int(L_/2.5))
   for k in range(n_):
    e0,n0=ax_+(bx_-ax_)*k/n_,ay_+(by_-ay_)*k/n_;e1,n1=ax_+(bx_-ax_)*(k+1)/n_,ay_+(by_-ay_)*(k+1)/n_
    if len(_hw_tree.query(_Line([(e0,n0),(e1,n1)]).buffer(2.0),predicate='intersects')):fenceGaps+=1;continue
    g0,g1=h(e0+ox,n0+oy),h(e1+ox,n1+oy)
    for z0,z1 in((g0+.25,g0+.35),(g0+1.45,g0+1.55)):   # two rails
     b_=len(pv);pv+=[v(e0+ox,n0+oy,z0,0,1),v(e1+ox,n1+oy,z0-g0+g1,1,1),v(e1+ox,n1+oy,z1-g0+g1,1,0),v(e0+ox,n0+oy,z1,0,0)];pi+=[b_,b_+1,b_+2,b_,b_+2,b_+3,b_,b_+2,b_+1,b_,b_+3,b_+2]
    tx,ty=(e1-e0),(n1-n0);ln=math.hypot(tx,ty) or 1;tx,ty=tx/ln*.05,ty/ln*.05;nx_,ny_=-ty,tx   # 10 cm post
    for (sx,sy),(qx,qy) in(((-tx-nx_,-ty-ny_),(tx-nx_,ty-ny_)),((tx-nx_,ty-ny_),(tx+nx_,ty+ny_)),((tx+nx_,ty+ny_),(-tx+nx_,-ty+ny_)),((-tx+nx_,-ty+ny_),(-tx-nx_,-ty-ny_))):
     b_=len(pv);pv+=[v(e0+sx+ox,n0+sy+oy,g0,0,1),v(e0+qx+ox,n0+qy+oy,g0,1,1),v(e0+qx+ox,n0+qy+oy,g0+1.7,1,0),v(e0+sx+ox,n0+sy+oy,g0+1.7,0,0)];pi+=[b_,b_+1,b_+2,b_,b_+2,b_+3]
    fencePosts+=1
    b_=len(cv);cv+=[v(e0+ox,n0+oy,g0-1),v(e1+ox,n1+oy,g1-1),v(e1+ox,n1+oy,g1+3),v(e0+ox,n0+oy,g0+3)];ci+=[b_,b_+1,b_+2,b_,b_+2,b_+3,b_,b_+2,b_+1,b_,b_+3,b_+2]
    if len(pv)>60000:add(2|256|1024,4,pv,pi,(40,40,40,255));pv=[];pi=[]
    if len(cv)>60000:add(2|256|512,1,cv,ci);cv=[];ci=[]
  if pv:add(2|256|1024,4,pv,pi,(40,40,40,255))
  if cv:add(2|256|512,1,cv,ci)
 for _refs in _bways.values():
  _ll=[_nodes[_r]for _r in _refs if _r in _nodes]
  if len(_ll)<4:continue
  _xy=np.array([_to.transform(*a)for a in _ll])
  _loc=_xy-[ox,oy]
  if not in_zone([_loc.mean(axis=0)])[0]:continue
  quad=[];qi=[]
  for (_ax,_ay),(_bx,_by) in zip(_xy[:-1],_xy[1:]):
   if math.dist((_ax,_ay),(_bx,_by))<.3:continue
   _e=_Line([(_ax-ox,_ay-oy),(_bx-ox,_by-oy)])
   if _e.intersects(deep_cross):osmPassageEdges+=1;continue
   g0,g1=h(_ax,_ay),h(_bx,_by);b_=len(quad)
   quad+= [v(_ax,_ay,g0-1),v(_bx,_by,g1-1),v(_bx,_by,g1+9),v(_ax,_ay,g0+9)]
   qi+=[b_,b_+1,b_+2,b_,b_+2,b_+3,b_,b_+2,b_+1,b_,b_+3,b_+2];osmWallEdges+=1
  if quad:add(2|256|512,1,quad,qi);osmWallBuildings+=1
 # Map boundary: invisible 7 m walls 15 m inside the ROI, in <=200 m segments (the
 # legacy wall collector ignores obstacles longer than 300 m). Both windings: solid from either side.
 boundarySegments=0;inset=15
 corners=[(x0+inset,y0+inset),(x1-inset,y0+inset),(x1-inset,y1-inset),(x0+inset,y1-inset)]
 for (ax,ay),(bx,by) in zip(corners,corners[1:]+corners[:1]):
  n_=max(1,math.ceil(math.dist((ax,ay),(bx,by))/200))
  for k in range(n_):
   e0,n0=ax+(bx-ax)*k/n_,ay+(by-ay)*k/n_;e1,n1=ax+(bx-ax)*(k+1)/n_,ay+(by-ay)*(k+1)/n_;g0,g1=h(e0,n0),h(e1,n1)
   quad=[v(e0,n0,g0-1),v(e1,n1,g1-1),v(e1,n1,g1+7),v(e0,n0,g0+7)]
   add(2|256|512,1,quad,[0,1,2,0,2,3,0,2,1,0,3,2]);boundarySegments+=1
 # Distant closed sky sphere, rendered by the native sky pass.
 verts=[];idx=[]
 for j in range(13):
  lat=-math.pi/2+j*math.pi/12
  for i in range(33):
   angle=i*2*math.pi/32;verts.append([12000*math.cos(lat)*math.cos(angle),12000*math.cos(lat)*math.sin(angle),12000*math.sin(lat),i/32,1-j/12])
 for j in range(12):
  for i in range(32):a=j*33+i;idx.extend([a,a+1,a+33,a+1,a+34,a+33])
 add(3,5,verts,idx)
# Explicit authored event files use the existing generic path/grid parser.
def chunk(id,b):return struct.pack('<II',id,len(b))+b
from city_bridges import surface_sampler
_profile=root/'bridge-audit/road-profiles.json'
from city_package import TerrainSurface
_race_base=TerrainSurface(G,x0,y1)
_race_ground=lambda x,y:_race_base.sample(x+ox,y+oy)-oz # Base street layer; event 7002 follows the upper Zamkowa way, 7003 passes underneath.
_race_upper=surface_sampler(_race_ground,json.loads(_profile.read_text()))if _profile.exists()else _race_ground
def race_height(e,n):return float((_race_upper if eid==7002 else _race_ground)(e-ox,n-oy))+oz
EVENTS=[int(p_.stem.split('-')[1])for p_ in sorted(root.glob('route-7*.json'))]
markers=bytearray(b'\x11'*8);eventReport={};outlineRecords=[];eventNav={}
for eid in EVENTS:
 route=json.loads((root/f'route-{eid}.json').read_text());expected=hashlib.sha256(json.dumps(route['course'],separators=(',',':')).encode()).hexdigest()
 if route.get('physicalFit',{}).get('courseSHA256')!=expected:raise ValueError(f'{eid}: run fit-routes.py on the current course before building events')
 course=[[p[0]-ox,p[1]-oy]for p in route['course']];outline=[[p[0]-ox,p[1]-oy]for p in route['outline']]
 b=bytearray(272);struct.pack_into('<HBBBB',b,0,eid,len(outline),1,0,0)
 for i,p in enumerate(outline):struct.pack_into('<ff',b,8+i*8,*p)
 nav=bytearray();distance=0
 for i,p in enumerate(course):
  if i:distance+=math.dist(p,course[i-1])
  nav+=struct.pack('<ffIHHHHf',*p,0,i-1 if i else 65535,i+1 if i+1<len(course)else 65535,65535,0,distance)
 outlineRecords.append(bytes(b));eventNav[eid]=bytes(nav)
 # Start grid: GRID_SLOTS (2 per row, rows 7 m apart) behind the start line on the course's
 # final approach. The engine requires straight rows on ONE grid heading, so rows step back
 # along the front row's heading (not along the curving course) and must stay inside the
 # 8 m race corridor. 10 slots = the largest shared room (humans + bots).
 GRID_SLOTS=10
 first=course[0];cl=LineString(course);clen=cl.length;s0=clen-8
 pa=np.array(cl.interpolate(s0-1.5).coords[0]);pb=np.array(cl.interpolate(s0+1.5).coords[0])
 heading=math.atan2(pb[1]-pa[1],pb[0]-pa[0]);front=np.array(cl.interpolate(s0).coords[0]);fwd=np.array([math.cos(heading),math.sin(heading)])
 for i in range(GRID_SLOTS):
  side=(-1 if i%2 else 1)*1.8;c0=front-fwd*(i//2)*7
  e=c0[0]-math.sin(heading)*side;n=c0[1]+math.cos(heading)*side
  if cl.distance(shapely.Point(e,n))>8.0-1.6:raise ValueError(f'{eid}: grid slot {i} leaves the race corridor; straighten the final approach')
  record=bytearray(48);struct.pack_into('<IIfff',record,8,0x8e55c895,i,e,n,race_height(e+ox,n+oy)-oz);struct.pack_into('<H',record,32,round(heading*65536/(2*math.pi))%65536);struct.pack_into('<I',record,36,eid);markers+=record
 # One closed polygon owns both visible boards and physical walls. Never omit
 # corners, start/finish or building overlaps: those omissions were escape holes.
 line=LineString(course);L=line.length
 band=line.buffer(8.0,quad_segs=8,join_style='round')
 if band.geom_type!='Polygon' or not band.is_valid or not band.interiors:
  raise ValueError(f'{eid}: course must form a closed race corridor')
 vis={};col={};nseg=0;barrier_length=0
 rings=[band.exterior,*band.interiors]
 for ring in rings:
  coords=list(ring.coords)
  for aa,bb in zip(coords,coords[1:]):
   count=max(1,math.ceil(math.dist(aa,bb)/3))
   for j in range(count):
    e0,n0=np.array(aa)+(np.array(bb)-aa)*j/count
    e1,n1=np.array(aa)+(np.array(bb)-aa)*(j+1)/count
    g0,g1=race_height(e0+ox,n0+oy),race_height(e1+ox,n1+oy);cell=(int(e0//40),int(n0//40))
    V,I=vis.setdefault(cell,([],[]));bs=len(V);seg=math.dist((e0,n0),(e1,n1));barrier_length+=seg
    V+=[v(e0+ox,n0+oy,g0,0,1),v(e1+ox,n1+oy,g1,seg/4,1),v(e1+ox,n1+oy,g1+1.3,seg/4,0),v(e0+ox,n0+oy,g0+1.3,0,0)]
    I+=[bs,bs+1,bs+2,bs,bs+2,bs+3,bs,bs+2,bs+1,bs,bs+3,bs+2]
    V,I=col.setdefault(cell,([],[]));bs=len(V)
    V+=[v(e0+ox,n0+oy,min(g0,h(e0+ox,n0+oy))-2),v(e1+ox,n1+oy,min(g1,h(e1+ox,n1+oy))-2),v(e1+ox,n1+oy,g1+8),v(e0+ox,n0+oy,g0+8)]
    I+=[bs,bs+1,bs+2,bs,bs+2,bs+3,bs,bs+2,bs+1,bs,bs+3,bs+2];nseg+=1
 # Direction chevrons painted on the race road every 20 m (geometry only: no alpha needed)
 chev={};nchev=0
 for d_ in np.arange(10,L-5,20.0):
  c_=np.array(line.interpolate(d_).coords[0]);t=np.array(line.interpolate(d_+1.5).coords[0])-np.array(line.interpolate(d_-1.5).coords[0])
  if np.linalg.norm(t)<1e-6:continue
  t=t/np.linalg.norm(t);nrm=np.array([-t[1],t[0]]);tip=c_+t*1.0;g=race_height(c_[0]+ox,c_[1]+oy)+.14;cell=(int(c_[0]//80),int(c_[1]//80))
  V,I=chev.setdefault(cell,([],[]))
  for sd in(-1,1):
   back=c_-t*1.0+nrm*sd*1.7;q=[tip,back,back-t*.55,tip-t*.55];bs=len(V)
   V+=[v(x+ox,y+oy,g,.5,.5)for x,y in q];I+=[bs,bs+1,bs+2,bs,bs+2,bs+3,bs,bs+2,bs+1,bs,bs+3,bs+2]
  nchev+=1
 for V,I in chev.values():add(2|256|1024|2048|(eid<<16),11,V,I)
 for V,I in vis.values():add(2|256|1024|2048|(eid<<16),10,V,I)
 for V,I in col.values():add(2|256|512|2048|(eid<<16),1,V,I)
 eventReport[eid]={'name':route['name'],'lengthM':round(route['lengthM']),'barrierSegments':nseg,'barrierM':round(barrier_length,2),'closedBoundaryRings':len(rings),'corridorHalfWidthM':8,'wallHeightM':8,'lowerGroundSealed':True,'sideStreetClosures':'continuous boundary','chevrons':nchev}
# world_load_events reads event outlines from the FIRST Paths file only (retail keeps all
# of a region's records together), so every outline goes into the lowest id's file; each
# file keeps its own course nodes.
for old in out.glob('Paths*.bin'):old.unlink()
for k,eid in enumerate(EVENTS):
 recs=b''.join(outlineRecords) if k==0 else outlineRecords[k]
 (out/f'Paths{eid}.bin').write_bytes(chunk(0x3414c,recs)+chunk(0x34148,eventNav[eid]))
(out/'TrackPosMarkersAll.bin').write_bytes(chunk(0x34146,markers))
# Serialise the package last: barriers and fences above add meshes.
body=io.BytesIO();body.write(struct.pack('<III',len(textures),len(meshes),photoCount))
for im in textures:body.write(struct.pack('<II',*im.size));body.write(im.tobytes())
for cat,tex,verts,idx,col in meshes:body.write(struct.pack('<IIII',cat,tex,len(verts),len(idx)));body.write(verts.tobytes());body.write(idx.tobytes());body.write(col.tobytes())
raw=body.getvalue();package=b'TOWNv002'+struct.pack('<I',len(raw))+zlib.compress(raw,6);(out/'PL01.town').write_bytes(package)
if '--events-only' in sys.argv:
 report=previous_report.copy();report.update(events=eventReport,meshes=len(meshes),triangles=sum(len(m[3])//3 for m in meshes),packageBytes=len(package),unpackedBytes=len(raw))
else:
 report={'fence':{'parks':len(_park),'posts':fencePosts,'gaps':fenceGaps},'events':eventReport,'passageClearAreaM2':passageClearAreaM2,'osmCollisionWalls':{'buildings':osmWallBuildings,'edges':osmWallEdges,'passageEdgesOpen':osmPassageEdges},'mapBoundary':{'insetM':inset,'segments':boundarySegments,'heightM':7,'visible':False},'cityMesh':cityMeshReport,'streetSigns':{'plates':signCount,'names':len(sign_names),'junctionPoints':len(junction_names),'source':'OSM name (ODbL)',"atlas":[SIGN_ATLAS_W,atlas_h]},'ground':groundReport,'meshes':len(meshes),'triangles':sum(len(m[3])//3 for m in meshes),'packageBytes':len(package),'unpackedBytes':len(raw),'wallTriangles':wallTriangles,'roofTriangles':roofTriangles,'skippedDegenerateOrInvalidPolygons':skipped,'bridges':bridges,'routeLengthM':route['lengthM'],'status':'isolated native prototype, not production','orthoSource':'GUGiK WMS HighResolution Raster only','orthoCacheMPerPixel':.1,'runtimeOrthoMPerPixel':.5,'orthoAtlasTiles':len(atlas),'attribution':'Źródło: GUGiK, geoportal.gov.pl','sources':['GUGiK NMT1m2017, PL-KRON86-NH','GUGiK LoD2buildings2017 CC BY4.0','GUGiK WCS ortho','©OpenStreetMapcontributors ODbL'],'textureSettings':{'gutterPx':16,'wrap':'clamp_to_edge for ortho atlases','anisotropy':16,'mips':'generated at native upload after padding'},'remainingTextureWork':['light ortho blend at road shoulders','epoch sharpness selection must feed mosaic before final build'],'limits':['facade textures are authored substitutes, not photographic elevations','bridge elevations interpolated, need road-level validation','source city/road dates differ']}
(out/'build-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print(json.dumps({k:v for k,v in report.items()if k!='bridges'},indent=2,ensure_ascii=False))
