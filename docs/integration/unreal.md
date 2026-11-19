# Unreal Engine 5

## Import

1. UE 5 imports glTF through the built-in **Interchange** pipeline (drag a `.gltf` into the Content
   Browser). Older 5.x versions use the **glTF Importer** plugin; enable it if `.gltf` is not offered.
2. Import `city/` and `photo/` tiles as Static Meshes, keeping their scene hierarchy. Unreal converts
   metres to centimetres and Y-up to Z-up on import; place every tile at the world origin.
3. Unlit photo materials import as unlit; if not, set the material's Shading Model to **Unlit** and
   plug the texture into Emissive.

## Collision

Import `collision/*.gltf` as Static Meshes, set **Collision Complexity → Use Complex Collision As
Simple**, and hide them in game (`Visible = false`, `Hidden in Game`). Chaos Vehicles drive on them.

## Large world

Enable **World Partition** and let it stream tiles by grid cell. The map is ≈ 5 × 3.5 km, well
inside single-precision limits.

## Landscape (optional)

Resample `terrain/heightmap-5m.npy` to a Landscape-friendly size (e.g. 1009 × 1009 or 2017 × 2017),
save as 16-bit PNG and import via **Landscape → Import from File**. Set Z scale so that the 16-bit
range maps to `maxHeightM − minHeightM`.

## Gameplay

- Splines from `layers/races.geojson` (`local = epsg2180 − originEPSG2180`, then
  `ue_cm = (x·100, −y·100, z·100)`) give checkpoints and AI racing lines.
- `layers/traffic-lanes.geojson` → ZoneGraph lanes for Mass traffic, or plain splines.
- Breakable props: replace `tree_*` / `sign_*` with Geometry Collections (Chaos destruction).
