"""Import City of Lublin 2022 photogrammetric OBJ tiles (gis.lublin.eu/pobierzdane/mesh/2022)
into engine-ready chunks for build-town.py.

Source: OBJ (Skyline), EPSG:2179 (PL-2000 zone 8), photo textures per material.
Output per tile (city-mesh-2022/import/<tile>/):
  mesh.npz      chunks: material id, vertices (N,5 local X,Y,Z,u,v), uint16 indices
  tex-<m>.png   downscaled source texture of material m (no repainting)
  tile.json     provenance, footprint polygon (local XY), decimation report
Decimation: vertex clustering on a cubic grid; each output corner keeps its ORIGINAL
UV (clusters merge positions, never texture coordinates). Cell size is chosen by
bisection so the tile lands near --target triangles.
"""
from pathlib import Path
import argparse, hashlib, json, sys, time
import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely.geometry import MultiPoint

Image.MAX_IMAGE_PIXELS = None
root = Path(__file__).resolve().parent
roi = json.loads((root / 'roi.json').read_text())
OX, OY, OZ = roi['originEPSG2180']
LODS = {'A': (750000, {0: 4096, 1: 2048}),   # streamed near the player (close to source density)
        'C': (25000, {0: 512, 1: 256})}        # always resident distant shell
MAX_VERTS = 65535

def parse_obj(path):
    v, vt, faces, mats, names = [], [], [], [], {}
    mat = 0
    with open(path, 'r') as fh:
        for line in fh:
            c = line[:2]
            if c == 'v ':
                v.append(line[2:].split())
            elif c == 'vt':
                vt.append(line[3:].split()[:2])
            elif c == 'f ':
                a, b, d = line[2:].split()
                faces.append((a.split('/')[:2], b.split('/')[:2], d.split('/')[:2]))
                mats.append(mat)
            elif line.startswith('usemtl'):
                name = line.split()[1]
                mat = names.setdefault(name, int(name.rsplit('_', 1)[1]))
    f = np.asarray(faces, dtype=np.int64) - 1            # (F,3,2): position idx, uv idx
    return (np.asarray(v, dtype=np.float64), np.asarray(vt, dtype=np.float64), f,
            np.asarray(mats, dtype=np.int32), names)

