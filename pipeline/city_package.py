"""Parsed facts for the generated TOWNv002 package and its original 10 m terrain.
Views retain the decoded buffer; consumers must not reinterpret atlas-clipped vertices as grid nodes.
"""
from pathlib import Path
from typing import NamedTuple
from dataclasses import dataclass
import hashlib,struct,zlib
import numpy as np
class MeshRecord(NamedTuple):
 category:int
 texture:int
 vertices:np.ndarray
 indices:np.ndarray
 colours:memoryview|bytes
 blob:memoryview|bytes
class TownPackage(NamedTuple):
 texture_count:int
 ortho_count:int
 texture_bytes:memoryview
 meshes:list[MeshRecord]
 sha256:str
class CityFormatError(ValueError):pass
def read_town(path):
 path=Path(path);raw=path.read_bytes()
 if len(raw)<16 or raw[:8]!=b'TOWNv002':raise CityFormatError(f'{path}: expected TOWNv002')
 size=struct.unpack_from('<I',raw,8)[0]
 if not 12<=size<=1024**3:raise CityFormatError(f'{path}: invalid unpacked size')
 decoder=zlib.decompressobj();body=decoder.decompress(raw[12:],size+1)
 if len(body)!=size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:raise CityFormatError(f'{path}: compressed size/header mismatch')
 data=memoryview(body);o=0
 def take(n):
  nonlocal o
  if n<0 or o+n>len(data):raise CityFormatError(f'{path}: truncated record at byte {o}')
  v=data[o:o+n];o+=n;return v
 nt,nm,no=struct.unpack('<III',take(12))
 if not(1<=no<=nt<=48 and 1<=nm<=60000):raise CityFormatError(f'{path}: invalid texture/mesh counts')
 start=o
 for _ in range(nt):
  w,h=struct.unpack('<II',take(8))
  if not(1<=w<=4096 and 1<=h<=4096):raise CityFormatError(f'{path}: invalid texture dimensions')
  take(w*h*3)
 textures=data[start:o];meshes=[]
 for _ in range(nm):
  start=o;cat,mat,nv,ni=struct.unpack('<IIII',take(16))
  if not(cat&255<=3 and mat<nt and 3<=nv<=65535 and 3<=ni<=196605 and ni%3==0):raise CityFormatError(f'{path}: invalid mesh header at {start}')
  v=np.frombuffer(take(nv*20),'<f4').reshape(nv,5);idx=np.frombuffer(take(ni*2),'<u2');colours=take(nv*4)
  if not np.isfinite(v).all()or idx.max()>=nv:raise CityFormatError(f'{path}: invalid vertex/index data at {start}')
  meshes.append(MeshRecord(cat,mat,v,idx,colours,data[start:o]))
 if o!=len(data):raise CityFormatError(f'{path}: trailing unparsed data')
 return TownPackage(nt,no,textures,meshes,hashlib.sha256(raw).hexdigest())
@dataclass(frozen=True)
class TerrainSurface:
 grid:np.ndarray
 west:float
 north:float
 def sample(self,x,y):
  x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float);G=self.grid;r=np.clip((self.north-y)/10,0,G.shape[0]-1.000001);c=np.clip((x-self.west)/10,0,G.shape[1]-1.000001);i=r.astype(int);j=c.astype(int);u=c-j;f=r-i;a,b,cc,d=G[i,j],G[i,j+1],G[i+1,j],G[i+1,j+1]
  return np.where(u+f<=1,a+(b-a)*u+(cc-a)*f,d+(cc-d)*(1-u)+(b-d)*(1-f))
def full_terrain(package):
 terrain=[m for m in package.meshes if m.category&255==1 and not m.category&256]
 if not terrain:raise CityFormatError('No original terrain in the baseline')
 P=np.concatenate([m.vertices[:,:3]for m in terrain]).astype(float);west,north=P[:,0].min(),P[:,1].max();east,south=P[:,0].max(),P[:,1].min();area=0
 for m in terrain:
  t=m.vertices[m.indices.reshape(-1,3),:2].astype(float);a=t[:,1]-t[:,0];b=t[:,2]-t[:,0];area+=np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0]).sum()/2
 if abs(area-(east-west)*(north-south))>2:raise CityFormatError('Use an original full-terrain baseline, not a package with road/ground partitioning')
 on_grid=(np.abs((P[:,0]-west)/10-np.rint((P[:,0]-west)/10))<1e-5)&(np.abs((north-P[:,1])/10-np.rint((north-P[:,1])/10))<1e-5);P=P[on_grid];cx=np.rint((P[:,0]-west)/10).astype(int);cy=np.rint((north-P[:,1])/10).astype(int);shape=(cy.max()+1,cx.max()+1);low=np.full(shape,np.inf);high=np.full(shape,-np.inf);np.minimum.at(low,(cy,cx),P[:,2]);np.maximum.at(high,(cy,cx),P[:,2])
 if not np.isfinite(low).all()or np.max(high-low)>.0002:raise CityFormatError('Missing or contradictory original 10 m terrain samples')
 return TerrainSurface(low,west,north)
