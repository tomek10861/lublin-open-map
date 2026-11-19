# BeamNG.drive

BeamNG handles large, dense city maps and soft-body physics, so the whole area works.

## Pipeline

1. **Terrain**: resample `terrain/heightmap-5m.npy` to a square power-of-two grid (e.g. 1024 ×
   1024, ≈ 4.8 m per pixel over the 4.9 km side, padding the shorter side), save as 16-bit PNG and
   create a TerrainBlock in the World Editor with the matching height scale
   (`maxHeightM − minHeightM`). Or skip TerrainBlock and use the terrain meshes in `city/`.
2. **Meshes**: BeamNG reads COLLADA (`.dae`). Import tiles into Blender and export each tile (or
   each group of buildings) as DAE, then place them as `TSStatic` objects at the origin. Set the
   collision type to the visible mesh for ground/walls, or export `collision/` tiles as separate
   invisible `TSStatic`s.
3. **Materials**: create `main.materials.json` entries; photo textures as unlit-looking materials
   (no specular).
4. **Roads and AI**: build DecalRoads along `layers/traffic-lanes.geojson` and mark them drivable
   so the AI and traffic can use them; `layers/races.geojson` gives race lines and checkpoints for
   time trials or scenarios.
5. **Props**: place breakable trees/signs from `layers/props.geojson` using BeamNG's own breakable
   assets.

Convert coordinates with `local = epsg2180 − originEPSG2180`; BeamNG is Z up in metres, so local
coordinates can be used directly.
