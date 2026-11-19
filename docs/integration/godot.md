# Godot 4

Godot imports glTF 2.0 natively, including `KHR_materials_unlit`.

## Import

1. Copy the release (or a subset) into the project, e.g. `res://lublin/`. Keep the folder layout:
   `city/*.gltf` refer to `../textures/`.
2. Godot imports every `.gltf` as a scene. Instance the `city/` and `photo/` scenes under one
   `Node3D`. No offsets are needed: all tiles share one origin and glTF is already Y up.
3. Lighting: photo and ortho materials are unlit. Add a `DirectionalLight3D` and a
   `WorldEnvironment` for the lit procedural parts.

## Collision

- Instance `collision/*.gltf`. In the Import dock, set **Meshes → Generate → Physics: Static Body,
  Trimesh**, or rename nodes with the `-colonly` suffix before import so Godot creates
  collision-only bodies.
- Hide the collision scenes (`visible = false`); the static bodies still collide.

## Breakable props

Trees and signs are nodes named `tree_*` / `sign_*` with `extras.breakable = true` (Godot exposes glTF
extras as metadata when **Import extras** is enabled in the import settings). Convert each into a
`RigidBody3D` that sleeps until hit, or replace them with your own scene instanced at
`layers/props.geojson` positions.

## Driving and gameplay

- `VehicleBody3D` drives on the `collision_ground` trimesh.
- Race checkpoints: sample `layers/races.geojson` every 50–100 m and place `Area3D` gates; convert
  coordinates with `local = epsg2180 − originEPSG2180`, then `godot = (x, z, −y)`.
- Traffic AI: `layers/traffic-lanes.geojson` lines become `Path3D` curves.

## Performance

Load `photo/` tiles near the camera only (e.g. within 800 m) with `ResourceLoader.load_threaded_request`.
The full photo set is ≈ 2.3 GB; downscale JPEGs to 2048 px for mobile.
