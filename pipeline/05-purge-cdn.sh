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
    echo "[05] WARN: purge failed (non-fatal — Cache-Control TTL kicks in eventually):"
    echo "       $RESPONSE"
    # NÃO faz exit — purge falhou mas tiles e styles já estão no R2 corretamente
fi

# ---------------------------------------------------------------------------
# Origin shield do raster.alfaero.com (spec 002 do alfaero-map-tiles)
#
# O nginx da Hostinger guarda os PNG renderizados pelo TileServer por 30 dias
# (zona `raster_cache`). Se o conteúdo mudou, purgar só a CDN NÃO basta: o
# Cloudflare repovoa a partir do disco da origem e o piloto continua vendo o
# mapa antigo. Quem limpa é `infrastructure/tileserver/purge-raster-cache.sh`,
# que roda NO servidor.
#
# Não é feito aqui automaticamente porque este passo roda no GitHub Actions,
# que não tem a chave SSH da Hostinger. Com `RASTER_SSH` definido
# (ex.: "-i ~/.ssh/<chave> root@<ip-da-origem>"), a limpeza acontece.
if [ -n "${RASTER_SSH:-}" ]; then
    echo "[05] Limpando o cache de origem do raster.alfaero.com ..."
    # shellcheck disable=SC2086
    ssh $RASTER_SSH '/opt/alfaero-tileserver/purge-raster-cache.sh --all'         || echo "[05] WARN: limpeza do cache de origem falhou — rodar à mão"
else
    echo "[05] ATENÇÃO: RASTER_SSH não definido — o cache de origem do"
    echo "       raster.alfaero.com NÃO foi limpo. Se o mapa base mudou, rodar:"
    echo "       ssh $RASTER_SSH /opt/alfaero-tileserver/purge-raster-cache.sh --all"
fi
