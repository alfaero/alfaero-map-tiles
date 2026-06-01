#!/usr/bin/env bash
# Upload do pmtiles versionado pro R2 com Cache-Control immutable.
# Usa aws cli (mais maduro que rclone 1.53.3 com R2).
set -euo pipefail

: "${WEEK:?WEEK env required}"
: "${PMTILES_NAME:?PMTILES_NAME env required}"
: "${R2_BUCKET:?R2_BUCKET env required}"
: "${R2_ENDPOINT:?R2_ENDPOINT env required}"
: "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID env required}"
: "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY env required}"

WORKDIR="${WORKDIR:-/work}"
cd "$WORKDIR"

if [[ ! -f "$PMTILES_NAME" ]]; then
    echo "[03] ERROR: $PMTILES_NAME not found in $WORKDIR" >&2
    exit 2
fi

SIZE_BYTES=$(stat -c%s "$PMTILES_NAME")
SIZE_GB=$((SIZE_BYTES / 1024 / 1024 / 1024))
echo "[03] Uploading $PMTILES_NAME (${SIZE_GB} GB) -> r2://$R2_BUCKET/ via aws s3..."

# Configurar perfil temporário pra aws cli (NÃO mexer no perfil default existente)
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

# aws s3 cp com multipart automático (default 8MB chunks, podemos aumentar)
aws configure set s3.multipart_chunksize 64MB --profile r2temp || true
aws configure set s3.multipart_threshold 64MB --profile r2temp || true
aws configure set s3.max_concurrent_requests 8 --profile r2temp || true

aws s3 cp "$PMTILES_NAME" "s3://$R2_BUCKET/$PMTILES_NAME" \
    --endpoint-url "$R2_ENDPOINT" \
    --region auto \
    --cache-control "public, max-age=31536000, immutable" \
    --content-type "application/octet-stream"

# Verifica
if aws s3api head-object \
    --bucket "$R2_BUCKET" \
    --key "$PMTILES_NAME" \
    --endpoint-url "$R2_ENDPOINT" \
    --region auto >/dev/null 2>&1; then
    echo "[03] Uploaded $PMTILES_NAME to r2://$R2_BUCKET/"
else
    echo "[03] ERROR: upload verification failed" >&2
    exit 3
fi
