"""Christian cemeteries mapped in OpenStreetMap: old trees, graves and the boundary wall.

Only the outlines, alleys (highway=*), walls/fences (barrier=*) and denominations are
observations (OSM, ODbL). Tree and grave POSITIONS and grave FORMS are procedural: seeded,
reproducible, placed inside the outline and clear of alleys and buildings. They are not a
survey of real graves. Forms follow the typology described for the Lipowa cemetery in Lublin
(lipowa.cmentarz.lublin.pl "Plastyka nagrobkow", dormitorium.lublin.pl "Style i formy"):
stele, cippus, obelisk, broken column, pillar, urn on a pedestal, sarcophagus on lion paws,
rock base (skalka) with a cross, tree-trunk cross, cast-iron cross, figure on a pedestal,
neo-gothic baldachin, plus slab graves; Orthodox crosses in the Orthodox cemetery and uniform
rows in the military one. Models are original low-poly geometry, coloured per vertex.

Jewish burial grounds are left untouched: generated matzevot would invent what was destroyed.

build() returns trees for city_landscape.tree_meshes (knockdown props), visual meshes (no
collision) and invisible collision quads for the walls.
"""
import math, random, xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
from pyproj import Transformer

SEED = 1794
TREE_SPACING_M, TREE_FILL = 12.0, .8
ROW_M, PLOT_M, PLOT_SKIP = 3.6, 2.4, .3   # row pitch, plot pitch along a row, empty plots
CHURCHYARD_SKIP = .85                     # amenity=grave_yard alone: a historic churchyard, a few monuments
EDGE_CLEAR_M, ALLEY_CLEAR_M, BUILDING_CLEAR_M, TREE_CLEAR_M = 2.0, 1.4, 2.5, 1.3
WALL_H, WALL_T, FENCE_H = 2.2, .45, 1.8
TREE_ID_BASE = 9_100_000_000              # numeric identities beside OSM node ids (colour variation)

# Materials: base RGB; jitter and moss are applied per grave.
MAT = {'sandstone_red': (150, 98, 82), 'sandstone': (168, 156, 132), 'limestone': (196, 190, 174),
       'marble': (222, 219, 210), 'granite': (112, 112, 114), 'granite_dark': (52, 52, 56),
       'terrazzo': (150, 146, 138), 'iron': (34, 34, 37), 'concrete': (176, 174, 168),
       'brick': (150, 82, 62), 'plaster': (196, 186, 166), 'bark': (104, 92, 80),
       'candle_red': (170, 30, 26), 'candle_amber': (205, 150, 40), 'earth': (78, 70, 58)}

MIX = {   # grave form frequencies per denomination ("niezwykle rozpowszechnione": obelisks, rock bases, stelae)
    'roman_catholic': {'slab_modern': 22, 'stele': 16, 'slab_old': 10, 'cippus': 9, 'obelisk': 9, 'rock_cross': 8,
                       'iron_cross': 7, 'broken_column': 4, 'sarcophagus': 4, 'urn': 3, 'pillar': 3, 'figure': 3,
                       'trunk_cross': 1, 'baldachin': .5},
    'orthodox': {'orthodox_cross': 30, 'orthodox_iron': 15, 'stele': 15, 'obelisk': 10, 'slab_old': 12, 'slab_modern': 8,
                 'cippus': 10},
    'lutheran': {'stele': 25, 'obelisk': 20, 'iron_cross': 15, 'slab_old': 18, 'cippus': 10, 'broken_column': 5,
                 'sarcophagus': 5, 'urn': 2},
    'military': {'military_cross': 1},
}
PRESTIGE = {'obelisk', 'figure', 'baldachin', 'sarcophagus', 'broken_column', 'pillar', 'urn', 'cippus'}   # favoured along alleys


