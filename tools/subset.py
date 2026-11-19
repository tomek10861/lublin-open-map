#!/usr/bin/env python3
"""Cut a rectangular area out of the exported map, e.g. one district for a game with a small map limit.

  python3 tools/subset.py --data dist --center 2300,-20 --size 400 --out stare-miasto
  python3 tools/subset.py --data dist --bbox 2100,-250,2700,350 --out old-town --local

--center/--size and --bbox are in local metres (see docs/format.md). The subset keeps whole tiles
that touch the area (tiles are not clipped), copies their textures, clips GeoJSON layers to the
area and writes its own manifest.json. --local also writes layers in local metres (*.local.json),
which is what most game tools want. Needs only the Python standard library.
"""
import argparse, json, shutil
from pathlib import Path


def inside(pt, b):
    return b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]


def touches(tb, b):
    return not (tb[2] < b[0] or tb[0] > b[2] or tb[3] < b[1] or tb[1] > b[3])


def coords_of(g):
    t, c = g['type'], g['coordinates']
    if t == 'Point': return [c]
    if t in ('LineString', 'MultiPoint'): return c
    if t in ('MultiLineString', 'Polygon'): return [p for part in c for p in part]
    if t == 'MultiPolygon': return [p for poly in c for ring in poly for p in ring]
    return []


def to_local(g, o):
    def f(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0] - o[0], 2), round(c[1] - o[1], 2)] + ([round(c[2] - o[2], 2)] if len(c) > 2 else [])
        return [f(x) for x in c]
    return {'type': g['type'], 'coordinates': f(g['coordinates'])}


def copy_gltf(src_dir, rel, out):
    """Copy a .gltf with its .bin and the images it references (relative URIs)."""
    src = src_dir / rel; dst = out / rel; dst.parent.mkdir(parents=True, exist_ok=True)
    j = json.loads(src.read_text())
    shutil.copy2(src, dst)
    for b in j.get('buffers', []): shutil.copy2(src.parent / b['uri'], dst.parent / b['uri'])
    for im in j.get('images', []):
        s = (src.parent / im['uri']).resolve(); d = (dst.parent / im['uri'])
        d.parent.mkdir(parents=True, exist_ok=True)
        if not d.exists(): shutil.copy2(s, d)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', type=Path, default=Path('dist'))
    ap.add_argument('--center'); ap.add_argument('--size', type=float, default=400)
    ap.add_argument('--bbox'); ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--no-photo', action='store_true', help='skip photogrammetry tiles')
    ap.add_argument('--local', action='store_true', help='also write layers in local metres')
    a = ap.parse_args()
    if a.bbox: b = [float(v) for v in a.bbox.split(',')]
    elif a.center:
        x, y = (float(v) for v in a.center.split(',')); h = a.size / 2; b = [x - h, y - h, x + h, y + h]
    else: ap.error('give --center or --bbox')
    m = json.loads((a.data / 'manifest.json').read_text()); s = m['coordinates']['cellM']; o = m['coordinates']['originEPSG2180']
    cellbox = lambda c: [c[0] * s, c[1] * s, (c[0] + 1) * s, (c[1] + 1) * s]
    sub = dict(m); sub['subsetBboxLocal'] = b
    for key in ('city', 'collision'):
        sub[key] = [t for t in m[key] if touches(cellbox(t['cell']), b)]
        for t in sub[key]: copy_gltf(a.data, t['file'], a.out)
    sub['photo'] = [] if a.no_photo else [t for t in m['photo'] if touches(t['bboxLocal'], b)]
    for t in sub['photo']: copy_gltf(a.data, t['file'], a.out)
    for t in m.get('races', []): copy_gltf(a.data, t['file'], a.out)
    eb = [b[0] + o[0], b[1] + o[1], b[2] + o[0], b[3] + o[1]]
    (a.out / 'layers').mkdir(parents=True, exist_ok=True); counts = {}
    for name, rel in m['layers'].items():
        fc = json.loads((a.data / rel).read_text())
        fc['features'] = [f for f in fc['features'] if any(inside(p, eb) for p in coords_of(f['geometry']))]
        counts[name] = len(fc['features'])
        (a.out / rel).write_text(json.dumps(fc, ensure_ascii=False))
        if a.local:
            loc = {'type': 'FeatureCollection', 'name': name, 'units': 'local metres (EPSG:2180 minus originEPSG2180)',
                   'features': [{'type': 'Feature', 'properties': f['properties'], 'geometry': to_local(f['geometry'], o)} for f in fc['features']]}
            (a.out / 'layers' / f'{name}.local.json').write_text(json.dumps(loc, ensure_ascii=False))
    shutil.copytree(a.data / 'terrain', a.out / 'terrain', dirs_exist_ok=True)
    sub['layerCounts'] = counts
    (a.out / 'manifest.json').write_text(json.dumps(sub, indent=1, ensure_ascii=False))
    print(f"city {len(sub['city'])}, collision {len(sub['collision'])}, photo {len(sub['photo'])}, layers {counts} -> {a.out}")


if __name__ == '__main__':
    main()
