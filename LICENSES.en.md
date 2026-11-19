# Licences and data sources

[Wersja polska](LICENSES.md) (authoritative)

Checked **2026-11-19**. A summary of the terms published by the data providers, not legal advice.

## Summary

| Part | Source | Terms | Attribution |
|---|---|---|---|
| Code (`pipeline/`, `tools/`, `viewer/`), documentation, own models and textures | this project | **MIT** ([LICENSE](LICENSE)) | — |
| Orthophoto | GUGiK (Polish Head Office of Geodesy and Cartography), Geoportal.gov.pl | free, "may be used for any purpose" | required |
| Terrain NMT 1 m, surface model NMPT | GUGiK | free, "may be used for any purpose" | required |
| 3D buildings LoD2 (CityGML, 2017) | GUGiK | **CC BY 4.0** | required |
| Streets, street names, traffic lanes, trees, signs, footbridges, OSM building outlines | OpenStreetMap | **ODbL 1.0** | required |
| Photogrammetric 3D mesh (2022) | City of Lublin, gis.lublin.eu | ⚠️ published for public download, no licence stated | required |

MIT does not cover third-party data: each layer keeps the terms of its source.

## Attribution block

```
Lublin Open Map — https://github.com/tomek10861/lublin-open-map
Data: Główny Urząd Geodezji i Kartografii, Geoportal.gov.pl (orthophoto, NMT/NMPT,
LoD2 3D building models, CC BY 4.0).
© OpenStreetMap contributors, ODbL 1.0 — openstreetmap.org/copyright.
3D mesh 2022: Urząd Miasta Lublin (City of Lublin), gis.lublin.eu.
Code and own models: Lublin Open Map contributors, MIT licence.
```

## OpenStreetMap

[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). The GeoJSON layers `streets`,
`traffic-lanes`, `props`, `landmarks` and `races` are derivative databases of OSM and are shared
under ODbL 1.0. glTF meshes, screenshots and games built from them are produced works: any licence,
but they must credit "© OpenStreetMap contributors".

## City of Lublin 3D mesh (2022)

Published on the city's official geoportal (`geoportal.lublin.eu`, "Pobierz dane" / download
layer `pobieranie_mesh`), files at `https://gis.lublin.eu/pobierzdane/mesh/2022/<tile>.zip`. No
licence is stated for the mesh (other city datasets on otwartedane.lublin.eu are CC BY). We publish
derived layers under the Polish Open Data Act of 11 August 2021 (Dz.U. 2023 poz. 1524), which
allows re-use of information published by public bodies, including on their own systems, "for any
purpose" and free of charge, subject to the limits in art. 6 (third-party rights, personal data).

Derived from it: `photo/` and the crane positions/heights in `city/`.
**We will remove these layers promptly at the request of the City of Lublin or another rights
holder.** For commercial ports consider a build without `photo/` (`tools/subset.py --no-photo`) or
ask the city (`geoportal@lublin.eu`).

## Not in this repository

No files from commercial games and no Google Maps / Street View imagery (used only as a visual
reference when checking accuracy). Game ports must not bundle files from those games.
