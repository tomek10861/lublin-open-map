# Data format

Everything in a release is plain glTF 2.0, GeoJSON, PNG/JPEG and JSON. No proprietary formats.
`manifest.json` is the entry point; read it instead of listing directories.

## Coordinates

| Space | Definition | Used by |
|---|---|---|
| **EPSG:2180** | Polish PUWG 1992 easting/northing in metres, heights PL-KRON86-NH | GeoJSON layers, `boundsEPSG2180` |
| **local** | `(easting, northing, height) − originEPSG2180`, metres, X east, Y north, Z up | glTF vertex data before axis swap, tile boxes, `subset.py` |
| **glTF** | glTF convention, Y up: `gltf = (local.x, local.z, −local.y)` | `.gltf` files |

`originEPSG2180 = [746600, 381750, 180]`. All tiles share this origin, so loading several tiles needs
no per-tile offset. The map covers about 4.9 × 3.5 km (local x −2100…2800, y −1750…1750). Float32
precision is about 0.5 mm here, so no origin shifting is needed in any engine.

Converting for a game: decide the game's up axis and unit, then apply one transform to the whole
scene. Examples: Unity is Y up, left-handed, so use `(x, z, y)` from local, or let the glTF importer
handle it. Unreal is Z up, centimetres, so use `(x·100, −y·100, z·100)`. Minecraft is Y up with 1 block = 1 m, so use `(x, z − zmin, −y)`.

## manifest.json

```jsonc
{
  "coordinates": { "originEPSG2180": [746600, 381750, 180], "cellM": 512, ... },
  "city":      [{ "cell": [4, 0], "file": "city/4_0.gltf", "props": 123 }],
  "collision": [{ "cell": [4, 0], "file": "collision/4_0.gltf" }],
  "photo":     [{ "tile": "Tile-54-75-1-1", "file": "photo/Tile-54-75-1-1/Tile-54-75-1-1.gltf",
                  "bboxLocal": [xmin, ymin, xmax, ymax] }],
  "races":     [{ "event": 7001, "file": "races/7001.gltf" }],
  "layers":    { "streets": "layers/streets.geojson", ... },
  "terrain":   "terrain/heightmap.json"
}
```

Cell `[cx, cy]` covers local `[cx·512, cy·512] … [(cx+1)·512, (cy+1)·512]`.

## Geometry sets

| Directory | Content | Materials | Notes |
|---|---|---|---|
| `city/` | Terrain, streets (asphalt, setts, pavement), GUGiK LoD2 buildings outside the photo zone, bridges and viaducts with piers, footbridges, city gates with arches, landmarks (Concert Shell, CSK, Portal, monuments), cranes, street-name plates, trees and road signs | Shared `textures/`: ortho atlases (unlit, clamp) and procedural textures (lit, repeat) | Trees and signs are separate nodes with `extras: {"breakable": true, "kind": "tree"|"sign"}` |
| `photo/` | Photogrammetry of the city centre (2022), with buildings rebuilt from LoD2 surfaces and textured by projecting the photo mesh onto them | Per-tile JPEG, unlit, clamp | Lighting is baked into the photos; render unlit |
| `collision/` | Physics geometry: `collision_ground` (drivable surfaces) and `collision_walls` (building walls, bridge parapets, barriers, landmark outlines) | none | Use as triangle-mesh colliders; trees/signs are not here (they are breakable props) |
| `races/` | Barriers and markers for the four race courses; `race_collision` blocks off side streets | as `city/` | Load only while that race runs |

`city/` and `photo/` overlap on purpose: inside the photo zone `city/` holds ground, streets and props,
and `photo/` holds the buildings. Load both for the full view.

Vertex data: `POSITION`, `NORMAL`, `TEXCOORD_0` (origin top-left, as glTF); `COLOR_0` only on
vertex-coloured untextured meshes (tree crowns and trunks). All materials are double-sided because
photogrammetry winding is not consistent; enable back-face culling only on `city/` if you need it.

## Layers (GeoJSON, EPSG:2180)

Coordinates are EPSG:2180 metres; the files carry a `crs` member, which QGIS and GDAL read.
Subtract `originEPSG2180` to get local metres, or run `tools/subset.py --local`.

| Layer | Geometry | Properties | Use |
|---|---|---|---|
| `streets` | MultiLineString | `name` | Street names for HUD/minimap/signs (OSM) |
| `traffic-lanes` | LineString Z | — | One line per driving direction, right-hand traffic, with heights; AI traffic paths |
| `races` | LineString | `id`, `name`, `lengthM`, `streets`, `loop` | Race courses (closed loops); first point is the start |
| `props` | Point Z | `id`, `kind` (tree/sign), `heightM`, `breakable` | Same ids as the glTF nodes; instance your own breakable models here |
| `landmarks` | Point | `name`, `kind` | 50 points of interest |
| `buildings` | MultiPolygon | `id` (GUGiK), `groundZ`, `roofTopZ`, `heightM` | Footprints + heights for low-poly or brush-based ports |

## Terrain

`terrain/heightmap.png` is 16-bit greyscale, 981 × 701 px, 5 m per pixel, row 0 = north edge
(`boundsEPSG2180` = 744500, 380000, 749400, 383500). Decode with
`height = minHeightM + value/65535 · (maxHeightM − minHeightM)` (values in `heightmap.json`).
`heightmap-5m.npy` holds the same grid as float32 metres. Source: GUGiK NMT 1 m (2017). It is bare
earth: bridges are in `city/`, not in the heightmap.

## Texture list (`textures/`)

`ortho_0…5.jpg` orthophoto atlases (GUGiK). Procedural, original: `facade_beige`, `facade_grey`,
`facade_bluegrey`, `asphalt_marked`, `setts`, `asphalt_residential`, `asphalt_service`,
`race_barrier`, `race_chevron`, `pavement_slabs`, `concrete`, `crane_lattice`, `shell_membrane`,
`bench`, `timber`, `portal_screen`, `church_facade`, `cast_iron`, `gilt`, `bronze`, `street_signs`
(atlas of street-name plates from OSM names).

## Size budget

| Part | Size | Files |
|---|---|---|
| core (`city`, `collision`, `races`, `layers`, `terrain`, `textures`) | ≈ 640 MB | 88 cells |
| `photo` | ≈ 2.3 GB | up to 31 MB per tile, JPEGs up to 4096 px |

For engines with texture limits, downscale photo JPEGs (e.g. to 2048 px) — UVs are normalised, so
any resize works.
