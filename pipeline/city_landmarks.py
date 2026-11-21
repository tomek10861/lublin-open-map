"""Landmarks the photo mesh cannot carry: modeled by hand from public references.

Muszla Koncertowa im. Romualda Lipki (Ogród Saski): OSM way 887354591 (two round footprints:
shell + backstage); GUGiK orthophoto: white shell at local (788.4, 141.0), about 20 x 16 m, the
fan of green benches to the east-south-east, backstage under the trees to the north-west.
Model: quarter-ellipsoid shell (white membrane, 6 dark ribs parallel to the opening rim),
round stage on a stone plinth, low timber backstage, fan-shaped bench rows.
Each landmark owns: zone() where the photo mesh is removed, meshes() and collision().
"""
import math
import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

MUSZLA = {'centre': (788.4, 141.0), 'facing_deg': -22.0, 'half_width': 10.0, 'depth': 8.0, 'height': 9.5,
          'stage_r': 7.0, 'backstage': (777.5, 147.5), 'backstage_r': 6.0, 'backstage_h': 4.2,
          'rows': (12.5, 30.0, .9), 'fan_deg': 55.0, 'aisles_deg': (-18.0, 18.0)}

def _frame(m):
    a = math.radians(m['facing_deg']); f = np.array([math.cos(a), math.sin(a)]); s = np.array([-f[1], f[0]])
    return np.asarray(m['centre'], float), f, s

def zone(m=MUSZLA):
    c, f, s = _frame(m)
    fan = [tuple(c)] + [tuple(c + m['rows'][1] * 1.05 * (f * math.cos(math.radians(t)) + s * math.sin(math.radians(t))))
                        for t in np.linspace(-m['fan_deg'] - 5, m['fan_deg'] + 5, 24)]
    return unary_union([Point(*c).buffer(m['half_width'] + 2.5), Point(*m['backstage']).buffer(m['backstage_r'] + 1.5), Polygon(fan)])

def collision(m=MUSZLA):
    """Solid outlines (each its own collision mesh): shell + stage + backstage, and the bench fan."""
    c, f, s = _frame(m)
    fan = [tuple(c + f * 10.5)] + [tuple(c + (m['rows'][1] + .6) * (f * math.cos(math.radians(t)) + s * math.sin(math.radians(t))))
                                  for t in np.linspace(-m['fan_deg'] - 2, m['fan_deg'] + 2, 20)]
    return [_shell_collision(m), Polygon(fan).buffer(0)]

def _shell_collision(m):
    c, f, s = _frame(m)
    return unary_union([Point(*c).buffer(m['half_width'] + .3).intersection(Polygon([tuple(c - f * 12 - s * 12), tuple(c + f * 1.5 - s * 12),
                        tuple(c + f * 1.5 + s * 12), tuple(c - f * 12 + s * 12)])),
                        Point(*(c + f * 2)).buffer(m['stage_r']), Point(*m['backstage']).buffer(m['backstage_r'])])

