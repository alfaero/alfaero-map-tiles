# Styles

3 estilos MapLibre apontando pra source `openmaptiles` (PMTiles em `tiles.alfaero.com`).

| Style | Uso |
|---|---|
| `alfaero-day.json` | UI geral (web, mobile claro) — paleta neutra clara, motorway laranja Alfaero |
| `alfaero-night.json` | Modo escuro / cockpit noturno — fundo escuro azulado, alto contraste |
| `alfaero-vfr.json` | Aeronáutico VFR — terreno destacado (verde/marrom), runways visíveis, urbano apagado |

## Placeholder do PMTiles

Cada style contém `"url": "pmtiles://https://tiles.alfaero.com/planet-PLACEHOLDER.pmtiles"`.

O script `pipeline/04-publish-style.sh` substitui `PLACEHOLDER` pela versão atual antes de subir pro R2.
Os styles **commitados** no repo são templates — não use direto, sempre buscar de `https://tiles.alfaero.com/styles/...` em produção.

## Editar visualmente

Os JSONs são compatíveis com [Maputnik](https://maplibre.org/maputnik/) — abra o arquivo, edite, exporte, dê commit.

## Próximas iterações

- [ ] Adicionar sprites custom (logo Alfaero, ícones aeroporto)
- [ ] Camada overlay aeronáutica vinda dos pipelines `procedures`, `static-data`, `infotemp`
- [ ] Estilo 3D (terrain extrusion) — depende de tiles de elevação, pode usar `alfaero-terrain-bff` existente
