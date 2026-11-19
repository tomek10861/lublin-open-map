# Integration guides

Each guide starts from the same release (`manifest.json` + glTF + GeoJSON, see [../format.md](../format.md))
and ends with a drivable or walkable map in the target engine. Tool names and limits below were
correct when written; check the current documentation of your tool version.

| Target | Kind | Whole city? | Guide |
|---|---|---|---|
| Godot 4 | open-source engine | yes | [godot.md](godot.md) |
| Unity | engine | yes | [unity.md](unity.md) |
| Unreal Engine 5 | engine | yes | [unreal.md](unreal.md) |
| Blender | open-source DCC, hub for all ports | yes | [blender.md](blender.md) |
| three.js / Babylon.js / CesiumJS | web | yes (streamed) | [web.md](web.md) |
| SuperTuxKart, Rigs of Rods, Stunt Rally, FlightGear, Luanti | open-source games | a district to the whole city | [open-source-games.md](open-source-games.md) |
| BeamNG.drive | driving sim | yes | [beamng.md](beamng.md) |
| Assetto Corsa | racing sim | one course | [assetto-corsa.md](assetto-corsa.md) |
| Need for Speed III / High Stakes, Underground 2 (OpenUG2), Trackmania, Euro Truck Simulator 2, Cities: Skylines, Minecraft, X-Plane | classic games | varies | [classic-games.md](classic-games.md) |

## What this map is for

Driving, racing, exploring, building and education. Guides for games built around shooting people
are intentionally not included: the map shows real, recognisable streets and squares.

## Common steps

1. **Pick an area.** Small-map engines need a district: `python3 tools/subset.py --data dist
   --center 2300,-20 --size 400 --out old-town --local`. Landmark coordinates are in
   `layers/landmarks.geojson` and `viewer/presets.json`.
2. **Pick a detail level.** Full photogrammetry (`photo/`) looks best but is heavy. For older
   games use `city/` only, or rebuild buildings from `layers/buildings.geojson` (footprint + height).
3. **Convert axes and units once** for the whole scene (table in [../format.md](../format.md#coordinates)).
4. **Collision.** Use `collision/` meshes as static triangle colliders. Place breakable trees and
   signs from `layers/props.geojson` with the engine's own breakable/dynamic objects.
5. **Gameplay data.** Race courses: `layers/races.geojson`. Traffic: `layers/traffic-lanes.geojson`.
   Street names for HUD or signs: `layers/streets.geojson`.
6. **Attribution.** Copy the attribution block from [../../LICENSES.md](../../LICENSES.md) into the
   game's credits or readme. Never ship files from a commercial game inside your port.

Using an AI agent? Point it at [../../AGENTS.md](../../AGENTS.md).
