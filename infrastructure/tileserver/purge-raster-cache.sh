#!/usr/bin/env bash
# Invalida o cache de disco do nginx (`raster_cache`) do raster.alfaero.com.
#
# QUANDO RODAR: sempre que o CONTEUDO renderizado mudar -- planet PMTiles novo,
# estilo alterado, mbtiles de carta re-registrado pelo admin-daemon. Sem isto o
# `proxy_cache_valid 200 30d` serve o tile antigo por 30 dias, e o Cloudflare
# repovoa a partir dele: o piloto ve mapa velho mesmo depois do purge da CDN.
#
# Uso (NO SERVIDOR, como root):
#   ./purge-raster-cache.sh --all                       # limpa tudo
#   ./purge-raster-cache.sh /styles/alfaero-night/6/22/36.png   # um URI
#   ./purge-raster-cache.sh --prefix /data/9fd58876     # tudo de uma carta
#
# O nginx de serie nao tem `proxy_cache_purge` (e do ngx_cache_purge, modulo
# nao compilado aqui), entao o purge por URI recalcula o caminho do arquivo:
# a chave e "raster:$uri", o nome do arquivo e o MD5 dela, e `levels=1:2`
# guarda em <ultimo char>/<2 chars anteriores>/<md5>.
set -euo pipefail

CACHE_DIR=/var/cache/nginx/raster

if [ $# -eq 0 ]; then
  echo "uso: $0 --all | --prefix <prefixo-uri> | <uri>" >&2; exit 2
fi

if [ ! -d "$CACHE_DIR" ]; then
  echo "[purge] $CACHE_DIR nao existe -- nada a fazer"; exit 0
fi

antes=$(du -sh "$CACHE_DIR" | cut -f1)

case "$1" in
  --all)
    # find -delete em vez de rm -rf: apaga o CONTEUDO sem destruir o diretorio
    # (que o nginx espera existir, com dono www-data).
    find "$CACHE_DIR" -mindepth 1 -type f -delete
    find "$CACHE_DIR" -mindepth 1 -type d -empty -delete
    echo "[purge] cache inteiro limpo (era $antes)"
    ;;
  --prefix)
    [ $# -ge 2 ] || { echo "--prefix exige o prefixo" >&2; exit 2; }
    # Sem indice reverso de chave->arquivo, a unica forma honesta e ler o
    # cabecalho de cada entrada: o nginx grava a KEY em texto no inicio do
    # arquivo, entao `grep -l` acha as do prefixo.
    n=0
    while IFS= read -r f; do rm -f "$f"; n=$((n+1)); done < <(
      grep -rlsa "^KEY: raster:$2" "$CACHE_DIR" || true
    )
    echo "[purge] $n entradas removidas para o prefixo $2 (era $antes)"
    ;;
  *)
    uri="$1"
    md5=$(printf '%s' "raster:$uri" | md5sum | cut -d' ' -f1)
    f="$CACHE_DIR/${md5: -1}/${md5: -3:2}/$md5"
    if [ -f "$f" ]; then rm -f "$f"; echo "[purge] removido $uri ($f)";
    else echo "[purge] $uri nao estava em cache ($f)"; fi
    ;;
esac
