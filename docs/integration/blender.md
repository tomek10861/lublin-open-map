# Blender

Blender is the hub for most ports: import glTF, cut and simplify, then export to the target format
with a community add-on (FBX for Assetto Corsa, Trackmania and Cities: Skylines, DAE for BeamNG, OBJ8 for X-Plane, AC3D for
FlightGear).

## Import

**File → Import → glTF 2.0**, select one or more `.gltf` files. Blender converts Y-up to Z-up, so the
scene lands in **local** coordinates (X east, Y north, Z up, metres). Import several tiles at once;
they line up without offsets.

GeoJSON layers: use the **BlenderGIS** add-on (set the scene CRS to EPSG:2180, then shift by the
origin) or convert first with `tools/subset.py --local` and read the `*.local.json` files with a
short script:

```python
import bpy, json
fc = json.load(open('/path/old-town/layers/races.local.json'))
for f in fc['features']:
    pts = f['geometry']['coordinates']
    curve = bpy.data.curves.new(f['properties']['name'], 'CURVE'); curve.dimensions = '3D'
    sp = curve.splines.new('POLY'); sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts): p.co = (c[0], c[1], c[2] if len(c) > 2 else 0, 1)
    bpy.context.collection.objects.link(bpy.data.objects.new(curve.name, curve))
```

## Typical clean-up for game ports

- **Decimate** photo tiles (Collapse, ratio 0.1–0.3) for older engines.
- **Bake** many photo textures into one atlas per area (Cycles → Bake → Diffuse, colour only).
- **Join** and split by material to keep draw calls low.
- Build low-poly buildings from `layers/buildings.geojson`: extrude each footprint to `heightM`.