class _Mesh:
    def __init__(self): self.V, self.I = [], []
    def tri_strip(self, rows, inside=None):
        """rows: list of lists of (x,y,z,u,v) with equal length; one winding, facing away from `inside`."""
        R = [np.asarray(r, float) for r in rows]; n = len(R[0])
        for i in range(len(R) - 1):
            for j in range(n - 1):
                quad = [R[i][j], R[i][j + 1], R[i + 1][j + 1], R[i + 1][j]]
                k = len(self.V); self.V.extend(q.tolist() for q in quad)
                a, b, c = (q[:3] for q in quad[:3]); nrm = np.cross(b - a, c - a)
                flip = inside is not None and nrm @ ((a + c) / 2 - np.asarray(inside, float)) < 0
                self.I.extend([k, k + 2, k + 1, k, k + 3, k + 2] if flip else [k, k + 1, k + 2, k, k + 2, k + 3])
    def box(self, p0, p1, w, h, z0):
        p0, p1 = np.asarray(p0, float), np.asarray(p1, float); d = p1 - p0; L = np.linalg.norm(d) or 1e-3
        n = np.array([-d[1], d[0]]) / L * w / 2; c = [p0 - n, p1 - n, p1 + n, p0 + n]; mid = np.array([*((p0 + p1) / 2), z0 + h / 2])
        for i in range(4):
            j = (i + 1) % 4; ln = np.linalg.norm(c[j] - c[i])
            self.tri_strip([[(*c[i], z0, 0, 1), (*c[j], z0, ln / 2, 1)], [(*c[i], z0 + h, 0, 0), (*c[j], z0 + h, ln / 2, 0)]], mid)
        self.tri_strip([[(*c[0], z0 + h, 0, 0), (*c[1], z0 + h, L / 2, 0)], [(*c[3], z0 + h, 0, w / 2), (*c[2], z0 + h, L / 2, w / 2)]], mid - [0, 0, h])
    def cylinder(self, centre, r, z0, h, seg=32):
        c = np.asarray(centre, float); pts = [c + r * np.array([math.cos(t), math.sin(t)]) for t in np.linspace(0, 2 * math.pi, seg + 1)]
        mid = (*c, z0 + h / 2); circ = 2 * math.pi * r
        self.tri_strip([[(*p, z0, k / seg * circ / 3, h / 3) for k, p in enumerate(pts)], [(*p, z0 + h, k / seg * circ / 3, 0) for k, p in enumerate(pts)]], mid)
        for k in range(seg):   # top disc
            a, b = pts[k], pts[k + 1]; i = len(self.V)
            self.V.extend([[*c, z0 + h, .5, .5], [*a, z0 + h, .5 + (a[0] - c[0]) / r / 2, .5 + (a[1] - c[1]) / r / 2], [*b, z0 + h, .5 + (b[0] - c[0]) / r / 2, .5 + (b[1] - c[1]) / r / 2]])
            self.I.extend([i, i + 1, i + 2])
    def out(self):
        return np.asarray(self.V, '<f4'), np.asarray(self.I, '<u4')

def meshes(ground, m=MUSZLA):
    """Yield (kind, vertices, indices); kinds: membrane, rib, stone, wood, bench."""
    c, f, s = _frame(m); g0 = float(ground(np.array([c[0]]), np.array([c[1]]))[0]); base = g0 + 1.0
    R, D, H = m['half_width'], m['depth'], m['height']
    def shell(theta, phi, scale=1.0):   # opening plane through c, dome behind it
        return np.array([*(c - f * D * scale * math.sin(theta) * math.cos(phi) + s * R * scale * math.cos(theta) * math.cos(phi)), base + H * scale * math.sin(phi)])
    mem = _Mesh(); T = np.linspace(0, math.pi, 25); P = np.linspace(0, math.pi / 2, 13)
    mem.tri_strip([[(*shell(t, p), t / math.pi * 6, p / (math.pi / 2) * 3) for t in T] for p in P], inside=(*(c + f * 6), base + 3))   # inner face lit
    yield 'membrane', *mem.out()
    rib = _Mesh()
    for k in range(6):   # ribs parallel to the opening rim, stepping back over the dome
        x = k / 6 * .92; sc = math.sqrt(max(0.0, 1 - x * x)); pts = []
        for t in np.linspace(-math.pi / 2, math.pi / 2, 19):
            p = np.array([*(c - f * D * x + s * R * sc * math.sin(t) * 1.03), base + H * sc * math.cos(t) * 1.03]); pts.append(p)
        for a, b in zip(pts[:-1], pts[1:]):
            d = b - a; L = np.linalg.norm(d); w = np.array([*f, 0]) * .2; up = np.cross(d / L, np.array([*f, 0])) * .2
            ring = lambda p, q: [(*(p - w - up), 0, q), (*(p + w - up), .2, q), (*(p + w + up), .4, q), (*(p - w + up), .6, q), (*(p - w - up), .8, q)]
            rib.tri_strip([ring(a, 0), ring(b, 1)], inside=(*(c - f * D * x), base))
    yield 'rib', *rib.out()
    stone = _Mesh(); stone.cylinder(c + f * 2, m['stage_r'], g0 - .3, 1.3); yield 'stone', *stone.out()
    wood = _Mesh(); wood.cylinder(m['backstage'], m['backstage_r'], g0 - .2, m['backstage_h'] + .2); yield 'wood', *wood.out()
    bench = _Mesh(); r0, r1, step = m['rows']
    for r in np.arange(r0, r1, step):
        for a0, a1 in zip([-m['fan_deg'], m['aisles_deg'][0] + 1.5, m['aisles_deg'][1] + 1.5], [m['aisles_deg'][0] - 1.5, m['aisles_deg'][1] - 1.5, m['fan_deg']]):
            ang = np.radians(np.arange(a0, a1 + 1e-6, 2.0))
            pts = [c + r * (f * math.cos(t) + s * math.sin(t)) for t in ang]
            for a, b in zip(pts[:-1], pts[1:]):
                gz = float(ground(np.array([(a[0] + b[0]) / 2]), np.array([(a[1] + b[1]) / 2]))[0]) + (r - r0) * .045   # raked seating
                bench.box(a, b, .42, .45, gz)
    yield 'bench', *bench.out()