class Mesh:
    """Vertex-coloured triangle soup, chunked below the 16-bit index limit."""
    def __init__(self): self.parts = []; self._new()
    def _new(self): self.v = []; self.c = []; self.i = []
    def quad(self, a, b, c, d, col):
        if len(self.v) > 64000: self.flush()
        k = len(self.v); self.v += [a, b, c, d]; self.c += [col] * 4; self.i += [k, k + 1, k + 2, k, k + 2, k + 3]
    def tri(self, a, b, c, col):
        if len(self.v) > 64000: self.flush()
        k = len(self.v); self.v += [a, b, c]; self.c += [col] * 3; self.i += [k, k + 1, k + 2]
    def flush(self):
        if self.v:
            v = np.zeros((len(self.v), 5), '<f4'); v[:, :3] = self.v; v[:, 3:] = .5
            c = np.array([[*map(int, np.clip(x, 0, 255)), 255] for x in self.c], 'u1')
            self.parts.append((v, np.array(self.i, '<u2'), c))
        self._new()


class Frame:
    """Local grave frame: origin on the ground, r along the row, f the facing direction."""
    def __init__(self, x, y, z, angle):
        self.o = np.array([x, y, z]); self.r = np.array([math.cos(angle), math.sin(angle), 0.]); self.f = np.array([-self.r[1], self.r[0], 0.])
    def p(self, a, b, h): return self.o + self.r * a + self.f * b + np.array([0, 0, h])


def shade(col, k): return tuple(min(255, c * k) for c in col)

