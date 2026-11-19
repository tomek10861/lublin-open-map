# Web: three.js, Babylon.js, CesiumJS

## three.js

`viewer/` in this repository is a complete three.js example: it reads `manifest.json`, loads tiles
near the camera with `GLTFLoader`, and draws race courses from GeoJSON. Run it with:

```sh
python3 -m http.server 8765        # in the repository root, with the release unpacked in dist/
open http://127.0.0.1:8765/viewer/?data=../dist#stare-miasto
```

URL options: `#<preset>` or `#x,y,dist,yaw,pitch` (local metres, degrees), `?routes` to show race
courses, `?radius=1200` to load more tiles, `?clean` to hide the panel.

## Babylon.js

Use `SceneLoader.ImportMeshAsync` with the glTF loader. Babylon's default is left-handed; set
`scene.useRightHandedSystem = true` to keep the glTF orientation unchanged.

## CesiumJS (globe)

Geometry is in a local frame around `originEPSG2180`. Convert the origin to WGS84
(EPSG:2180 → EPSG:4326, e.g. with pyproj or proj4js), then place each tile with
`Cesium.Model.fromGltfAsync({ url, modelMatrix: Cesium.Transforms.eastNorthUpToFixedFrame(origin) })`,
rotating glTF Y-up to ENU Z-up. For large-scale streaming, convert tiles to 3D Tiles with a tiler
of your choice.
