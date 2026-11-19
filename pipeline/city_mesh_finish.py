"""Bounded, seam-preserving regularization of the source photographic city mesh."""
import json,collections
import numpy as np
import shapely
from shapely.geometry import Polygon

def weld_inverse(positions,scale):
 q=np.rint(positions*scale).astype(np.int64);q-=q.min(0);bits=[max(1,int(v).bit_length())for v in q.max(0)]
 if sum(bits)>63:raise ValueError('Tile weld coordinates exceed the bounded 64-bit lattice')
 q=q.astype(np.uint64);keys=q[:,0]|(q[:,1]<<bits[0])|(q[:,2]<<(bits[0]+bits[1]));keys,inverse=np.unique(keys,return_inverse=True);return inverse.reshape(-1),len(keys)

def wall_planes(root):
 ox,oy,oz=json.loads((root/'roi.json').read_text())['originEPSG2180'];planes=[]
 for building in json.loads((root/'lublin-buildings-clipped.json').read_text())['buildings']:
  for surface in building['surfaces']:
   if surface['surface']!='WallSurface' or len(surface['coordinates'])<3:continue
   q=np.array(surface['coordinates'],float)-[ox,oy,oz];normal=np.zeros(3)
   for k in range(1,len(q)-1):
    normal=np.cross(q[k]-q[0],q[k+1]-q[0])
    if np.linalg.norm(normal)>1e-4:break
   length=np.linalg.norm(normal)
   if length<1e-4 or abs(normal[2])/length>.2:continue
   n=normal[:2]/np.linalg.norm(normal[:2]);t=np.array([-n[1],n[0]]);projection=q[:,:2]@t;a=q[projection.argmin(),:2];b=q[projection.argmax(),:2]
   if np.linalg.norm(b-a)>2 and q[:,2].max()-q[:,2].min()>3:planes.append((a,b,n,float(q[:,2].min()),float(q[:,2].max())))
 return planes

def regularize(chunks,meta,planes,iterations=5,max_shift=.4):
 original=np.concatenate([v[:,:3]for _,v,_ in chunks]);inverse,count=weld_inverse(original,1000)
 U=np.zeros((count,3));np.add.at(U,inverse,original);U/=np.bincount(inverse,minlength=count)[:,None];source=U.copy();offsets=np.cumsum([0]+[len(v)for _,v,_ in chunks]);tri=np.concatenate([inverse[offsets[k]+idx.reshape(-1,3).astype(int)]for k,(_,v,idx)in enumerate(chunks)])
 vectors=np.cross(U[tri[:,1]]-U[tri[:,0]],U[tri[:,2]]-U[tri[:,0]]);normals=np.zeros_like(U)
 for k in range(3):np.add.at(normals,tri[:,k],vectors)
 normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-9)
 cells=collections.defaultdict(list)
 for i,c in enumerate(map(tuple,np.floor(U[:,:2]/2).astype(int))):cells[c].append(i)
 boundary=~shapely.contains_xy(Polygon(meta['footprintLocal']).buffer(-1.5),source[:,0],source[:,1])
 best=np.full(count,np.inf);shift=np.zeros((count,2));flat=np.zeros(count,bool);snapped=0
 xmin,ymin=U[:,:2].min(0);xmax,ymax=U[:,:2].max(0)
 for a,b,n,z0,z1 in planes:
  if max(a[0],b[0])+1.2<xmin or min(a[0],b[0])-1.2>xmax or max(a[1],b[1])+1.2<ymin or min(a[1],b[1])-1.2>ymax:continue
  low=np.floor((np.minimum(a,b)-1.2)/2).astype(int);high=np.floor((np.maximum(a,b)+1.2)/2).astype(int)
  idx=np.array([i for x in range(low[0],high[0]+1)for y in range(low[1],high[1]+1)for i in cells.get((x,y),())],dtype=int)
  if len(idx)<24:continue
  P=U[idx];t=b-a;s=((P[:,:2]-a)@t)/(t@t);d=(P[:,:2]-a)@n;vertical=np.abs(normals[idx,:2]@n)>.7
  fit=(s>.03)&(s<.97)&(P[:,2]>z0+2)&(P[:,2]<z1+.5)&(np.abs(d)<.8)&vertical
  if fit.sum()<24:continue
  plane=float(np.median(d[fit]));residual=d-plane;weight=np.clip((.8-np.abs(residual))/.55,0,1);take=(s>0)&(s<1)&(P[:,2]>z0-.3)&(P[:,2]<z1+.3)&vertical&(weight>0)&(np.abs(residual)<best[idx])
  best[idx[take]]=np.abs(residual[take]);shift[idx[take]]=-(residual[take]*weight[take])[:,None]*n;flat[idx[take]]=weight[take]>.999
 shift[boundary]=0;magnitude=np.linalg.norm(shift,axis=1,keepdims=True);shift*=np.minimum(1,max_shift/np.maximum(magnitude,1e-9));U[:,:2]+=shift;snapped=int((magnitude[:,0]>.001).sum())
 pinned=flat|boundary
 edges=np.concatenate((tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]));edges=np.concatenate((edges,edges[:,::-1]));degree=np.bincount(edges[:,0],minlength=count);pinned|=degree==0
 for k in range(iterations*2):
  total=np.zeros_like(U);np.add.at(total,edges[:,0],U[edges[:,1]]);delta=total/np.maximum(degree[:,None],1)-U;U[~pinned]+=(.5 if k%2==0 else -.53)*delta[~pinned]
  displacement=U-source;length=np.linalg.norm(displacement,axis=1,keepdims=True);U=source+displacement*np.minimum(1,max_shift/np.maximum(length,1e-9))
 changed=U[inverse];changed[boundary[inverse]]=original[boundary[inverse]];distance=np.linalg.norm(changed-original,axis=1)
 for k,(_,v,_)in enumerate(chunks):v[:,:3]=changed[offsets[k]:offsets[k+1]]
 return {'vertices':len(original),'planeRegularized':snapped,'meanDisplacementM':float(distance.mean()),'maxDisplacementM':float(distance.max()),'tileBoundaryPinned':True,'iterations':iterations}

