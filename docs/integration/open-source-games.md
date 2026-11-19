# Open-source games

## SuperTuxKart

Tracks are authored in Blender with the SuperTuxKart Blender add-ons (track exporter). Good fit:
one race course from `layers/races.geojson` with the surrounding `city/` tiles, heavily decimated.

1. Cut the area with `tools/subset.py --local`, import tiles into Blender.
2. Build the **driveline** (the main path karts follow) from the course polyline: one quad strip
   along the course, ≈ 8–12 m wide; mark it as the main driveline in the add-on panel.
3. Add start positions, checklines and item boxes along the course; replace photogrammetry with
   LoD2 or simplified blocks textured with ortho/photo crops (STK prefers stylised, light scenes).
4. Export with the add-on; test with `supertuxkart --track=<name>`.

## Rigs of Rods

Terrains are defined by a `.terrn2` with a heightmap and objects (`.odef` + OGRE `.mesh`). Use the
heightmap from `terrain/` (resampled to a square size) and convert buildings to OGRE meshes
(Blender → OGRE exporter). Race courses become checkpoints in a race script.

## Stunt Rally

Tracks combine a terrain heightmap with a road spline. `layers/races.geojson` gives the road spline
directly (sample points with heights from the heightmap); buildings can be added as static objects.

## FlightGear

Scenery objects are AC3D (`.ac`) models placed with `.stg` files in the scenery tile folders. Export
landmarks or decimated `photo/` tiles from Blender as AC3D and add `OBJECT_STATIC` lines with their
WGS84 position (convert from EPSG:2180) and heading. Lublin Airport (EPLB) is about 10 km east.

## Luanti (Minetest) and voxel games

Voxelise `collision/` + `layers/buildings.geojson` at 1 m: ground height from the heightmap,
building blocks up to `heightM`, block colours sampled from the orthophoto. Street names from
`layers/streets.geojson` make good signs.