# Landmarks whose 2022 photo mesh IS the characteristic look (a planar LoD2 box with baked or
# generic facade would erase it): they keep the photo mesh, and no crane is inferred near them
# (their rooftop structures stand well above the LoD2 roof).
PHOTO_LANDMARKS = [
    {'name': 'Centrum Spotkania Kultur', 'lod2': 'ID-0663-26780F22-4C2E-DA8A-E053-CC2BA8C01EC0', 'osm_way': 401769397,
     'crane_free_m': 80.0, 'keep_photo': False, 'facade': 'concrete_grid', 'photo_clear_m': 15.0,
     'why': 'photo mesh loses the glazed ground floor (volumes float): modeled LoD2 with its white concrete grid facade, roof garden baked; user-confirmed no crane (2026-11-18)'},
]
# Walls of these LoD2 buildings get a characteristic procedural facade instead of photo/generic.
FACADE_OVERRIDES = {l['lod2']: l['facade'] for l in PHOTO_LANDMARKS if l.get('facade')}
PHOTO_LANDMARK_IDS = {l['lod2'] for l in PHOTO_LANDMARKS if l.get('keep_photo', True)}

def crane_free_zone(root, origin):
    import json
    ox, oy = origin[:2]; zones = []
    for b in json.loads((root / 'lublin-buildings-clipped.json').read_text())['buildings']:
        hit = [l for l in PHOTO_LANDMARKS if l['lod2'] == b['id']]
        if not hit: continue
        for s in b['surfaces']:
            if s['surface'] == 'GroundSurface' and len(s['coordinates']) >= 3:
                zones.append(Polygon([(v[0] - ox, v[1] - oy) for v in s['coordinates']]).buffer(0).buffer(hit[0]['crane_free_m']))
    return unary_union(zones)

def photo_clear_zone(root, origin):
    """Photo mesh removed around modeled landmarks whose 2022 volumes overhang the 2017 LoD2 footprint."""
    import json
    ox, oy = origin[:2]; zones = []
    for b in json.loads((root / 'lublin-buildings-clipped.json').read_text())['buildings']:
        hit = [l for l in PHOTO_LANDMARKS if l['lod2'] == b['id'] and l.get('photo_clear_m')]
        for s in (b['surfaces'] if hit else []):
            if s['surface'] == 'GroundSurface' and len(s['coordinates']) >= 3:
                zones.append(Polygon([(v[0] - ox, v[1] - oy) for v in s['coordinates']]).buffer(0).buffer(hit[0]['photo_clear_m']))
    return unary_union(zones)

# Portal Wilno-Lublin (OSM node "Portal Wilno-Lublin", artwork/installation): concrete ring
# with a round live screen (the Vilnius square), on a low plinth. Plane across the promenade.
PORTAL = {'centre': (1747.7, -51.0),   # GPS 51.24781 N, 22.55980 E (user-provided; OSM node is 4 m off)
           'facing_deg': 0.0, 'outer_r': 1.8, 'inner_r': 1.2, 'depth': .6, 'plinth': .15}

def portal_zone(m=PORTAL):
    return Point(*m['centre']).buffer(4.0)