def fill_facade_holes(chunks,meta,ground):
 """Close only small, planar, interior facade loops with a coherent source UV map.
 Tile seams, ground-level passages, nonplanar gaps and ambiguous texture seams remain untouched.
 """
 from shapely import constrained_delaunay_triangles
 original=np.concatenate([v for _,v,_ in chunks]);inverse,node_count=weld_inverse(original[:,:3],100);xyz=np.zeros((node_count,3));np.add.at(xyz,inverse,original[:,:3]);xyz/=np.bincount(inverse)[:,None];offset=0;edges=[];owners=[];edge_directions=[];edge_normals=[];examples={}
 for material,v,idx in chunks:
  tri=inverse[offset+idx.reshape(-1,3).astype(int)]
  normal=np.cross(xyz[tri[:,1]]-xyz[tri[:,0]],xyz[tri[:,2]]-xyz[tri[:,0]])
  for a,b in [(0,1),(1,2),(2,0)]:edges.append(np.sort(tri[:,[a,b]],axis=1));owners.append(np.full(len(tri),material,dtype=np.int32));edge_directions.append(tri[:,[a,b]]);edge_normals.append(normal)
  offset+=len(v)
 edges=np.concatenate(edges).astype(np.uint64);owners=np.concatenate(owners);edge_keys=edges[:,0]*node_count+edges[:,1];keys,indices,counts=np.unique(edge_keys,return_index=True,return_counts=True);boundary=np.column_stack((keys[counts==1]//node_count,keys[counts==1]%node_count)).astype(np.int64);materials=owners[indices[counts==1]];adj=collections.defaultdict(list);edge_material={};edge_direction={};edge_normal={};directions=np.concatenate(edge_directions)[indices[counts==1]];normals=np.concatenate(edge_normals)[indices[counts==1]]
 for (a,b),material,direction,normal in zip(boundary,materials,directions,normals):
  key=(int(a),int(b));adj[int(a)].append(int(b));adj[int(b)].append(int(a));edge_material[key]=int(material);edge_direction[key]=tuple(map(int,direction));edge_normal[key]=normal
 boundary_nodes=np.unique(boundary);offset=0
 for material,v,idx in chunks:
  nodes=inverse[offset:offset+len(v)];take=np.flatnonzero(np.isin(nodes,boundary_nodes))
  for i in take:examples.setdefault((int(nodes[i]),material),v[i,3:5])
  offset+=len(v)
 visited=set();added=[];filled=0;footprint=Polygon(meta['footprintLocal']).buffer(-1.5)
 for start in adj:
  if start in visited or len(adj[start])!=2:continue
  loop=[];previous=-1;at=start
  while at not in visited and len(adj[at])==2 and len(loop)<500:
   visited.add(at);loop.append(at);following=adj[at][0]if adj[at][0]!=previous else adj[at][1];previous,at=at,following
  if at!=start or len(loop)<4 or len(loop)>=500:continue
  if tuple(loop[:2])!=edge_direction[tuple(sorted(loop[:2]))]:loop=[loop[0],*loop[:0:-1]]
  p=xyz[loop];centre=p.mean(0);area_normal=np.cross(p-centre,np.roll(p,-1,axis=0)-centre).sum(0);source_normal=sum((edge_normal[tuple(sorted((a,b)))]for a,b in zip(loop,loop[1:]+loop[:1])),np.zeros(3))
  if area_normal@source_normal>=0:continue # Outer shell boundaries are not holes.
  if not shapely.contains_xy(footprint,p[:,0],p[:,1]).all()or (p[:,2]-ground(p[:,0],p[:,1])).min()<2:continue
  _,_,axes=np.linalg.svd(p-centre,full_matrices=False);normal=axes[2]
  if abs(normal[2])>.4 or np.abs((p-centre)@normal).max()>.25:continue
  plane=(p-centre)@axes[:2].T;polygon=Polygon(plane)
  if not polygon.is_valid or not(.2<polygon.area<80):continue
  mats=[edge_material[tuple(sorted((a,b)))]for a,b in zip(loop,loop[1:]+loop[:1])];material,majority=collections.Counter(mats).most_common(1)[0]
  if majority<len(mats)*.8 or not all((node,material)in examples for node in loop):continue
  uv=np.array([examples[node,material]for node in loop]);design=np.column_stack((plane,np.ones(len(plane))));mapping=np.linalg.lstsq(design,uv,rcond=None)[0]
  if np.max(np.linalg.norm(design@mapping-uv,axis=1))>.015:continue
  vertices=[]
  for triangle in constrained_delaunay_triangles(polygon).geoms:
   q=np.array(triangle.exterior.coords)[:3];pos=centre+q@axes[:2];tex=np.column_stack((q,np.ones(3)))@mapping;vertices.extend(np.column_stack((pos,tex)))
  if vertices:
   v=np.array(vertices,dtype='<f4');idx=np.arange(len(v),dtype='<u2').reshape(-1,3);added.append((material,v,np.concatenate((idx,idx[:,::-1])).reshape(-1)));filled+=1
 chunks.extend(added);return {'filledPlanarFacadeHoles':filled,'preservedTileSeamsAndGroundPassages':True,'maximumAreaM2':80,'maximumPlanarityErrorM':.25,'maximumUVResidual':.015}

def finish_chunks(chunks,meta,planes,buildings,street,passages,ground,building_shell):
 from city_road_clearance import clip
 report=regularize(chunks,meta,planes);report.update(fill_facade_holes(chunks,meta,ground));keep=buildings;result=[];removed=0
 for material,v,idx in chunks:
  bounds=shapely.box(v[:,0].min()-.01,v[:,1].min()-.01,v[:,0].max()+.01,v[:,1].max()+.01)
  building_chunks,_=clip(v,idx,bounds.difference(keep),shapely.Polygon(),None)
  for vv,ii in building_chunks:
   final,count=clip(vv,ii,street,passages,ground);removed+=count;result.extend((material,vv,ii)for vv,ii in final)
 report.update(project_facades(result,building_shell))
 clear=[]
 for material,v,idx in result:
  vv,count=clip(v,idx,street,shapely.Polygon(),None);removed+=count;clear.extend((material,p,i)for p,i in vv)
 return clear,report,removed

def project_facades(chunks,building_shell,max_distance=.3):   # 1.8 m flattened real oriels, balconies and cornices
 """Conform nearby outward vertices to the building shell, identically across UV seams.
 Height and source UV stay intact. Only referenced mesh vertices are examined.
 """
 tree=shapely.STRtree(shapely.get_parts(building_shell.boundary));shapely.prepare(building_shell);moved=0;maximum=0
 for material,v,idx in chunks:
  used=np.unique(idx);points=shapely.points(v[used,0],v[used,1]);outside=~shapely.covers(building_shell,points);take=used[outside];points=points[outside]
  if not len(take):continue
  nearest=tree.nearest(points);lines=shapely.shortest_line(points,tree.geometries[nearest]);distance=shapely.length(lines);good=(distance>.01)&(distance<=max_distance);take=take[good]
  if not len(take):continue
  points=shapely.get_point(lines[good],-1);v[take,0]=shapely.get_x(points);v[take,1]=shapely.get_y(points);moved+=len(take);maximum=max(maximum,float(distance[good].max()))
 return {'outwardFacadeVerticesProjected':moved,'maximumFacadeProjectionM':maximum,'projectionLimitM':max_distance,'UVAndHeightPreserved':True,'seamRule':'one position maps to one shell point, independently of material normals'}

def drop_loose(chunks,ground,footprints,support=None,float_m=2.5,skirt_m=1.2,found=None):
 """Final photo-mesh cleanup after every other cut (street, modeled buildings).
 * floating: a connected piece whose LOWEST point is > float_m above what can carry it:
   max(terrain, LoD2 roof top) at that spot (support), so a crane jib above a building site
   goes, while roofs, towers and eaves (resting at roof level) stay;
 * ground skirt: near-horizontal triangles outside footprints within skirt_m of the terrain
   (lumpy photo pavement next to facades; the smooth shared terrain floor lies beneath).
 chunks: [(tex,vertices(N,5),indices)]; returns (chunks, {'floating':n,'skirt':n}) in triangles."""
 from scipy.sparse import coo_matrix
 from scipy.sparse.csgraph import connected_components
 import shapely
 shapely.prepare(footprints);out=[];report={"floating":0,"skirt":0}
 for tex,v,idx in chunks:
  tri=idx.reshape(-1,3).astype(np.int64)
  if not len(tri):continue
  p=v[tri,:3].astype(np.float64);c=p.mean(1)
  n=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);ln=np.linalg.norm(n,axis=1)+1e-12
  lift=p[:,:,2]-ground(p[:,:,0],p[:,:,1])        # per corner height above terrain
  inside=shapely.contains_xy(footprints,c[:,0],c[:,1])
  skirt=(~inside)&(np.abs(n[:,2])/ln>.6)&(lift.max(1)<skirt_m)
  keep=~skirt;report['skirt']+=int(skirt.sum())
  # connected pieces over shared vertices (only among kept triangles)
  t=tri[keep];nv=len(v)
  if len(t):
   rows=np.concatenate([t[:,0],t[:,1]]);cols=np.concatenate([t[:,1],t[:,2]])
   _,label=connected_components(coo_matrix((np.ones(len(rows)),(rows,cols)),shape=(nv,nv)),directed=False)
   comp=label[t[:,0]];k=comp.max()+1
   pk=p[keep];carry=pk[:,:,2]-(support(pk[:,:,0],pk[:,:,1])if support else ground(pk[:,:,0],pk[:,:,1]))
   low=np.full(k,np.inf);np.minimum.at(low,comp,carry.min(1))
   floating=low>float_m
   if found is not None:   # long thin high pieces (crane jibs) for the crane model owner in build-town
    for cid in np.flatnonzero(floating):
     sel=comp==cid
     if sel.sum()<20 or low[cid]<8:continue
     q=pk[sel].reshape(-1,3);m=q[:,:2].mean(0);u_,sv,vt=np.linalg.svd(q[:,:2]-m,full_matrices=False);ax=vt[0];t_=(q[:,:2]-m)@ax;w_=(q[:,:2]-m)@vt[1]
     length=t_.max()-t_.min();width=w_.max()-w_.min()
     lift=float(q[:,2].min()-ground(np.array([m[0]]),np.array([m[1]]))[0])
     if length>15 and width<max(4,.25*length):found.append({'centre':m,'axis':ax,'t':(float(t_.min()),float(t_.max())),'z':float(q[:,2].min()),'zt':float(q[:,2].max()),'width':float(width),'lift':lift,'clear':float(low[cid]),'tri':t_.tolist()})
   drop=floating[comp];report['floating']+=int(drop.sum())
   kidx=np.flatnonzero(keep);keep[kidx[drop]]=False
  if keep.any():out.append((tex,v,tri[keep].reshape(-1).astype('<u2')))
 return out,report
