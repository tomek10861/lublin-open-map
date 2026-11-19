"""Free-roam traffic lanes for the authored city, in the engine's RoutesFreeRoam.bin form.

Chunk 0x34121 (8-byte 0x11 filler, then records). Record: 128-byte header (+0 u32 id<<16,
+44 u32 count|count<<16), count x 56-byte points (+4 x, +8 y, +12 distance, +20 z in eighths
of a metre in the high 16 bits, +24 lane half widths lo|hi in 1/256 m), 12 trailing bytes
(4 after the last record). No join chunk: the engine joins lane ends within 5 m geometrically.
One record per driving direction, offset to the right-hand lane, split at junctions.
"""
import json, math, struct
import numpy as np
from shapely.geometry import LineString

CLASSES = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential',
           'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link'}
STEP_M, LANE_HALF_M = 8.0, 1.75

def lanes(root, origin):
    from city_road_clearance import road_width
    ox, oy, oz = origin
    roads = json.loads((root / 'terrain-build/roads-with-ground-heights.json').read_text())['roads']
    prof = {}
    p = root / 'bridge-audit/road-profiles.json'
    for r in (json.loads(p.read_text()) if p.exists() else []):
        prof[(str(r['way']), r['part'])] = (np.asarray(r['xy']), np.asarray(r['z']))
    use = [r for r in roads if r['properties'].get('highway') in CLASSES and r['properties'].get('area') != 'yes']
    key = lambda q: (round(q[0] * 2), round(q[1] * 2))
    seen = {}
    for r in use:
        for part in r['parts']:
            for i, q in enumerate(part): seen[key(q)] = seen.get(key(q), 0) + (2 if i in (0, len(part) - 1) else 1)
    out = []
    for r in use:
        t = r['properties']; one = t.get('oneway'); width = road_width(t)
        for pi, part in enumerate(r['parts']):
            if len(part) < 2: continue
            cuts = [0] + [i for i in range(1, len(part) - 1) if seen[key(part[i])] > 1] + [len(part) - 1]
            for a, b in zip(cuts[:-1], cuts[1:]):
                pts = np.asarray(part[a:b + 1], float)
                if len(pts) < 2: continue
                xy = pts[:, :2] - [ox, oy]; z = pts[:, 2] - oz
                pr = prof.get((str(r.get('id')), pi))
                if pr is not None:   # bridge decks: the drivable profile height
                    d2 = ((pr[0][None, :, :] - xy[:, None, :]) ** 2).sum(2); z = pr[1][d2.argmin(1)]
                line = LineString(xy)
                if line.length < 4: continue
                s = np.linspace(0, line.length, max(2, int(math.ceil(line.length / STEP_M)) + 1))
                P = np.array([line.interpolate(v).coords[0] for v in s]); Z = np.interp(s, np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))], z)
                dirs = [1] if one in ('yes', 'true', '1') else [-1] if one == '-1' else [1, -1]
                off = 0.0 if len(dirs) == 1 else min(width / 4, 2.0)
                for d in dirs:
                    Q, ZZ = (P, Z) if d == 1 else (P[::-1], Z[::-1])
                    tan = np.gradient(Q, axis=0); tan /= np.linalg.norm(tan, axis=1)[:, None] + 1e-9
                    right = np.column_stack((tan[:, 1], -tan[:, 0]))
                    out.append((Q + right * off, ZZ))
    return out

def write(path, lane_list):
    recs = []
    for k, (Q, Z) in enumerate(lane_list[:65535]):
        for s0 in range(0, len(Q), 4000):   # engine limit: 4096 points per record
            q, z = Q[s0:s0 + 4001], Z[s0:s0 + 4001]
            if len(q) < 2: continue
            head = bytearray(128); struct.pack_into('<I', head, 0, (len(recs) & 0xffff) << 16); struct.pack_into('<I', head, 44, len(q) | len(q) << 16)
            body = bytearray(56 * len(q)); dist = 0.0
            for j in range(len(q)):
                if j: dist += float(np.linalg.norm(q[j] - q[j - 1]))
                hw = int(LANE_HALF_M * 256)
                struct.pack_into('<fff', body, 56 * j + 4, float(q[j][0]), float(q[j][1]), dist)
                struct.pack_into('<I', body, 56 * j + 20, (int(round(float(z[j]) * 8)) & 0xffff) << 16)
                struct.pack_into('<I', body, 56 * j + 24, hw | hw << 16)
            recs.append(bytes(head) + bytes(body))
    payload = b'\x11' * 8 + b''.join(r + (b'\0' * 12 if i + 1 < len(recs) else b'\0' * 4) for i, r in enumerate(recs))
    path.write_bytes(struct.pack('<II', 0x34121, len(payload)) + payload)
    return len(recs)
