"""Modeled buildings: LoD2 GUGiK planar walls/roofs carrying photogrammetric colour.

Owner of the "game-style" building representation inside MODELED_TILES:
 * geometry = LoD2 CityGML surfaces (lublin-buildings-clipped.json), planar and straight;
 * colour   = baked from the City of Lublin 2022 photo mesh (original source textures)
             by facade-baker.c, ray along each surface normal (first hit, +-OUT/IN m);
 * the photo mesh is removed inside each modeled footprint (buffer REPLACE_BUFFER_M),
   in every streamed tile and LOD, so no doubled facades remain.
Collision is unchanged (LoD2 walls are already the invisible physics; this is visual).
bake() caches results in work/modeled-buildings/; apply() is called by build-town.py.
"""
import hashlib, json, math, struct, subprocess
from city_landmarks import PHOTO_LANDMARK_IDS, FACADE_OVERRIDES, owned_zone
from pathlib import Path
import numpy as np
from PIL import Image
import shapely
from shapely.geometry import Polygon, MultiPoint, LineString
from shapely.ops import unary_union

Image.MAX_IMAGE_PIXELS = None
MODELED_TILES = ['Tile-52-74-1-1', 'Tile-53-74-1-1', 'Tile-54-74-1-1', 'Tile-52-75-1-1', 'Tile-53-75-1-1', 'Tile-54-75-1-1']   # pilot: both sides of Krakowskie Przedmiescie -> Brama Krakowska
OUT_M, IN_M = 1.5, 3.0          # ray starts 1.5 m outside the plane, searches 3 m behind it (LoD2 2017 vs mesh 2022)
REPLACE_BUFFER_M = 1.8          # covers the whole 1.6 m photo envelope kept by city_mesh_finish (no orphan lumps)
ATLAS = 4096                    # LOD A atlas; LOD C gets a 512 downsample
ATLAS_C = 512
MIN_TEXEL_M = .04
PAD = 2
VERSION = 17
MIN_FACE_HIT = .10            # below this a face has no usable photo (party wall/occluded): building's mean colour
ROUTE_BUFFER_M = 40.0         # (kept for reports) route-side buildings
MODEL_ALL = True              # every building whose LoD2 is hidden in the photo zone is modeled
MIN_BUILDING_HIT = 0.0         # disabled: exterior-wall photo coverage proved unreliable (courtyards); every zone building is modeled
PASSAGE_W, PASSAGE_SPRING = 3.6, 3.0   # arched gate opening: width, height where the arch starts
PASSAGE_EXTEND_M = 4.0                 # passage line extension beyond its mapped ends

def _frame(poly):
    """Plane frame (origin, U, V, N) of a planar 3D polygon. Walls: V is world-up."""
    p = np.asarray(poly, float)
    n = np.zeros(3)
    for a, b in zip(p, np.roll(p, -1, 0)):
        n += [(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])]
    ln = np.linalg.norm(n)
    if ln < 1e-6: return None
    n /= ln
    if abs(n[2]) < .7:
        v = np.array([0, 0, 1.]) - n * n[2]; v /= np.linalg.norm(v); u = np.cross(v, n)
    else:
        h = np.cross([0, 0, 1.], n); hl = np.linalg.norm(h)
        u = h / hl if hl > 1e-3 else np.array([1., 0, 0]); v = np.cross(n, u)
    return p[0], u, v, n

def _assign(centroid, tiles):
    return min(tiles, key=lambda t: np.hypot(*(centroid - t['centre'])))

def _tiles(root):
    out = []
    for f in sorted((root / 'city-mesh-2022/import').glob('Tile-*/A/tile.json')):
        m = json.loads(f.read_text()); b = m['boundsLocal']
        out.append({'tile': m['tile'], 'bbox': (b[0], b[1], b[3], b[4]), 'centre': np.array([(b[0] + b[3]) / 2, (b[1] + b[4]) / 2]),
                    'footprint': Polygon(m['footprintLocal']), 'textures': m['textures']})
    return out

