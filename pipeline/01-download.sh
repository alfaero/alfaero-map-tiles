#!/usr/bin/env bash
# Baixa o pmtiles mais recente do OpenFreeMap diretamente via HTTPS.
# OpenFreeMap distribui em https://btrfs.openfreemap.com/areas/planet/{version}/tiles.pmtiles
set -euo pipefail

: "${WEEK:?WEEK env required}"

WORKDIR="${WORKDIR:-/work}"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

OFM_BASE="${OFM_BASE:-https://btrfs.openfreemap.com}"

echo "[01] Fetching version index from $OFM_BASE/files.txt..."

# files.txt lista todos os arquivos de todas as versões. Extrair só versões e pegar a mais recente.
LATEST_VERSION=$(curl -sSfL "$OFM_BASE/files.txt" \
    | grep -oP 'areas/planet/\K[0-9]{8}_[0-9]{6}_pt' \
    | sort -u | tail -n 1)

if [[ -z "$LATEST_VERSION" ]]; then
    echo "[01] ERROR: could not parse latest version from $OFM_BASE/files.txt" >&2
    exit 2
fi

echo "[01] Latest version: $LATEST_VERSION"

# Verificar que pmtiles existe pra essa versão (algumas versões podem não ter)
PMTILES_URL="$OFM_BASE/areas/planet/$LATEST_VERSION/tiles.pmtiles"
if ! curl -sIfL "$PMTILES_URL" >/dev/null; then
    echo "[01] WARN: pmtiles not available for $LATEST_VERSION, trying previous versions..."
    PREV_VERSIONS=$(curl -sSfL "$OFM_BASE/files.txt" \
        | grep -oP 'areas/planet/\K[0-9]{8}_[0-9]{6}_pt' \
        | sort -ur | head -n 5)
    for v in $PREV_VERSIONS; do
        if curl -sIfL "$OFM_BASE/areas/planet/$v/tiles.pmtiles" >/dev/null; then
            LATEST_VERSION="$v"
            PMTILES_URL="$OFM_BASE/areas/planet/$v/tiles.pmtiles"
            echo "[01] Found pmtiles in: $v"
            break
        fi
    done
fi

# Tamanho esperado
SIZE_BYTES=$(curl -sIfL "$PMTILES_URL" | awk -v IGNORECASE=1 '/^content-length:/ {gsub("\r",""); print $2}')
SIZE_GB=$((SIZE_BYTES / 1024 / 1024 / 1024))
echo "[01] Downloading $PMTILES_URL (~${SIZE_GB} GB)..."

# Baixa direto como nosso planet pmtiles (já no formato certo, sem conversão necessária)
curl -fL --retry 3 --retry-delay 30 \
    -o "$WORKDIR/$PMTILES_NAME" \
    "$PMTILES_URL"

# Validação básica
ACTUAL_SIZE=$(stat -c%s "$WORKDIR/$PMTILES_NAME")
if [[ "$ACTUAL_SIZE" -lt 1000000000 ]]; then
    echo "[01] ERROR: downloaded file too small (${ACTUAL_SIZE} bytes), expected >1GB" >&2
    exit 3
fi

ACTUAL_GB=$((ACTUAL_SIZE / 1024 / 1024 / 1024))
echo "[01] Downloaded $PMTILES_NAME (${ACTUAL_GB} GB) — source: $LATEST_VERSION"

# Exporta variável pra ser usada na etapa de notificação/styles
echo "$LATEST_VERSION" > "$WORKDIR/.source_version"
