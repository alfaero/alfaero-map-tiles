# Benchmark

Validação de performance do `tiles.alfaero.com`. Roda depois de subir o primeiro `planet-{week}.pmtiles` (Sprint S2 concluído).

## 1. Benchmark interativo (browser)

```bash
# servir local
python3 -m http.server 8080
# abrir http://localhost:8080/index.html

# OU host gratuito: subir como Cloudflare Pages (free) em benchmark.alfaero.com
```

Pan/zoom pelas cidades pré-configuradas (SP, RJ, BSB, Manaus, Paris, NYC, Tóquio) e observe o painel:

- **Tiles loaded** — quantos requests foram feitos
- **Avg / P95 load time** — TTFB médio e P95
- **Last fetch** — último arquivo + duração

Override do host (pra testar staging): `?host=staging-tiles.alfaero.com`

## 2. Benchmark CLI (TTFB de Range Requests)

```bash
./benchmark.sh 200
```

Output esperado em produção saudável (POP Brasil, cache aquecido):

```
=== Latencies (ms) ===
  Count:   195
  Min:     8.2 ms
  P50:     22.4 ms
  P75:     38.1 ms
  P95:     142.6 ms
  P99:     287.3 ms
  Max:     410.5 ms
  Avg:     38.9 ms
```

Critério de aprovação:
- ✅ P50 < 50 ms (cache hit)
- ✅ P95 < 200 ms (incluindo alguns cold)
- ✅ 100% requests com status 206 (Partial Content)
- ✅ Zero erros 5xx

## 3. Teste de carga (vegeta)

```bash
# Instalar vegeta: https://github.com/tsenart/vegeta
URL="https://tiles.alfaero.com/planet-2026w22.pmtiles"
OFFSET=$((RANDOM * RANDOM % 1000000000 + 1000000))

echo "GET $URL" | vegeta attack \
  -rate=100 -duration=120s \
  -header="Range: bytes=${OFFSET}-$((OFFSET + 30000))" \
  | vegeta report
```

Alvo: throughput ≥100 req/s, latência P99 <500 ms.

## 4. Comparativo direto

Abrir 3 abas do browser lado a lado, mesma localização:

| URL | Esperado |
|---|---|
| `index.html` (alfaero) | medir |
| `https://demotiles.maplibre.org/` (OpenFreeMap) | medir |
| Mapbox (se tiver chave) | medir |

Devtools → Network → filter `pmtiles` ou `tiles` → ver TTFB.

## Que fazer se falhar

| Sintoma | Diagnóstico | Ação |
|---|---|---|
| P50 alto (>100ms) | Cache Reserve desligado ou TTL curto | Ativar Cache Reserve no R2/CF Rules |
| P95 muito alto, P50 ok | Tiered Cache desligado | Ativar Tiered Cache → Smart |
| Erros 5xx | Custom domain mal configurado | Verificar DNS + R2 custom domain status |
| Status 200 em vez de 206 | Cloudflare não está respeitando Range | Verificar Cache Rules (Range Request handling) |
| Tudo lento globalmente | R2 location ruim | Mover bucket pra WNAM (Western North America) |
