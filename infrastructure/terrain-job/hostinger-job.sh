#!/bin/bash
# Terreno da visão sintética (spec 005) rodando na VPS da Hostinger, que é a
# origem de produção: prioridade mínima de CPU e disco, banda limitada no
# upload, trava de disco e limpeza no fim. A chave do R2 chega pelo ambiente
# (variáveis RCLONE_CONFIG_ALFAERO_*) e nunca é gravada em disco.
#
# Não rode direto: use hostinger-launch.sh, que envia este script e as chaves.
#
# Modo de região (spec 007): com REGION_NAME, REGION_BBOX e REGION_MINZOOM no
# ambiente o job recorta só essa região (até z11) e sobe só esse arquivo.
set -o pipefail
STAMP="${STAMP:?}"
SRC="https://download.mapterhorn.com/planet.pmtiles"
WORK="/root/terrain-job"
LOG="$WORK/terrain-${STAMP}.log"
MAX_DISK_PCT=85
STATUS="FAILED"
mkdir -p "$WORK" && cd "$WORK" || exit 4
exec > >(tee -a "$LOG") 2>&1
echo "=== TERRAIN START $(date -u +%FT%TZ) host=$(hostname) ==="
renice -n 19 $$ >/dev/null
ionice -c 3 -p $$

PLANET="terrain-glo30-planet-z0-9-${STAMP}.pmtiles"
SA="terrain-glo30-sa-z0-11-${STAMP}.pmtiles"
if [[ -n "${REGION_NAME:-}" ]]; then
  REGION="terrain-glo30-${REGION_NAME}-z${REGION_MINZOOM:?}-11-${STAMP}.pmtiles"
  : "${REGION_BBOX:?}"
fi

finish() {
  [[ -n "${GUARD:-}" ]] && kill "$GUARD" 2>/dev/null
  echo "=== TERRAIN END $(date -u +%FT%TZ) status=${STATUS} ==="
  rclone copyto "$LOG" "alfaero:alfaero-map-tiles/logs/terrain-${STAMP}-${STATUS}.log" \
    --header-upload "Content-Type: text/plain" || true
  rm -f "$WORK"/*.pmtiles "$WORK"/sha256.txt
}
trap finish EXIT

# Trava de disco: a origem de produção nunca chega a encher.
(
  while sleep 30; do
    pct=$(df --output=pcent / | tail -1 | tr -dc 0-9)
    if (( pct >= MAX_DISK_PCT )); then
      echo "DISK GUARD: / em ${pct}%, abortando"
      pkill -TERM -f "pmtiles extract" ; pkill -TERM -f "rclone copyto"
      kill -TERM $$
      exit
    fi
  done
) &
GUARD=$!

# Teto de tempo: 6 horas.
( sleep 21600; echo "TIMEOUT"; kill -TERM $$ ) &

# Confere leitura e escrita no R2 antes de baixar 16 GB.
echo "$STAMP" > probe.txt
rclone copyto probe.txt "alfaero:alfaero-map-tiles/logs/terrain-${STAMP}-probe.txt" || exit 3
rm -f probe.txt

if [[ -n "${REGION:-}" ]]; then
  FILES=("$REGION")
  pmtiles extract "$SRC" "$REGION" --bbox="$REGION_BBOX" --minzoom="$REGION_MINZOOM" --maxzoom=11 \
    --download-threads=4 || exit 6
else
  FILES=("$PLANET" "$SA")
  pmtiles extract "$SRC" "$PLANET" --maxzoom=9 --download-threads=4 || exit 5
  pmtiles extract "$SRC" "$SA" --bbox=-82,-56,-34,13 --maxzoom=11 --download-threads=4 || exit 6
fi
for f in "${FILES[@]}"; do
  pmtiles verify "$f" || exit 8
  pmtiles show "$f"
done
ls -la "$WORK"
sha256sum "${FILES[@]}" | tee sha256.txt

for f in "${FILES[@]}"; do
  rclone copyto "$f" "alfaero:alfaero-map-tiles/$f" \
    --s3-chunk-size 64M --s3-upload-concurrency 4 --bwlimit 25M --stats 60s || exit 9
done
rclone copyto sha256.txt "alfaero:alfaero-map-tiles/terrain-glo30-${REGION_NAME:+${REGION_NAME}-}${STAMP}.sha256" || exit 10
STATUS="SUCCESS"
