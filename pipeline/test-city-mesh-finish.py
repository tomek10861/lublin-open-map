import unittest
import numpy as np
from city_mesh_finish import fill_facade_holes,weld_inverse,regularize,project_facades
class FinishTests(unittest.TestCase):
 def fixture(self,hole):
  p=np.array([[0,0,4],[6,0,4],[6,0,10],[0,0,10],[2,0,6],[4,0,6],[4,0,8],[2,0,8]],dtype='<f4');v=np.column_stack((p,p[:,[0,2]]/[6,12])).astype('<f4');quads=[[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]if hole else [[0,1,2,3]];idx=np.array([[a,b,c,a,c,d]for a,b,c,d in quads],dtype='<u2').reshape(-1);return [(1,v,idx)]
 def test_closes_interior_hole_preserves_outer_shell(self):
  meta={'footprintLocal':[[-10,-10],[10,-10],[10,10],[-10,10]]}
  for hole in [False,True]:
   chunks=self.fixture(hole);r=fill_facade_holes(chunks,meta,lambda x,y:np.zeros_like(x));self.assertEqual(r['filledPlanarFacadeHoles'],int(hole))
   if hole:self.assertEqual(len(chunks[-1][2]),12)
 def test_numeric_weld_matches_quantized_identity(self):
  p=np.array([[1,2,3],[1.0001,2,3],[3,2,1],[-2,0,1]])
  inverse,n=weld_inverse(p,1000);self.assertEqual(n,3);self.assertEqual(inverse[0],inverse[1]);self.assertNotEqual(inverse[0],inverse[2])
 def test_projection_keeps_shared_roof_wall_seam_and_source_uv(self):
  from shapely.geometry import box
  a=np.array([[-1,0,0,0,0],[-1,1,0,1,0],[-1,1,4,1,1],[-1,0,4,0,1]],dtype='<f4');b=np.array([[-1,0,4,0,0],[-1,1,4,1,0],[1,1,4,1,1]],dtype='<f4');uv_a=a[:,2:].copy();uv_b=b[:,2:].copy()
  project_facades([(0,a,np.array([0,1,2,0,2,3],dtype='<u2')),(1,b,np.array([0,1,2],dtype='<u2'))],box(0,-10,10,10))
  np.testing.assert_array_equal(a[2,:3],b[1,:3]);np.testing.assert_array_equal(a[:,2:],uv_a);np.testing.assert_array_equal(b[:,2:],uv_b)
if __name__=='__main__':unittest.main()
