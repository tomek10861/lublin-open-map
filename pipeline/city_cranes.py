"""Tower cranes standing where the 2022 photo mesh shows a crane jib floating in the air.

The photo mesh keeps a crane's jib but its thin lattice mast is lost (it is clipped with the
street / non-building photo), so the jib floats. drop_loose() reports such long, thin, high
pieces; this module merges the pieces of one jib (tile and chunk borders split it) and builds
a simple procedural tower crane of the observed height and reach (no third-party model):
mast, slewing cab, jib, counter-jib with counterweight, apex and ties. Visual only.
"""
import math
import numpy as np

MIN_CLEAR_M = 10.0
MIN_LIFT_M, MAX_DEPTH_M, MAX_WIDTH_M = 15.0, 10.0, 6.0   # a jib: high and thin (hook block and ties allowed)
def merge(found):
    """One jib per crane: pieces whose axes are collinear and whose spans touch are merged."""
    jibs = []
    # 'clear' = height above max(terrain, LoD2 roof) under the piece: roof gardens, rooftop plant
    # and canopies (e.g. the Centre for the Meeting of Cultures) sit just above their roof; a jib does not.
    found = [f for f in found if f.get('lift', 0) > MIN_LIFT_M and f.get('clear', 0) > MIN_CLEAR_M
             and f['zt'] - f['z'] < MAX_DEPTH_M and f.get('width', 0) < MAX_WIDTH_M]
    for f in found:
        c, ax = np.asarray(f['centre'], float), np.asarray(f['axis'], float)
        a, b = c + ax * f['t'][0], c + ax * f['t'][1]
        for j in jibs:
            if abs(abs(float(ax @ j['axis'])) - 1) < .02 and abs(f['z'] - j['z']) < 3:
                pts = np.array([a, b, j['a'], j['b']]); s = (pts - j['a']) @ j['axis']
                off = np.abs((pts - j['a']) @ np.array([-j['axis'][1], j['axis'][0]]))
                gap = max(min(s[:2]) - max(s[2:]), min(s[2:]) - max(s[:2]))
                if off.max() < 4 and gap < 8:
                    j['a'], j['b'] = pts[np.argmin(s)], pts[np.argmax(s)]; j['z'] = min(j['z'], f['z'])
                    j['samples'] += [float(((c + ax * t) - j['a']) @ j['axis']) for t in f['tri']]; break
        else:
            jibs.append({'a': a, 'b': b, 'axis': ax, 'z': f['z'], 'samples': [float(t - f['t'][0]) for t in f['tri']]})
    out = []
    for j in sorted(jibs, key=lambda j: -float(np.linalg.norm(j['b'] - j['a']))):
        length = float(np.linalg.norm(j['b'] - j['a']))
        if length < 15: continue
        # counterweight end = denser end (concrete blocks + machinery); mast at ~1/4 from it
        s = np.clip(np.asarray(j['samples']) / length, 0, 1); dense_a = (s < .2).sum() >= (s > .8).sum()
        back, front = (j['a'], j['b']) if dense_a else (j['b'], j['a'])
        axis = (front - back) / length
        mast = back + axis * length * .25
        if any(np.linalg.norm(mast - o["mast"]) < 25 for o in out): continue   # jibs of real cranes do not overlap: one per 25 m
        out.append({'mast': mast, 'back': back, 'front': front, 'axis': axis, 'jibZ': j['z'], 'reachM': length})
    return out

def _box(V, I, p0, p1, w, h, z0, uvscale=4):
    """Box along segment p0->p1 (xy), width w, from z0 up h; all faces double-sided."""
    d = np.asarray(p1, float) - np.asarray(p0, float); L = np.linalg.norm(d)
    if L < 1e-3: d, L = np.array([1., 0]), 1e-3
    d /= L; n = np.array([-d[1], d[0]]) * w / 2
    c = [np.asarray(p0) - n, np.asarray(p1) - n, np.asarray(p1) + n, np.asarray(p0) + n]
    lo = [(*q, z0) for q in c]; hi = [(*q, z0 + h) for q in c]
    centre = np.array([*((np.asarray(p0) + np.asarray(p1)) / 2), z0 + h / 2])
    def quad(a, b, cc, e, uw, vh):   # one winding, facing out of the box (engine sums face normals)
        k = len(V); V.extend([[*a, 0, vh], [*b, uw, vh], [*cc, uw, 0], [*e, 0, 0]])
        A, B, C = (np.asarray(q, float) for q in (a, b, cc))
        out = np.cross(B - A, C - A) @ ((A + C) / 2 - centre) >= 0
        I.extend([k, k + 1, k + 2, k, k + 2, k + 3] if out else [k, k + 2, k + 1, k, k + 3, k + 2])
    for i in range(4):
        j = (i + 1) % 4; side = np.linalg.norm(np.subtract(c[j], c[i]))
        quad(lo[i], lo[j], hi[j], hi[i], side / uvscale, h / uvscale)
    quad(hi[0], hi[1], hi[2], hi[3], L / uvscale, w / uvscale); quad(lo[0], lo[3], lo[2], lo[1], w / uvscale, L / uvscale)

def meshes(cranes, ground):
    """Yield (texture_kind, vertices, indices): 'lattice' (yellow steel) and 'concrete'."""
    for c in cranes:
        m, z = c['mast'], c['jibZ']; g = float(ground(np.array([m[0]]), np.array([m[1]]))[0]); ax = c['axis']
        V, I, W, J = [], [], [], []
        _box(V, I, m - ax * .9, m + ax * .9, 1.8, z - g + 1.4, g - .5)                 # mast
        _box(V, I, m - ax * .9, m + ax * .9, 1.8, 6.5, z + 1.4)                        # apex
        _box(V, I, c['back'], c['front'], 1.4, 1.4, z)                                  # jib + counter-jib
        _box(V, I, m - ax * 1.3, m + ax * 1.3, 2.6, 2.4, z - 2.4)                      # slewing cab
        top = z + 7.9
        for target, zz in ((m + (c['front'] - m) * .65, z + 1.4), (c['back'], z + 1.4)):   # tie bars
            steps = 12
            for k in range(steps):
                a = m + (target - m) * k / steps; b = m + (target - m) * (k + 1) / steps
                za = top + (zz - top) * k / steps
                _box(V, I, a, b, .25, .3, za + (zz - top) / steps / 2 - .15)
        _box(W, J, c['back'], c['back'] + ax * 3.5, 2.6, 2.6, z - 2.6, 2)               # counterweight
        yield 'lattice', np.asarray(V, '<f4'), np.asarray(I, '<u4')
        yield 'concrete', np.asarray(W, '<f4'), np.asarray(J, '<u4')