def owned_zone():
    """Spots owned by hand-modeled landmarks: no other generator (e.g. OSM LoD1 blocks) builds there."""
    import city_skansen   # the open-air museum owns its buildings' spots too
    return unary_union([zone(), portal_zone(), city_skansen.zone()])

def portal_collision(m=PORTAL):
    a = math.radians(m['facing_deg']); f = np.array([math.cos(a), math.sin(a)]); s = np.array([-f[1], f[0]]); c = np.asarray(m['centre'])
    hw, hd = m['outer_r'] + .1, m['depth'] / 2 + .1
    return Polygon([tuple(c - s * hw - f * hd), tuple(c + s * hw - f * hd), tuple(c + s * hw + f * hd), tuple(c - s * hw + f * hd)])

def portal_meshes(ground, m=PORTAL):
    """Yield (kind, vertices, indices): 'concrete' ring + plinth, 'screen' discs on both faces."""
    a = math.radians(m['facing_deg']); f = np.array([math.cos(a), math.sin(a)]); s = np.array([-f[1], f[0]]); c = np.asarray(m['centre'], float)
    g = float(ground(np.array([c[0]]), np.array([c[1]]))[0]); R, r, D = m['outer_r'], m['inner_r'], m['depth'] / 2
    zc = g + m['plinth'] + R; N = 40; T = np.linspace(0, 2 * math.pi, N + 1)
    P = lambda rad, t, d: np.array([*(c + s * rad * math.cos(t) + f * d), zc + rad * math.sin(t)])
    ring = _Mesh(); centre3 = np.array([*c, zc])
    for d, sign in ((D, 1), (-D, -1)):   # front/back annulus faces
        ring.tri_strip([[(*P(R, t, d), t, 0) for t in T], [(*P(r, t, d), t, .3) for t in T]], inside=centre3 - np.array([*(f * d * 3), 0]))
    ring.tri_strip([[(*P(R, t, D), t, 0) for t in T], [(*P(R, t, -D), t, .3) for t in T]], inside=centre3)            # outer rim
    rim_in = _Mesh(); rim_in.tri_strip([[(*P(r, t, D), t, 0) for t in T], [(*P(r, t, -D), t, .3) for t in T]], inside=None)
    ring.V += rim_in.V; ring.I += [i + 0 for i in rim_in.I]
    k0 = len(ring.V) - len(rim_in.V); ring.I[-len(rim_in.I):] = [i + k0 for i in rim_in.I]
    ring.box(c - s * (R + .3), c + s * (R + .3), 1.2, m['plinth'] + .2, g - .2)                                       # plinth
    yield 'concrete', *ring.out()
    scr = _Mesh()
    for d in (D * .3, -D * .3):   # screen discs, one per face, slightly recessed
        k = len(scr.V); scr.V.append([*c + f * d, zc, .5, .5])
        for t in T:
            p = P(r, t, d); scr.V.append([*p, .5 + .5 * math.cos(t) * (1 if d > 0 else -1), .5 - .5 * math.sin(t)])
        for j in range(N):
            tri = [k, k + 1 + j, k + 2 + j]; A, B, C = (np.asarray(scr.V[q][:3]) for q in tri)
            if np.cross(B - A, C - A) @ np.array([*(f * np.sign(d)), 0]) < 0: tri = [tri[0], tri[2], tri[1]]   # face outwards
            scr.I += tri
    yield 'screen', *scr.out()

def church_lod2_ids(root, origin):
    """LoD2 buildings that OSM maps as churches (building=church/chapel/cathedral or a building
    with amenity=place_of_worship): outside the photo zone they get the church facade."""
    import json, xml.etree.ElementTree as ET
    from pyproj import Transformer
    ox, oy = origin[:2]; tr = Transformer.from_crs(4326, 2180, always_xy=True); nodes = {}; polys = []
    for path in sorted((root / 'osm-tiles').glob('*.osm')):
        t = ET.parse(path).getroot()
        for n in t.findall('node'): nodes[n.get('id')] = (float(n.get('lon')), float(n.get('lat')))
        for w in t.findall('way'):
            tags = {x.get('k'): x.get('v') for x in w.findall('tag')}
            if tags.get('building') in ('church', 'chapel', 'cathedral', 'basilica') or (tags.get('building') and tags.get('amenity') == 'place_of_worship'):
                refs = [x.get('ref') for x in w.findall('nd')]
                if len(refs) >= 4 and all(r in nodes for r in refs):
                    polys.append(Polygon([tuple(np.array(tr.transform(*nodes[r])) - [ox, oy]) for r in refs]).buffer(0))
    church = unary_union(polys); out = set()
    if church.is_empty: return out
    for b in json.loads((root / 'lublin-buildings-clipped.json').read_text())['buildings']:
        for s in b['surfaces']:
            if s['surface'] == 'GroundSurface' and len(s['coordinates']) >= 3:
                fp = Polygon([(v[0] - ox, v[1] - oy) for v in s['coordinates']]).buffer(0)
                if fp.area > 20 and fp.intersection(church).area > .4 * fp.area: out.add(b['id'])
    return out

