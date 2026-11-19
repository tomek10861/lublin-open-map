"""Close bounded missing gable faces between observed LoD2 walls and roof edges.
Only draw geometry is added; collision and surveyed source vertices remain unchanged.
"""
import numpy as np

def gable_faces(wall,roofs):
 triangles=wall[0][wall[1].reshape(-1,3),:3].astype(float);out=[]
 xy=triangles[:,:,:2];delta=xy-np.roll(xy,1,axis=1);lengths=np.linalg.norm(delta,axis=2);k=lengths.argmax(1);rows=np.arange(len(triangles));origins=xy[rows,k];direction=xy[rows,(k-1)%3]-origins;length=lengths[rows,k];axis=direction/np.maximum(length[:,None],1e-9);normal=np.column_stack((-axis[:,1],axis[:,0]));stations=np.sum((xy-origins[:,None,:])*axis[:,None,:],axis=2)
 def top(point):
  station=np.sum((point-origins)*axis,axis=1);distance=np.abs(np.sum((point-origins)*normal,axis=1));candidates=np.flatnonzero((length>.1)&(distance<=.03)&(station>=stations.min(1)-.01)&(station<=stations.max(1)+.01));heights=[]
  for i in candidates:
   tri=triangles[i];s=station[i];t=stations[i]
   for j in range(3):
    q=(j+1)%3;ds=t[q]-t[j]
    if abs(ds)<1e-8:
     if abs(s-t[j])<.01:heights.extend([tri[j,2],tri[q,2]])
    elif min(t[j],t[q])-.01<=s<=max(t[j],t[q])+.01:heights.append(tri[j,2]+(tri[q,2]-tri[j,2])*(s-t[j])/ds)
  return max(heights)if heights else None
 vertices=np.concatenate([v[:,:3]for v,idx in roofs]);quant=np.round(vertices*1000).astype(np.int64);_,inverse=np.unique(quant,axis=0,return_inverse=True);inverse=inverse.reshape(-1);edges=[];positions={};offset=0
 for v,idx in roofs:
  tri=inverse[offset+idx.reshape(-1,3).astype(int)]
  for a,b in [(0,1),(1,2),(2,0)]:edges.extend(np.sort(tri[:,[a,b]],axis=1))
  for i,node in enumerate(inverse[offset:offset+len(v)]):positions[int(node)]=v[i,:3].astype(float)
  offset+=len(v)
 unique,counts=np.unique(np.array(edges),axis=0,return_counts=True)
 for ai,bi in unique[counts==1]:
  a,b=positions[int(ai)],positions[int(bi)];length=np.linalg.norm(b[:2]-a[:2])
  if length<.2:continue
  za,zb,mid=top(a[:2]),top(b[:2]),top((a[:2]+b[:2])/2)
  if za is None or zb is None or mid is None:continue
  gaps=np.array([a[2]-za,b[2]-zb])
  if gaps.max()<.15 or gaps.min()<-.15 or gaps.max()>12:continue
  # The whole roof boundary belongs to an existing facade plane, not an overhang.
  bottom_a=a.copy();bottom_b=b.copy();bottom_a[2]=min(a[2],za);bottom_b[2]=min(b[2],zb);quad=np.array([a,b,bottom_b,bottom_a]);horizontal=0 if abs(b[0]-a[0])>=abs(b[1]-a[1])else 1;uv=np.column_stack(((quad[:,horizontal]+[746600,381750][horizontal])/12,(quad[:,2]+180)/12));v=np.column_stack((quad,uv))
  for tri in [[0,1,2],[0,2,3]]:
   if np.linalg.norm(np.cross(v[tri[1],:3]-v[tri[0],:3],v[tri[2],:3]-v[tri[0],:3]))>1e-5:out.extend(v[tri]);out.extend(v[tri[::-1]])
 return np.array(out,dtype='<f4').reshape(-1,5)

def gable_chunks(package):
 meshes=package.meshes
 for i,m in enumerate(meshes):
  if m.category!=257 or m.texture<package.ortho_count:continue
  roofs=[]
  for j in range(i+1,len(meshes)):
   r=meshes[j]
   if r.category!=2 or r.texture>=package.ortho_count:break
   roofs.append((r.vertices,r.indices))
  if roofs:
   vertices=gable_faces((m.vertices,m.indices),roofs)
   if len(vertices):yield m.texture,vertices
