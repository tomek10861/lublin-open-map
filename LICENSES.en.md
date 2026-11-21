# Licences and data sources

[Wersja polska](LICENSES.md) (authoritative)

Checked **2026-11-20**. A summary of the terms published by the data providers, not legal advice.

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

Derived from it: `photo/`, the roof heights and colours of the LoD1 blocks (buildings newer than
LoD2) and the crane heights in `city/`.
**We will remove these layers promptly at the request of the City of Lublin or another rights
holder.** For commercial ports consider a build without `photo/` (`tools/subset.py --no-photo`) or
ask the city (`geoportal@lublin.eu`).

## Own models

The procedural models and textures of this project (gates, viaducts, footbridges, the Concert Shell,
the CSK facade, the Portal, monuments, cranes, benches, trees, signs, surfaces, facades, cemetery
graves, walls and fences) are MIT. Their positions and sizes come from GUGiK and OSM data; graves
are placed procedurally inside the OSM cemetery outlines. Grave forms follow written descriptions
(no photos or text copied): [Plastyka nagrobków](https://lipowa.cmentarz.lublin.pl/wazne-miejsca/plastyka-nagrobkow/)
(Lipowa street cemetery) and [Style i formy](https://dormitorium.lublin.pl/28/style-i-formy.htm).

The Open-Air Village Museum buildings (MIT) stand on OSM outlines. Object numbers and names come from
the [museum's official map](https://skansen.lublin.pl/wp-content/uploads/2025/06/0270-MWL-mapa-STANDARD-A3.pdf);
roof form, covering and wall construction from its [sector pages](https://skansen.lublin.pl/pl/ekspozycja/)
(kept as keywords, texts not copied). Photos from Wikimedia Commons and the museum site were visual
references only and are not included.

## Not in this repository

No files from commercial games and no Google Maps / Street View imagery (used only as a visual
reference when checking accuracy). Game ports must not bundle files from those games.