# Monuments (OSM historic=monument / artwork): small hand models, visible AND solid (cat 2|256).
MONUMENTS = [
    {'name': 'Pomnik Unii Lubelskiej', 'centre': (1782.5, -11.5), 'kind': 'obelisk'},
    {'name': 'Pomnik Marii Curie-Skłodowskiej', 'centre': (492.4, -367.1), 'kind': 'statue'},
]

def _frustum(mesh, c, r0, r1, z0, z1, sides, phase=0.0):
    """Prism/frustum: `sides` 4 = square (r = half side), larger = round."""
    c = np.asarray(c, float); T = np.linspace(phase, phase + 2 * math.pi, sides + 1)
    k = 1 / math.cos(math.pi / sides) if sides == 4 else 1.0
    bot = [(*(c + r0 * k * np.array([math.cos(t), math.sin(t)])), z0, i / sides, 1) for i, t in enumerate(T)]
    top = [(*(c + r1 * k * np.array([math.cos(t), math.sin(t)])), z1, i / sides, 0) for i, t in enumerate(T)]
    mesh.tri_strip([bot, top], inside=(*c, (z0 + z1) / 2))
    i = len(mesh.V); mesh.V.append([*c, z1, .5, .5]); mesh.V += [[q[0], q[1], z1, .5, .5] for q in top[:-1]]
    for j in range(sides): mesh.I += [i, i + 1 + j, i + 1 + (j + 1) % sides]

def monument_meshes(ground, items=MONUMENTS):
    """Yield (kind, vertices, indices): 'granite', 'iron', 'gilt', 'bronze'."""
    for m in items:
        c = np.asarray(m['centre'], float); g = float(ground(np.array([c[0]]), np.array([c[1]]))[0]); parts = {}
        P = lambda k: parts.setdefault(k, _Mesh())
        if m['kind'] == 'obelisk':
            _frustum(P('granite'), c, 1.8, 1.8, g - .3, g + .25, 4, math.pi / 4); _frustum(P('granite'), c, 1.45, 1.45, g + .25, g + .6, 4, math.pi / 4)
            _frustum(P('iron'), c, 1.0, .95, g + .6, g + 2.9, 4, math.pi / 4); _frustum(P('iron'), c, 1.1, 1.1, g + 2.9, g + 3.2, 4, math.pi / 4)
            _frustum(P('iron'), c, .55, .2, g + 3.2, g + 9.4, 4, math.pi / 4); _frustum(P('gilt'), c, .22, .02, g + 9.4, g + 10.0, 4, math.pi / 4)
        else:   # standing figure on a pedestal
            _frustum(P('granite'), c, .9, .9, g - .3, g + .3, 4, math.pi / 4); _frustum(P('granite'), c, .7, .65, g + .3, g + 2.6, 4, math.pi / 4)
            z = g + 2.6; _frustum(P('bronze'), c, .45, .28, z, z + 1.1, 16); _frustum(P('bronze'), c, .28, .3, z + 1.1, z + 1.75, 16)
            _frustum(P('bronze'), c, .3, .12, z + 1.75, z + 1.9, 16); _frustum(P('bronze'), c, .15, .15, z + 1.9, z + 2.12, 12); _frustum(P('bronze'), c, .15, .02, z + 2.12, z + 2.22, 12)
        for k, mesh in parts.items(): yield k, *mesh.out()
