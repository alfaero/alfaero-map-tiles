#!/usr/bin/env bash
# Purga apenas /styles/* no Cloudflare (os .pmtiles são imutáveis e versionados).
set -euo pipefail

: "${CF_API_TOKEN:?CF_API_TOKEN env required}"
: "${CF_ZONE_ID_ALFAERO:?CF_ZONE_ID_ALFAERO env required}"
: "${TILES_DOMAIN:?TILES_DOMAIN env required}"

FILES=(
    "https://${TILES_DOMAIN}/styles/alfaero-day.json"
    "https://${TILES_DOMAIN}/styles/alfaero-night.json"
    "https://${TILES_DOMAIN}/styles/alfaero-vfr.json"
)

# Monta array JSON
JSON_FILES=$(printf '"%s",' "${FILES[@]}")
JSON_FILES="[${JSON_FILES%,}]"

echo "[05] Purging Cloudflare cache for styles..."
RESPONSE=$(curl -sS -X POST \
    "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID_ALFAERO}/purge_cache" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    --data "{\"files\":${JSON_FILES}}")

if echo "$RESPONSE" | grep -q '"success":true'; then
    echo "[05] Purge OK"
else
    echo "[05] ERROR: $RESPONSE" >&2
    exit 4
fi
