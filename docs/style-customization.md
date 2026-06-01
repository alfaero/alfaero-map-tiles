# Style customization

## Editar visualmente (Maputnik)

[Maputnik](https://maplibre.org/maputnik/) é o editor de styles MapLibre. Workflow:

1. Abra https://maplibre.org/maputnik/
2. **Open → Upload** → carregar `styles/alfaero-day.json`
3. Editar visualmente (cores, fontes, filtros)
4. **Export → Download** → salvar de volta em `styles/alfaero-day.json`
5. Commit + push → próximo run do pipeline publica

## Editar à mão

Especificação MapLibre: https://maplibre.org/maplibre-style-spec/

Cada style é um JSON com:
- `sources`: fontes de dados (no nosso caso só `openmaptiles` apontando pro PMTiles)
- `glyphs`: URL template das fonts
- `sprite`: URL base dos sprites
- `layers`: array ordenada (renderiza de baixo pra cima)

## Camadas (layers) disponíveis no source

Schema OpenMapTiles. Layers principais:

| source-layer | Conteúdo |
|---|---|
| `landcover` | wood, grass, glacier, sand, farmland |
| `landuse` | residential, commercial, industrial, park, cemetery |
| `water` | oceanos, lagos, rios (polígono) |
| `waterway` | rios (linha) |
| `transportation` | roads (motorway, primary, secondary, minor, service) |
| `transportation_name` | nomes de ruas |
| `building` | edificações |
| `boundary` | fronteiras admin |
| `aeroway` | runways, taxiways |
| `aerodrome_label` | aeroportos |
| `place` | cidades, países, continentes |
| `housenumber` | numerações |
| `poi` | POIs |
| `mountain_peak` | picos |

Doc completa: https://openmaptiles.org/schema/

## Paleta Alfaero (referência)

| Cor | Hex | Uso |
|---|---|---|
| Laranja Alfaero | `#FF6B35` | Motorways, destaque, marca |
| Marrom Alfaero | `#5a3a2a` | Texto em fundos claros (VFR) |
| Bege VFR | `#f0e4c8` | Background VFR |
| Cinza claro | `#f5f3ee` | Background day |
| Azul noite | `#1a1a2e` | Background night |
| Azul água | `#a8c8e0` (day) / `#0e1730` (night) | Polígonos de água |

## Adicionar uma camada custom (overlay)

Exemplo: overlay com aeroportos vindo do `alfaero-static-data-pipeline`.

```json
{
  "id": "custom-airports",
  "type": "circle",
  "source": "alfaero-airports",
  "paint": {
    "circle-color": "#FF6B35",
    "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 2, 12, 8]
  }
}
```

E adicionar a source ao style:

```json
"alfaero-airports": {
  "type": "geojson",
  "data": "https://0f6ly15wg0.execute-api.us-east-1.amazonaws.com/static-data/airports"
}
```

## Validar mudanças

```bash
# Servir local com pmtiles serve (precisa do .pmtiles)
pmtiles serve planet.pmtiles --port 8080

# Servir style local apontando pro localhost (editar URL pra http://localhost:8080)
# Abrir benchmark/index.html?host=localhost:8080
```

## Boas práticas

- **Não mexer em sources** sem entender o impacto no pipeline
- **`text-font`** sempre usar valores já gerados nos fonts/ (Noto Sans Regular, Bold, Italic)
- **`text-field`** usar `["coalesce", ["get", "name:latin"], ["get", "name"]]` pra fallback i18n
- **Filtros** `["in", "class", "a", "b"]` mais rápidos que `["any", ["==", ...], ["==", ...]]`
- **Minzoom** generoso pra layers densas (buildings só >=13)
