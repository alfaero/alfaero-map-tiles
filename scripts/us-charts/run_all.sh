#!/usr/bin/env bash
# Gera as quatro cartas raster dos EUA de uma edição, dentro da imagem alfaero-us-charts.
#
# Montagens esperadas (ver README.md):
#   /dl       zips da FAA (somente leitura)
#   /scripts  esta pasta (somente leitura)
#   /work     volume Docker (partes em tiles e mbtiles; NÃO usar pasta do Windows)
#   /work/tmp tmpfs (docker run --tmpfs /work/tmp:size=6g): reprojeções temporárias fora do vhdx
#
# Uso: bash /scripts/run_all.sh <AAAA-MM-DD edição> <AAAA-MM-DD validade> [series...]
#   series: sec enr_l enr_h enr_p (padrão: todas)
set -euo pipefail
EDITION="$1"; VALID="$2"; shift 2
SERIES="${*:-sec enr_l enr_h enr_p}"
NEATLINES="${NEATLINES:-/scripts/neatlines.geojson}"   # a rotina automática passa os recortes da edição nova
Q=75   # WebP: q75 escolhido na comparação de 21/10/2026 (q85 +41% de tamanho, ganho invisível)

declare -A ID ZOOM META
ID[sec]=3447a49e-bcf6-4a02-a033-f726105eb5a0;   ZOOM[sec]=1-11
ID[enr_l]=c75884f3-443a-4f1a-aa1a-01f99ad9075f; ZOOM[enr_l]=5-10
ID[enr_h]=c3fba2b7-575e-4fb9-bf30-8f75a86520f2; ZOOM[enr_h]=4-9
ID[enr_p]=7f17cb4a-88b3-41c7-bf31-67b1f0c48929; ZOOM[enr_p]=2-7
# metadados iguais aos dos arquivos no ar em 21/10/2026 (faa_edition e valid_until são acrescentados)
META[sec]='{"description": "Sectional Chart Tiles", "version": "1.0"}'
META[enr_l]='{"name": "enr_low_usa", "description": "enr_low_usa", "version": "1.4-q75"}'
META[enr_h]='{"name": "enr_high_usa", "description": "enr_high_usa", "version": "1.4-q75"}'
META[enr_p]='{"name": "hawaii_pacific", "description": "hawaii_pacific", "version": "1.3"}'

for s in $SERIES; do
  t0=$(date +%s)
  echo "== $s: partes (zoom ${ZOOM[$s]})"
  rm -rf "/work/parts/$s"
  python3 /scripts/build_parts.py --neatlines "$NEATLINES" --series "$s" \
    --zoom "${ZOOM[$s]}" --quality $Q --work /work
  t1=$(date +%s)
  echo "== $s: junção"
  python3 /scripts/merge.py --series "$s" --work /work --out "/work/out/${ID[$s]}.mbtiles" --quality $Q \
    --meta "${META[$s]}" --edition "$EDITION" --valid-until "$VALID"
  t2=$(date +%s)
  echo "== $s: partes $((t1-t0)) s, junção $((t2-t1)) s"
  rm -rf "/work/parts/$s"   # partes só servem para a junção
done
