from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess,xml.etree.ElementTree as E,json
root=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'/osm-tiles');root.mkdir(exist_ok=True)
def fetch(pair):
 i,j=pair;x=22.50+i*.01;y=51.23+j*.01;p=root/f'{i}-{j}.osm'
 if not p.exists():
  url=f'https://api.openstreetmap.org/api/0.6/map?bbox={x:.3f},{y:.3f},{x+.01:.3f},{y+.01:.3f}'
  r=subprocess.run(['/usr/bin/curl','-sSfL','--max-time','25',url,'-o',str(p)],capture_output=True)
  if r.returncode:return {'tile':[i,j],'error':r.stderr.decode()}
 try:
  t=E.parse(p);return {'tile':[i,j],'nodes':len(t.findall('node')),'ways':len(t.findall('way'))}
 except Exception as e:return {'tile':[i,j],'error':str(e)}
pairs=[(i,j)for i in range(8) for j in range(4)]  # i=7: 22.57-22.58 E (Zamek, Stare Miasto)
with ThreadPoolExecutor(max_workers=2) as pool:
 reports=[]
 for r in pool.map(fetch,pairs):reports.append(r);print(json.dumps(r),flush=True)
Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'/osm-fetch-report.json').write_text(json.dumps(reports,indent=2))
