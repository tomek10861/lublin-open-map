#!/usr/bin/env python3
"""Export the Lublin city build to engine-neutral files.

Inputs (produced by build-town.py / build-race-meta.py):
  <custom-city>/PL01.town            city package (terrain, streets, LoD2 buildings, bridges, props...)
  <custom-city>/stream/*-A.tmesh     photogrammetry tiles, LOD A (TMSHj001: JPEG textures + meshes)
  <custom-city>/stream-manifest.json tile index
  <custom-city>/streets.json         OSM street names (local metres)
  <work>/route-*.json                race courses (EPSG:2180)
  <work>/terrain-build/*             5 m terrain grid
  <work>/lublin-buildings-clipped.json  GUGiK LoD2 buildings

Outputs (<out>/):
  manifest.json                      coordinate system, tile index, layer list, sources
  textures/                          shared city textures (ortho atlases JPEG, procedural PNG)
  city/<cx>_<cy>.gltf|.bin           city geometry per 512 m cell, materials per texture,
                                     breakable props (trees, signs) as separate nodes
  collision/<cx>_<cy>.gltf|.bin      collision geometry per cell: ground + walls, untextured
  photo/<tile>/<tile>.gltf|.bin|*.jpg  photogrammetry tiles with their original JPEG textures
  races/<event>.gltf|.bin            race-only barriers and markers
  layers/*.geojson                   EPSG:2180 vector layers (streets, lanes, races, props,
                                     landmarks, buildings)
  terrain/heightmap.png|.json        16-bit heightmap, 5 m cells, row 0 = north

Coordinates: geometry is in local metres. Local = EPSG:2180 easting/northing and
PL-KRON86-NH height minus ORIGIN. glTF files use glTF axes (Y up): gltf = (x, z, -y).
"""
import argparse, json, struct, zlib, io, re, sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from city_package import read_town

ORIGIN = (746600.0, 381750.0, 180.0)
CELL = 512.0
# Procedural texture slots after the ortho atlases, in build-town.py order (sky is last).
PROC_NAMES = ['facade_beige', 'facade_grey', 'facade_bluegrey', 'asphalt_marked', 'setts',
              'asphalt_residential', 'asphalt_service', 'race_barrier', 'race_chevron',
              'pavement_slabs', 'concrete', 'crane_lattice', 'shell_membrane', 'bench', 'timber',
              'portal_screen', 'church_facade', 'cast_iron', 'gilt', 'bronze', 'street_signs', 'sky']
F_GROUND_OFF, F_PHYS_ONLY, F_VISUAL_ONLY, F_EVENT, F_PROP, F_SIGN = 256, 512, 1024, 2048, 4096, 16384
CLAMP, REPEAT = 33071, 10497


def gl(p):
    """local (x east, y north, z up) -> glTF (x, y up, z south). A proper rotation."""
    p = np.asarray(p, '<f4')
    return np.stack([p[:, 0], p[:, 2], -p[:, 1]], 1)


