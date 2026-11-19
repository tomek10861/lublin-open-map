import sys,numpy as np
sys.path.insert(0,'work');from city_lod2_finish import gable_faces
wall=np.array([[0,0,0,0,0],[6,0,0,0,0],[6,0,3,0,0],[0,0,3,0,0]],dtype='<f4');wi=np.array([0,1,2,0,2,3],dtype='<u2');roof=np.array([[0,0,3,0,0],[3,0,6,0,0],[6,0,3,0,0]],dtype='<f4');ri=np.array([0,1,2],dtype='<u2');out=gable_faces((wall,wi),[(roof,ri)]);assert len(out)==12,len(out)
roof[:,1]=1;assert len(gable_faces((wall,wi),[(roof,ri)]))==0
print('Missing gable closes against the actual wall top; roof overhang stays open')