def select(root, origin, mesh_z_offset=0.0):
    ox, oy, oz = origin
    # Same rule as build-town.py's LoD2 replacement (mean wall position inside mesh_zone =
    # tile footprints shrunk 3 m): every building whose LoD2 walls are hidden is modeled here.
    tiles = _tiles(root); cover = unary_union([t['footprint'] for t in tiles]).buffer(-3.0); shapely.prepare(cover)
    import city_skansen; skansen_lod2 = city_skansen.lod2_ids(root, origin)
    passages = []
    for road in json.loads((root / 'terrain-build/roads-with-ground-heights.json').read_text())['roads']:
        t = road['properties']
        if t.get('tunnel') == 'building_passage' or t.get('covered') == 'yes':
            for q in road['parts']:
                if len(q) < 2: continue
                xy = np.asarray(q, float)[:, :2] - [ox, oy]
                # OSM often maps only the covered stretch, ending inside the gate: extend both ends
                # so the line crosses BOTH facades and each gets its arched opening.
                d0 = xy[0] - xy[1]; d1 = xy[-1] - xy[-2]
                d0 /= np.linalg.norm(d0) + 1e-9; d1 /= np.linalg.norm(d1) + 1e-9
                passages.append(LineString(np.vstack([xy[0] + d0 * PASSAGE_EXTEND_M, xy, xy[-1] + d1 * PASSAGE_EXTEND_M])))
    near = unary_union([LineString(np.asarray(json.loads(p.read_text())['course'])[:, :2] - [ox, oy]).buffer(ROUTE_BUFFER_M)
                        for p in sorted(root.glob('route-7*.json'))]); shapely.prepare(near)
    chosen = []
    for b in json.loads((root / 'lublin-buildings-clipped.json').read_text())['buildings']:
        ground = [s for s in b['surfaces'] if s['surface'] == 'GroundSurface' and len(s['coordinates']) >= 3]
        if not ground: continue
        fp = unary_union([Polygon([(v[0] - ox, v[1] - oy) for v in s['coordinates']]).buffer(0) for s in ground])
        walls = [v for s in b['surfaces'] if s['surface'] == 'WallSurface' for v in s['coordinates']]
        if fp.is_empty or not walls: continue
        wx, wy = np.mean([[v[0] - ox, v[1] - oy] for v in walls], axis=0)
        if not shapely.contains_xy(cover, wx, wy): continue
        owner = _assign(np.array(fp.centroid.coords[0]), tiles)['tile']
        if b['id'] in PHOTO_LANDMARK_IDS: continue   # keeps its photo mesh (city_landmarks)
        if b['id'] in skansen_lod2: continue   # hand-modeled (city_skansen); LoD2 stays as collision only
        if MODEL_ALL or owner in MODELED_TILES or near.intersects(fp):
            faces = [np.array(s['coordinates'], float) - [ox, oy, oz] for s in b['surfaces']
                     if s['surface'] in ('WallSurface', 'RoofSurface', 'ClosureSurface') and len(s['coordinates']) >= 3]
            chosen.append({'id': b['id'], 'tile': owner, 'footprint': fp, 'faces': faces,
                           'passages': [g for g in passages if g.intersects(fp)]})
    for b in osm_lod1(root, origin, tiles, cover, mesh_z_offset):
        b['passages'] = [g for g in passages if g.intersects(b['footprint'])]; chosen.append(b)
    return chosen, tiles

def _source_rgb(root, cache, tile, mat, meta):
    src = root / 'city-mesh-2022' / tile / meta['textures'][str(mat)]['source']
    raw = cache / f'src-{tile}-{mat}.rgb'
    if not raw.exists():
        im = Image.open(src).convert('RGB'); raw.write_bytes(im.tobytes()); size = im.size
    else:
        size = Image.open(src).size
    return raw, size

