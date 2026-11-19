# Unity

## Import

1. Install **glTFast** (`com.unity.cloud.gltf-fast`) from the Package Manager. It imports `.gltf`
   files as prefabs in the editor and supports `KHR_materials_unlit`.
2. Copy the release into `Assets/Lublin/`, keeping the folder layout (city tiles reference
   `../textures/`).
3. Drag the `city/` and `photo/` prefabs into one scene at position 0. glTFast converts glTF's
   right-handed Y-up space to Unity's left-handed Y-up space.

## Collision

Add a `MeshCollider` to each `collision/*` mesh and disable its `MeshRenderer`. For many tiles, do it
with an editor script that walks the imported prefabs.

## Terrain (optional)

The scenes already contain terrain meshes. To use a Unity `Terrain` instead, resample
`terrain/heightmap-5m.npy` to a square power-of-two-plus-one size (e.g. 1025 × 1025), write it as
16-bit little-endian RAW and import it with **Terrain → Import Raw**; size 4900 × 3500 m with height
range `minHeightM…maxHeightM` from `heightmap.json`.

## Gameplay

- Wheel colliders or a vehicle asset drive on the collision meshes.
- Race checkpoints and AI waypoints: convert `layers/races.geojson` and
  `layers/traffic-lanes.geojson` with `local = epsg2180 − originEPSG2180`, then
  `unity = (x, z, y)`.
- Breakable props: nodes named `tree_*` / `sign_*`; add a `Rigidbody` (kinematic until hit).

## Performance

Use Addressables to stream `photo/` tiles by distance. Enable GPU instancing on the procedural
materials. glTFast can also load tiles at runtime from `StreamingAssets`.
