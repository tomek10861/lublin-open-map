# Rebuilding the map from source data

`pipeline/` holds every script used to build the map from public data. You only need it to change
or extend the map; the release already contains the results.

Requirements: Python 3.11+, a C compiler (`cc`), about 70 GB of disk, and a day of mostly unattended
compute for a full build (the 126-tile photogrammetry import and facade bake dominate).

```sh
python3 -m venv venv && venv/bin/pip install -r pipeline/requirements-lublin.txt
export LUBLIN_WORK=$PWD/pipeline          # data is downloaded next to the scripts by default
```

## Stages

| # | Script | Does | Source |
|---|---|---|---|
| 1 | `fetch-osm.py`, `prepare-roads.py` | Download OSM tiles, build the road graph and road surfaces | OpenStreetMap API |
| 2 | `clip-buildings.py` | Clip GUGiK LoD2 buildings (`0663_gml.zip`) to the area (`roi.json`) | GUGiK opendata |
| 3 | `fetch-nmt-files.py`, `build-terrain.py`, `verify-terrain.py` | Download NMT 1 m sheets, build the 5 m terrain and road heights | GUGiK NMT |
| 4 | `fetch-ortho-high.py`, `select-ortho-epochs.py`, `verify-gutters.py` | Orthophoto atlases (0.1 m source, 0.5 m runtime) | GUGiK ORTO WMS |
| 5 | `fetch_bridge_surfaces.py`, `build-bridge-profiles.py` | Bridge and viaduct deck heights from the surface model | GUGiK NMPT |
| 6 | `import-city-mesh.py <tiles> --lod A|C` | Import and decimate photogrammetry tiles | City of Lublin mesh 2022 |
| 7 | `route-plan.py`, `build-routes.py`, `profile-routes.py`, `fit-routes.py` | Plan race loops on the road graph and fit them to the walls | OSM + built city |
| 8 | `build-town.py` | Assemble the city: surfaces, LoD2 buildings, bridges, modeled buildings (`city_modeled_buildings.py` + `facade-baker.c`), photo clean-up (`city_mesh_finish.py`), landmarks (`city_landmarks.py`), cranes (`city_cranes.py`), trees and signs (`city_landscape.py`) | all of the above |
| 9 | `build-race-meta.py` | Street names and traffic lanes (`city_traffic.py`) | OSM |
| 10 | `export_open_map.py` | Write the open release: glTF, GeoJSON, heightmap | stage 8–9 output |
| 11 | `tools/screenshots.cjs`, `tools/package-release.sh` | README screenshots and release archives | release |

Photogrammetry tiles are downloaded as `https://gis.lublin.eu/pobierzdane/mesh/2022/<tile>.zip`;
the tile index is the WFS layer `geoportal:pobieranie_mesh` on
`https://geoportal.lublin.eu/2d/geoserver/geoportal/ows`.

## Notes and limits

- Stages 7–9 were written for the engine this map was first built for, an extended
  [OpenUG2](https://github.com/whoismept/OpenUG2) (see
  [integration/classic-games.md](integration/classic-games.md#need-for-speed-underground-2)):
  `build-town.py` writes its package (`build/custom-city/PL01.town` + `stream/`), and
  `fit-routes.py` used a physics probe compiled from that engine (not included). The fitted courses are included as
  `pipeline/route-*.json`, so a rebuild does not need it. `export_open_map.py` turns the package into
  open formats.
- `build-town.py` is long and dense; read `city_*.py` modules first, they hold most of the logic and
  are documented at the top.
- Landmark coordinates and the hand-made models (Concert Shell, CSK facade, Portal Wilno-Lublin,
  monuments, gates with arches) live in `city_landmarks.py`.
- `landmarks.json` is the list of 50 points of interest used for the screenshots and review.
