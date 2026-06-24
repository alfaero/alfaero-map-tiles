#!/usr/bin/env bash
# rclone-sync.sh — Copia o planet PMTiles do OpenFreeMap DIRETO pro R2 da Alfaero,
# em streaming, SEM passar pela AWS (zero egress AWS). Substitui 01-download +
# 02-convert + 03-upload (que rodavam no EC2 spot e geravam o egress de ~$30/mês).
#
# Roda em qualquer runner com rclone — ex.: GitHub Actions no repo público (grátis,
# sem cobrança de banda). OpenFreeMap é Cloudflare R2 (egress de leitura grátis) e o
# R2 da Alfaero não cobra ingest → custo da transferência = $0.
#
# Remotes rclone necessários (ver workflow): `ofm` (type=http, OpenFreeMap) e
# `alfaero` (type=s3 provider=Cloudflare, R2 da Alfaero).
# Env: R2_BUCKET (obrigatório). OFM_VERSION (opcional; default = última do files.txt).
set -euo pipefail

: "${R2_BUCKET:?R2_BUCKET env required}"
OFM_BASE="${OFM_BASE:-https://btrfs.openfreemap.com}"
log() { printf '[sync] %s\n' "$*"; }

# 1) Resolve a versão (input manual ou a mais recente disponível).
VERSION="${OFM_VERSION:-}"
if [[ -z "$VERSION" ]]; then
  VERSION=$(curl -sSfL "$OFM_BASE/files.txt" \
    | grep -oE 'areas/planet/[0-9]{8}_[0-9]{6}_pt' \
    | sed 's#areas/planet/##' | sort -u | tail -1)
fi
[[ -n "$VERSION" ]] || { echo "[sync] ERRO: não consegui resolver a versão" >&2; exit 2; }

SRC_PATH="areas/planet/${VERSION}/tiles.pmtiles"
SRC_URL="${OFM_BASE}/${SRC_PATH}"

# Valida existência + tamanho da fonte (circuit breaker contra fonte quebrada).
SIZE=$(curl -sIfL "$SRC_URL" | awk -v IGNORECASE=1 '/^content-length:/ {gsub("\r","");print $2}')
[[ "${SIZE:-0}" -gt 1000000000 ]] || { echo "[sync] ERRO: fonte ausente/pequena (${SIZE:-0} bytes) p/ $VERSION" >&2; exit 3; }
SIZE_GB=$((SIZE / 1024 / 1024 / 1024))

PMTILES_NAME="planet-${VERSION}.pmtiles"
WEEK="$(date -u +%Yw%V)"
log "versão=$VERSION  tamanho=${SIZE_GB}GB  destino=$PMTILES_NAME"

# Exporta pros próximos passos do workflow (04/05 usam WEEK e PMTILES_NAME).
if [[ -n "${GITHUB_ENV:-}" ]]; then
  { echo "VERSION=$VERSION"; echo "PMTILES_NAME=$PMTILES_NAME"; echo "WEEK=$WEEK"; } >> "$GITHUB_ENV"
fi
export PMTILES_NAME WEEK VERSION

# 2) Idempotência: se já existe no R2 com o MESMO tamanho, não re-sobe (nome é
#    derivado da versão da fonte → re-run da mesma versão é no-op = $0).
DEST_SIZE=$(rclone size "alfaero:${R2_BUCKET}/${PMTILES_NAME}" --json 2>/dev/null \
  | grep -oE '"bytes":[0-9]+' | grep -oE '[0-9]+' | tail -1 || true)
if [[ "${DEST_SIZE:-0}" == "$SIZE" ]]; then
  log "já existe no R2 com ${SIZE} bytes — pulando upload (idempotente)"
  exit 0
fi

# 3) Cópia em streaming HTTP(OpenFreeMap) → R2(Alfaero). rclone lê por ranges e
#    sobe em multipart — não precisa do arquivo inteiro em disco, e não toca a AWS.
log "copiando $SRC_URL → alfaero:${R2_BUCKET}/${PMTILES_NAME} ..."
rclone copyto "ofm:${SRC_PATH}" "alfaero:${R2_BUCKET}/${PMTILES_NAME}" \
  --s3-chunk-size 64M \
  --s3-upload-concurrency 8 \
  --s3-disable-checksum \
  --header-upload "Cache-Control: public, max-age=31536000, immutable" \
  --header-upload "Content-Type: application/octet-stream" \
  --retries 5 --low-level-retries 20 --retries-sleep 30s \
  --stats 30s --stats-one-line -v

# 4) Verifica o tamanho no destino.
DEST_SIZE=$(rclone size "alfaero:${R2_BUCKET}/${PMTILES_NAME}" --json 2>/dev/null \
  | grep -oE '"bytes":[0-9]+' | grep -oE '[0-9]+' | tail -1 || true)
[[ "${DEST_SIZE:-0}" == "$SIZE" ]] || { echo "[sync] ERRO: destino ${DEST_SIZE:-0} != fonte ${SIZE}" >&2; exit 4; }
log "OK — $PMTILES_NAME (${SIZE_GB}GB) no R2, sem egress AWS"
