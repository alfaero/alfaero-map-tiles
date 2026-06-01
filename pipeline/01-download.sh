#!/usr/bin/env bash
# Baixa o MBTiles mais recente do OpenFreeMap (R2 público, sem auth).
set -euo pipefail

: "${WEEK:?WEEK env required}"

WORKDIR="${WORKDIR:-/work}"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

OFM_ENDPOINT="${OFM_R2_ENDPOINT:-https://4ddd8b88c1ea4b4ba84c33b8b30b62ac.r2.cloudflarestorage.com}"
OFM_BUCKET="${OFM_BUCKET:-openfreemap}"

# Configura rclone (perfil read-only sem auth pro R2 público do OFM)
mkdir -p "$HOME/.config/rclone"
cat > "$HOME/.config/rclone/rclone.conf" <<EOF
[ofm]
type = s3
provider = Cloudflare
endpoint = $OFM_ENDPOINT
no_auth = true

[alfaero]
type = s3
provider = Cloudflare
endpoint = $R2_ENDPOINT
access_key_id = $R2_ACCESS_KEY_ID
secret_access_key = $R2_SECRET_ACCESS_KEY
EOF

echo "[01] Listing OpenFreeMap bucket to find latest mbtiles..."
LATEST=$(rclone lsf "ofm:$OFM_BUCKET/" --include 'planet-*.mbtiles' | sort | tail -n 1)

if [[ -z "$LATEST" ]]; then
    echo "[01] ERROR: no mbtiles found in ofm:$OFM_BUCKET" >&2
    exit 2
fi

echo "[01] Latest: $LATEST"
echo "[01] Downloading (this takes ~30-60 min depending on bandwidth)..."

rclone copy "ofm:$OFM_BUCKET/$LATEST" "$WORKDIR/" \
    --progress \
    --transfers 8 \
    --checkers 16 \
    --multi-thread-streams 4

mv "$WORKDIR/$LATEST" "$WORKDIR/planet.mbtiles"

SIZE_GB=$(du -BG "$WORKDIR/planet.mbtiles" | cut -f1)
echo "[01] Downloaded planet.mbtiles ($SIZE_GB)"
