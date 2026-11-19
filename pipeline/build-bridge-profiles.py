from pathlib import Path
import json,argparse
from city_package import read_town,full_terrain
from city_bridges import profiles
ap=argparse.ArgumentParser();ap.add_argument('--base-town',required=True,type=Path);args=ap.parse_args();root=Path(__file__).resolve().parent;terrain=full_terrain(read_town(args.base_town));records=profiles(root,terrain.sample);(root/'bridge-audit/road-profiles.json').write_text(json.dumps(records,indent=2));
for r in records:print(r['way'],r['name'],r['status'],'grade',round(r['maxGrade'],3),'lift',round(r['maxLiftM'],2),flush=True)
