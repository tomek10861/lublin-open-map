"""Muzeum Wsi Lubelskiej (open-air museum, Aleja Warszawska 96): hand-modeled wooden architecture.

Observations: outlines and names from OpenStreetMap (ODbL); object numbers and names from the
museum's official map; roof form, roof covering and wall construction from the museum's sector
pages (keywords only, texts not copied) collected in skansen/objects.json. Photos (Wikimedia
Commons, the museum site) were visual references only; nothing is copied from them.
Inferred (not observed), and listed per object in the report: wall and eave heights, roof pitch,
window and door placement, colours, and the roof form where the sources do not name it (the
typical form of the region is used). Unnamed outlines tagged historic=building are taken as
outbuildings of the nearest farmstead and get its roof covering (an inference).
Owns: zone() where photo mesh and LoD1 blocks give way, lod2_ids() (LoD2 kept as invisible
collision only), build() (vertex-coloured visual meshes + invisible collision for OSM-only outlines).
"""
import json, math, glob, zlib, xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent
MUSEUM_WAY = '59258969'
FARM_LINK_M = 40.0
_state = {}

# ---- colours (RGB, inferred from reference photos: weathered timber, straw, shingle)
LOG, BOARD, HONEY, PLASTER, STONE = (118, 88, 60), (132, 112, 92), (168, 122, 72), (236, 233, 224), (150, 145, 135)
THATCH, SHINGLE, SHINGLE_NEW, DRANICE = (146, 126, 88), (112, 96, 80), (124, 96, 68), (104, 92, 78)
TIN, FELT, PLANK_ROOF, DARK, METAL, CROSS = (124, 128, 133), (62, 62, 64), (110, 100, 88), (38, 36, 34), (62, 60, 57), (196, 196, 190)
COVER = {'thatch': THATCH, 'shingle': SHINGLE, 'shingle_new': SHINGLE_NEW, 'dranice': DRANICE, 'tin': TIN, 'felt': FELT, 'boards': PLANK_ROOF}
THICK = {'thatch': .35, 'shingle': .08, 'shingle_new': .08, 'dranice': .08, 'tin': .04, 'felt': .04, 'boards': .06}
WALL = {'log': LOG, 'board': BOARD, 'honey': HONEY, 'plaster': PLASTER, 'stone': (214, 208, 194)}

