#!/usr/bin/env bash
# run-update.sh — Orquestra o ciclo completo de atualização semanal.
# Esperado rodar no EC2 spot launched via Step Functions / EventBridge.
#
# Variáveis obrigatórias (vindas do user-data do EC2 ou .env):
#   R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, R2_BUCKET
#   CF_API_TOKEN, CF_ZONE_ID_ALFAERO
#   TILES_DOMAIN (ex: tiles.alfaero.com)
#   SLACK_WEBHOOK_URL (opcional)
#
# Exit codes:
#   0  sucesso
#   1+ falha (detalhado no log)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEEK="$(date -u +%Yw%V)"
PMTILES_NAME="planet-${WEEK}.pmtiles"

export WEEK PMTILES_NAME

log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
notify() {
    local msg="$1"
    log "$msg"
    if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
        curl -sS -X POST -H 'Content-Type: application/json' \
            --data "{\"text\":\"[alfaero-map-tiles] ${msg}\"}" \
            "$SLACK_WEBHOOK_URL" >/dev/null || true
    fi
}

trap 'notify "ABORTED at line $LINENO"' ERR

notify "Pipeline started — target: $PMTILES_NAME"

bash "$SCRIPT_DIR/01-download.sh"
bash "$SCRIPT_DIR/02-convert.sh"
bash "$SCRIPT_DIR/03-upload.sh"
bash "$SCRIPT_DIR/04-publish-style.sh"
bash "$SCRIPT_DIR/05-purge-cdn.sh"
bash "$SCRIPT_DIR/06-cleanup.sh"

notify "Pipeline completed — $PMTILES_NAME live on https://${TILES_DOMAIN}/"
