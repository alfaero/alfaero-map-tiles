#!/usr/bin/env bash
# 02-convert.sh — NO-OP desde 2026-06-01.
#
# OpenFreeMap agora distribui pmtiles diretamente em
#   https://btrfs.openfreemap.com/areas/planet/{version}/tiles.pmtiles
#
# Então 01-download.sh já baixa no formato final, e este script vira nada.
# Mantido pra retro-compatibilidade caso queiramos voltar a converter de mbtiles.
set -euo pipefail

: "${PMTILES_NAME:?PMTILES_NAME env required}"

WORKDIR="${WORKDIR:-/work}"
cd "$WORKDIR"

if [[ ! -f "$PMTILES_NAME" ]]; then
    echo "[02] ERROR: $PMTILES_NAME not found in $WORKDIR" >&2
    exit 2
fi

echo "[02] No conversion needed (OpenFreeMap distributes pmtiles directly)"
echo "[02] Pre-existing $PMTILES_NAME — skipping conversion"

# Sanity check rápido
pmtiles show "$PMTILES_NAME" > "${PMTILES_NAME}.metadata.txt" 2>&1 || {
    echo "[02] WARN: pmtiles show failed — file may be corrupted"
    head -20 "${PMTILES_NAME}.metadata.txt"
}
echo "[02] Metadata first 5 lines:"
head -5 "${PMTILES_NAME}.metadata.txt"