def cluster(pos, faces, mats, cell):
    key = np.floor(pos / cell).astype(np.int64)
    _, cid = np.unique(key, axis=0, return_inverse=True)
    cid = cid.reshape(-1)
    fc = cid[faces[:, :, 0]]
    keep = (fc[:, 0] != fc[:, 1]) & (fc[:, 1] != fc[:, 2]) & (fc[:, 0] != fc[:, 2])
    srt = np.sort(fc, axis=1)
    sig = np.concatenate([srt, mats[:, None]], axis=1)[keep]
    _, first = np.unique(sig, axis=0, return_index=True)
    idx = np.flatnonzero(keep)[first]
    return cid, idx

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tiles', nargs='+')
    ap.add_argument('--lod', choices=sorted(LODS), default='A')
    a = ap.parse_args()
    to2180 = Transformer.from_crs(2179, 2180, always_xy=True)
    for tile in a.tiles:
        t0 = time.time()
        src = root / 'city-mesh-2022' / tile
        target, TEX_LIMIT = LODS[a.lod]
        out = root / 'city-mesh-2022' / 'import' / tile / a.lod
        out.mkdir(parents=True, exist_ok=True)
        v, vt, f, mats, names = parse_obj(src / f'{tile}.obj')
        e, n = to2180.transform(v[:, 0], v[:, 1])
        pos = np.stack([np.asarray(e) - OX, np.asarray(n) - OY, v[:, 2] - OZ], axis=1)
        assert np.isfinite(pos).all() and vt.min() >= -1e-4 and vt.max() <= 1 + 1e-4
        lo, hi = 0.02, 2.0
        for _ in range(18):                               # bisection on cell size
            cell = (lo * hi) ** .5
            cid, idx = cluster(pos, f, mats, cell)
            if len(idx) > target: lo = cell
            else: hi = cell
        cell = hi
        cid, idx = cluster(pos, f, mats, cell)
        ncl = cid.max() + 1
        rep = np.zeros((ncl, 3)); np.add.at(rep, cid, pos); rep /= np.bincount(cid, minlength=ncl)[:, None]
        chunks = []
        cx = np.floor(rep[cid[f[idx, 0, 0]], :2] / 60).astype(np.int64)   # 60 m spatial chunks
        for m in sorted(set(mats.tolist())):
            sel = idx[mats[idx] == m]
            ckey = np.floor(rep[cid[f[sel, 0, 0]], :2] / 60).astype(np.int64)
            order = np.lexsort((ckey[:, 1], ckey[:, 0])); sel = sel[order]; ckey = ckey[order]
            start = 0
            while start < len(sel):
                # grow the run of one spatial cell until the vertex budget is reached
                end = start; corner = {}
                while end < len(sel) and (ckey[end] == ckey[start]).all():
                    for k in range(3):
                        corner.setdefault((int(cid[f[sel[end], k, 0]]), int(f[sel[end], k, 1])), len(corner))
                    if len(corner) > MAX_VERTS - 3: end += 1; break
                    end += 1
                run = sel[start:end]
                pairs = np.stack([cid[f[run, :, 0]], f[run, :, 1]], axis=2).reshape(-1, 2)
                uniq, inv = np.unique(pairs, axis=0, return_inverse=True)
                assert len(uniq) <= MAX_VERTS
                verts = np.concatenate([rep[uniq[:, 0]], vt[uniq[:, 1]]], axis=1).astype('<f4')
                verts[:, 4] = 1.0 - verts[:, 4]              # OBJ v=0 bottom -> engine v=0 top row
                chunks.append((m, verts, inv.reshape(-1).astype('<u2')))
                start = end
        np.savez_compressed(out / 'mesh.npz', **{f'm{i}': c[0] for i, c in enumerate(chunks)},
                            **{f'v{i}': c[1] for i, c in enumerate(chunks)},
                            **{f'i{i}': c[2] for i, c in enumerate(chunks)}, count=len(chunks))
        textures = {}
        mtl = (src / f'{tile}.mtl').read_text().split('newmtl ')[1:]
        for block in mtl:
            name = block.split()[0]; tex = [l.split(None, 1)[1].strip() for l in block.splitlines() if l.startswith('map_Kd')][0]
            m = names.get(name, int(name.rsplit('_', 1)[1]))
            im = Image.open(src / tex).convert('RGB'); limit = TEX_LIMIT.get(m, 2048)
            scale = min(1.0, limit / max(im.size)); size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
            if scale < 1: im = im.resize(size, Image.LANCZOS)
            im.save(out / f'tex-{m}.png')
            textures[m] = {'source': tex, 'sourceSha256': hashlib.sha256((src / tex).read_bytes()).hexdigest(), 'size': list(im.size)}
        hull = MultiPoint(pos[:, :2][::7]).convex_hull
        report = {'tile': tile, 'lod': a.lod, 'source': f'https://gis.lublin.eu/pobierzdane/mesh/2022/{tile}.zip',
                  'publisher': 'Urząd Miasta Lublin, model mesh 3D 2022 (OBJ)', 'crsSource': 'EPSG:2179',
                  'crsLocal': f'EPSG:2180 minus {roi["originEPSG2180"]}', 'heightNote': 'source Z kept (datum unverified vs PL-KRON86-NH)',
                  'sourceVertices': int(len(v)), 'sourceTriangles': int(len(f)), 'clusterCellM': round(float(cell), 4),
                  'triangles': int(len(idx)), 'chunks': len(chunks), 'vertices': int(sum(len(c[1]) for c in chunks)),
                  'boundsLocal': [*map(float, pos.min(0).round(3)), *map(float, pos.max(0).round(3))],
                  'footprintLocal': [list(map(float, p)) for p in hull.exterior.coords], 'textures': textures,
                  'seconds': round(time.time() - t0, 1)}
        (out / 'tile.json').write_text(json.dumps(report, indent=1, ensure_ascii=False))
        print(json.dumps({k: report[k] for k in ['tile', 'sourceTriangles', 'triangles', 'clusterCellM', 'chunks', 'vertices', 'seconds']}), flush=True)

if __name__ == '__main__':
    main()
