# Integration snippets

Snippets prontos pra copy/paste nos repos consumidores. Não dependem deste repo — são auto-contidos, é só copiar e ajustar onde os mapas devem entrar.

## Arquivos

| Snippet | Onde colocar | Tipo |
|---|---|---|
| `flutter-alfaero-map.dart` | `alfaero-mobile/lib/shared/widgets/alfaero_map.dart` | Widget Flutter |
| `flutter-alfaero-map.dart` | `alfaero-operator/lib/shared/widgets/alfaero_map.dart` | Widget Flutter |
| `react-alfaero-map.tsx` | `alfaero-b2b/resources/js/Components/AlfaeroMap.tsx` | Componente React/Inertia |
| `laravel-blade-map.blade.php` | `alfaero-vip-web/resources/views/components/alfaero-map.blade.php` | Componente Blade |

## Dependências

### Flutter (mobile + operator)
```yaml
# pubspec.yaml
dependencies:
  maplibre_gl: ^0.21.0
```

### React (b2b + backoffice)
```bash
npm install maplibre-gl pmtiles
```

### Laravel (vip-web)
Sem deps via npm — usa CDN de `maplibre-gl` e `pmtiles` direto no Blade.

## Uso básico

**Flutter:**
```dart
AlfaeroMap(
  initialLocation: LatLng(-23.5, -46.6),
  initialZoom: 10,
  variant: AlfaeroMapVariant.day, // day | night | vfr
  onMapCreated: (controller) {
    // adicionar markers, polylines, etc
  },
)
```

**React:**
```tsx
<AlfaeroMap
  center={[-46.6, -23.5]}
  zoom={10}
  variant="day"
  onLoad={(map) => {
    new maplibregl.Marker().setLngLat([-46.6, -23.5]).addTo(map);
  }}
/>
```

**Laravel Blade:**
```blade
<x-alfaero-map center="-46.6,-23.5" zoom="10" variant="day" height="600px" />
```

## Atribuição

Os snippets já configuram `AttributionControl` collapsed (ícone "ⓘ" pequeno). É **obrigatório** por causa do OSM/OpenMapTiles — não remover.

## Modo escuro/dia automático

Detectar do sistema:

**Flutter:**
```dart
final isDark = MediaQuery.platformBrightnessOf(context) == Brightness.dark;
AlfaeroMap(
  variant: isDark ? AlfaeroMapVariant.night : AlfaeroMapVariant.day,
)
```

**React:**
```tsx
const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
<AlfaeroMap variant={isDark ? 'night' : 'day'} />
```

## Próximos passos por repo

1. **alfaero-mobile** — substituir `MapboxMap`/`GoogleMap` atual por `AlfaeroMap`. Procurar com `grep -r 'Mapbox\|GoogleMap' lib/`
2. **alfaero-operator** — idem
3. **alfaero-b2b** — adicionar no dashboard de unidades / pedidos onde fizer sentido
4. **alfaero-vip-web** — adicionar em telas que mostrem localização de aeronaves
5. **alfaero-backoffice** — adicionar onde tiver mapa Mapbox/Google ativo

Depois: cancelar billing Mapbox/Google se não usar em mais lugar nenhum.
