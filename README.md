# Alfaero Map Tiles

Self-hosted vector map tile infrastructure baseado em [OpenFreeMap](https://openfreemap.org/), [PMTiles](https://protomaps.com/docs/pmtiles), [Cloudflare R2](https://developers.cloudflare.com/r2/) e [Cloudflare CDN](https://developers.cloudflare.com/cache/).

Serve `tiles.alfaero.com` com cobertura mundial (planet OpenStreetMap), atualizada semanalmente, consumida pelos apps Alfaero (mobile, operator, vip-web, b2b, backoffice) via MapLibre.

## Arquitetura

```
Clientes (MapLibre + pmtiles)
    │ HTTPS Range Requests
    ▼
Cloudflare CDN (tiles.alfaero.com, Cache Reserve ON, Tiered Cache)
    │
    ▼
R2 bucket alfaero-map-tiles
  ├─ planet-{YYYY}w{WW}.pmtiles
  ├─ styles/{alfaero-day,alfaero-night,alfaero-vfr}.json
  ├─ sprites/alfaero/
  └─ fonts/

Pipeline semanal (Step Functions + EC2 spot):
  1. rclone download mbtiles do OpenFreeMap
  2. pmtiles convert mbtiles → pmtiles
  3. rclone upload pro R2
  4. Atualiza styles/*.json
  5. Cloudflare API purge styles
```

## Estrutura do repo

- `pipeline/` — Scripts shell que rodam no job semanal
- `terraform/` — IaC: R2, Cloudflare, AWS (Step Functions + EC2)
- `styles/` — MapLibre style JSONs (day, night, vfr)
- `sprites/` — Ícones custom Alfaero (SVG fonte + PNG gerado)
- `fonts/` — Glyphs gerados via fontnik
- `benchmark/` — Página HTML + scripts pra validar performance
- `infrastructure/` — User-data scripts e workflows
- `docs/` — Integração Flutter, Web, runbook operacional

## Setup inicial

Veja [docs/operations.md](docs/operations.md).

Resumo:
1. Configurar credenciais Cloudflare e AWS no `.env`
2. `cd terraform && terraform apply` (cria R2, custom domain, AWS SFN)
3. Trigger manual do job (gera primeiro `planet-{...}.pmtiles`)
4. Validar com `benchmark/`
5. Migrar clientes (Flutter, web) — ver `docs/integration-*.md`

## Custos estimados

- R2 storage: ~$4/mês (250GB com 2 versões)
- R2 reads: ~$30/mês (~80M tiles/mês)
- Egress: $0 (Cloudflare R2 não cobra)
- AWS pipeline: ~$5/mês (EC2 spot semanal)
- **Total: ~$40/mês**

## Atribuição obrigatória

Por licença OSM/OpenMapTiles/OpenFreeMap, todos os clientes devem exibir:

> © OpenFreeMap © OpenMapTiles © OpenStreetMap

MapLibre faz isso automaticamente via `AttributionControl`. Não remover.

## Licença

MIT (dados externos seguem suas próprias licenças — ver atribuição).
