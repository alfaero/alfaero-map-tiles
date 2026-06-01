#!/usr/bin/env bash
# Converte planet.mbtiles → planet-{week}.pmtiles via go-pmtiles.
set -euo pipefail

: "${WEEK:?WEEK env required}"
: "${PMTILES_NAME:?PMTILES_NAME env required}"

WORKDIR="${WORKDIR:-/work}"
cd "$WORKDIR"

if [[ ! -f planet.mbtiles ]]; then
    echo "[02] ERROR: planet.mbtiles not found in $WORKDIR" >&2
    exit 2
fi

echo "[02] Converting mbtiles → pmtiles (this takes ~1-2h)..."

# pmtiles CLI baixado no user-data do EC2
pmtiles convert planet.mbtiles "$PMTILES_NAME"

# Sanity check
pmtiles show "$PMTILES_NAME" > "${PMTILES_NAME}.metadata.txt"
echo "[02] Metadata:"
cat "${PMTILES_NAME}.metadata.txt"

SIZE_GB=$(du -BG "$PMTILES_NAME" | cut -f1)
echo "[02] Created $PMTILES_NAME ($SIZE_GB)"

# Liberar espaço — não precisamos mais do mbtiles
rm -f planet.mbtiles
echo "[02] Freed mbtiles"
