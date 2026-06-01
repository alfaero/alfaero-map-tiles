#!/usr/bin/env bash
# Mede latência (TTFB) de Range Requests no pmtiles em produção.
# Uso: ./benchmark.sh [num_requests=100] [tiles_url=https://tiles.alfaero.com/...]

set -euo pipefail

N="${1:-100}"
URL="${2:-https://tiles.alfaero.com/planet-latest.pmtiles}"

# Detecta tamanho do arquivo
SIZE=$(curl -sIL "$URL" | awk -v IGNORECASE=1 '/^content-length:/ {print $2}' | tr -d '\r')

if [[ -z "$SIZE" ]]; then
    echo "ERROR: could not get Content-Length from $URL" >&2
    exit 1
fi

echo "Target: $URL"
echo "File size: $SIZE bytes ($(($SIZE / 1024 / 1024 / 1024)) GB)"
echo "Sampling $N random tile ranges..."
echo

TMPFILE=$(mktemp)
trap 'rm -f $TMPFILE' EXIT

for i in $(seq 1 $N); do
    # Random offset within file (avoid first 1MB header and last 100KB)
    OFFSET=$(( (RANDOM * RANDOM) % (SIZE - 1100000) + 1000000 ))
    RANGE_END=$((OFFSET + 30000))

    curl -o /dev/null -s \
        -w "%{http_code} %{time_namelookup} %{time_connect} %{time_starttransfer} %{time_total} %{size_download}\n" \
        -H "Range: bytes=${OFFSET}-${RANGE_END}" \
        "$URL" >> "$TMPFILE"

    printf '.'
    [[ $((i % 50)) -eq 0 ]] && printf ' %d\n' "$i"
done
echo

echo
echo "=== Status codes ==="
awk '{print $1}' "$TMPFILE" | sort | uniq -c

echo
echo "=== Latencies (ms) ==="
# time_starttransfer = TTFB in seconds. Convert to ms.
awk '$1 ~ /^20/ { print $4 * 1000 }' "$TMPFILE" | sort -n | awk '
  {
    a[NR] = $1
    sum += $1
  }
  END {
    if (NR == 0) { print "No successful requests."; exit }
    printf "  Count:   %d\n", NR
    printf "  Min:     %.1f ms\n", a[1]
    printf "  P50:     %.1f ms\n", a[int(NR*0.50)]
    printf "  P75:     %.1f ms\n", a[int(NR*0.75)]
    printf "  P95:     %.1f ms\n", a[int(NR*0.95)]
    printf "  P99:     %.1f ms\n", a[int(NR*0.99)]
    printf "  Max:     %.1f ms\n", a[NR]
    printf "  Avg:     %.1f ms\n", sum/NR
  }
'

echo
echo "=== Acceptance criteria ==="
echo "  ✓ PASS  if P50 < 50 ms AND P95 < 200 ms AND zero non-206 statuses"
echo "  ✗ FAIL  otherwise — check Cache Reserve + Tiered Cache config"
