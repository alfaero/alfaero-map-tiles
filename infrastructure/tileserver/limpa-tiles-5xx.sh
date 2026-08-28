#!/usr/bin/env bash
# Varre o mapa base pela borda (Cloudflare), acha tiles com 5xx grudado,
# confirma que a origem serve 200 e purga essas URLs no Cloudflare.
#
# Uso:  bash limpa-502-raster.sh
#
# Precisa de: aws cli logado (conta 954222311704), python, curl.
set -uo pipefail

# IP da origem NAO vai versionado: este repo e publico e o IP atras do
# Cloudflare e justamente o que impede bypass da CDN/WAF.
ORIGEM_IP="${ORIGEM_IP:?defina ORIGEM_IP=<ip da origem> antes de rodar}"
HOST="raster.alfaero.com"
TMP=$(mktemp -d)

echo "== lendo credenciais do Secrets Manager (nao imprime) =="
SEC=$(aws secretsmanager get-secret-value --secret-id alfaero/map-tiles-pipeline --query SecretString --output text) || exit 1
CF_API_TOKEN=$(echo "$SEC" | python -c "import sys,json;print(json.load(sys.stdin)['CF_API_TOKEN'])")
CF_ZONE=$(echo "$SEC" | python -c "import sys,json;print(json.load(sys.stdin)['CF_ZONE_ID_ALFAERO'])")
unset SEC

echo "== gerando lista de tiles do Brasil =="
{
  # z6 completo
  for st in alfaero-day alfaero-night; do for suf in "" "@2x"; do
    for x in $(seq 18 26); do for y in $(seq 31 38); do echo "styles/$st/6/$x/$y$suf.png"; done; done
  done; done
  # z7 completo
  for st in alfaero-day alfaero-night; do for suf in "" "@2x"; do
    for x in $(seq 37 53); do for y in $(seq 62 77); do echo "styles/$st/7/$x/$y$suf.png"; done; done
  done; done
  # z8 completo
  for st in alfaero-day alfaero-night; do for suf in "" "@2x"; do
    for x in $(seq 75 107); do for y in $(seq 124 154); do echo "styles/$st/8/$x/$y$suf.png"; done; done
  done; done
} > "$TMP/urls.txt"
echo "   $(wc -l < "$TMP/urls.txt") URLs"

echo "== varrendo pela borda (alguns minutos) =="
: > "$TMP/ruins.txt"
xargs -a "$TMP/urls.txt" -P 12 -I{} sh -c '
  c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 40 "https://'"$HOST"'/{}")
  case "$c" in 5*) echo "{}" >> "'"$TMP"'/ruins.txt"; echo "  5xx($c) {}";; esac
' 2>/dev/null

N=$(wc -l < "$TMP/ruins.txt" 2>/dev/null | tr -d ' ')
N=${N:-0}
echo "== $N tiles com 5xx na borda =="
if [ "$N" -eq 0 ]; then echo "nada a purgar"; rm -rf "$TMP"; exit 0; fi

echo "== conferindo na origem (so purga o que a origem serve 200) =="
: > "$TMP/purgar.txt"
while read -r u; do
  c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 60 -H "Host: $HOST" "http://$ORIGEM_IP/$u")
  if [ "$c" = "200" ]; then
    echo "https://$HOST/$u" >> "$TMP/purgar.txt"
  else
    echo "  ORIGEM TAMBEM RUIM ($c): $u  -> nao e cache de borda, investigar"
  fi
done < "$TMP/ruins.txt"

P=$(wc -l < "$TMP/purgar.txt" 2>/dev/null | tr -d ' ')
P=${P:-0}
echo "== purgando $P URLs no Cloudflare (lotes de 30) =="
split -l 30 "$TMP/purgar.txt" "$TMP/lote."
for lote in "$TMP"/lote.*; do
  JSON=$(python -c "
import json,sys
print(json.dumps({'files':[l.strip() for l in open(sys.argv[1]) if l.strip()]}))" "$lote")
  R=$(curl -sS -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE/purge_cache" \
      -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" --data "$JSON")
  echo "  $(basename "$lote"): $(echo "$R" | python -c "import sys,json;d=json.load(sys.stdin);print('success='+str(d.get('success')),d.get('errors') or '')")"
done

echo "== reconferindo apos o purge =="
ok=0; ainda=0
while read -r full; do
  c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 60 "$full")
  if [ "$c" = "200" ]; then ok=$((ok+1)); else ainda=$((ainda+1)); echo "  AINDA $c: $full"; fi
done < "$TMP/purgar.txt"
echo "== resolvidos: $ok   ainda ruins: $ainda =="
rm -rf "$TMP"