def bake(root, origin, mesh_z_offset):
    root = Path(root).resolve(); cache = root / 'modeled-buildings'; cache.mkdir(exist_ok=True)
    chosen, tiles = select(root, origin, mesh_z_offset)
    key = hashlib.sha256(json.dumps([VERSION, MODELED_TILES, OUT_M, IN_M, ATLAS, MIN_TEXEL_M, round(mesh_z_offset, 4),
                                     sorted(b['id'] for b in chosen)]).encode()).hexdigest()[:16]
    stamp = cache / 'bake.json'
    if stamp.exists() and json.loads(stamp.read_text()).get('key') == key: return json.loads(stamp.read_text())
    report = {'key': key, 'tiles': {}, 'buildings': len(chosen), 'meshZOffsetM': mesh_z_offset,
              'source': 'geometry LoD2 GUGiK (lublin-buildings-clipped.json), or LoD1 from an OSM outline newer than LoD2 2017 (height from the 2022 mesh); colour baked from UM Lublin mesh 2022'}
    baker = root / 'facade-baker'
    if not baker.exists() or baker.stat().st_mtime < (root / 'facade-baker.c').stat().st_mtime:
        subprocess.run(['cc', '-O3', '-o', str(baker), str(root / 'facade-baker.c'), '-lpthread'], check=True)
    ox, oy, oz = origin
    all_fp = unary_union([Polygon([(v[0] - ox, v[1] - oy) for v in s_['coordinates']]).buffer(0)
                          for b_ in json.loads((root / 'lublin-buildings-clipped.json').read_text())['buildings']
                          for s_ in b_['surfaces'] if s_['surface'] == 'GroundSurface' and len(s_['coordinates']) >= 3]); shapely.prepare(all_fp)
    passages_of = {b['id']: b['passages'] for b in chosen}; accepted_all = []; rejected_all = []
    base_of = {b['id']: min(float(np.min(q[:, 2])) for q in b['faces']) for b in chosen if b['faces']}
    for tile in sorted({b['tile'] for b in chosen}):
        mine = [b for b in chosen if b['tile'] == tile]
        if not mine: continue
        # Surfaces -> plane frames and rectangles; texel chosen so the tile fits one atlas.
        faces = []
        for b in mine:
            for poly in b['faces']:
                fr = _frame(poly)
                if fr is None: continue
                o, u, v, n = fr; d = poly - o; uv = np.stack([d @ u, d @ v], 1)
                lo_, hi_ = uv.min(0), uv.max(0)
                if (hi_ - lo_).min() < .05: continue
                faces.append({'b': b['id'], 'poly': poly, 'o': o, 'u': u, 'v': v, 'n': n, 'uv': uv, 'lo': lo_, 'hi': hi_})
        for f in faces:   # exterior-wall flag (for the LoD2-vs-photo match) and arched gate openings
            f['ext'] = False; f['cuts'] = []
            if abs(f['n'][2]) >= .7: continue
            nxy = f['n'][:2] / (np.linalg.norm(f['n'][:2]) + 1e-9)
            a_ = f['o'] + f['lo'][0] * f['u']; c_ = f['o'] + f['hi'][0] * f['u']; mid = (a_[:2] + c_[:2]) / 2 + nxy * 1.0
            f['ext'] = not bool(shapely.contains_xy(all_fp, mid[0], mid[1]))
            if not passages_of[f['b']] or float(np.min(f['poly'][:, 2])) > base_of[f['b']] + 1.0: continue   # arches only in walls standing on the ground
            r_ = PASSAGE_W / 2; ux = f['u'][:2]
            seg = LineString([a_[:2] - ux * (r_ + .5), c_[:2] + ux * (r_ + .5)])   # reach: an opening at a corner spans both walls
            for pl in passages_of[f['b']]:
                hit = seg.intersection(pl)
                for pt in getattr(hit, 'geoms', [hit]):
                    if pt.is_empty or pt.geom_type != 'Point': continue
                    uc = float((np.array(pt.coords[0]) - f['o'][:2]) @ f['u'][:2]); vb = float(f['lo'][1]); r_ = PASSAGE_W / 2
                    f['cuts'].append(shapely.box(uc - r_, vb - 1, uc + r_, vb + PASSAGE_SPRING).union(shapely.Point(uc, vb + PASSAGE_SPRING).buffer(r_, quad_segs=8)))
        faces.append({'b': None, 'stone': True, 'o': np.array([0., 0, -1e4]), 'u': np.array([1., 0, 0]), 'v': np.array([0., 1, 0]),
                      'n': np.array([0., 0, 1]), 'uv': np.zeros((3, 2)), 'lo': np.zeros(2), 'hi': np.array([.3, .3]), 'ext': False, 'cuts': []})
        area = sum(float(np.prod(f['hi'] - f['lo'])) for f in faces)
        def pack(size, texel):
            for f in faces: f['w'], f['h'] = [int(math.ceil(x / texel)) + 2 * PAD for x in f['hi'] - f['lo']]
            order = sorted(range(len(faces)), key=lambda i: -faces[i]['h']); x = y = shelf = 0
            for i in order:
                f = faces[i]
                if f['w'] > size: return False
                if x + f['w'] > size: x = 0; y += shelf; shelf = 0
                f['x'], f['y'] = x, y; x += f['w']; shelf = max(shelf, f['h'])
            return y + shelf <= size
        # Smallest power-of-two atlas holding the tile at MIN_TEXEL_M; else 4096 with a coarser texel.
        asz = next((s for s in (512, 1024, 2048) if pack(s, MIN_TEXEL_M)), ATLAS)
        texel = MIN_TEXEL_M if asz < ATLAS else max(MIN_TEXEL_M, math.sqrt(area / (.70 * ATLAS * ATLAS)))
        while not pack(asz, texel): texel *= 1.08
        # Queries: every texel centre of every face rectangle (padding included, clamped later).
        qs = []
        for f in faces:
            gx = (np.arange(f['w']) - PAD + .5) * texel + f['lo'][0]; gy = (np.arange(f['h']) - PAD + .5) * texel + f['lo'][1]
            gu, gv = np.meshgrid(gx, gy[::-1])   # atlas row 0 = top of the face
            p = f['o'] + gu[..., None] * f['u'] + gv[..., None] * f['v']
            qs.append(np.concatenate([p.reshape(-1, 3), np.broadcast_to(f['n'], (p.shape[0] * p.shape[1], 3))], 1))
        qs = np.concatenate(qs).astype('<f4')
        # Photo triangles of every tile near these buildings, original source textures.
        bx = unary_union([b['footprint'] for b in mine]).buffer(4).bounds
        tris = []; texlist = []
        for t in tiles:
            tb = t['bbox']
            if tb[2] < bx[0] or tb[0] > bx[2] or tb[3] < bx[1] or tb[1] > bx[3]: continue
            z = np.load(root / 'city-mesh-2022/import' / t['tile'] / 'A/mesh.npz'); slot = {}
            for i in range(int(z['count'])):
                m = int(z[f'm{i}']); vv = z[f'v{i}'].astype(np.float64); ii = z[f'i{i}'].astype(np.int64).reshape(-1, 3)
                if m not in slot:
                    raw, size = _source_rgb(root, cache, t['tile'], m, t); slot[m] = len(texlist); texlist.append((raw, size))
                c = vv[ii, :2].mean(1); sel = (c[:, 0] > bx[0]) & (c[:, 0] < bx[2]) & (c[:, 1] > bx[1]) & (c[:, 1] < bx[3])
                if not sel.any(): continue
                tv = vv[ii[sel]]; tv[..., 2] += mesh_z_offset
                rec = np.zeros(len(tv), dtype=[('p', '<f4', 9), ('uv', '<f4', 6), ('t', '<u4')])
                rec['p'] = tv[..., :3].reshape(-1, 9); uvs = tv[..., 3:5].copy(); uvs[..., 1] = 1 - uvs[..., 1]   # back to OBJ v
                rec['uv'] = uvs.reshape(-1, 6); rec['t'] = slot[m]; tris.append(rec)
        tris = np.concatenate(tris)
        # Photo presence per building (centroids >2 m above its base inside the footprint +1.5 m):
        # a low exterior-wall hit rate only means "LoD2 differs from 2022" when the photo HAS a building there.
        tp = tris['p'].reshape(-1, 3, 3).astype(np.float64); cen = tp.mean(1); photo_here = {}
        tn = np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0]); upright = np.abs(tn[:, 2]) < .5 * (np.linalg.norm(tn, axis=1) + 1e-12)
        for b in mine:   # photo WALLS (upright triangles) standing around this footprint
            base = min(float(np.min(q[:, 2])) for q in b['faces']); zone_ = b['footprint'].buffer(3.0)
            sel = upright & (cen[:, 2] > base + 2) & shapely.contains_xy(zone_, cen[:, 0], cen[:, 1]); photo_here[b['id']] = int(sel.sum())
        inp = cache / f'{tile}.bakein'; outp = cache / f'{tile}.bakeout'
        with open(inp, 'wb') as fh:
            fh.write(b'FBAK1' + struct.pack('<I', len(texlist)))
            for raw, (w, h) in texlist: fh.write(struct.pack('<II', w, h) + str(raw).encode().ljust(256, b'\0'))
            fh.write(struct.pack('<I', len(tris))); fh.write(tris.tobytes())
            fh.write(struct.pack('<Iff', len(qs), OUT_M, IN_M)); fh.write(qs.tobytes())
        log = subprocess.run([str(baker), str(inp), str(outp)], check=True, capture_output=True, text=True).stderr.strip()
        res = np.fromfile(outp, np.uint8).reshape(-1, 4); inp.unlink(); outp.unlink()
        atlas = np.zeros((asz, asz, 3), np.uint8); at = 0; hits = 0
        verts = []; dropped = 0; colour = {}; ext = {}
        for f in faces:   # per-building mean photo colour; exterior-wall photo coverage
            n = f['w'] * f['h']; f['r'] = res[at:at + n].reshape(f['h'], f['w'], 4); at += n
            if f.get('stone'): continue
            ok = f['r'][..., 3] > 0; hits += int(ok.sum())
            c = colour.setdefault(f['b'], [np.zeros(3), 0]); c[0] += f['r'][..., :3][ok].sum(0); c[1] += int(ok.sum())
            pg = Polygon(f['uv']).buffer(0)
            for cut in f['cuts']: pg = pg.difference(cut)
            gx = (np.arange(f['w']) - PAD + .5) * texel + f['lo'][0]; gy = ((np.arange(f['h']) - PAD + .5) * texel + f['lo'][1])[::-1]
            gu, gv = np.meshgrid(gx, gy); f['pg'] = pg; f['inside'] = shapely.contains_xy(pg, gu, gv) if not pg.is_empty else np.zeros(gu.shape, bool)
            if f['ext']:
                e = ext.setdefault(f['b'], [0, 0]); e[0] += int((ok & f['inside']).sum()); e[1] += int(f['inside'].sum())
        accepted = {b['id'] for b in mine if b['id'] not in ext or ext[b['id']][1] == 0 or ext[b['id']][0] / ext[b['id']][1] >= MIN_BUILDING_HIT
                    or photo_here[b['id']] < 300}   # nothing in the photo: modeled with the generic facade
        accepted_all += [b for b in mine if b['id'] in accepted]; rejected_all += [b['id'] for b in mine if b['id'] not in accepted]
        stone_uv = None
        for f in faces:
            r = f.pop('r')
            if f.get('stone'):
                atlas[f['y']:f['y'] + f['h'], f['x']:f['x'] + f['w']] = (92, 86, 78)
                stone_uv = ((f['x'] + f['w'] / 2) / asz, (f['y'] + f['h'] / 2) / asz); continue
            if f['b'] not in accepted: continue
            pg, inside = f.pop('pg'), f.pop('inside')
            if pg.is_empty: continue
            if FACADE_OVERRIDES.get(f['b']) == 'concrete_grid' and abs(f['n'][2]) < .7:
                img = _concrete_grid(r.shape[0], r.shape[1], texel)
            elif inside.sum() and (r[..., 3][inside] > 0).mean() < MIN_FACE_HIT:
                dropped += 1; c = colour[f['b']]
                mean = c[0] / c[1] if c[1] else np.array(FACADE_COLOURS[int(hashlib.sha256(f['b'].encode()).hexdigest()[:4], 16) % 3], float)
                img = (_facade(r.shape[0], r.shape[1], texel, mean) if abs(f['n'][2]) < .7
                       else np.broadcast_to((mean * .8).astype(np.uint8), r[..., :3].shape))
            else:
                img = _fill_holes(r)
            atlas[f['y']:f['y'] + f['h'], f['x']:f['x'] + f['w']] = img
            # Geometry: constrained triangulation of the planar polygon (minus gate arches) in its own frame.
            for piece in getattr(pg, 'geoms', [pg]):
                if piece.geom_type != 'Polygon' or piece.area < 1e-4: continue
                for t in shapely.constrained_delaunay_triangles(piece).geoms:
                    xy = np.asarray(t.exterior.coords)[:3]
                    p3 = f['o'] + xy[:, :1] * f['u'] + xy[:, 1:2] * f['v']
                    au = (f['x'] + PAD + (xy[:, 0] - f['lo'][0]) / texel) / asz
                    av = (f['y'] + f['h'] - PAD - (xy[:, 1] - f['lo'][1]) / texel) / asz
                    tri = np.column_stack([p3, au, av])
                    if np.cross(p3[1] - p3[0], p3[2] - p3[0]) @ f['n'] < 0: tri = tri[[0, 2, 1]]
                    verts.append(tri)
        for b in mine:   # vaulted passage through an arched gate (both faces drawn)
            if b['id'] not in accepted or not b['passages'] or stone_uv is None: continue
            base = min(float(np.min(q[:, 2])) for q in b['faces'])
            r_ = PASSAGE_W / 2; prof = [(-r_, 0.), (-r_, PASSAGE_SPRING)] + [(-r_ * math.cos(t), PASSAGE_SPRING + r_ * math.sin(t)) for t in np.linspace(0, math.pi, 9)[1:-1]] + [(r_, PASSAGE_SPRING), (r_, 0.)]
            for pl in b['passages']:
                inner = pl.intersection(b['footprint'].buffer(.05))
                for line in getattr(inner, 'geoms', [inner]):
                    if line.is_empty or line.geom_type != 'LineString' or line.length < .5: continue
                    q = np.asarray(line.coords)
                    for a_, c_ in zip(q[:-1], q[1:]):
                        d_ = c_ - a_; ln = np.linalg.norm(d_)
                        if ln < 1e-3: continue
                        side = np.array([-d_[1], d_[0]]) / ln
                        ring = lambda P, k: np.array([*(P + side * prof[k][0]), base + prof[k][1], *stone_uv])
                        for k in range(len(prof) - 1):
                            A, B, C, D = ring(a_, k), ring(c_, k), ring(c_, k + 1), ring(a_, k + 1)
                            axis_pt = np.array([*((a_ + c_) / 2), base + PASSAGE_SPRING * .6]); nrm = np.cross(B[:3] - A[:3], C[:3] - A[:3])
                            inward = nrm @ (axis_pt - (A[:3] + C[:3]) / 2) >= 0   # one winding facing into the passage
                            verts += [np.array([A, B, C]), np.array([A, C, D])] if inward else [np.array([A, C, B]), np.array([A, D, C])]
        verts = np.concatenate(verts).astype('<f4') if verts else np.zeros((0, 5), '<f4')
        Image.fromarray(atlas).save(cache / f'{tile}-atlas.png')
        np.save(cache / f'{tile}-faces.npy', verts)
        report['tiles'][tile] = {'buildings': len(mine), 'surfaces': len(faces), 'texelM': round(texel, 4), 'atlasPx': asz, 'triangles': len(verts) // 3, 'facesWithoutPhotoMeanColour': dropped,
                                 'hitFraction': round(hits / max(1, len(qs)), 4), 'baker': log}
    fps = [shapely.to_wkb(b['footprint']).hex() for b in accepted_all]
    report['rejectedLoD2Mismatch'] = sorted(rejected_all); report['modeled'] = len(accepted_all)
    (cache / 'footprints.json').write_text(json.dumps(fps))
    report['footprintCount'] = len(fps)
    stamp.write_text(json.dumps(report, indent=1))
    return report