# ---- per-object specs keyed by OSM way/node id. src: facts from skansen/objects.json (museum sector
# pages); every value not named in src is inferred.
S = lambda **k: k
SPECS = {
    # Zespół dworski
    'way/80119935': S(mwl=15, kind='manor', roof='mansard', cover='shingle', wall='plaster', eave=3.6, porches=3, src='mansardowy/łamany dach kryty gontem, tynkowany, ganki kolumnowe na 3 elewacjach'),
    'way/80119929': S(mwl=11, kind='house', roof='hip', cover='shingle', wall='plaster', eave=3.2, porches=1, src='gont, tynkowany, ganek'),
    'way/80119930': S(mwl=12, kind='granary', roof='halfhip', cover='shingle', wall='log', eave=3.4, arcade=True, src='dach naczółkowy kryty gontem, podcień'),
    'way/80119922': S(mwl=13, kind='granary', roof='hip', cover='shingle', wall='log', eave=3.2, arcade=True, src='gont, podcienia'),
    'way/80119915': S(mwl=14, kind='house', roof='hip', cover='shingle', wall='log', eave=2.8, src='gont, konstrukcja węgłowa'),
    'way/80119926': S(mwl=51, kind='granary', roof='hip', cover='shingle', wall='log', eave=3.2, arcade=True, src='podcień (katalog MWL)'),
    # Roztocze
    'way/80119934': S(mwl=19, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.3, src='strzecha, wieńcowe ściany'),
    'way/80119925': S(mwl=20, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.4, src='dach czterospadowy, słoma z okapem z dranic'),
    'way/80119932': S(mwl=22, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.4, porches=1, src='dach czterospadowy słomiany, ganek'),
    'way/80119940': S(mwl=23, kind='cottage', roof='gable', cover='thatch', wall='log', eave=2.4, porches=1, src='dach dwuspadowy, słoma, ganek'),
    'way/80119916': S(mwl=24, kind='house', roof='hip', cover='shingle', wall='log', eave=2.9, src='dach kryty gontem, węgłowy, murowana piwnica'),
    'way/80119936': S(mwl=25, kind='smithy', roof='gable', cover='boards', wall='log', eave=2.3, arcade=True, src='dach dwuspadowy kryty deskami, podcień'),
    'way/80119945': S(mwl=26, kind='tserkva', cover='shingle_new', wall='honey', src='trójdzielna z 3 kopułami, gont, konstrukcja węgłowa (1759)'),
    'way/403951863': S(mwl=27, kind='belfry', cover='shingle_new', wall='honey', src='dwukondygnacyjna, kamienna podmurówka, szerokie zadaszenie, arkadki w górnej kondygnacji, dach namiotowy ośmiopołaciowy'),
    'way/80119912': S(mwl=29, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.4, src='słoma, węgłowa'),
    'way/80119913': S(mwl=30, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.4, src='słoma, węgłowa'),
    'way/80119919': S(mwl=None, kind='ruin', wall='log', src='OSM building=ruins (Zagroda z Lipiny Nowej): low log walls, no roof'),
    # Powiśle, Podlasie
    'way/80119942': S(mwl=62, kind='cottage', roof='hip', cover='thatch', wall='stone', eave=2.5, src='murowana z opoki'),
    'way/80119958': S(mwl=55, kind='cottage', roof='mansard', cover='thatch', wall='stone', eave=2.5, src='dach łamany, murowana'),
    'way/80119951': S(mwl=57, kind='cottage', roof='hip', cover='thatch', wall='board', eave=2.4, src='konstrukcja sumikowo-łątkowa'),
    'way/80119953': S(mwl=59, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.4, src='(brak opisu konstrukcji)'),
    'way/80119954': S(mwl=60, kind='cottage', roof='hip', cover='thatch', wall='stone', eave=2.5, src='murowana'),
    'way/80119949': S(mwl=61, kind='cottage', roof='hip', cover='thatch', wall='stone', eave=2.5, src='murowana'),
    'way/185122344': S(mwl=68, kind='firehouse', roof='gable', cover='felt', wall='board', eave=3.8, src='drewniana, szerokofrontowa, dach kryty papą, bez wieży'),
    'way/668688332': S(mwl=65, kind='hayrick', cover='thatch', src='bróg (OSM building=roof)'),
    'way/668688333': S(mwl=65, kind='hayrick', cover='thatch', src='bróg (OSM building=roof)'),
    # Wyżyna Lubelska
    'way/80119434': S(mwl=1, kind='windmill', cover='shingle', wall='board', src='wiatrak typu holenderskiego, pokrycie deskami/dranicami'),
    'way/80119428': S(mwl=2, kind='smithy', roof='hip', cover='thatch', wall='log', eave=2.4, arcade=True, src='słoma, węgłowa, podcień'),
    'way/80119437': S(mwl=4, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.4, src='słoma, węgłowa, podcień'),
    'way/80119422': S(mwl=6, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.4, src='słoma, węgłowa'),
    'way/80119418': S(mwl=7, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.4, arcade=True, src='słoma, zrębowa, podcień'),
    'way/80119405': S(mwl=8, kind='cottage', roof='hip', cover='thatch', wall='log', eave=2.3, src='słoma, węgłowana'),
    'way/80119416': S(mwl=9, kind='workshop', roof='hip', cover='thatch', wall='log', eave=2.4, src='słoma'),
    'way/80119414': S(mwl=10, kind='cottage', roof='halfhip', cover='thatch', wall='log', eave=2.4, porches=1, src='dach naczółkowy, słoma, ganek'),
    'way/1054252946': S(mwl=None, kind='workshop', roof='gable', cover='thatch', wall='log', eave=2.0, src='Piec garncarski (OSM)'),
    # Miasteczko and the church (sector pages give no construction keywords: forms from photos / name)
    'way/80119928': S(mwl=49, kind='church', cover='shingle', wall='board', src='kościół modrzewiowy kryty gontem (ok. 1668)'),
    'way/80119927': S(mwl=50, kind='house', roof='hip', cover='shingle', wall='board', eave=3.0, porches=1, src='plebania (forma przyjęta)'),
    'way/185122340': S(mwl=48, kind='belfry_simple', cover='shingle', wall='board', src='dzwonnica (forma przyjęta)'),
    'way/80119956': S(mwl=54, kind='house', roof='hip', cover='shingle', wall='board', eave=3.2, src='stajnia podworska (forma przyjęta)'),
    'way/403951860': S(mwl=36, kind='townhouse', roof='hip', cover='shingle', wall='board', eave=3.4, porches=1, src='ratusz (forma przyjęta)'),
    'way/403951862': S(mwl=37, kind='townhouse', roof='gable', cover='shingle', wall='log', eave=3.0, arcade=True, src='domy podcieniowe (nazwa)'),
    'way/984810974': S(mwl=33, kind='townhouse', roof='gable', cover='tin', wall='board', eave=3.0, src='domy (forma przyjęta)'),
    'way/403951853': S(mwl=34, kind='townhouse', roof='gable', cover='shingle', wall='board', eave=3.0, src='restauracja (forma przyjęta)'),
    'way/403951859': S(mwl=35, kind='townhouse', roof='hip', cover='shingle', wall='board', eave=3.0, src='szkoła (forma przyjęta)'),
    'way/403951855': S(mwl=38, kind='townhouse', roof='gable', cover='shingle', wall='board', eave=3.0, src='dom (forma przyjęta)'),
    'way/403951856': S(mwl=39, kind='firehouse', roof='gable', cover='tin', wall='board', eave=3.8, src='remiza (forma przyjęta)'),
    'way/403951858': S(mwl=40, kind='townhouse', roof='gable', cover='shingle', wall='log', eave=2.6, src='areszt (forma przyjęta)'),
    'way/403951861': S(mwl=41, kind='barn', roof='gable', cover='thatch', wall='board', eave=3.4, src='stodoła (katalog: strzecha/gont)'),
    'way/403951857': S(mwl=42, kind='barn', roof='gable', cover='shingle', wall='board', eave=3.2, src='stodoła (forma przyjęta)'),
    'way/1053274197': S(mwl=32, kind='workshop', roof='gable', cover='shingle', wall='board', eave=2.6, src='kołodziejnia (forma przyjęta)'),
    'way/1054037703': S(mwl=47, kind='workshop', roof='gable', cover='shingle', wall='board', eave=2.4, src='jatki (forma przyjęta)'),
    'way/403951852': S(mwl=None, kind='workshop', roof='gable', cover='shingle', wall='log', eave=2.0, src='Lodownia z Siedliszcza (OSM)'),
    'way/1054037710': S(mwl=None, kind='workshop', roof='gable', cover='shingle', wall='board', eave=2.0, src='Domek pszczelarza (OSM)'),
}
NODE_SPECS = {
    'node/5760308362': S(mwl=21, kind='post_shrine', cover='dranice', src='kapliczka brogowa, dach czterospadowy kryty dranicami, profilowane słupy'),
    'node/5760308361': S(mwl=31, kind='chapel', cover='tin', src='dach dwuspadowy kryty blachą, wieżyczka z hełmem'),
    'node/9737918263': S(mwl=70, kind='chapel_small', cover='tin', src='dach dwuspadowy kryty blachą'),
    'node/9778590748': S(mwl=66, kind='chapel_small', cover='tin', src='dach dwuspadowy kryty blachą'),
    'node/934694739': S(mwl=3, kind='post_shrine', cover='shingle', src='kapliczka (forma przyjęta)'),
    'node/9740061390': S(mwl=44, kind='wayside_figure', cover='tin', src='figura przydrożna (forma przyjęta)'),
    'node/1229801697': S(mwl=53, kind='cross', src='krzyż drewniany (kopia)'),
    'node/9917762026': S(mwl=None, kind='cross', src='Krzyż z Dzbenina (OSM)'),
    'node/9961379177': S(mwl=28, kind='dance_floor', src='parkiet na potańcówki'),
}
GATES = {'way/1054037711': S(mwl=16, cover='shingle', src='brama kryta gontem, arkadowa')}
FARM_KINDS = {'cottage', 'smithy', 'workshop'}


