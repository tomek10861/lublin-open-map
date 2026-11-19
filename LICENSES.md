# Licencje i źródła danych

[English version](LICENSES.en.md)

Stan sprawdzenia: **2026-11-19**. Zestawienie warunków opublikowanych przez dostawców danych,
nie porada prawna.

## Podsumowanie

| Część | Źródło | Warunki | Podpis |
|---|---|---|---|
| Kod (`pipeline/`, `tools/`, `viewer/`), dokumentacja, modele i tekstury własne | ten projekt | **MIT** ([LICENSE](LICENSE)) | — |
| Ortofotomapa | GUGiK, Geoportal.gov.pl | bezpłatna, „możliwa do dowolnego wykorzystania” | wymagany |
| Teren NMT 1 m, model pokrycia NMPT | GUGiK, Geoportal.gov.pl | bezpłatne, „możliwe do dowolnego wykorzystania” | wymagany |
| Budynki 3D LoD2 (CityGML, stan 2017) | GUGiK, opendata.geoportal.gov.pl | **CC BY 4.0** | wymagany |
| Ulice, nazwy ulic, pasy ruchu, drzewa, znaki, kładki, obrysy budynków OSM | OpenStreetMap | **ODbL 1.0** | wymagany |
| Fotogrametryczna siatka 3D (2022) | Urząd Miasta Lublin, gis.lublin.eu | ⚠️ publicznie udostępniona do pobrania, licencja nieopublikowana | wymagany |

Licencja MIT nie obejmuje danych zewnętrznych: każda warstwa ma warunki swojego źródła.

## Podpis (do README portu, napisów końcowych, ekranu tytułowego)

```
Lublin Open Map — https://github.com/tomek10861/lublin-open-map
Dane: Główny Urząd Geodezji i Kartografii, Geoportal.gov.pl (ortofotomapa, NMT/NMPT,
modele 3D budynków LoD2, CC BY 4.0).
© OpenStreetMap contributors, dane na licencji ODbL 1.0 — openstreetmap.org/copyright.
Model 3D 2022: Urząd Miasta Lublin, gis.lublin.eu.
Kod i modele własne: Lublin Open Map contributors, licencja MIT.
```

## GUGiK

- [Ortofotomapa](https://www.geoportal.gov.pl/pl/dane/ortofotomapa/): „Ortofotomapa jest dostępna
  bezpłatnie do pobrania i możliwa do dowolnego wykorzystania.”
- [NMT](https://www.geoportal.gov.pl/pl/dane/numeryczny-model-terenu-nmt/): „Dane NMT są dostępne
  bezpłatnie i możliwe do dowolnego wykorzystania.”
- [Modele 3D budynków](https://www.geoportal.gov.pl/pl/dane/modele-3d-budynkow/): „Modele 3D budynków
  są dostępne bezpłatnie i możliwe do dowolnego wykorzystania.” Informacja o zbiorze
  „LoD2 powiat Lublin (2017)” (TERYT 0663) w Geoportalu podaje: „Licencja CC BY 4.0”.
- [Regulamin Geoportalu](https://www.geoportal.gov.pl/pl/o-geoportalu/regulamin/) §3 ust. 2:
  publikacja materiałów jest dozwolona pod warunkiem podania źródła.

Usługi: `mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/HighResolution`,
`.../NMPT/GRID1/WCS/DigitalSurfaceModel`, `opendata.geoportal.gov.pl/InneDane/Budynki3D/LOD2/0663_gml.zip`.

## OpenStreetMap

Licencja [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), zasady:
[openstreetmap.org/copyright](https://www.openstreetmap.org/copyright).
Warstwy `layers/streets`, `traffic-lanes`, `props`, `landmarks`, `races` są bazami pochodnymi
OSM i są udostępniane na ODbL 1.0. Siatki glTF, zrzuty i gry z nich zbudowane są dziełami
wytworzonymi: mogą mieć inną licencję, ale muszą zawierać podpis „© OpenStreetMap contributors”.

## Urząd Miasta Lublin — siatka 3D 2022

Pochodzenie: oficjalny geoportal miasta (`geoportal.lublin.eu`, grupa „Pobierz dane”, warstwa
`pobieranie_mesh`: „Usługa udostępnia pokafelkowany model mesh 3D miasta Lublin, wykonany w roku
2022”), pliki `https://gis.lublin.eu/pobierzdane/mesh/2022/<tile>.zip`.

Przy usłudze ani na [otwartedane.lublin.eu](https://otwartedane.lublin.eu/) nie opublikowano
licencji dla siatki (inne zbiory miasta, np. chmura punktów, NMT i NMPT, mają tam licencję CC BY).
Publikujemy warstwy z niej pochodne na podstawie ustawy z 11 sierpnia 2021 r. o otwartych danych
i ponownym wykorzystywaniu informacji sektora publicznego
([Dz.U. 2023 poz. 1524](https://eli.gov.pl/api/acts/DU/2023/1524/text.html)): informacje
udostępnione przez urząd, także w jego systemach teleinformatycznych, można wykorzystywać
„w jakimkolwiek celu” (art. 2 pkt 12, art. 5), bezpłatnie (art. 17), z ograniczeniami z art. 6
(m.in. prawa osób trzecich i dane osobowe).

Pochodzą z niej: `photo/` (kafle fotogrametrii, z budynkami odbudowanymi z LoD2 i oteksturowanymi
rzutem siatki) oraz pozycje i wysokości żurawi w `city/`.

**Usuniemy te warstwy niezwłocznie na żądanie Urzędu Miasta Lublin lub uprawnionego podmiotu.**
Kontakt w sprawie siatki po stronie miasta: Referat ds. Systemów Geoprzestrzennych,
`geoportal@lublin.eu`. Jeśli budujesz port komercyjny, rozważ wersję bez `photo/`
(`tools/subset.py --no-photo`) albo uzyskanie zgody miasta.

## Modele własne

Proceduralne modele i tekstury tego projektu (bramy z przejazdami, wiadukty z filarami, kładki,
Muszla Koncertowa w Ogrodzie Saskim, fasada CSK, Portal Wilno-Lublin, obelisk Unii Lubelskiej,
pomnik Curie-Skłodowskiej, żurawie, ławki, drzewa, znaki, nawierzchnie, fasady) są na MIT.
Ich położenie i wymiary pochodzą z danych GUGiK i OSM.

## Czego nie ma w tym repozytorium

Żadnych plików z gier komercyjnych ani obrazów z Google Maps / Street View (służyły wyłącznie
jako podgląd wzrokowy przy sprawdzaniu zgodności). Porty do gier nie mogą dołączać plików
z tych gier.
