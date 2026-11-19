# Classic games (driving, building, flying)

Older commercial games with active modding communities. Tool names and limits come from those
communities and change over time; check the current tools for your game version. Ship only
converted Lublin data and your own files, never files from the game itself.

## Need for Speed III: Hot Pursuit / Need for Speed: High Stakes

These two games have the most open custom-track scene in the series: tracks are `.FRD` files,
edited with the community editor **T3ED**, and many fan tracks exist.

- An FRD track is a chain of blocks along one driving line, which matches a closed course from
  `layers/races.geojson`. Pick one course (3.5–5.5 km) and the tiles around it with
  `tools/subset.py --bbox … --no-photo`.
- Build the road and the street walls along the course from `city/` streets and
  `collision/` walls; use LoD2 buildings (low-poly) for the city around it. Photo tiles are far too
  dense for these engines; bake facade crops into small textures instead.
- Textures go into the track's texture archive in the sizes and formats the game expects
  (small, 8- or 16-bit era textures).
- The AI follows the track's driving line, so a clean course polyline matters more than detail.

## Need for Speed: Underground 2

This map was originally built for Underground 2, but not by modding the original game: it runs in
[OpenUG2](https://github.com/whoismept/OpenUG2), an open-source (MIT) recreation of the Underground 2
engine that needs your own copy of the game. We extended OpenUG2 with city loading (the package
written by `pipeline/build-town.py`: `PL01.town` + streamed photo tiles), breakable props, free-roam
traffic and 10-car races. **That engine extension is not published yet**, so for now the
Underground 2 version cannot be reproduced from this repository alone.

The original executables of Underground, Underground 2, Most Wanted and Carbon have no public tools
for adding a city. Until the OpenUG2 extension is published, use BeamNG.drive or Assetto Corsa for
street racing in Lublin ([beamng.md](beamng.md), [assetto-corsa.md](assetto-corsa.md)).

## Trackmania (2020)

Custom meshes become **Items** through the official NadeoImporter (export FBX from Blender with the
item's collision as a separate mesh), then you place them in the map editor. Good fit: a stylised
race through a few landmarks — the Kraków Gate, the Market Square, the Castle — rather than the
whole city. Keep items light (a few thousand triangles, small textures).

## Euro Truck Simulator 2

The game ships with a map editor for mods and SCS provides official Blender tools for models.
Lublin data helps with a detailed city mod: road layout and names from `layers/streets.geojson`,
lanes from `layers/traffic-lanes.geojson`, landmark models (decimated `city/` or `photo/` tiles)
as custom models. Scale: game map scale differs from real distances; follow the mod guides.

## Cities: Skylines

- **Terrain**: resample `terrain/heightmap-5m.npy` into the game's heightmap (16-bit, 1081 × 1081
  for the whole map area); Lublin's 4.9 × 3.5 km sits in the middle tiles.
- **Roads**: draw them over an overlay of the orthophoto (`textures/ortho_*.jpg`) or use a
  community OSM-import mod with the same OSM data.
- **Landmarks** as custom assets: import decimated models (FBX from Blender) in the Asset Editor.

## Minecraft (and Luanti)

1 block = 1 m works well. Voxelise the ground from the heightmap (subtract the lowest point,
≈ 167 m), buildings from `layers/buildings.geojson` (footprint up to `heightM`), and pick block
colours from the orthophoto. Write a schematic and paste it with WorldEdit or open the world with
Amulet. Street signs from `layers/streets.geojson`. See also
[open-source-games.md](open-source-games.md#luanti-minetest-and-voxel-games).

## X-Plane

Custom scenery: export landmarks and photo tiles as OBJ8 with the XPlane2Blender add-on and place
them with WorldEditor (WED). Lublin Airport (EPLB, Świdnik) is about 10 km east of the map, so the
Old Town and the castle become a visual approach landmark. Keep the photo tiles decimated; X-Plane
handles many medium objects better than a few huge ones.
