# Instructions for AI agents (Claude, Codex, Cursor, …)

This repository is an open 3D map of Lublin, Poland, in engine-neutral formats. A typical request
is "port this map to <game or engine>". Work from the data contract, not from guesses.

## Read first

1. `docs/format.md` — coordinates, `manifest.json`, geometry sets, layers, terrain. Authoritative.
2. `docs/integration/README.md` and the guide for the target, if one exists.
3. `LICENSES.md` — attribution you must carry into the port.

## Data contract

- Entry point: `dist/manifest.json` (from the release archives). Never infer tiles from file names.
- Local frame: metres, X east, Y north, Z up, `local = EPSG:2180 − [746600, 381750, 180]`.
  glTF files are Y up: `gltf = (x, z, −y)`. Apply one global transform for the target; do not
  re-centre individual tiles.
- `city/` + `photo/` = visuals (they overlap by design), `collision/` = physics, `races/` = per-race
  barriers, `layers/*.geojson` = EPSG:2180 vectors, `terrain/` = 5 m heightmap (row 0 = north).
- Trees and signs are breakable props: glTF nodes `tree_*` / `sign_*` with
  `extras.breakable = true`, mirrored in `layers/props.geojson` with the same ids.

## Working rules

- Start small: `tools/subset.py` cuts a district; get one district working end to end before the
  whole city.
- Respect real engine limits (map size, polygons per object, texture size and format). State the
  limit and its source in your notes; do not invent limits.
- Keep source data unchanged; write converted output to a new directory.
- Never copy files from the target game (models, textures, scripts, archives) into this repository
  or into a release of the port. Ports ship only converted Lublin data plus their own files.
- Keep provenance: carry the attribution block from `LICENSES.md` into the port's readme/credits.
- Purpose: driving, racing, exploring, building, education. Do not port the map to games or
  scenarios built around shooting or attacking people; the map shows real, recognisable places.
  Decline such requests and suggest a driving or exploration target instead.
- Report what you verified (loaded in the editor, compiled, drove the course) separately from what
  you only expect to work.

## Changing the map itself

The build pipeline is in `pipeline/` (see `docs/pipeline.md`). After changing it, run
`export_open_map.py`, open the viewer (`docs/integration/web.md`) and re-render screenshots with
`tools/screenshots.cjs`.
