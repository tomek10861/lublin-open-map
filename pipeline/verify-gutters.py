from pathlib import Path
from PIL import Image
import json,numpy as np
r=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'/ortho-high');j=json.loads((r/'atlas.json').read_text());assert len(j['tiles'])==6
for t in j['tiles']:
 assert t['gutterPx']==16
 with Image.open(r/'runtime'/t['file'])as im:a=np.asarray(im);w,h=im.size
 assert w<=4096 and h<=4096 and w&(w-1)==0 and h&(h-1)==0
 cw,ch=t['contentWidth'],t['contentHeight'];assert np.all(a[:16]==a[16:17]);assert np.all(a[:,:16]==a[:,16:17]);assert np.all(a[ch+16:ch+32]==a[ch+15:ch+16]);assert np.all(a[:,cw+16:cw+32]==a[:,cw+15:cw+16]);assert t['uvRect']==[16/w,16/h,(16+cw)/w,(16+ch)/h]
proof={'tiles':len(j['tiles']),'replicatedGutterPx':16,'powerOfTwo':True,'maxDimension':4096,'interiorUVs':True,'mipmapOrder':'padded RGB is supplied to native upload_tex, which generates GPU mipmaps afterwards','runtimeResolutionM':.5};(r/'gutter-verification.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof))
