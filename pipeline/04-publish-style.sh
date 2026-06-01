#!/usr/bin/env bash
# Atualiza styles/*.json no R2 apontando pra nova versão do pmtiles.
set -euo pipefail

: "${WEEK:?WEEK env required}"
: "${PMTILES_NAME:?PMTILES_NAME env required}"
: "${R2_BUCKET:?R2_BUCKET env required}"
: "${TILES_DOMAIN:?TILES_DOMAIN env required}"

WORKDIR="${WORKDIR:-/work}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STYLES_SRC="${STYLES_SRC:-$SCRIPT_DIR/../styles}"

mkdir -p "$WORKDIR/styles-publish"
cd "$WORKDIR/styles-publish"

NEW_URL="pmtiles://https://${TILES_DOMAIN}/${PMTILES_NAME}"
echo "[04] Patching styles to point at $NEW_URL"

for STYLE in "$STYLES_SRC"/*.json; do
    NAME="$(basename "$STYLE")"
    # Substitui qualquer pmtiles://... pelo novo URL
    jq --arg url "$NEW_URL" '
      .sources |= with_entries(
        if .value.type == "vector" and (.value.url | tostring | startswith("pmtiles://"))
        then .value.url = $url
        else .
        end
      )
    ' "$STYLE" > "$NAME"

    echo "[04]   patched $NAME"
done

echo "[04] Uploading styles/ → r2://$R2_BUCKET/styles/ ..."

rclone copy . "alfaero:$R2_BUCKET/styles/" \
    --progress \
    --header-upload "Cache-Control: public, max-age=300, must-revalidate" \
    --header-upload "Content-Type: application/json"

echo "[04] Published styles for $PMTILES_NAME"