def vertex_normals(P, I):
    tri = I.reshape(-1, 3)
    fn = np.cross(P[tri[:, 1]] - P[tri[:, 0]], P[tri[:, 2]] - P[tri[:, 0]])
    n = np.zeros_like(P)
    for k in range(3):
        np.add.at(n, tri[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.where(ln > 1e-12, n / np.maximum(ln, 1e-12), np.array([0, 1, 0], '<f4'))
    return n.astype('<f4')


class Gltf:
    def __init__(self, extras=None):
        self.bin = bytearray()
        self.j = {'asset': {'version': '2.0', 'generator': 'lublin-open-map export_open_map.py'},
                  'scene': 0, 'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [], 'buffers': [],
                  'bufferViews': [], 'accessors': []}
        if extras: self.j['scenes'][0]['extras'] = extras
        self.materials = {}

    def _view(self, data, target):
        while len(self.bin) % 4: self.bin.append(0)
        self.j['bufferViews'].append({'buffer': 0, 'byteOffset': len(self.bin), 'byteLength': len(data), 'target': target})
        self.bin += data
        return len(self.j['bufferViews']) - 1

    def _acc(self, arr, kind, ctype, target, bounds=False):
        a = {'bufferView': self._view(arr.tobytes(), target), 'componentType': ctype, 'count': len(arr), 'type': kind}
        if bounds: a['min'], a['max'] = arr.min(0).tolist(), arr.max(0).tolist()
        self.j['accessors'].append(a)
        return len(self.j['accessors']) - 1

    def material(self, key, name, uri=None, wrap=REPEAT, unlit=False, color=(1, 1, 1, 1)):
        if key in self.materials: return self.materials[key]
        m = {'name': name, 'doubleSided': True,
             'pbrMetallicRoughness': {'baseColorFactor': list(color), 'metallicFactor': 0.0, 'roughnessFactor': 1.0}}
        if uri:
            j = self.j
            j.setdefault('samplers', []).append({'magFilter': 9729, 'minFilter': 9987, 'wrapS': wrap, 'wrapT': wrap})
            j.setdefault('images', []).append({'uri': uri})
            j.setdefault('textures', []).append({'sampler': len(j['samplers']) - 1, 'source': len(j['images']) - 1})
            m['pbrMetallicRoughness']['baseColorTexture'] = {'index': len(j['textures']) - 1}
        if unlit:
            m['extensions'] = {'KHR_materials_unlit': {}}
            self.j.setdefault('extensionsUsed', [])
            if 'KHR_materials_unlit' not in self.j['extensionsUsed']: self.j['extensionsUsed'].append('KHR_materials_unlit')
        self.j.setdefault('materials', []).append(m)
        self.materials[key] = len(self.j['materials']) - 1
        return self.materials[key]

    def node(self, name, prims, extras=None):
        """prims: list of (local vertices (n,5) or (n,3), indices, material index or None)."""
        out = []
        for prim in prims:
            V, I, mat = prim[:3]; C = prim[3] if len(prim) > 3 else None
            V = np.asarray(V, '<f4'); I = np.asarray(I, '<u4')
            if len(I) < 3: continue
            P = gl(V[:, :3])
            attrs = {'POSITION': self._acc(P, 'VEC3', 5126, 34962, True),
                     'NORMAL': self._acc(vertex_normals(P, I), 'VEC3', 5126, 34962)}
            if V.shape[1] >= 5 and mat is not None and C is None:
                attrs['TEXCOORD_0'] = self._acc(np.ascontiguousarray(V[:, 3:5]), 'VEC2', 5126, 34962)
            if C is not None:   # glTF COLOR_0 is linear; the town stores authored sRGB colours
                attrs['COLOR_0'] = self._acc(srgb_to_linear_u8(C), 'VEC4', 5121, 34962)
                self.j['accessors'][attrs['COLOR_0']]['normalized'] = True
            p = {'attributes': attrs, 'indices': self._acc(I, 'SCALAR', 5125, 34963), 'mode': 4}
            if mat is not None: p['material'] = mat
            out.append(p)
        if not out: return None
        self.j['meshes'].append({'name': name, 'primitives': out})
        n = {'name': name, 'mesh': len(self.j['meshes']) - 1}
        if extras: n['extras'] = extras
        self.j['nodes'].append(n)
        self.j['scenes'][0]['nodes'].append(len(self.j['nodes']) - 1)
        return len(self.j['nodes']) - 1

    def save(self, path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        if not self.j['meshes']: return False
        self.j['buffers'] = [{'uri': path.with_suffix('.bin').name, 'byteLength': len(self.bin)}]
        path.with_suffix('.bin').write_bytes(bytes(self.bin))
        path.write_text(json.dumps(self.j, separators=(',', ':')))
        return True


def merge(parts):
    """[(V, I[, C])] -> (V, I[, C]) with u32 indices."""
    Vs, Is, Cs, off = [], [], [], 0
    for p in parts:
        V, I = p[0], p[1]
        Vs.append(V); Is.append(I.astype('<u4') + off); off += len(V)
        if len(p) > 2: Cs.append(p[2])
    out = (np.concatenate(Vs), np.concatenate(Is))
    return out + (np.concatenate(Cs),) if Cs else out


def srgb_to_linear_u8(C):
    """RGB channels sRGB -> linear (IEC 61966-2-1), alpha unchanged, as normalized u8."""
    C = np.asarray(C, 'u1'); c = C[:, :3] / 255.0
    lin = np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)
    return np.ascontiguousarray(np.column_stack([np.rint(lin * 255), C[:, 3:]]).astype('u1'))


def vertex_coloured(m):
    """Meshes coloured per vertex on a single texel (trees, poles): the colour is the material."""
    C = np.frombuffer(m.colours, 'u1').reshape(-1, 4)
    uv = np.asarray(m.vertices)[:, 3:5]
    return C if (C[:, :3] != 128).any() and np.ptp(uv, 0).max() < 1e-6 else None


VC = 'vertex_colour'


def mat_for(g, t, tex):
    if t == VC: return g.material(VC, VC)
    T = tex[t]; return g.material(t, T['name'], T['uri'], T['wrap'], T['unlit'])


def cell_of(V):
    c = V[:, :2].mean(0)
    return int(np.floor(c[0] / CELL)), int(np.floor(c[1] / CELL))


def export_textures(pkg, out):
    """Slot -> (relative uri from a sibling dir, wrap, unlit, name)."""
    tex = []
    data, o = pkg.texture_bytes, 0
    names = [f'ortho_{i}' for i in range(pkg.ortho_count)] + PROC_NAMES
    if len(names) != pkg.texture_count:
        raise SystemExit(f'texture count {pkg.texture_count} does not match the known slot list ({len(names)})')
    (out / 'textures').mkdir(parents=True, exist_ok=True)
    for i in range(pkg.texture_count):
        w, h = struct.unpack_from('<II', data, o); o += 8
        im = Image.frombytes('RGB', (w, h), bytes(data[o:o + w * h * 3])); o += w * h * 3
        ortho = i < pkg.ortho_count
        fn = f'{names[i]}.jpg' if ortho else f'{names[i]}.png'
        if ortho: im.save(out / 'textures' / fn, 'JPEG', quality=90, optimize=True)
        else: im.save(out / 'textures' / fn, optimize=True)
        tex.append({'uri': f'../textures/{fn}', 'wrap': CLAMP if ortho else REPEAT, 'unlit': ortho, 'name': names[i]})
    return tex


def export_town(pkg, tex, out):
    cells, coll, races, props = {}, {}, {}, []
    for k, m in enumerate(pkg.meshes):
        low, fl, ev = m.category & 255, m.category & 0xffff & ~255, m.category >> 16
        if low == 3 or tex[m.texture]['name'] == 'sky': continue
        V, I = np.asarray(m.vertices), np.asarray(m.indices)
        C = vertex_coloured(m); key = VC if C is not None else m.texture
        part = (V, I, C) if C is not None else (V, I)
        if fl & F_EVENT:
            races.setdefault(ev, {'visual': {}, 'collision': []})
            if fl & F_PHYS_ONLY: races[ev]['collision'].append((V, I))
            else: races[ev]['visual'].setdefault(key, []).append(part)
            continue
        c = cell_of(V)
        if fl & F_PROP:
            kind = 'sign' if fl & F_SIGN else 'tree'
            base = V[:, :3].min(0); top = V[:, 2].max()
            x, y = V[:, 0].mean(), V[:, 1].mean()
            props.append({'kind': kind, 'x': float(x), 'y': float(y), 'z': float(base[2]), 'heightM': float(top - base[2]), 'cell': c, 'id': f'{kind}_{len(props)}'})
            cells.setdefault(c, {'tex': {}, 'props': []})['props'].append((props[-1]['id'], kind, key, part))
            continue
        if not fl & F_PHYS_ONLY:
            cells.setdefault(c, {'tex': {}, 'props': []})['tex'].setdefault(key, []).append(part)
        if (low in (0, 1) and not fl & F_GROUND_OFF):
            coll.setdefault(c, {'ground': [], 'walls': []})['ground'].append((V, I))
        elif low == 2 and not fl & F_VISUAL_ONLY:
            coll.setdefault(c, {'ground': [], 'walls': []})['walls'].append((V, I))
    index = []
    for c, d in sorted(cells.items()):
        g = Gltf({'originEPSG2180': ORIGIN, 'cell': c, 'cellM': CELL})
        for t, parts in sorted(d['tex'].items(), key=lambda kv: str(kv[0])):
            M = merge(parts)
            g.node(f'city_{VC if t == VC else tex[t]["name"]}', [(M[0], M[1], mat_for(g, t, tex)) + M[2:]])
        for pid, kind, t, part in d['props']:
            g.node(pid, [(part[0], part[1].astype('<u4'), mat_for(g, t, tex)) + tuple(part[2:])],
                   {'breakable': True, 'kind': kind})
        name = f'{c[0]}_{c[1]}'
        g.save(out / 'city' / f'{name}.gltf')
        index.append({'cell': c, 'file': f'city/{name}.gltf', 'props': len(d['props'])})
    cindex = []
    for c, d in sorted(coll.items()):
        g = Gltf({'originEPSG2180': ORIGIN, 'cell': c, 'collision': True})
        for kind in ('ground', 'walls'):
            if d[kind]:
                V, I = merge(d[kind]); g.node(f'collision_{kind}', [(V[:, :3], I, None)], {'collision': kind})
        name = f'{c[0]}_{c[1]}'
        if g.save(out / 'collision' / f'{name}.gltf'): cindex.append({'cell': c, 'file': f'collision/{name}.gltf'})
    rindex = []
    for ev, d in sorted(races.items()):
        g = Gltf({'originEPSG2180': ORIGIN, 'event': ev})
        for t, parts in sorted(d['visual'].items(), key=lambda kv: str(kv[0])):
            M = merge(parts)
            g.node(f'race_{VC if t == VC else tex[t]["name"]}', [(M[0], M[1], mat_for(g, t, tex)) + M[2:]])
        if d['collision']:
            V, I = merge(d['collision']); g.node('race_collision', [(V[:, :3], I, None)], {'collision': 'walls'})
        if g.save(out / 'races' / f'{ev}.gltf'): rindex.append({'event': ev, 'file': f'races/{ev}.gltf'})
    return index, cindex, rindex, props


def read_tmshj(path):
    b = Path(path).read_bytes()
    if b[:8] != b'TMSHj001': raise ValueError(f'{path}: not TMSHj001')
    o = 8; n = struct.unpack_from('<I', b, o)[0]; o += 4; ims = []
    for _ in range(n):
        w, h, ln = struct.unpack_from('<III', b, o); o += 12; ims.append(b[o:o + ln]); o += ln
    raw_len, z_len = struct.unpack_from('<II', b, o); o += 8
    raw = zlib.decompress(b[o:o + z_len])
    if len(raw) != raw_len: raise ValueError(f'{path}: mesh size mismatch')
    p = 0; nc = struct.unpack_from('<I', raw, p)[0]; p += 4; chunks = []
    for _ in range(nc):
        t, nv, ni = struct.unpack_from('<III', raw, p); p += 12
        V = np.frombuffer(raw, '<f4', nv * 5, p).reshape(nv, 5); p += nv * 20
        I = np.frombuffer(raw, '<u2', ni, p); p += ni * 2
        chunks.append((t, V, I))
    return ims, chunks


def export_photo(custom, out):
    index = []
    for e in json.loads((custom / 'stream-manifest.json').read_text()):
        a = e['A']
        if a.get('format') != 'TMSHj001': continue
        ims, chunks = read_tmshj(custom / 'stream' / a['file'])
        tile = e['tile']; d = out / 'photo' / tile; d.mkdir(parents=True, exist_ok=True)
        g = Gltf({'originEPSG2180': ORIGIN, 'tile': tile, 'source': 'Urząd Miasta Lublin 3D mesh 2022 (gis.lublin.eu)'})
        by = {}
        for t, V, I in chunks: by.setdefault(t, []).append((V, I))
        for t, parts in sorted(by.items()):
            fn = f'{tile}_t{t}.jpg'; (d / fn).write_bytes(ims[t])
            V, I = merge(parts)
            g.node(f'photo_t{t}', [(V, I, g.material(t, f'{tile}_t{t}', fn, CLAMP, True))])
        if g.save(d / f'{tile}.gltf'):   # a tile can be empty after cleanup (all photo replaced)
            index.append({'tile': tile, 'file': f'photo/{tile}/{tile}.gltf', 'bboxLocal': e['bbox']})
        elif not any(d.iterdir()): d.rmdir()
    return index


def fc(features, name):
    return {'type': 'FeatureCollection', 'name': name,
            'crs': {'type': 'name', 'properties': {'name': 'urn:ogc:def:crs:EPSG::2180'}}, 'features': features}


def feat(geom, props):
    return {'type': 'Feature', 'geometry': geom, 'properties': props}


def r2(v): return [round(float(a), 2) for a in v]


def export_layers(work, custom, props, landmarks, out):
    ox, oy, oz = ORIGIN; L = out / 'layers'; L.mkdir(parents=True, exist_ok=True); counts = {}
    # streets: OSM names
    s = json.loads((custom / 'streets.json').read_text())['streets']
    f = [feat({'type': 'MultiLineString', 'coordinates': [[r2((p[0] + ox, p[1] + oy)) for p in line] for line in lines]}, {'name': n})
         for n, lines in s.items()]
    counts['streets'] = len(f); (L / 'streets.geojson').write_text(json.dumps(fc(f, 'streets'), ensure_ascii=False))
    # traffic lanes (one per direction, right-hand traffic)
    from city_traffic import lanes
    f = []
    for Q, Z in lanes(work, ORIGIN):
        Z = np.broadcast_to(np.asarray(Z, float), (len(Q),))
        f.append(feat({'type': 'LineString', 'coordinates': [r2((q[0] + ox, q[1] + oy, z + oz)) for q, z in zip(Q, Z)]}, {}))
    counts['traffic-lanes'] = len(f); (L / 'traffic-lanes.geojson').write_text(json.dumps(fc(f, 'traffic-lanes')))
    # races
    f = []
    for p in sorted(work.glob('route-*.json')):
        r = json.loads(p.read_text())
        f.append(feat({'type': 'LineString', 'coordinates': [r2(q) for q in r['course']]},
                      {'id': r['id'], 'name': r['name'], 'lengthM': round(r['lengthM']), 'streets': r.get('streets', {}), 'loop': True}))
    counts['races'] = len(f); (L / 'races.geojson').write_text(json.dumps(fc(f, 'races'), ensure_ascii=False))
    # breakable props
    f = [feat({'type': 'Point', 'coordinates': r2((p['x'] + ox, p['y'] + oy, p['z'] + oz))},
              {'id': p['id'], 'kind': p['kind'], 'heightM': round(p['heightM'], 1), 'breakable': True}) for p in props]
    counts['props'] = len(f); (L / 'props.geojson').write_text(json.dumps(fc(f, 'props')))
    # landmarks
    f = [feat({'type': 'Point', 'coordinates': r2((l['x'] + ox, l['y'] + oy))}, {'name': l['name'], 'kind': l.get('kind')}) for l in landmarks]
    counts['landmarks'] = len(f); (L / 'landmarks.geojson').write_text(json.dumps(fc(f, 'landmarks'), ensure_ascii=False))
    # GUGiK LoD2 buildings: footprints + heights (for low-poly / brush-based ports)
    b = json.loads((work / 'lublin-buildings-clipped.json').read_text())['buildings']; f = []
    for bd in b:
        zs = [v[2] for s_ in bd['surfaces'] for v in s_['coordinates']]
        ground = [s_ for s_ in bd['surfaces'] if s_['surface'] == 'GroundSurface' and len(s_['coordinates']) >= 3]
        if not ground or not zs: continue
        rings = [[r2(v[:2]) for v in g['coordinates']] for g in ground]
        rings = [r + [r[0]] if r[0] != r[-1] else r for r in rings]
        f.append(feat({'type': 'MultiPolygon', 'coordinates': [[r] for r in rings]},
                      {'id': bd.get('id'), 'groundZ': round(min(zs), 2), 'roofTopZ': round(max(zs), 2), 'heightM': round(max(zs) - min(zs), 1)}))
    counts['buildings'] = len(f); (L / 'buildings.geojson').write_text(json.dumps(fc(f, 'buildings')))
    return counts


def export_terrain(work, out):
    meta = json.loads((work / 'terrain-build/terrain.json').read_text())
    G = np.load(work / 'terrain-build/terrain-5m.npy').astype(float)
    lo, hi = float(G.min()), float(G.max())
    q = np.rint((G - lo) / (hi - lo) * 65535).astype('>u2')
    (out / 'terrain').mkdir(parents=True, exist_ok=True)
    Image.frombytes('I;16B', (G.shape[1], G.shape[0]), q.tobytes()).save(out / 'terrain/heightmap.png')
    np.save(out / 'terrain/heightmap-5m.npy', G.astype('<f4'))
    j = {'boundsEPSG2180': meta['boundsEPSG2180'], 'cellM': meta['meshCellM'], 'columns': G.shape[1], 'rows': G.shape[0],
         'row0': 'north', 'heightDatum': meta['heightDatum'], 'minHeightM': lo, 'maxHeightM': hi,
         'decode': 'height = minHeightM + png/65535 * (maxHeightM - minHeightM)', 'source': 'GUGiK NMT 1 m (2017), resampled to 5 m'}
    (out / 'terrain/heightmap.json').write_text(json.dumps(j, indent=1))
    return j


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True, type=Path, help='pipeline work directory')
    ap.add_argument('--custom-city', required=True, type=Path, help='directory with PL01.town and stream/')
    ap.add_argument('--landmarks', type=Path, help='landmarks JSON: [{name,x,y,kind}] in local metres')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--skip-photo', action='store_true')
    a = ap.parse_args(); out = a.out; out.mkdir(parents=True, exist_ok=True)
    pkg = read_town(a.custom_city / 'PL01.town')
    tex = export_textures(pkg, out); print('textures', len(tex))
    city, coll, races, props = export_town(pkg, tex, out); print('city cells', len(city), 'collision cells', len(coll), 'races', len(races), 'props', len(props))
    if a.skip_photo:   # keep the index of photo tiles exported earlier
        prev = out / 'manifest.json'
        photo = json.loads(prev.read_text()).get('photo', []) if prev.exists() else []
    else:
        photo = export_photo(a.custom_city, out)
    print('photo tiles', len(photo))
    landmarks = json.loads(a.landmarks.read_text()) if a.landmarks else []
    counts = export_layers(a.work, a.custom_city, props, landmarks, out); print('layers', counts)
    terrain = export_terrain(a.work, out)
    manifest = {
        'name': 'Lublin Open Map', 'version': 1,
        'coordinates': {'crs': 'EPSG:2180 (PUWG 1992) + PL-KRON86-NH heights', 'originEPSG2180': ORIGIN,
                        'local': 'local = (easting, northing, height) - originEPSG2180, metres, Z up',
                        'gltf': 'glTF Y up: gltf = (local.x, local.z, -local.y)', 'cellM': CELL},
        'city': city, 'collision': coll, 'races': races, 'photo': photo,
        'layers': {k: f'layers/{k}.geojson' for k in counts}, 'layerCounts': counts, 'terrain': 'terrain/heightmap.json',
        'notes': ['photo/ tiles and city/ overlap by design: in the photogrammetry zone city/ holds ground, streets and props, photo/ holds buildings',
                  'collision/ is the physics geometry used by the original engine: ground surfaces and walls; props are breakable and not in collision/',
                  'materials: ortho and photo textures are unlit (lighting baked in); procedural textures repeat'],
        'sources': 'see LICENSES.md'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print('done', out)


if __name__ == '__main__':
    main()
