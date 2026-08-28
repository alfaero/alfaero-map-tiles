#!/usr/bin/env bash
# Aquece o cache de origem (zona raster_cache do nginx) com o MUNDO INTEIRO
# nos zooms baixos, para o zoom global do app nao renderizar nada na hora.
#
# Roda NO servidor: bate no nginx local com Host raster.alfaero.com, entao o
# PNG renderizado fica gravado na zona e serve todos os POPs do Cloudflare.
#
# Uso:  nohup bash /opt/alfaero-tileserver/warm-world.sh 7 >> /var/log/alfaero-warm-world.log 2>&1 &
#       (argumento = zoom maximo; padrao 7. z0-7 = 21.845 tiles por combo)
set -uo pipefail

ZMAX="${1:-7}"
HOST="raster.alfaero.com"
PAR=2   # 2 vCPU: mais que isso so enfileira render

gerar() {
  for st in alfaero-day alfaero-night; do
    for suf in "" "@2x"; do
      for z in $(seq 0 "$ZMAX"); do
        n=$(( 1 << z ))
        for x in $(seq 0 $((n-1))); do
          for y in $(seq 0 $((n-1))); do
            echo "/styles/$st/$z/$x/$y$suf.png"
          done
        done
      done
    done
  done
}

echo "[$(date -Is)] inicio zmax=$ZMAX"
gerar | xargs -P "$PAR" -I{} sh -c '
  r=$(curl -s -o /dev/null -w "%{http_code}" --max-time 90 -H "Host: '"$HOST"'" "http://127.0.0.1{}")
  [ "$r" = "200" ] || echo "FALHOU $r {}"
'
echo "[$(date -Is)] fim. cache: $(du -sh /var/cache/nginx/raster | cut -f1)"
echo "reexecutar para conferir: as linhas FALHOU acima sao os que precisam de nova passada"