def box(m, F, a, b, z0, w, d, h, col, taper=1.0, top=True):
    """Box centred at (a, b) in frame F: w along r, d along f, from z0 to z0+h; top scaled by taper."""
    lo = [F.p(a + sa * w / 2, b + sb * d / 2, z0) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    hi = [F.p(a + sa * w / 2 * taper, b + sb * d / 2 * taper, z0 + h) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for k, light in zip(range(4), (.82, .95, .88, 1.0)):
        n = (k + 1) % 4; m.quad(lo[k], lo[n], hi[n], hi[k], shade(col, light))
    if top: m.quad(hi[0], hi[1], hi[2], hi[3], shade(col, 1.06))

def pyramid(m, F, a, b, z0, w, d, h, col):
    base = [F.p(a + sa * w / 2, b + sb * d / 2, z0) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]; apex = F.p(a, b, z0 + h)
    for k, light in zip(range(4), (.84, .97, .9, 1.02)): m.tri(base[k], base[(k + 1) % 4], apex, shade(col, light))

def gable(m, F, a, b, z0, w, d, h, col):
    """Ridge roof along f (sarcophagus lid, chapel roof)."""
    c = [F.p(a + sa * w / 2, b + sb * d / 2, z0) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    r0, r1 = F.p(a, b - d / 2, z0 + h), F.p(a, b + d / 2, z0 + h)
    m.quad(c[0], r0, r1, c[3], shade(col, .9)); m.quad(c[1], c[2], r1, r0, shade(col, 1.0))
    m.tri(c[0], c[1], r0, shade(col, .85)); m.tri(c[2], c[3], r1, shade(col, .95))

def cylinder(m, F, a, b, z0, r0, r1, h, col, n=6, cap=True):
    ring = lambda r, z: [F.p(a + r * math.cos(2 * math.pi * k / n), b + r * math.sin(2 * math.pi * k / n), z) for k in range(n)]
    lo, hi = ring(r0, z0), ring(r1, z0 + h)
    for k in range(n):
        j = (k + 1) % n; m.quad(lo[k], lo[j], hi[j], hi[k], shade(col, .82 + .2 * (.5 + .5 * math.cos(2 * math.pi * k / n))))
    if cap and r1 > 0:
        top = F.p(a, b, z0 + h)
        for k in range(n): m.tri(hi[k], hi[(k + 1) % n], top, shade(col, 1.05))

def cross(m, F, a, b, z0, h, arm, t, col, at=.68):
    box(m, F, a, b, z0, t, t, h, col); box(m, F, a, b, z0 + h * at - t / 2, arm, t, t, col)

def orthodox_cross(m, F, a, b, z0, h, t, col):
    """Three bars; the lowest slanted (Orthodox)."""
    box(m, F, a, b, z0, t, t, h, col); box(m, F, a, b, z0 + h * .8, h * .22, t, t * .8, col); box(m, F, a, b, z0 + h * .64, h * .42, t, t, col)
    s = h * .14; p = [F.p(a - s, b, z0 + h * .30), F.p(a + s, b, z0 + h * .42), F.p(a + s, b, z0 + h * .42 + t), F.p(a - s, b, z0 + h * .30 + t)]
    q = [x + F.f * t / 2 for x in p]; m.quad(*q, col); m.quad(*[x - F.f * t / 2 for x in p[::-1]], shade(col, .85))

def railing(m, F, w, d, col):
    """Low cast-iron railing around a plot (posts and two rails)."""
    corners = [(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)]
    for (a0, b0), (a1, b1) in zip(corners, corners[1:] + corners[:1]):
        box(m, F, a0, b0, 0, .05, .05, .75, col, top=False)
        p = [F.p(a0, b0, .62), F.p(a1, b1, .62), F.p(a1, b1, .68), F.p(a0, b0, .68)]; m.quad(*p, col); m.quad(*p[::-1], col)

def candles(m, F, rng, b, n):
    for k in range(n):
        box(m, F, rng.uniform(-.25, .25), b + rng.uniform(-.1, .1), .18, .08, .08, .13, MAT['candle_red' if rng.random() < .6 else 'candle_amber'], top=False)


def grave(m, F, kind, rng, mat):
    """One grave in frame F (plot about 1 x 2 m, headstone at the head end b=+0.8)."""
    H = .8   # head end along f
    if kind == 'slab_modern':
        box(m, F, 0, 0, 0, .95, 1.95, .18, mat); box(m, F, 0, -.1, .18, .85, 1.6, .04, shade(mat, 1.08))
        box(m, F, 0, H + .05, 0, .8, .12, rng.uniform(.7, 1.1), mat, taper=.96); candles(m, F, rng, .1, rng.choice((0, 0, 1, 2)))
    elif kind == 'slab_old':
        box(m, F, 0, 0, 0, .9, 1.9, .12, mat, taper=.98); box(m, F, 0, H, .12, .45, .08, .55, mat)
    elif kind == 'stele':
        box(m, F, 0, H, 0, .85, .38, .25, mat); h = rng.uniform(1.1, 2.2); box(m, F, 0, H, .25, .62, .16, h, mat, taper=.88)
        if rng.random() < .5: cross(m, F, 0, H, .25 + h, .45, .3, .07, mat)
        box(m, F, 0, -.15, 0, .8, 1.6, .14, shade(mat, .9))
    elif kind == 'cippus':
        box(m, F, 0, H, 0, .75, .75, .3, mat); box(m, F, 0, H, .3, .52, .52, rng.uniform(.9, 1.4), mat, taper=.92)
        top = .3 + 1.2; box(m, F, 0, H, top - .05, .64, .64, .12, shade(mat, 1.05)); pyramid(m, F, 0, H, top + .07, .6, .6, .18, mat)
        cross(m, F, 0, H, top + .2, .55, .32, .07, mat)
    elif kind == 'obelisk':
        h = rng.uniform(1.8, 3.4); box(m, F, 0, H, 0, .85, .85, .35, mat); box(m, F, 0, H, .35, .58, .58, .5, mat)
        box(m, F, 0, H, .85, .4, .4, h, mat, taper=.55); pyramid(m, F, 0, H, .85 + h, .22, .22, .22, mat)
    elif kind == 'rock_cross':
        z = 0
        for s, hh in ((.95, .42), (.68, .36), (.45, .3)):
            F2 = Frame(*F.p(rng.uniform(-.04, .04), H + rng.uniform(-.04, .04), 0)[:2], F.o[2], math.atan2(F.r[1], F.r[0]) + rng.uniform(-.25, .25))
            box(m, F2, 0, 0, z, s, s * .85, hh, shade(mat, rng.uniform(.85, 1.0)), taper=.8); z += hh * .92
        cross(m, F, 0, H, z, rng.uniform(1.1, 1.6), .62, .12, mat)
    elif kind == 'iron_cross':
        box(m, F, 0, H, 0, .4, .3, .25, MAT['sandstone']); cross(m, F, 0, H, .25, rng.uniform(1.3, 1.8), .7, .05, MAT['iron'])
        if rng.random() < .3: railing(m, F, 1.1, 2.1, MAT['iron'])
    elif kind == 'broken_column':
        box(m, F, 0, H, 0, .8, .8, .4, mat); box(m, F, 0, H, .4, .55, .55, .85, mat)
        cylinder(m, F, 0, H, 1.25, .19, .17, rng.uniform(.9, 1.5), mat)
    elif kind == 'pillar':
        box(m, F, 0, H, 0, .7, .7, .35, mat); h = rng.uniform(1.6, 2.4); cylinder(m, F, 0, H, .35, .2, .18, h, mat)
        box(m, F, 0, H, .35 + h, .48, .48, .14, shade(mat, 1.05)); cross(m, F, 0, H, .49 + h, .5, .3, .07, mat)
    elif kind == 'urn':
        box(m, F, 0, H, 0, .8, .8, .3, mat); box(m, F, 0, H, .3, .55, .55, 1.15, mat); box(m, F, 0, H, 1.45, .66, .66, .1, shade(mat, 1.05))
        cylinder(m, F, 0, H, 1.55, .12, .24, .22, mat, cap=False); cylinder(m, F, 0, H, 1.77, .24, .16, .2, mat, cap=False)
        cylinder(m, F, 0, H, 1.97, .17, 0, .16, mat, cap=False)
    elif kind == 'sarcophagus':
        box(m, F, 0, 0, 0, 1.1, 2.1, .45, mat)
        for sa in (-1, 1):
            for sb in (-1, 1): box(m, F, sa * .36, sb * .78, .45, .16, .16, .14, shade(mat, .9))   # lion paws
        box(m, F, 0, 0, .59, .82, 1.8, .55, mat, taper=.92); gable(m, F, 0, 0, 1.14, .82, 1.8, .2, shade(mat, 1.05))
        cross(m, F, 0, .5, 1.3, .45, .28, .06, mat)
    elif kind == 'figure':
        box(m, F, 0, H, 0, .85, .85, .35, mat); box(m, F, 0, H, .35, .6, .6, rng.uniform(.9, 1.3), mat); top = 1.45
        cylinder(m, F, 0, H, top, .24, .13, 1.0, MAT['marble'], cap=False); box(m, F, 0, H, top + 1.0, .17, .17, .2, MAT['marble'])
        if rng.random() < .6:   # angel: two wings
            for s in (-1, 1):
                p = [F.p(s * .08, H - .05, top + .45), F.p(s * .5, H - .2, top + .65), F.p(s * .45, H - .25, top + 1.2), F.p(s * .08, H - .1, top + .95)]
                m.quad(*p, shade(MAT['marble'], .95)); m.quad(*p[::-1], shade(MAT['marble'], .9))
    elif kind == 'trunk_cross':
        for s, hh in ((.8, .35), (.55, .3)): box(m, F, 0, H, 0 if s > .7 else .35, s, s * .9, hh, MAT['sandstone'], taper=.8)
        cylinder(m, F, 0, H, .62, .11, .09, 1.6, MAT['bark'], n=6); cylinder(m, F, 0, H, 1.6, .07, .07, .01, MAT['bark'], n=6)
        box(m, F, 0, H, 1.62, .75, .12, .12, MAT['bark'])
    elif kind == 'baldachin':
        box(m, F, 0, H - .3, 0, 1.4, 1.4, .3, mat)
        for sa in (-1, 1):
            for sb in (-1, 1): box(m, F, sa * .55, H - .3 + sb * .55, .3, .14, .14, 2.2, mat); pyramid(m, F, sa * .55, H - .3 + sb * .55, 2.5, .16, .16, .35, mat)
        box(m, F, 0, H - .3, 2.5, 1.35, 1.35, .2, mat); pyramid(m, F, 0, H - .3, 2.7, 1.35, 1.35, 1.3, mat)
        cylinder(m, F, 0, H - .3, .3, .18, .11, 1.1, MAT['marble'], cap=False); box(m, F, 0, H - .3, 1.4, .14, .14, .17, MAT['marble'])
    elif kind == 'orthodox_cross':
        box(m, F, 0, H, 0, .7, .45, .35, mat); orthodox_cross(m, F, 0, H, .35, rng.uniform(1.4, 2.0), .11, mat)
        box(m, F, 0, -.15, 0, .8, 1.6, .14, shade(mat, .9))
    elif kind == 'orthodox_iron':
        box(m, F, 0, H, 0, .4, .3, .25, MAT['sandstone']); orthodox_cross(m, F, 0, H, .25, rng.uniform(1.5, 2.0), .05, MAT['iron'])
        if rng.random() < .35: railing(m, F, 1.1, 2.1, MAT['iron'])
    elif kind == 'military_cross':
        box(m, F, 0, .3, 0, .5, .3, .15, MAT['concrete']); cross(m, F, 0, .3, .15, .95, .5, .1, MAT['concrete'], at=.7)
        box(m, F, 0, -.4, 0, .6, 1.2, .1, shade(MAT['concrete'], .92))


def _material(kind, rng):
    if kind in ('slab_modern',): base = MAT[rng.choice(('granite', 'granite_dark', 'granite_dark', 'terrazzo', 'marble'))]
    elif kind in ('military_cross',): base = MAT['concrete']
    else: base = MAT[rng.choices(('sandstone', 'sandstone_red', 'limestone', 'marble', 'granite'), (34, 18, 24, 12, 12))[0]]
    j = rng.uniform(.9, 1.08); moss = rng.random() < .35 and kind not in ('slab_modern', 'military_cross')
    c = tuple(x * j for x in base)
    return (c[0] * .9, c[1] * .96, c[2] * .84) if moss else c   # moss and soot on old stone


def _osm(root, origin):
    ox, oy = origin[:2]; tr = Transformer.from_crs(4326, 2180, always_xy=True); nodes = {}; ways = {}
    for path in sorted(Path(root, 'osm-tiles').glob('*.osm')):
        t = ET.parse(path).getroot()
        for n in t.findall('node'): nodes[n.get('id')] = (float(n.get('lon')), float(n.get('lat')))
        for w in t.findall('way'): ways[w.get('id')] = ({x.get('k'): x.get('v') for x in w.findall('tag')}, [x.get('ref') for x in w.findall('nd')])
    xy = lambda refs: [tuple(np.array(tr.transform(*nodes[r])) - [ox, oy]) for r in refs if r in nodes]
    return ways, xy


def _denomination(tags):
    d = tags.get('denomination', ''); name = tags.get('name', '').lower()
    if 'wojsk' in name or tags.get('cemetery') == 'war_cemetery' or tags.get('historic') == 'war_grave': return 'military'
    if d in ('orthodox', 'russian_orthodox', 'polish_orthodox') or 'prawosł' in name: return 'orthodox'
    if d in ('lutheran', 'protestant', 'evangelical', 'reformed') or 'ewangel' in name: return 'lutheran'
    return 'roman_catholic'


def build(root, origin, ground, buildings):
    """ground(x, y) -> local height (array ok); buildings: shapely area of building outlines."""
    ways, xy = _osm(root, origin); rng = random.Random(SEED)
    cems = []
    for wid, (t, refs) in sorted(ways.items()):
        if t.get('landuse') != 'cemetery' and t.get('amenity') != 'grave_yard': continue
        q = xy(refs)
        if len(q) < 4: continue
        p = Polygon(q).buffer(0); c = p.centroid
        if p.is_empty or not (-2100 < c.x < 2800 and -1750 < c.y < 1750): continue
        cems.append((wid, t, p))
    report = {'cemeteries': [], 'skipped': []}
    alleys = []; walls = []
    for wid, (t, refs) in ways.items():
        if 'highway' in t:
            q = xy(refs)
            if len(q) > 1: alleys.append(LineString(q))
        elif t.get('barrier') in ('wall', 'fence'):
            q = xy(refs)
            if len(q) > 1: walls.append((wid, t['barrier'], LineString(q)))
    alley_tree = shapely.STRtree(alleys)
    visual, collision, trees = Mesh(), [], []
    for wid, t, p in cems:
        if t.get('religion') == 'jewish':
            report['skipped'].append({'osmWay': int(wid), 'reason': 'Jewish burial ground: no generated matzevot'}); continue
        den = _denomination(t); paths = [alleys[k] for k in alley_tree.query(p, predicate='intersects')]
        clear_alley = unary_union([a.buffer(ALLEY_CLEAR_M) for a in paths]) if paths else Polygon()
        free = p.buffer(-EDGE_CLEAR_M).difference(clear_alley).difference(buildings.buffer(BUILDING_CLEAR_M))
        rect = np.asarray(p.minimum_rotated_rectangle.exterior.coords)
        e = max(((rect[k + 1] - rect[k]) for k in range(4)), key=lambda d: np.hypot(*d)); angle = math.atan2(e[1], e[0])
        shapely.prepare(free); near_alley = clear_alley.buffer(3.0); shapely.prepare(near_alley)
        # Old trees on a jittered grid (alleys and buildings kept clear).
        placed = []; x0_, y0_, x1_, y1_ = free.bounds
        if den != 'military':
            for gx in np.arange(x0_, x1_, TREE_SPACING_M):
                for gy in np.arange(y0_, y1_, TREE_SPACING_M):
                    if rng.random() > TREE_FILL: continue
                    x, y = gx + rng.uniform(-4, 4), gy + rng.uniform(-4, 4)
                    if not shapely.contains_xy(free, x, y): continue
                    h = rng.uniform(13, 20); placed.append((x, y))
                    trees.append((str(TREE_ID_BASE + len(trees)), x, y, {'height': f'{h:.1f}', 'diameter_crown': f'{h * rng.uniform(.5, .62):.1f}'}))
        tree_pts = shapely.points(np.array(placed)) if placed else None
        tree_zone = unary_union(shapely.buffer(tree_pts, TREE_CLEAR_M)) if placed else Polygon(); shapely.prepare(tree_zone)
        # Graves: rows along the outline's long axis.
        ca, sa = math.cos(angle), math.sin(angle); cx, cy = p.centroid.x, p.centroid.y
        local = np.asarray(p.exterior.coords) - [cx, cy]; ua = local @ [ca, sa]; va = local @ [-sa, ca]
        row, plot = (3.0, 2.0) if den == 'military' else (ROW_M, PLOT_M)
        kinds, weights = zip(*MIX[den].items()); counts = {}
        skip = CHURCHYARD_SKIP if t.get('landuse') != 'cemetery' else PLOT_SKIP
        for v_ in np.arange(va.min(), va.max(), row):
            for u_ in np.arange(ua.min(), ua.max(), plot):
                if den != 'military' and rng.random() < skip: continue
                ju = 0 if den == 'military' else rng.uniform(-.15, .15); jv = 0 if den == 'military' else rng.uniform(-.2, .2)
                x = cx + (u_ + ju) * ca - (v_ + jv) * sa; y = cy + (u_ + ju) * sa + (v_ + jv) * ca
                # whole plot inside the free area, off the tree trunks
                if not shapely.contains_xy(free, x, y) or shapely.contains_xy(tree_zone, x, y): continue
                hx, hy = x - .8 * sa, y + .8 * ca
                if not shapely.contains_xy(free, hx, hy) or not shapely.contains_xy(free, x + .8 * sa, y - .8 * ca): continue
                prestige = den == 'roman_catholic' and shapely.contains_xy(near_alley, x, y)
                w = [wt * (3 if prestige and k in PRESTIGE else 1) for k, wt in zip(kinds, weights)]
                kind = rng.choices(kinds, w)[0]; counts[kind] = counts.get(kind, 0) + 1
                z = float(np.min(ground(np.array([x, hx]), np.array([y, hy])))) - .05
                grave(visual, Frame(x, y, z, angle + (math.pi if rng.random() < .04 else 0) + rng.uniform(-.03, .03)), kind, rng, _material(kind, rng))
        report['cemeteries'].append({'osmWay': int(wid), 'name': t.get('name'), 'denomination': den, 'areaM2': round(p.area), 'churchyard': skip == CHURCHYARD_SKIP,
                                     'trees': len(placed), 'graves': sum(counts.values()), 'forms': counts})
    # Boundary walls and fences mapped in OSM (within 4 m of a cemetery outline); gates where an alley crosses.
    bound = unary_union([p.boundary for wid, t, p in cems if t.get('religion') != 'jewish']).buffer(4.0); shapely.prepare(bound)
    gates = unary_union([a.buffer(2.0) for a in alleys if a.intersects(bound)]); wall_m = 0
    for wid, kind, line in walls:
        if line.buffer(.5).intersection(bound).area < 2.0: continue
        q = np.asarray(line.coords)
        for a_, b_ in zip(q[:-1], q[1:]):
            n = max(1, int(np.hypot(*(b_ - a_)) / 2.5))
            for k in range(n):
                s0, s1 = a_ + (b_ - a_) * k / n, a_ + (b_ - a_) * (k + 1) / n
                mid = (s0 + s1) / 2
                if not shapely.contains_xy(bound, *mid) or gates.contains(Point(*mid)): continue
                g0, g1 = (float(z) for z in ground(np.array([s0[0], s1[0]]), np.array([s0[1], s1[1]])))
                F = Frame(*mid, min(g0, g1) - .1, math.atan2(*(s1 - s0)[::-1])); L = float(np.hypot(*(s1 - s0)))
                if kind == 'wall':
                    box(visual, F, 0, 0, 0, L + .02, WALL_T, WALL_H + abs(g1 - g0), MAT['brick'])
                    box(visual, F, 0, 0, WALL_H + abs(g1 - g0), L + .04, WALL_T + .08, .12, MAT['plaster'])
                else:
                    box(visual, F, -L / 2, 0, 0, .08, .08, FENCE_H, MAT['iron'])
                    for zz in (.2, FENCE_H - .15):
                        pp = [F.p(-L / 2, 0, zz), F.p(L / 2, 0, zz), F.p(L / 2, 0, zz + .05), F.p(-L / 2, 0, zz + .05)]; visual.quad(*pp, MAT['iron']); visual.quad(*pp[::-1], MAT['iron'])
                    for bar in np.arange(-L / 2 + .3, L / 2, .3): box(visual, F, bar, 0, .2, .02, .02, FENCE_H - .3, MAT['iron'], top=False)
                cv = np.zeros((4, 5), '<f4'); cv[:, :3] = [[*s0, g0 - 1], [*s1, g1 - 1], [*s1, g1 + 3], [*s0, g0 + 3]]; cv[:, 3:] = .5
                collision.append((cv, np.array([0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2], '<u2'))); wall_m += L
    visual.flush()
    report['wallsM'] = round(wall_m); report['trees'] = len(trees)
    report['graves'] = sum(c['graves'] for c in report['cemeteries']); report['visualTriangles'] = sum(len(i) // 3 for _, i, _ in visual.parts)
    report['provenance'] = 'outlines, alleys, walls, denominations: OSM (ODbL); tree and grave positions and forms: procedural (seed %d)' % SEED
    return {'trees': trees, 'visual': visual.parts, 'collision': collision, 'report': report}