FACADE_COLOURS = [(172, 158, 132), (185, 180, 169), (145, 151, 151)]
def _facade(h, w, texel, colour):
    """Wall without photo: the map's generic LoD2 facade (4 floors x 4 bays per 12 m, as in
    build-town.py) in the building's own mean photo colour, ground floor at the wall base."""
    from PIL import ImageDraw
    c = tuple(int(x) for x in np.clip(colour, 0, 255)); im = Image.new('RGB', (256, 256), c); d = ImageDraw.Draw(im)
    for floor in range(4):
        y = floor * 64; d.rectangle((0, y + 59, 255, y + 63), fill=tuple(max(0, a - 20) for a in c))
        for bay in range(4):
            x = bay * 64; d.rectangle((x + 15, y + 10, x + 49, y + 50), fill=(70, 74, 77)); d.rectangle((x + 18, y + 12, x + 46, y + 47), fill=(76, 111, 130))
            d.line((x + 32, y + 12, x + 32, y + 47), fill=(190, 193, 189), width=2); d.line((x + 18, y + 30, x + 46, y + 30), fill=(190, 193, 189))
            d.rectangle((x + 12, y + 50, x + 52, y + 53), fill=(218, 215, 201))
    n = max(8, round(12 / texel)); tile = np.asarray(im.resize((n, n), Image.LANCZOS))
    big = np.tile(tile, (h // n + 2, w // n + 1, 1))
    return np.ascontiguousarray(big[big.shape[0] - h - PAD:big.shape[0] - PAD, :w])

def _concrete_grid(h, w, texel):
    """Centre for the Meeting of Cultures: white concrete grid (1.9 m bays, 0.35 m members) over dark glazing."""
    bay = max(4, round(1.9 / texel)); mem = max(1, round(.35 / texel))
    img = np.empty((h, w, 3), np.uint8); img[:] = (58, 66, 74)
    rows = (np.arange(h)[::-1] - PAD) % bay < mem; cols = (np.arange(w) - PAD) % bay < mem
    img[rows, :] = (226, 224, 218); img[:, cols] = (226, 224, 218)
    shade = (np.arange(h)[::-1] - PAD) % bay == mem; img[shade, :] = np.minimum(img[shade, :], (150, 150, 146))   # soffit shadow
    return img

def _fill_holes(r):
    """Texels without a photo hit: push-pull fill (smooth local colour, no streaks)."""
    img = r[..., :3].astype(np.float32); w = (r[..., 3] > 0).astype(np.float32)
    if not w.any(): return np.full(img.shape, 128, np.uint8)
    def pull(c, w):
        h, ww = w.shape
        if h <= 1 and ww <= 1: return c / np.maximum(w, 1e-6)[..., None]
        H, W = (h + 1) // 2 * 2, (ww + 1) // 2 * 2
        cp = np.zeros((H, W, 3), np.float32); wp = np.zeros((H, W), np.float32); cp[:h, :ww] = c * w[..., None]; wp[:h, :ww] = w
        cs = cp.reshape(H // 2, 2, W // 2, 2, 3).sum((1, 3)); ws = wp.reshape(H // 2, 2, W // 2, 2).sum((1, 3))
        coarse = pull(cs / np.maximum(ws, 1e-6)[..., None], np.minimum(ws, 1))
        up = coarse.repeat(2, 0).repeat(2, 1)[:h, :ww]
        for ax in (0, 1):   # smooth the upsampled level (no blocky squares)
            up = (np.roll(up, 1, ax) + 2 * up + np.roll(up, -1, ax)) / 4
        return np.where(w[..., None] > 0, c, up)
    return pull(img, w).clip(0, 255).astype(np.uint8)

_state = {}
def _load(root):
    if 'fp' not in _state:
        cache = Path(root) / 'modeled-buildings'
        fps = [shapely.from_wkb(bytes.fromhex(h)) for h in json.loads((cache / 'footprints.json').read_text())]
        zone = unary_union(fps).buffer(REPLACE_BUFFER_M); shapely.prepare(zone); _state['fp'] = zone
    return _state['fp']

LOD1_CLEAR_ABOVE_M = 3.0   # photo above a LoD1 roof by more than this is not that building (jibs, booms)

def _lod1_above():
    """(outlines, roof heights) of the LoD1 blocks built in this process, or None."""
    r = _state.get('lod1Roofs')
    if not r: return None
    if _state.get('lod1AboveFor') is not r:   # built once per LoD1 set, not per chunk
        _state['lod1Above'] = (shapely.STRtree([p.buffer(REPLACE_BUFFER_M) for p, _ in r]), np.array([z for _, z in r])); _state['lod1AboveFor'] = r
    return _state['lod1Above']

def apply(root, tile, lod, kept, images):
    """kept: [(texslot, verts(N,5), idx)], images: [PIL]. Removes photo triangles inside the
    modeled zone; appends this tile's modeled faces with their atlas. Returns (kept, images, removed)."""
    zone = _load(root); out = []; removed = 0; above = _lod1_above()
    for slot, vv, ii in kept:
        tri = ii.reshape(-1, 3).astype(np.int64); c = vv[tri, :2].mean(1)
        inside = shapely.contains_xy(zone, c[:, 0], c[:, 1])
        if above is not None and inside.any():   # pieces well above a LoD1 roof (crane jibs) stay for drop_loose
            area, roof = above; z = vv[tri, 2].min(1); k = np.flatnonzero(inside)
            hit = area.query(shapely.points(c[k]), predicate='within')
            keep = np.zeros(len(k), bool); keep[hit[0]] = z[k[hit[0]]] > roof[hit[1]] + LOD1_CLEAR_ABOVE_M
            inside[k[keep]] = False
        removed += int(inside.sum())
        if inside.all(): continue
        out.append((slot, vv, tri[~inside].reshape(-1).astype('<u2')))
    cache = Path(root) / 'modeled-buildings'
    if (cache / f'{tile}-faces.npy').exists():
        verts = np.load(cache / f'{tile}-faces.npy'); atlas = Image.open(cache / f'{tile}-atlas.png').convert('RGB')
        if lod != 'A': atlas = atlas.resize((max(64, atlas.width // 8),) * 2, Image.LANCZOS)
        slot = len(images); images = images + [atlas]
        for s in range(0, len(verts), 65535 - 65535 % 3):
            vv = verts[s:s + 65535 - 65535 % 3]; out.append((slot, vv, np.arange(len(vv), dtype='<u2')))
    return out, images, removed

LEFTOVER_M = 6.0   # photo pieces mostly within this distance of modeled buildings are leftovers

LOD1_SKIP = {'ruins', 'collapsed', 'no'}   # remains are not solid blocks
LOD1_CANOPY = {'roof', 'carport'}   # open structures: roof slab on posts, no walls
CANOPY_SLAB_M, CANOPY_POST_M, CANOPY_MAX_POSTS = .35, .3, 16
LOD1_MIN_AREA_M2, LOD1_MIN_HEIGHT_M, LOD1_TOP_QUANTILE = 12.0, 2.5, .95
# The mesh quantile also catches tree canopy and 2022 cranes over the outline (a garage under a
# chestnut came out 22 m tall). OSM height/levels, or a single-storey building type, bound it from above.
LOD1_LOW_TYPES = {'garage': 4.5, 'garages': 4.5, 'shed': 4.5, 'carport': 4.5, 'roof': 5.0, 'kiosk': 4.5,
                  'hut': 4.5, 'cabin': 4.5, 'guardhouse': 4.5, 'greenhouse': 5.0, 'outbuilding': 5.5,
                  'farm_auxiliary': 7.0, 'service': 6.0}
LOD1_STOREY_M, LOD1_SLENDER = 3.3, 2.5   # untagged: height over LOD1_SLENDER*sqrt(area)+3 is not that building

def _metres(v):
    try: return float(str(v).split()[0].replace(',', '.'))
    except (ValueError, IndexError): return None

def _lod1_cap(tags):
    """Upper bound (m above the outline's highest ground) from OSM tags, or None when untagged."""
    h = _metres(tags.get('height'))
    if h and h > 0: return h * 1.1 + 1.0
    lv = _metres(tags.get('building:levels'))
    if lv and lv > 0: return (lv + (_metres(tags.get('roof:levels')) or 0)) * LOD1_STOREY_M + 2.5
    return LOD1_LOW_TYPES.get(tags.get('building'))

def _osm_buildings(root, origin):
    """[(way id, tags, outline polygon in local metres)] for every closed OSM building way (ODbL)."""
    if 'osm' in _state: return _state['osm']
    import xml.etree.ElementTree as ET
    from pyproj import Transformer
    ox, oy = origin[:2]; tr = Transformer.from_crs(4326, 2180, always_xy=True); nodes = {}; ways = {}
    for path in sorted((Path(root) / 'osm-tiles').glob('*.osm')):
        t = ET.parse(path).getroot()
        for n in t.findall('node'): nodes[n.get('id')] = (float(n.get('lon')), float(n.get('lat')))
        for w in t.findall('way'):
            tags = {x.get('k'): x.get('v') for x in w.findall('tag')}
            if 'building' in tags: ways[w.get('id')] = (tags, [x.get('ref') for x in w.findall('nd')])
    out = []
    for wid, (tags, refs) in sorted(ways.items()):   # tiles overlap: one entry per way
        if len(refs) >= 4 and all(r in nodes for r in refs):
            p = Polygon([tuple(np.array(tr.transform(*nodes[r])) - [ox, oy]) for r in refs]).buffer(0)
            if not p.is_empty and p.area > 0: out.append((wid, tags, p))
    _state['osm'] = out
    return out

def _osm_only(root, origin):
    """The OSM outlines not covered by any LoD2 building (newer than the 2017 LoD2): area not
    covered by LoD2 (+1 m) must exceed half. Per outline, against only the LoD2 ground polygons
    it touches (a city-wide union re-buffered for every OSM outline took hours)."""
    ox, oy = origin[:2]
    lod2 = [Polygon([(v[0] - ox, v[1] - oy) for v in s['coordinates']]).buffer(0)
            for b in json.loads((Path(root) / 'lublin-buildings-clipped.json').read_text())['buildings']
            for s in b['surfaces'] if s['surface'] == 'GroundSurface' and len(s['coordinates']) >= 3]
    lod2 = shapely.buffer(np.array([g for g in lod2 if not g.is_empty], dtype=object), 1); tree = shapely.STRtree(lod2)
    out = []
    for wid, tags, p in _osm_buildings(root, origin):
        hit = tree.query(p, predicate='intersects')
        covered = unary_union(lod2[hit]).intersection(p).area if len(hit) else 0.0
        if p.area - covered > .5 * p.area: out.append((wid, tags, p))
    return out

def osm_only_footprints(root, origin):
    """Union of the OSM-only outlines: their photo mesh is never treated as a leftover."""
    u = unary_union([p for _, _, p in _osm_only(root, origin)]); shapely.prepare(u); return u

def _terrain(root):
    """Bilinear sampler of the GUGiK NMT 5 m grid (local metres -> local height)."""
    meta = json.loads((Path(root) / 'terrain-build/terrain.json').read_text())
    G = np.load(Path(root) / 'terrain-build/terrain-5m.npy').astype(np.float64)
    x0, _, _, y1 = meta['boundsEPSG2180']
    def sample(x, y, origin):
        ox, oy, oz = origin
        r = np.clip((y1 - (np.asarray(y) + oy)) / 5, 0, G.shape[0] - 1.000001); c = np.clip((np.asarray(x) + ox - x0) / 5, 0, G.shape[1] - 1.000001)
        i, j = r.astype(int), c.astype(int); f, u = r - i, c - j
        return (G[i, j] * (1 - u) * (1 - f) + G[i, j + 1] * u * (1 - f) + G[i + 1, j] * (1 - u) * f + G[i + 1, j + 1] * u * f) - oz
    return sample

def osm_lod1(root, origin, tiles, cover, mesh_z_offset):
    """OSM-only buildings inside the photo zone as LoD1 blocks: walls along the OSM outline (and its
    courtyards), a flat roof at the 2022 mesh height (LOD1_TOP_QUANTILE of the photo vertices inside
    the outline shrunk 1 m), base on the NMT. Without enough photo evidence the outline is skipped
    (its photo mesh stays as it is). Raw mesh heights are cached per outline set."""
    root = Path(root); cache = root / 'modeled-buildings'; cache.mkdir(exist_ok=True)
    cand = []; owned = owned_zone(); landmark = 0
    for wid, tags, p in _osm_only(root, origin):
        if tags.get('building') in LOD1_SKIP or p.area < LOD1_MIN_AREA_M2: continue
        if p.intersects(owned): landmark += 1; continue   # a hand-modeled landmark owns this spot (city_landmarks)
        c = p.representative_point()
        if not shapely.contains_xy(cover, c.x, c.y): continue
        q = shapely.orient_polygons(p.simplify(.15))
        if q.geom_type == 'Polygon' and q.is_valid and not q.is_empty: cand.append((wid, tags, q))
    key = hashlib.sha256(json.dumps([VERSION, LOD1_TOP_QUANTILE,
                                     [(w, shapely.to_wkb(p).hex()) for w, _, p in cand]]).encode()).hexdigest()[:16]
    stamp = cache / 'osm-lod1.json'
    tops = json.loads(stamp.read_text())['tops'] if stamp.exists() and json.loads(stamp.read_text()).get('key') == key else None
    if tops is None:
        tops = {}; inner = {w: p.buffer(-1.0) for w, _, p in cand}
        for t in tiles:
            tb = t['bbox']; mine = [w for w, _, p in cand if not inner[w].is_empty and shapely.intersects(inner[w], shapely.box(*tb))]
            if not mine: continue
            z = np.load(root / 'city-mesh-2022/import' / t['tile'] / 'A/mesh.npz')
            P = np.concatenate([z[f'v{i}'][:, :3].astype(np.float64) for i in range(int(z['count']))])
            for w in mine:
                b = inner[w].bounds; s_ = (P[:, 0] > b[0]) & (P[:, 0] < b[2]) & (P[:, 1] > b[1]) & (P[:, 1] < b[3])
                if not s_.any(): continue
                q = P[s_]; q = q[shapely.contains_xy(inner[w], q[:, 0], q[:, 1])]
                if len(q): tops.setdefault(w, []).extend(q[:, 2].tolist())
        tops = {w: [len(v), float(np.quantile(v, LOD1_TOP_QUANTILE))] for w, v in tops.items()}   # raw mesh z
        stamp.write_text(json.dumps({'key': key, 'tops': tops}))
    ground = _terrain(root); out = []; report = {'candidates': len(cand), 'landmarkOwned': landmark, 'heightCapped': 0, 'implausibleSkipped': 0, 'built': 0, 'canopies': 0, 'noPhoto': 0, 'tooLow': 0}
    for wid, tags, p in cand:
        ring = np.asarray(p.exterior.coords)[:-1]
        base = float(np.min(ground(ring[:, 0], ring[:, 1], origin))) - .3
        if wid not in tops or tops[wid][0] < 30: report['noPhoto'] += 1; continue
        top = tops[wid][1] + mesh_z_offset; cap = _lod1_cap(tags)
        if cap is not None:
            high = float(np.max(ground(ring[:, 0], ring[:, 1], origin))) + cap
            if top > high: top = high; report['heightCapped'] += 1
        elif top - base > LOD1_SLENDER * p.area ** .5 + 3:   # canopy/crane over an untagged outline: keep its photo mesh
            report['implausibleSkipped'] += 1; continue
        if top - base < LOD1_MIN_HEIGHT_M: report['tooLow'] += 1; continue
        faces = []; canopy = tags.get('building') in LOD1_CANOPY
        low = top - CANOPY_SLAB_M if canopy else base      # walls, or the slab's edge band
        for r in [p.exterior, *p.interiors]:   # oriented: exterior CCW, holes CW -> outward wall normals
            q = np.asarray(r.coords)
            for a_, b_ in zip(q[:-1], q[1:]):
                if np.hypot(*(b_ - a_)) < .3: continue
                faces.append(np.array([[*a_, low], [*b_, low], [*b_, top], [*a_, top]]))
        roofs = [p] if not p.interiors else [shapely.orient_polygons(g) for g in shapely.constrained_delaunay_triangles(p).geoms]   # CCW: roof normal up
        if canopy:
            for g in roofs:   # underside: reversed ring, normal down
                faces.append(np.column_stack([np.asarray(g.exterior.coords)[:-1][::-1], np.full(len(g.exterior.coords) - 1, low)]))
            corners = np.asarray(p.buffer(-CANOPY_POST_M).exterior.coords)[:-1] if not p.buffer(-CANOPY_POST_M).is_empty else ring
            for c_ in corners[np.linspace(0, len(corners) - 1, min(len(corners), CANOPY_MAX_POSTS)).astype(int)]:
                h_ = CANOPY_POST_M / 2
                sq = [c_ + d for d in ((-h_, -h_), (h_, -h_), (h_, h_), (-h_, h_))]
                for a_, b_ in zip(sq, sq[1:] + sq[:1]): faces.append(np.array([[*a_, base], [*b_, base], [*b_, low], [*a_, low]]))
        for g in roofs: faces.append(np.column_stack([np.asarray(g.exterior.coords)[:-1], np.full(len(g.exterior.coords) - 1, top)]))   # roof last (lod1Roofs)
        out.append({'id': f'OSM-way-{wid}', 'tile': _assign(np.array(p.centroid.coords[0]), tiles)['tile'], 'footprint': p, 'faces': faces})
        report['built'] += 1; report['canopies'] += canopy
    _state['lod1Report'] = report; _state['lod1Roofs'] = [(b['footprint'], b['faces'][-1][0, 2]) for b in out]
    return out

def drop_leftovers(root, kept, photo_slots, osm_only):
    """Remove connected photo pieces that lie (>70 %) within LEFTOVER_M of modeled buildings and not
    (>30 %) inside OSM-only buildings. Returns (kept, removed triangles)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    near = _state.get('near')
    if near is None:
        cache = Path(root) / 'modeled-buildings'
        fps = [shapely.from_wkb(bytes.fromhex(h)) for h in json.loads((cache / 'footprints.json').read_text())]
        near = _state['near'] = unary_union(shapely.buffer(np.array(fps, dtype=object), LEFTOVER_M)); shapely.prepare(near)
    shapely.prepare(osm_only)   # reused for every chunk
    out = []; removed = 0
    for slot, vv, ii in kept:
        if slot >= photo_slots: out.append((slot, vv, ii)); continue
        tri = ii.reshape(-1, 3).astype(np.int64); c = vv[tri, :2].mean(1)
        a = shapely.contains_xy(near, c[:, 0], c[:, 1])
        if not a.any(): out.append((slot, vv, ii)); continue
        b = shapely.contains_xy(osm_only, c[:, 0], c[:, 1]); n = len(vv)
        rows = np.concatenate([tri[:, 0], tri[:, 1]]); cols = np.concatenate([tri[:, 1], tri[:, 2]])
        _, label = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n)), directed=False)
        comp = label[tri[:, 0]]; k = comp.max() + 1; cnt = np.bincount(comp, minlength=k)
        frac_near = np.bincount(comp, weights=a, minlength=k) / cnt; frac_osm = np.bincount(comp, weights=b, minlength=k) / cnt
        drop = ((frac_near > .7) & (frac_osm < .3))[comp]; removed += int(drop.sum())
        if not drop.all(): out.append((slot, vv, tri[~drop].reshape(-1).astype('<u2')))
    return out, removed