def _origin():
    return json.loads((ROOT / 'roi.json').read_text())['originEPSG2180']


def _osm():
    """Museum outline, buildings and nodes inside it (local metres)."""
    if 'osm' in _state: return _state['osm']
    to = Transformer.from_crs(4326, 2180, always_xy=True); ox, oy = _origin()[:2]
    nodes, ntags, ways = {}, {}, {}
    for f in sorted(glob.glob(str(ROOT / 'osm-tiles/*.osm'))):
        r = ET.parse(f).getroot()
        for n in r.iter('node'):
            i = n.get('id')
            if i not in nodes:
                x, y = to.transform(float(n.get('lon')), float(n.get('lat'))); nodes[i] = (x - ox, y - oy)
                t = {k.get('k'): k.get('v') for k in n.iter('tag')}
                if t: ntags[i] = t
        for w in r.iter('way'):
            if w.get('id') not in ways:
                ways[w.get('id')] = ([nd.get('ref') for nd in w.iter('nd')], {k.get('k'): k.get('v') for k in w.iter('tag')})
    xy = lambda refs: [nodes[r] for r in refs if r in nodes]
    museum = Polygon(xy(ways[MUSEUM_WAY][0])).buffer(0)
    blds, lines = {}, {}
    for i, (refs, t) in ways.items():
        pts = xy(refs)
        if i == MUSEUM_WAY or len(pts) != len(refs) or len(pts) < 2: continue
        if 'building' in t and len(pts) >= 4 and refs[0] == refs[-1]:
            p = Polygon(pts).buffer(0)
            if not p.is_empty and museum.contains(p.representative_point()): blds['way/' + i] = (t, p)
        elif 'way/' + i in GATES:
            lines['way/' + i] = (t, LineString(pts))
    pts = {('node/' + i): (t, Point(nodes[i])) for i, t in ntags.items() if 'node/' + i in NODE_SPECS}
    _state['osm'] = (museum, blds, lines, pts)
    return _state['osm']


def objects():
    """[(id, spec, geometry, tags)] of everything modeled here, specs resolved (outbuildings linked)."""
    if 'objects' in _state: return _state['objects']
    museum, blds, lines, pts = _osm(); out = []
    farms = [(i, SPECS[i], p) for i, (t, p) in blds.items() if i in SPECS and SPECS[i]['kind'] in FARM_KINDS]
    for i, (t, p) in blds.items():
        if i in SPECS: out.append((i, dict(SPECS[i]), p, t)); continue
        if t.get('historic') != 'building' or not farms: continue
        d, fi, fs = min((p.distance(fp), j, s) for j, s, fp in farms)
        if d > FARM_LINK_M: continue
        out.append((i, dict(kind='outbuilding', mwl=fs['mwl'], roof='hip' if fs['cover'] == 'thatch' else 'gable', cover=fs['cover'],
                            wall='board' if fs['wall'] == 'plaster' else fs['wall'], eave=2.6,
                            src=f'zabudowa gospodarcza zagrody {fi} (wniosek: najbliższa zagroda, historic=building)'), p, t))
    for i, (t, g) in lines.items(): out.append((i, dict(GATES[i], kind='gate'), g, t))
    for i, (t, g) in pts.items(): out.append((i, dict(NODE_SPECS[i]), g, t))
    _state['objects'] = out
    return out


def zone():
    """Where the photo mesh and OSM LoD1 blocks give way to these models."""
    if 'zone' not in _state:
        _state['zone'] = unary_union([g.buffer(1.5) if g.geom_type == 'Polygon' else g.buffer(3.0) for _, _, g, _ in objects()])
    return _state['zone']


def lod2_ids(root=None, origin=None):
    """LoD2 2017 buildings standing on a modeled outline (>=30 % of their footprint): kept only as invisible collision."""
    if 'lod2' in _state: return _state['lod2']
    ox, oy = (origin or _origin())[:2]; polys = [g for _, s, g, _ in objects() if g.geom_type == 'Polygon']
    if not polys: _state['lod2'] = set(); return set()
    import shapely; tree = shapely.STRtree(polys); ids = set()
    for b in json.loads((Path(root or ROOT) / 'lublin-buildings-clipped.json').read_text())['buildings']:
        g = [Polygon([(v[0] - ox, v[1] - oy) for v in s['coordinates']]).buffer(0) for s in b['surfaces'] if s['surface'] == 'GroundSurface' and len(s['coordinates']) >= 3]
        if not g: continue
        fp = unary_union(g)
        if fp.is_empty or fp.area <= 0: continue
        hit = tree.query(fp, predicate='intersects')
        if len(hit) and sum(fp.intersection(polys[k]).area for k in hit) >= .3 * fp.area: ids.add(b['id'])
    _state['lod2'] = ids
    return ids


