import unittest,struct,zlib,tempfile
from pathlib import Path
import numpy as np
from city_package import read_town,full_terrain,CityFormatError
class PackageTests(unittest.TestCase):
 def make(self,vertices,indices):
  v=np.column_stack((np.array(vertices,dtype='<f4'),np.zeros((len(vertices),2),dtype='<f4'))).astype('<f4');idx=np.array(indices,dtype='<u2');body=struct.pack('<III',1,1,1)+struct.pack('<II',1,1)+b'\xff'*3+struct.pack('<IIII',1,0,len(v),len(idx))+v.tobytes()+idx.tobytes()+b'\x80\x80\x80\xff'*len(v);return b'TOWNv002'+struct.pack('<I',len(body))+zlib.compress(body)
 def test_atlas_edge_vertex_is_not_a_grid_node(self):
  raw=self.make([[0,10,0],[10,10,10],[0,0,20],[10,0,30],[5,10,5]],[0,2,4,4,2,1,1,2,3])
  with tempfile.TemporaryDirectory()as td:
   path=Path(td)/'map';path.write_bytes(raw);terrain=full_terrain(read_town(path));np.testing.assert_allclose(terrain.grid,[[0,10],[20,30]]);self.assertAlmostEqual(float(terrain.sample(5,5)),15)
 def test_truncated_compressed_payload_and_bad_index_are_rejected(self):
  raw=self.make([[0,10,0],[10,10,10],[0,0,20]],[0,1,3])
  with tempfile.TemporaryDirectory()as td:
   path=Path(td)/'map'
   for invalid in [raw,raw[:-2],b'TOWNv002'+struct.pack('<I',2**32-1)+b'bad']:
    path.write_bytes(invalid)
    with self.assertRaises(CityFormatError):read_town(path)
if __name__=='__main__':unittest.main()
