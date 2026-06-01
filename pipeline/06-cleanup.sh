#!/usr/bin/env bash
# Mantém últimas 2 versões de planet-*.pmtiles no R2. Deleta o resto.
set -euo pipefail

: "${R2_BUCKET:?R2_BUCKET env required}"
KEEP="${KEEP_VERSIONS:-2}"

echo "[06] Listing planet-*.pmtiles in r2://$R2_BUCKET/ ..."
LIST=$(rclone lsf "alfaero:$R2_BUCKET/" --include 'planet-*.pmtiles' | sort)

COUNT=$(echo "$LIST" | wc -l)
echo "[06] Found $COUNT versions, keeping last $KEEP"

if [[ "$COUNT" -le "$KEEP" ]]; then
    echo "[06] Nothing to delete"
    exit 0
fi

TO_DELETE=$(echo "$LIST" | head -n -"$KEEP")
echo "[06] To delete:"
echo "$TO_DELETE" | sed 's/^/  /'

while IFS= read -r FILE; do
    [[ -z "$FILE" ]] && continue
    echo "[06] Deleting $FILE..."
    rclone delete "alfaero:$R2_BUCKET/$FILE"
done <<< "$TO_DELETE"

echo "[06] Cleanup done"
