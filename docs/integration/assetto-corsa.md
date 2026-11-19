# Assetto Corsa

Assetto Corsa tracks are single KN5 models built from FBX in **ksEditor** (part of the official
SDK). Pick one race course from `layers/races.geojson` and the tiles around it.

## Pipeline

1. **Area**: `python3 tools/subset.py --data dist --bbox <course bbox + 200 m> --out course --local`.
2. **Blender**: import the tiles, cut the drivable surface out of `collision_ground` (or the street
   meshes in `city/`) along the course and name objects with AC's physical-surface prefixes, e.g.
   `1ROAD_...` for asphalt, `1KERB_...`, `1GRASS_...`, `1SAND_...`; walls must be separate objects
   with a wall surface defined in `surfaces.ini`.
3. **Timing and spawns**: add empties `AC_START_0…N`, `AC_PIT_0…N`, `AC_HOTLAP_START_0` and timing
   gates `AC_TIME_0_L` / `AC_TIME_0_R` at the first point of the course (start/finish). Grid
   direction follows the course direction.
4. **Export FBX** (Z up, metres), open in ksEditor, assign shaders (`ksPerPixel`; for photo textures
   reduce specular to zero), export KN5.
5. **AI line**: drive the course in-game in AI recording mode (`fast_lane.ai`), or use a community
   AI-line tool fed with the course polyline.
6. **Content Manager / Custom Shaders Patch** add lights, grass and extra materials if wanted.

Courses are closed city loops of 3.5–5.5 km with tight corners; realistic wall placement matters
more than kerbs.
