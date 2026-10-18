#!/bin/bash
# Terreno da visão sintética (spec 005): recorta o Copernicus GLO-30 já
# empacotado pelo Mapterhorn e sobe para o R2. Roda uma vez numa EC2 do
# template do pipeline (mesmo papel IAM e o mesmo segredo) e se desliga; a
# instância é criada com shutdown = terminate.
#
# Saída no bucket alfaero-map-tiles:
#   terrain-glo30-planet-z0-9-${STAMP}.pmtiles  (planeta, z0 a z9, ~10 GB)
#   terrain-glo30-sa-z0-11-${STAMP}.pmtiles     (América do Sul, z0 a z11, ~6 GB)
#   logs/terrain-${STAMP}-<status>.log
set -o pipefail
STAMP="__STAMP__"
SRC="https://download.mapterhorn.com/planet.pmtiles"
STATUS="FAILED"
exec > >(tee /var/log/terrain.log) 2>&1
echo "=== TERRAIN START $(date -u +%FT%TZ) ==="

finish() {
  echo "=== TERRAIN END $(date -u +%FT%TZ) status=${STATUS} ==="
  if [[ -f /root/.config/rclone/rclone.conf ]]; then
    rclone copyto /var/log/terrain.log "alfaero:alfaero-map-tiles/logs/terrain-${STAMP}-${STATUS}.log" \
      --header-upload "Content-Type: text/plain" || true
  fi
  shutdown -h now
}
trap finish EXIT

# Teto de segurança: nunca mais de 6 horas ligada.
( sleep 21600; echo "TIMEOUT"; shutdown -h now ) &

apt-get update && apt-get install -y --no-install-recommends curl ca-certificates jq rclone awscli || exit 1

PMTILES_VERSION="1.31.2"
curl -fsSL "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_Linux_x86_64.tar.gz" \
  | tar xz -C /usr/local/bin pmtiles || exit 2

SECRETS=$(aws secretsmanager get-secret-value --secret-id alfaero/map-tiles-pipeline \
  --region us-east-1 --query SecretString --output text) || exit 3
mkdir -p /root/.config/rclone
cat > /root/.config/rclone/rclone.conf <<RCLONE_EOF
[alfaero]
type = s3
provider = Cloudflare
endpoint = $(echo "$SECRETS" | jq -r .R2_ENDPOINT)
access_key_id = $(echo "$SECRETS" | jq -r .R2_ACCESS_KEY_ID)
secret_access_key = $(echo "$SECRETS" | jq -r .R2_SECRET_ACCESS_KEY)
RCLONE_EOF
unset SECRETS

mkdir -p /data && cd /data || exit 4
PLANET="terrain-glo30-planet-z0-9-${STAMP}.pmtiles"
SA="terrain-glo30-sa-z0-11-${STAMP}.pmtiles"

pmtiles extract "$SRC" "$PLANET" --maxzoom=9 --download-threads=16 || exit 5
pmtiles extract "$SRC" "$SA" --bbox=-82,-56,-34,13 --maxzoom=11 --download-threads=16 || exit 6
pmtiles verify "$PLANET" || exit 7
pmtiles verify "$SA" || exit 8
pmtiles show "$PLANET"
pmtiles show "$SA"
ls -la /data
sha256sum "$PLANET" "$SA" | tee sha256.txt

for f in "$PLANET" "$SA"; do
  rclone copyto "$f" "alfaero:alfaero-map-tiles/$f" \
    --s3-chunk-size 64M --s3-upload-concurrency 16 --stats 60s || exit 9
done
rclone copyto sha256.txt "alfaero:alfaero-map-tiles/terrain-glo30-${STAMP}.sha256" || exit 10
STATUS="SUCCESS"