# ---------------------------------------------------------------- geometry
class Mesh:
    """Vertex-coloured triangles, chunked below the 16-bit index limit. Materials are double-sided in
    both consumers (engine: no culling for city meshes; glTF export: doubleSided), so every face is
    emitted once: a reversed copy sharing vertices would cancel the exported vertex normals."""
    def __init__(self): self.parts = []; self.v = []; self.c = []; self.i = []
    def poly(self, pts, col, two=False):
        if len(self.v) > 64000: self.flush()
        k = len(self.v); self.v += [tuple(p) for p in pts]; self.c += [col] * len(pts)
        for j in range(1, len(pts) - 1): self.i += [k, k + j, k + j + 1]
    def flush(self):
        if self.v:
            v = np.zeros((len(self.v), 5), '<f4'); v[:, :3] = self.v; v[:, 3:] = .5
            c = np.array([[*map(int, np.clip(x, 0, 255)), 255] for x in self.c], 'u1')
            self.parts.append((v, np.array(self.i, '<u2'), c))
        self.v, self.c, self.i = [], [], []

def shade(col, k): return tuple(min(255, c * k) for c in col)

def _jitter(col, key, amount=.07):
    k = 1 + amount * ((zlib.crc32(key.encode()) % 1000) / 500 - 1)
    return shade(col, k)

class Frame:
    """Origin at the outline centre at z = 0 (callers pass absolute heights); r along the long side, f across."""
    def __init__(self, c, ang, z):
        self.o = np.array([c[0], c[1], z]); self.r = np.array([math.cos(ang), math.sin(ang), 0.]); self.f = np.array([-self.r[1], self.r[0], 0.])
    def p(self, a, b, h): return self.o + self.r * a + self.f * b + np.array([0., 0., h])

def _rect(p):
    """(centre, angle of the long side, length, width) of the outline's minimum rotated rectangle."""
    q = np.asarray(p.minimum_rotated_rectangle.exterior.coords)[:4]
    e0, e1 = q[1] - q[0], q[2] - q[1]
    if np.hypot(*e0) < np.hypot(*e1): e0, e1 = e1, e0
    return q.mean(0), math.atan2(e0[1], e0[0]), float(np.hypot(*e0)), float(np.hypot(*e1))

