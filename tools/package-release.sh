#!/bin/sh
# Pack dist/ into GitHub Release assets (each below the 2 GiB per-file limit) plus SHA256SUMS.
#   lublin-open-map-core.zip     manifest, textures, city, collision, races, layers, terrain
#   lublin-open-map-photo-N.zip  photogrammetry tiles, split by tile count
# usage: sh tools/package-release.sh [dist] [release]
set -eu
DIST=${1:-dist}; OUT=${2:-release}; PER=${PER:-45}
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
cd "$DIST"
rm -f "$OUT"/lublin-open-map-*.zip "$OUT"/SHA256SUMS
zip -qr -9 "$OUT/lublin-open-map-core.zip" manifest.json textures city collision races layers terrain
ls -d photo/*/ | sort | split -l "$PER" - "$OUT/.photo-part-"
n=1
for list in "$OUT"/.photo-part-*; do
  zip -qr -0 "$OUT/lublin-open-map-photo-$n.zip" $(cat "$list")   # JPEG and binary meshes: store, do not recompress
  rm "$list"; n=$((n + 1))
done
cd "$OUT" && shasum -a 256 lublin-open-map-*.zip > SHA256SUMS && ls -lh lublin-open-map-*.zip
