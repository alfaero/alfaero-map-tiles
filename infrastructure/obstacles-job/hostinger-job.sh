#!/bin/bash
# Base de obstáculos da visão sintética (spec 006) rodando na VPS da Hostinger,
# que é a origem de produção: prioridade mínima de CPU e disco, banda limitada
# no upload, trava de disco e limpeza no fim. A chave do R2 chega pelo ambiente
# (variáveis RCLONE_CONFIG_ALFAERO_*) e nunca é gravada em disco.
#
# Não rode direto: use hostinger-launch.sh, que envia este script, o pacote
# Python e as chaves.
set -o pipefail
STAMP="${STAMP:?}"
PBF_URL="https://download.geofabrik.de/south-america-latest.osm.pbf"
WORK="/root/obstacles-job"
LOG="$WORK/obstacles-${STAMP}.log"
MAX_DISK_PCT=85
# A1: abaixo disto a coleta da ANEEL ou a junção veio pela metade (17.012 em 18/10).
MIN_TURBINES=12000
STATUS="FAILED"
mkdir -p "$WORK" && cd "$WORK" || exit 4
exec > >(tee -a "$LOG") 2>&1
echo "=== OBSTACLES START $(date -u +%FT%TZ) host=$(hostname) ==="
renice -n 19 $$ >/dev/null
ionice -c 3 -p $$

OUT="obstacles-sa-z10-${STAMP}.pmtiles"

finish() {
  [[ -n "${GUARD:-}" ]] && kill "$GUARD" 2>/dev/null
  echo "=== OBSTACLES END $(date -u +%FT%TZ) status=${STATUS} ==="
  rclone copyto "$LOG" "alfaero:alfaero-map-tiles/logs/obstacles-${STAMP}-${STATUS}.log" \
    --header-upload "Content-Type: text/plain" || true
  rm -f "$WORK"/*.pbf "$WORK"/*.pmtiles "$WORK"/*.mbtiles "$WORK"/sha256.txt
}
trap finish EXIT

# Trava de disco: a origem de produção nunca chega a encher.
(
  while sleep 30; do
    pct=$(df --output=pcent / | tail -1 | tr -dc 0-9)
    if (( pct >= MAX_DISK_PCT )); then
      echo "DISK GUARD: / em ${pct}%, abortando"
      pkill -TERM -f "osmium" ; pkill -TERM -f "obstacles.build" ; pkill -TERM -f "rclone copyto"
      kill -TERM $$
      exit
    fi
  done
) &
GUARD=$!

# Teto de tempo: 4 horas.
( sleep 14400; echo "TIMEOUT"; kill -TERM $$ ) &

# Ferramentas: osmium-tool e um venv com pyosmium e requests (só na primeira vez).
command -v osmium >/dev/null || { apt-get update -qq && apt-get install -y -qq osmium-tool python3-venv; } || exit 11
[[ -x venv/bin/python ]] || { python3 -m venv venv && venv/bin/pip install -q osmium requests; } || exit 12
command -v pmtiles >/dev/null || exit 13

# Confere escrita no R2 antes de baixar 3 GB.
echo "$STAMP" > probe.txt
rclone copyto probe.txt "alfaero:alfaero-map-tiles/logs/obstacles-${STAMP}-probe.txt" || exit 3
rm -f probe.txt

# O Geofabrik troca o arquivo uma vez por dia: o md5 vem antes do PBF e, se
# o arquivo mudou no meio do download, baixa de novo (até 3 vezes).
ok=0
for attempt in 1 2 3; do
  curl -fsSL --retry 5 -o sa.osm.pbf.md5 "$PBF_URL.md5" || exit 5
  curl -fsSL --retry 5 --retry-delay 30 -o sa.osm.pbf "$PBF_URL" || exit 5
  if [[ "$(md5sum sa.osm.pbf | cut -d' ' -f1)" == "$(cut -d' ' -f1 sa.osm.pbf.md5)" ]]; then ok=1; break; fi
  echo "md5 do PBF nao confere (tentativa $attempt)"
  sleep 120
done
(( ok )) || exit 6

# Mesmo filtro de obstacles/osm.py (OSMIUM_FILTERS).
osmium tags-filter sa.osm.pbf \
  w/power=line n/power=tower \
  nw/man_made=mast,tower,communications_tower,chimney \
  nw/generator:source=wind \
  -o filtered.pbf --overwrite || exit 7
ls -la sa.osm.pbf filtered.pbf
rm -f sa.osm.pbf

venv/bin/python -m obstacles.build --osm-pbf filtered.pbf --stamp "$STAMP" \
  --mbtiles out.mbtiles --save-aneel-json "aneel-${STAMP}.json" || exit 8
venv/bin/python -m obstacles.check out.mbtiles --min-turbines "$MIN_TURBINES" || exit 9

pmtiles convert out.mbtiles "$OUT" || exit 10
pmtiles verify "$OUT" || exit 10
pmtiles show "$OUT"
sha256sum "$OUT" | tee sha256.txt

rclone copyto "$OUT" "alfaero:alfaero-map-tiles/$OUT" --bwlimit 25M --stats 60s || exit 14
rclone copyto sha256.txt "alfaero:alfaero-map-tiles/obstacles-sa-z10-${STAMP}.sha256" || exit 15
# A coleta da ANEEL fica guardada: refazer a base sem depender do SIGEL no ar.
rclone copyto "aneel-${STAMP}.json" "alfaero:alfaero-map-tiles/sources/aneel-${STAMP}.json" || exit 16
STATUS="SUCCESS"