def box(m, F, a, b, z0, w, d, h, col, top=True, taper=1.0):
    lo = [F.p(a + sa * w / 2, b + sb * d / 2, z0) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    hi = [F.p(a + sa * w / 2 * taper, b + sb * d / 2 * taper, z0 + h) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for k, light in zip(range(4), (.82, .95, .88, 1.0)):
        n = (k + 1) % 4; m.poly([lo[k], lo[n], hi[n], hi[k]], shade(col, light))
    if top: m.poly(hi, shade(col, 1.04))

def prism(m, F, a, b, z0, rads, zs, col, n=8, rot=0., cap=True, two=False):
    """Stacked n-gon rings (radius rads[k] at height zs[k]) around (a, b): domes, drums, towers."""
    ring = lambda r, z: [F.p(a + r * math.cos(rot + 2 * math.pi * k / n), b + r * math.sin(rot + 2 * math.pi * k / n), z0 + z) for k in range(n)]
    R = [ring(r, z) for r, z in zip(rads, zs)]
    for lo, hi in zip(R[:-1], R[1:]):
        for k in range(n):
            j = (k + 1) % n; m.poly([lo[k], lo[j], hi[j], hi[k]], shade(col, .8 + .22 * (.5 + .5 * math.cos(2 * math.pi * k / n + .8))), two)
    if cap and rads[-1] > 0: m.poly(R[-1], shade(col, 1.05), two)

def roof(m, F, L, W, ze, form, cover, pitch=None, over=.5, hl=None, wallcol=None):
    """Roof over an L x W body whose walls end at ze. Returns the ridge height."""
    col = COVER[cover]; th = THICK[cover]; pitch = pitch or (48 if cover == 'thatch' else 40)
    t = math.tan(math.radians(pitch)); Lr, Wr = L + 2 * over, W + 2 * over
    zl = ze - over * t; zr = ze + W / 2 * t
    E = [F.p(sa * Lr / 2, sb * Wr / 2, zl) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for k in range(4):   # eave thickness band
        n = (k + 1) % 4; m.poly([E[k] - [0, 0, th], E[n] - [0, 0, th], E[n], E[k]], shade(col, .62), True)
    m.poly([e - [0, 0, th] for e in E], shade(col, .5), True)   # soffit
    if form == 'mansard':
        k_ = min(W * .12, 1.1); zb = ze + 2.7   # steep lower slope (~70 deg), gentle upper hip
        B = [F.p(sa * (Lr / 2 - k_), sb * (Wr / 2 - k_), zb) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        for k in range(4):
            n = (k + 1) % 4; m.poly([E[k], E[n], B[n], B[k]], shade(col, (.86, .97, .9, 1.0)[k]), True)
        return roof_top(m, F, Lr - 2 * k_, Wr - 2 * k_, zb, col, 32)
    if form == 'gable':
        R0, R1 = F.p(-Lr / 2, 0, zr), F.p(Lr / 2, 0, zr)
        m.poly([E[0], E[1], R1, R0], shade(col, .88), True); m.poly([E[2], E[3], R0, R1], shade(col, 1.0), True)
        wc = wallcol or col
        for sa in (-1, 1):   # gable walls (timber)
            m.poly([F.p(sa * L / 2, -W / 2, ze), F.p(sa * L / 2, W / 2, ze), F.p(sa * L / 2, 0, zr)], shade(wc, .92), True)
        return zr
    if form == 'halfhip':
        tt = .62; zh = ze + tt * (zr - ze); inset = (1 - tt) * Wr / 2
        R0, R1 = F.p(-Lr / 2 + inset, 0, zr), F.p(Lr / 2 - inset, 0, zr)
        H0 = [F.p(-Lr / 2, sb * (1 - tt) * Wr / 2, zh) for sb in (-1, 1)]; H1 = [F.p(Lr / 2, sb * (1 - tt) * Wr / 2, zh) for sb in (-1, 1)]
        m.poly([E[0], E[1], H1[0], R1, R0, H0[0]], shade(col, .88), True)
        m.poly([E[2], E[3], H0[1], R0, R1, H1[1]], shade(col, 1.0), True)
        m.poly([H0[0], R0, H0[1]], shade(col, .82), True); m.poly([H1[1], R1, H1[0]], shade(col, .95), True)
        wc = wallcol or col
        for sa, H in ((-1, H0), (1, H1)):
            m.poly([F.p(sa * L / 2, -W / 2, ze), F.p(sa * L / 2, W / 2, ze), F.p(sa * L / 2, (1 - tt) * Wr / 2, zh), F.p(sa * L / 2, -(1 - tt) * Wr / 2, zh)], shade(wc, .92), True)
        return zr
    # hip (also the default): ridge along the long side
    return roof_top(m, F, Lr, Wr, zl, col, pitch, E)

def roof_top(m, F, Lr, Wr, z0, col, pitch, E=None):
    t = math.tan(math.radians(pitch)); zr = z0 + Wr / 2 * t; ridge = max(0., Lr / 2 - Wr / 2)
    E = E or [F.p(sa * Lr / 2, sb * Wr / 2, z0) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    R0, R1 = F.p(-ridge, 0, zr), F.p(ridge, 0, zr)
    m.poly([E[0], E[1], R1, R0], shade(col, .88), True); m.poly([E[2], E[3], R0, R1], shade(col, 1.0), True)
    m.poly([E[3], E[0], R0], shade(col, .82), True); m.poly([E[1], E[2], R1], shade(col, .95), True)
    return zr

def openings(m, F, L, W, z0, ze, wall, key, door=True):
    """Windows on both long walls and a door: dark insets slightly proud of the wall."""
    win = DARK if wall != 'plaster' else (52, 58, 60); fr = shade(WALL.get(wall, LOG), 1.25) if wall != 'plaster' else (70, 62, 52)
    n = max(1, int(L / 3.2)); hw, zw0, zw1 = .42, z0 + min(1.0, (ze - z0) * .38), z0 + min(1.9, (ze - z0) * .75)
    for side in (-1, 1):
        b = side * (W / 2 + .03)
        for k in range(n):
            a = -L / 2 + L * (k + .5) / n
            if door and side == 1 and k == n // 2: a += L / n * .5 if n > 1 else .9
            if wall == 'plaster':   # shutters
                for s in (-1, 1): m.poly([F.p(a + s * hw, b, zw0), F.p(a + s * (hw + .4), b, zw0), F.p(a + s * (hw + .4), b, zw1), F.p(a + s * hw, b, zw1)], fr, True)
            m.poly([F.p(a - hw, b, zw0), F.p(a + hw, b, zw0), F.p(a + hw, b, zw1), F.p(a - hw, b, zw1)], win, True)
    if door:
        a, b = 0., W / 2 + .03
        m.poly([F.p(a - .5, b, z0), F.p(a + .5, b, z0), F.p(a + .5, b, z0 + min(2.0, ze - z0 - .1)), F.p(a - .5, b, z0 + min(2.0, ze - z0 - .1))], shade(LOG, .7), True)

def porch(m, F, a, side, ze, cover, wide=3.2, deep=2.0, cols=PLASTER, arch=False, z0=0.):
    """Columned porch (ganek) on a long wall: posts and a small gable roof facing out."""
    b0 = side * F_W[0] / 2; b1 = b0 + side * deep
    for s in (-1, 1):
        for bb in (b0 + side * .25, b1 - side * .2):
            box(m, F, a + s * (wide / 2 - .2), bb, z0, .26, .26, ze - z0, cols)
    col = COVER[cover]; zr = ze + wide / 2 * .9
    L0, L1, R0, R1 = F.p(a - wide / 2 - .2, b0, ze), F.p(a - wide / 2 - .2, b1 + side * .3, ze), F.p(a + wide / 2 + .2, b0, ze), F.p(a + wide / 2 + .2, b1 + side * .3, ze)
    T0, T1 = F.p(a, b0, zr), F.p(a, b1 + side * .3, zr)
    m.poly([L0, L1, T1, T0], shade(col, .9), True); m.poly([R1, R0, T0, T1], shade(col, 1.0), True)
    m.poly([L1, R1, T1], shade(cols, .95), True)   # pediment
    m.poly([F.p(a - wide / 2, b0 - side * .02, z0), F.p(a + wide / 2, b0 - side * .02, z0), F.p(a + wide / 2, b1, z0 + .02), F.p(a - wide / 2, b1, z0 + .02)], STONE, True)

F_W = [0.]   # current body width, read by porch()

def onion(m, F, a, b, z0, r, col=METAL):
    prism(m, F, a, b, z0, [r * .55, r * .95, r, r * .7, r * .2, r * .05], [0, r * .5, r * .9, r * 1.4, r * 1.9, r * 2.3], col, n=8)
    box(m, F, a, b, z0 + r * 2.3, .06, .06, 1.2, CROSS); box(m, F, a, b, z0 + r * 2.3 + .8, .55, .06, .06, CROSS)
    return z0 + r * 2.3 + 1.2

def dome(m, F, a, b, z0, r, h, cover):
    """Octagonal tented dome over a drum: bell-shaped profile, gont."""
    col = COVER[cover]
    prism(m, F, a, b, z0, [r, r * .98, r * .78, r * .42, r * .16], [0, h * .25, h * .6, h * .88, h], col, n=8, cap=True, two=True)
    return z0 + h

# ---------------------------------------------------------------- objects
def _body(m, F, L, W, z0, ze, spec, key):
    wall = spec.get('wall', 'log'); wc = _jitter(WALL[wall], key)
    box(m, F, 0, 0, z0 - 1.2, L + .12, W + .12, 1.2 + .35, STONE, top=False)   # plinth into the slope
    box(m, F, 0, 0, z0 + .35, L, W, ze - z0 - .35, wc, top=False)
    openings(m, F, L, W, z0 + .35, ze, wall, key, door=spec['kind'] not in ('granary',))
    return wc

def _building(m, F, L, W, z0, spec, key):
    ze = z0 + spec.get('eave', 2.5); F_W[0] = W
    if spec['kind'] == 'ruin':
        box(m, F, 0, 0, z0 - .5, L, W, 1.4, _jitter(LOG, key), top=False); return
    wc = _body(m, F, L, W, z0, ze, spec, key)
    if spec.get('arcade'):   # podcień: the roof reaches over posts along one long side
        for k in range(max(2, int(L / 2.5)) + 1):
            box(m, F, -L / 2 + L * k / max(2, int(L / 2.5)), W / 2 + 1.3, z0, .22, .22, ze - z0, shade(LOG, .9))
        roof(m, Frame(F.p(0, .75, 0)[:2], math.atan2(F.r[1], F.r[0]), F.o[2]), L, W + 1.5, ze, spec.get('roof', 'hip'), spec['cover'], wallcol=wc)
    else:
        roof(m, F, L, W, ze, spec.get('roof', 'hip'), spec['cover'], pitch=35 if spec.get('roof') == 'mansard' else None, wallcol=wc)
    for k in range(spec.get('porches', 0)):
        side = (1, -1, 1)[k] if k < 2 else 1
        if k < 2: porch(m, F, 0, side, ze - .1, spec['cover'], cols=PLASTER if spec.get('wall') == 'plaster' else shade(LOG, 1.1), z0=z0)
        else:   # third porch on a gable end (dwór z Żyrzyna)
            G = Frame(F.o[:2], math.atan2(F.r[1], F.r[0]) + math.pi / 2, F.o[2]); F_W[0] = L
            porch(m, G, 0, 1, ze - .1, spec['cover'], z0=z0); F_W[0] = W
    if spec['kind'] in ('manor', 'house', 'cottage', 'townhouse'):   # chimney through the ridge
        rz = ze + W / 2 * math.tan(math.radians(48 if spec['cover'] == 'thatch' else 40))
        box(m, F, L * .12, 0, ze, .6, .6, (rz - ze) + .8, PLASTER if spec.get('wall') == 'plaster' else (168, 150, 130))

def _tserkva(m, F, L, W, z0, spec, key):
    """Three log frames on one axis (babiniec, nave, sanctuary), each with an octagonal gont dome and
    an onion lantern; a skirt roof around; two low sacristies beside the sanctuary (museum page)."""
    wc = _jitter(WALL['honey'], key); parts = [(-L / 2 + L * .15, L * .3, W * .78, 6.2), (0, L * .36, W, 7.6), (L / 2 - L * .15, L * .3, W * .74, 6.2)]
    box(m, F, 0, 0, z0 - 1.2, L + .2, W + .2, 1.6, STONE, top=False)
    for a, l, w, h in parts:
        box(m, F, a, 0, z0 + .4, l, w, h - .4, wc, top=True)
        r = min(l, w) / 2 * .72; col = COVER[spec['cover']]
        prism(m, F, a, 0, z0 + h - .2, [min(l, w) / 2 + .35, r + .1], [0, .5], col, n=8, rot=math.pi / 8, cap=False, two=True)   # roof skirt of the frame
        prism(m, F, a, 0, z0 + h + .3, [r, r], [0, 1.3], wc, n=8, rot=math.pi / 8, cap=False)   # octagonal drum
        zd = dome(m, F, a, 0, z0 + h + 1.6, r * 1.06, r * 1.5, spec['cover'])
        prism(m, F, a, 0, zd - .1, [r * .2, r * .2], [0, .8], wc, n=8); onion(m, F, a, 0, zd + .7, max(.35, r * .24))
    for sb in (-1, 1):   # sacristies
        box(m, F, L / 2 - L * .15, sb * (W * .37 + 1.3), z0 + .4, L * .22, 2.6, 2.8, wc)
    over = 1.1; zs = z0 + 3.0; col = COVER[spec['cover']]   # skirt roof (okap) around the whole body
    for sa, sb, l, w in ((0, -1, L, 0), (0, 1, L, 0), (-1, 0, 0, W), (1, 0, 0, W)):
        if sb:
            a0, a1 = -L / 2 - over, L / 2 + over; b_in, b_out = sb * W / 2, sb * (W / 2 + over)
            m.poly([F.p(a0, b_out, zs - .7), F.p(a1, b_out, zs - .7), F.p(a1, b_in, zs), F.p(a0, b_in, zs)], shade(col, .95), True)
        else:
            a_in, a_out = sa * L / 2, sa * (L / 2 + over)
            m.poly([F.p(a_out, -W / 2 - over, zs - .7), F.p(a_out, W / 2 + over, zs - .7), F.p(a_in, W / 2, zs), F.p(a_in, -W / 2, zs)], shade(col, .85), True)
    box(m, F, -L / 2 - .02, 0, z0 + .4, .05, 1.2, 2.1, shade(LOG, .6), top=False)   # west door

def _belfry(m, F, L, W, z0, spec, key):
    """Two storeys on a stone footing, wide skirt roof between, open arcaded upper storey, eight-sided tent roof."""
    wc = _jitter(WALL['honey'], key); s = min(L, W); col = COVER[spec['cover']]
    box(m, F, 0, 0, z0 - 1.0, s + .3, s + .3, 1.5, STONE, top=False)
    box(m, F, 0, 0, z0 + .5, s, s, 4.3, wc, top=False)
    prism(m, F, 0, 0, z0 + 4.8, [s / 2 * 1.42 + 1.0, s / 2 * 1.42 * .82], [-.6, .5], col, n=8, rot=math.pi / 8, cap=False, two=True)
    u = s * .78; zu = z0 + 5.3
    for sa in (-1, 1):
        for sb in (-1, 1): box(m, F, sa * (u / 2 - .12), sb * (u / 2 - .12), zu, .22, .22, 2.4, wc)
    box(m, F, 0, 0, zu, u - .5, u - .5, 2.4, shade(DARK, 1.4))   # bells in the dark interior
    for sb in (-1, 1): box(m, F, 0, sb * (u / 2 - .1), zu, u, .1, .9, wc)   # parapets
    for sa in (-1, 1): box(m, F, sa * (u / 2 - .1), 0, zu, .1, u, .9, wc)
    zt = zu + 2.4; R = u / 2 * 1.42 + .8
    prism(m, F, 0, 0, zt - .3, [R, R * .55, .08], [0, 1.6, 3.6], col, n=8, rot=math.pi / 8, cap=False, two=True)
    box(m, F, 0, 0, zt + 3.3, .07, .07, 1.3, CROSS); box(m, F, 0, 0, zt + 4.1, .5, .07, .07, CROSS)

def _belfry_simple(m, F, L, W, z0, spec, key):
    s = min(L, W); wc = _jitter(WALL['board'], key)
    box(m, F, 0, 0, z0 - 1, s, s, 7.5, wc, top=False, taper=.85)
    prism(m, F, 0, 0, z0 + 6.5, [s * .62, .08], [0, 3.0], COVER[spec['cover']], n=4, rot=math.pi / 4, cap=False, two=True)

def _church(m, F, L, W, z0, spec, key):
    """Nave and a narrower, lower sanctuary; steep gont roofs; ridge turret with a baroque helmet."""
    wc = _jitter(WALL['board'], key); Ln, Lp = L * .64, L * .36; wp = W * .74
    box(m, F, 0, 0, z0 - 1.2, L + .2, W + .2, 1.6, STONE, top=False)
    Fn = Frame(F.p(-L / 2 + Ln / 2, 0, 0)[:2], math.atan2(F.r[1], F.r[0]), F.o[2]); Fp = Frame(F.p(L / 2 - Lp / 2, 0, 0)[:2], math.atan2(F.r[1], F.r[0]), F.o[2])
    box(m, Fn, 0, 0, z0 + .4, Ln, W, 6.0, wc, top=False); box(m, Fp, 0, 0, z0 + .4, Lp, wp, 5.2, wc, top=False)
    zn = roof(m, Fn, Ln, W, z0 + 6.4, 'gable', spec['cover'], pitch=55, over=.6, wallcol=wc)
    roof(m, Fp, Lp, wp, z0 + 5.6, 'hip', spec['cover'], pitch=55, over=.6)
    a = Ln / 2 - 1.0
    box(m, Fn, a, 0, zn - 1.0, 1.3, 1.3, 2.6, wc); onion(m, Fn, a, 0, zn + 1.6, .75)
    over = .9; zs = z0 + 2.4; col = COVER[spec['cover']]   # soboty: low skirt roof
    for sb in (-1, 1):
        m.poly([Fn.p(-Ln / 2, sb * (W / 2 + over), zs - .6), Fn.p(Ln / 2, sb * (W / 2 + over), zs - .6), Fn.p(Ln / 2, sb * W / 2, zs), Fn.p(-Ln / 2, sb * W / 2, zs)], shade(col, .9), True)
    box(m, Fn, -Ln / 2 - .02, 0, z0 + .4, .05, 1.4, 2.3, shade(LOG, .6), top=False)

def _windmill(m, F, L, W, z0, spec, key):
    """Dutch (smock) mill: tapered eight-sided boarded tower, domed gont cap, four lattice sails."""
    r = min(L, W) / 2 * 1.02; wc = _jitter(WALL['board'], key); col = COVER[spec['cover']]
    prism(m, F, 0, 0, z0 - .8, [r, r, r * .62], [0, .8, 9.5], wc, n=8, rot=math.pi / 8, cap=False)
    prism(m, F, 0, 0, z0 + 8.6, [r * .7, r * .66, r * .45, .1], [0, 1.2, 2.2, 2.9], col, n=10, cap=False, two=True)
    hub = F.p(0, -r * .75, z0 + 9.2)   # sails face -f
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2; d = np.array([math.cos(a), 0, math.sin(a)])
        ax = F.r * d[0] + np.array([0, 0, d[2]]); side = F.r * -d[2] + np.array([0, 0, d[0]])
        tip = hub + ax * 8.5; root = hub + ax * 1.2; out = -F.f * .05
        m.poly([root - side * .14, tip - side * .14, tip + side * .14, root + side * .14], shade(LOG, .8))   # stock
        m.poly([root + side * .14 + out, tip + side * .14 + out, tip + side * 1.8 + out, root + side * 1.8 + out], (172, 150, 118))   # sail frame (boarded lattice)

def _hayrick(m, F, L, W, z0, spec, key):
    s = max(3.2, min(L, W)); col = COVER['thatch']
    for sa in (-1, 1):
        for sb in (-1, 1): box(m, F, sa * (s / 2 - .15), sb * (s / 2 - .15), z0 - .3, .18, .18, 6.0, shade(LOG, .85))
    box(m, F, 0, 0, z0, s - .4, s - .4, 2.0, (176, 152, 96))   # hay
    prism(m, F, 0, 0, z0 + 3.2, [s * .75, .1], [0, 2.0], col, n=4, rot=math.pi / 4, cap=False, two=True)

def _node_object(m, p, spec, ground, key):
    x, y = p.x, p.y; z = float(ground(np.array([x]), np.array([y]))[0]); F = Frame((x, y), (zlib.crc32(key.encode()) % 360) * math.pi / 180, 0.)
    k = spec['kind']; col = COVER.get(spec.get('cover', 'shingle'), SHINGLE)
    if k == 'cross':
        box(m, F, 0, 0, z - .3, .2, .2, 5.0, shade(LOG, .8)); box(m, F, 0, 0, z + 3.3, 1.8, .18, .18, shade(LOG, .8))
    elif k == 'post_shrine':   # kapliczka brogowa: roof on profiled posts over a fenced figure
        for sa in (-1, 1):
            for sb in (-1, 1): box(m, F, sa * .9, sb * .9, z - .2, .16, .16, 2.6, shade(LOG, .95))
        box(m, F, 0, 0, z - .2, .7, .7, 1.6, STONE); box(m, F, 0, 0, z + 1.4, .3, .3, .7, (190, 180, 160))
        for sb in (-1, 1): box(m, F, 0, sb * .9, z, 1.9, .05, .8, shade(LOG, 1.1))
        prism(m, F, 0, 0, z + 2.3, [1.75, .1], [0, 1.2], col, n=4, rot=math.pi / 4, cap=False, two=True)
        box(m, F, 0, 0, z + 3.4, .05, .05, .9, CROSS); box(m, F, 0, 0, z + 3.95, .4, .05, .05, CROSS)
    elif k in ('chapel', 'chapel_small'):
        L, W, H = (4.2, 3.2, 3.0) if k == 'chapel' else (2.0, 1.6, 2.2); F_W[0] = W
        box(m, F, 0, 0, z - .6, L, W, .9, STONE, top=False); box(m, F, 0, 0, z + .3, L, W, H - .3, _jitter(WALL['board'], key), top=False)
        zr = roof(m, F, L, W, z + H, 'gable', spec['cover'], pitch=45, over=.3, wallcol=WALL['board'])
        box(m, F, -L / 2 - .02, 0, z + .3, .05, .9, min(1.9, H - .5), shade(LOG, .6), top=False)
        if k == 'chapel':   # wieżyczka z hełmem
            box(m, F, -L / 2 + .8, 0, zr - .9, .9, .9, 1.6, WALL['board']); onion(m, F, -L / 2 + .8, 0, zr + .7, .5, TIN)
    elif k == 'wayside_figure':
        box(m, F, 0, 0, z - .3, .6, .6, 3.0, PLASTER); box(m, F, 0, 0, z + 2.7, .5, .5, .9, (190, 180, 160))
        prism(m, F, 0, 0, z + 3.6, [.6, .05], [0, .7], col, n=4, rot=math.pi / 4, cap=False, two=True)
        box(m, F, 0, 0, z + 4.2, .04, .04, .6, CROSS)
    elif k == 'dance_floor':
        prism(m, F, 0, 0, z - .4, [6.0, 6.0], [0, .75], shade(PLANK_ROOF, 1.2), n=12)

def _gate(m, line, spec, ground, key):
    a, b = np.asarray(line.coords[0]), np.asarray(line.coords[-1]); c = (a + b) / 2; d = b - a; L = max(3.0, float(np.hypot(*d)))
    z = float(ground(np.array([c[0]]), np.array([c[1]]))[0]); F = Frame(c, math.atan2(d[1], d[0]), 0.); F_W[0] = 1.2
    for sa in (-1, 1): box(m, F, sa * (L / 2 - .2), 0, z - .3, .35, .35, 3.6, shade(LOG, .95))
    box(m, F, 0, 0, z + 3.0, L, .3, .3, shade(LOG, .95))
    roof(m, F, L, .8, z + 3.3, 'gable', spec['cover'], pitch=45, over=.35, wallcol=LOG)


def build(root, origin, ground):
    """{'visual': [(v, i, rgba)], 'collision': [(v, i)], 'report'} for everything modeled here."""
    m = Mesh(); col_parts = []; report = {'objects': 0, 'buildings': 0, 'outbuildings': 0, 'nodes': 0, 'gates': 0, 'byMwl': {}, 'inferred': []}
    lod2 = lod2_ids(root, origin); lod2_fp = None
    for oid, spec, g, tags in objects():
        key = oid
        if g.geom_type == 'Point': _node_object(m, g, spec, ground, key); report['nodes'] += 1
        elif g.geom_type == 'LineString': _gate(m, g, spec, ground, key); report['gates'] += 1
        else:
            c, ang, L, W = _rect(g); ring = np.asarray(g.exterior.coords)
            z0 = float(np.min(ground(ring[:, 0], ring[:, 1]))); F = Frame(c, ang, 0.)
            {'tserkva': _tserkva, 'belfry': _belfry, 'belfry_simple': _belfry_simple, 'church': _church,
             'windmill': _windmill, 'hayrick': _hayrick}.get(spec['kind'], _building)(m, F, L, W, z0, spec, key)
            report['outbuildings' if spec['kind'] == 'outbuilding' else 'buildings'] += 1
            if spec['kind'] not in ('hayrick',):   # invisible 3 m collision walls along the outline
                q = ring[:-1]; v = []; idx = []
                for (ax, ay), (bx, by) in zip(q, np.roll(q, -1, 0)):
                    k = len(v); ga, gb = float(ground(np.array([ax]), np.array([ay]))[0]), float(ground(np.array([bx]), np.array([by]))[0])
                    v += [(ax, ay, ga - 1), (bx, by, gb - 1), (bx, by, gb + 3), (ax, ay, ga + 3)]; idx += [k, k + 1, k + 2, k, k + 2, k + 3, k, k + 2, k + 1, k, k + 3, k + 2]
                vv = np.zeros((len(v), 5), '<f4'); vv[:, :3] = v; vv[:, 3:] = .5; col_parts.append((vv, np.array(idx, '<u2')))
        report['objects'] += 1
        if spec.get('mwl'): report['byMwl'].setdefault(f"MWL-{spec['mwl']:02d}", []).append(oid)
        report['inferred'].append({'id': oid, 'name': tags.get('name'), 'kind': spec['kind'], 'observed': spec.get('src')})
    m.flush()
    report['lod2Replaced'] = len(lod2); report['visualTriangles'] = int(sum(len(i) for _, i, _ in m.parts) // 3)
    return {'visual': m.parts, 'collision': col_parts, 'report': report}
