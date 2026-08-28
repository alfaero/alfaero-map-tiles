#!/usr/bin/env bash
# Pre-aquece o cache de tiles raster do mapa base para o bbox do Brasil.
#
# POR QUE EXISTE: o TileServer GL renderiza cada tile sob demanda (200-1300ms
# medidos em 26/08/2026) e nao guarda o PNG. Com a zona `raster_cache` do nginx
# (spec 002), o SEGUNDO pedido do mesmo tile sai do disco em ~0,3ms -- este
# script garante que o piloto nunca seja o primeiro a pedir.
#
# Rodar DENTRO do servidor (http://127.0.0.1 + Host) enche o cache da ORIGEM.
# Rodar de fora (https://raster.alfaero.com) enche tambem o POP do Cloudflare,
# mas so o POP de quem executa -- por isso o de dentro e o que importa.
#
# Uso:
#   ./warm-brazil.sh                      # origem, alfaero-night, z0-10
#   ./warm-brazil.sh --max-zoom 8         # so ate z8
#   ./warm-brazil.sh --style alfaero-day --retina
#   ./warm-brazil.sh --base https://raster.alfaero.com   # aquece o POP
#
# Reexecutavel: tile ja em cache nao custa render (responde em ~0,3ms).
set -euo pipefail

STYLE="alfaero-night"
MIN_ZOOM=0
MAX_ZOOM=10
RETINA=""
BASE="http://127.0.0.1"
HOST_HEADER="raster.alfaero.com"
# 2 vCPU na Hostinger, compartilhados com backoffice/tpeps/trolley-spot: 3 e o
# teto que aquece rapido sem competir com o trafego real.
JOBS=3

# bbox do Brasil com folga (inclui faixas de fronteira e as rotas oceanicas
# proximas): lat 6 -> -34, lon -74 -> -34.
LAT_N=6; LAT_S=-34; LON_W=-74; LON_E=-34

while [ $# -gt 0 ]; do
  case "$1" in
    --style)     STYLE="$2"; shift 2 ;;
    --min-zoom)  MIN_ZOOM="$2"; shift 2 ;;
    --max-zoom)  MAX_ZOOM="$2"; shift 2 ;;
    --retina)    RETINA="@2x"; shift ;;
    --base)      BASE="$2"; shift 2 ;;
    --jobs)      JOBS="$2"; shift 2 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 2 ;;
  esac
done

URLS=$(mktemp); trap 'rm -f "$URLS"' EXIT

python3 - "$MIN_ZOOM" "$MAX_ZOOM" "$LAT_N" "$LAT_S" "$LON_W" "$LON_E" \
         "$BASE" "$STYLE" "$RETINA" > "$URLS" <<'PY'
import math, sys
zmin, zmax = int(sys.argv[1]), int(sys.argv[2])
latN, latS, lonW, lonE = (float(x) for x in sys.argv[3:7])
base, style, retina = sys.argv[7], sys.argv[8], sys.argv[9]

def xy(lat, lon, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat = max(min(lat, 85.05), -85.05)
    r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))

for z in range(zmin, zmax + 1):
    x0, y0 = xy(latN, lonW, z)
    x1, y1 = xy(latS, lonE, z)
    for x in range(min(x0, x1), max(x0, x1) + 1):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            print(f"{base}/styles/{style}/{z}/{x}/{y}{retina}.png")
PY

TOTAL=$(wc -l < "$URLS")
echo "[warm] estilo=$STYLE retina=${RETINA:-nao} z$MIN_ZOOM-$MAX_ZOOM base=$BASE tiles=$TOTAL jobs=$JOBS"
START=$(date +%s)

# --fail-with-body nao existe em curl antigo; -f basta. -s pra nao poluir o log.
# `nice` porque a maquina serve producao enquanto isto roda.
nice -n 10 xargs -a "$URLS" -P "$JOBS" -I{} \
  curl -sf -o /dev/null -H "Host: $HOST_HEADER" --max-time 30 {} \
  || echo "[warm] AVISO: pelo menos um tile falhou (segue o baile; reexecutar cobre)"

ELAPSED=$(( $(date +%s) - START ))
echo "[warm] concluido em ${ELAPSED}s ($((TOTAL / (ELAPSED > 0 ? ELAPSED : 1))) tiles/s)"
