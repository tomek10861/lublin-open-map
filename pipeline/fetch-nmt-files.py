from pathlib import Path
import re,subprocess,concurrent.futures,json
r=Path(__import__('os').environ.get('LUBLIN_WORK',str(Path(__file__).resolve().parent))+'');out=r/'nmt-original';out.mkdir(exist_ok=True)
urls=sorted(set(re.findall(r'https://opendata[^<\s]+\.asc', (r/'nmt-tiles-2017.gml').read_text())))
def get(url):
 p=out/url.rsplit('/',1)[-1]
 if not p.exists():
  t=subprocess.run(['/usr/bin/curl','-sSfL','--max-time','55',url,'-o',str(p)],capture_output=True)
  if t.returncode:return {'url':url,'error':t.stderr.decode()}
 return {'url':url,'file':p.name,'bytes':p.stat().st_size}
with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
 reports=[]
 for result in pool.map(get,urls):reports.append(result);print(json.dumps(result),flush=True)
(r/'nmt-downloads.json').write_text(json.dumps(reports,indent=2))
