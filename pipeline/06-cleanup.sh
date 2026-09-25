#!/usr/bin/env bash
# Apaga planetas antigos (planet-*.pmtiles) do R2 sem nunca apagar um em uso.
#
# Em uso = referenciado por algum estilo publicado em styles/*.json no R2, ou
# listado em PROTECT_PMTILES (separado por virgula).
#
# O tileserver raster da Hostinger le o planeta por URL no config.json dele
# (/opt/alfaero-tileserver/config.json, fonte "planet"), que fica fora do
# bucket. Por isso o planeta dele e o padrao de PROTECT_PMTILES: quando o
# raster migrar de planeta, atualizar aqui junto.
#
# Dos que nao estao em uso, mantem os KEEP_VERSIONS mais novos por DATA de
# modificacao (a reserva para voltar atras). Nao ordenar por nome:
# `planet-2026w25` ordena depois de `planet-20260830_...` ('w' vem depois dos
# digitos), e a ordem por nome mantinha o velho e apagava o bom.
#
# DRY_RUN=1 so lista o que apagaria.
set -euo pipefail

: "${R2_BUCKET:?R2_BUCKET env required}"
KEEP="${KEEP_VERSIONS:-1}"
PROTECT="${PROTECT_PMTILES:-planet-2026w25.pmtiles}"
DRY_RUN="${DRY_RUN:-0}"

echo "[06] Lendo os estilos publicados em r2://$R2_BUCKET/styles/ ..."
# Se a leitura falhar, o set -e aborta ANTES de qualquer apagamento: sem saber
# o que esta em uso, nada e apagado.
STYLES=$(rclone cat "alfaero:$R2_BUCKET/styles/" --include '*.json')
IN_USE=$(printf '%s\n' "$STYLES" | grep -oE 'planet-[0-9A-Za-z_.-]+\.pmtiles' | sort -u || true)
if [[ -z "$IN_USE" ]]; then
    echo "[06] ERRO: nenhum estilo referencia um planeta; abortando sem apagar nada" >&2
    exit 1
fi
for f in ${PROTECT//,/ }; do
    IN_USE=$(printf '%s\n%s\n' "$IN_USE" "$f")
done
IN_USE=$(printf '%s\n' "$IN_USE" | sed '/^$/d' | sort -u)
echo "[06] Em uso (nunca apagados):"
echo "$IN_USE" | sed 's/^/  /'

echo "[06] Listando planet-*.pmtiles ..."
# "data;nome", do mais novo para o mais velho.
LIST=$(rclone lsf "alfaero:$R2_BUCKET/" --include 'planet-*.pmtiles' --format "tp" --separator ";" | sort -r)

KEPT=0
TO_DELETE=""
while IFS=';' read -r MODTIME FILE; do
    [[ -z "${FILE:-}" ]] && continue
    if grep -qxF "$FILE" <<< "$IN_USE"; then
        echo "[06] Mantem $FILE ($MODTIME, em uso)"
    elif (( KEPT < KEEP )); then
        KEPT=$((KEPT + 1))
        echo "[06] Mantem $FILE ($MODTIME, reserva)"
    else
        TO_DELETE+="$FILE"$'\n'
    fi
done <<< "$LIST"

if [[ -z "$TO_DELETE" ]]; then
    echo "[06] Nada a apagar"
    exit 0
fi

while IFS= read -r FILE; do
    [[ -z "$FILE" ]] && continue
    if [[ "$DRY_RUN" == "1" ]]; then
        echo "[06] (simulacao) apagaria $FILE"
    else
        echo "[06] Apagando $FILE ..."
        rclone deletefile "alfaero:$R2_BUCKET/$FILE"
    fi
done <<< "$TO_DELETE"

echo "[06] Limpeza concluida"
