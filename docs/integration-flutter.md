# Flutter integration

Aplica-se a `alfaero-mobile` e `alfaero-operator`.

## 1. Dependência

`pubspec.yaml`:
```yaml
dependencies:
  maplibre_gl: ^0.21.0
```

MapLibre Native (engine usado pelo plugin) suporta PMTiles nativamente via `pmtiles://` protocol handler (build flag `MLN_DRAWABLE_RENDERER=ON` + protocol registration). A maioria das builds estáveis 11+ já inclui.

Se sua versão do `maplibre_gl` empacotar MapLibre Native < 11.0, atualize o plugin OU mude o style pra expandir tiles XYZ manualmente (não recomendado).

## 2. Configuração do mapa

```dart
import 'package:flutter/material.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

class AlfaeroMap extends StatefulWidget {
  const AlfaeroMap({super.key});

  @override
  State<AlfaeroMap> createState() => _AlfaeroMapState();
}

class _AlfaeroMapState extends State<AlfaeroMap> {
  static const String styleDay   = 'https://tiles.alfaero.com/styles/alfaero-day.json';
  static const String styleNight = 'https://tiles.alfaero.com/styles/alfaero-night.json';
  static const String styleVfr   = 'https://tiles.alfaero.com/styles/alfaero-vfr.json';

  String _currentStyle = styleDay;
  MaplibreMapController? _controller;

  @override
  Widget build(BuildContext context) {
    return MaplibreMap(
      styleString: _currentStyle,
      initialCameraPosition: const CameraPosition(
        target: LatLng(-23.5, -46.6),
        zoom: 10,
      ),
      onMapCreated: (c) => _controller = c,
      // Atribuição obrigatória — exibida nativamente pelo plugin
      attributionButtonPosition: AttributionButtonPosition.BottomRight,
    );
  }

  void switchToNight() => setState(() => _currentStyle = styleNight);
  void switchToVfr() => setState(() => _currentStyle = styleVfr);
}
```

## 3. Cache offline (crítico aeronáutico)

MapLibre Native cacheia tiles no disco do device. Pra rotas planejadas, pré-baixar:

```dart
// Pseudo: percorrer bbox da rota planejada nos zooms relevantes
Future<void> prefetchRoute(LatLngBounds routeBbox, {int minZoom = 6, int maxZoom = 12}) async {
  // OfflineRegionDefinition do maplibre_gl ainda em evolução; alternativa via Channel:
  // Por enquanto, força pre-render movendo a câmera por waypoints da rota antes do voo.
  for (final waypoint in routeWaypoints) {
    await _controller?.animateCamera(
      CameraUpdate.newCameraPosition(CameraPosition(target: waypoint, zoom: 10)),
    );
    await Future.delayed(const Duration(milliseconds: 500));
  }
}
```

Roadmap: migrar pra `offline_regions` quando o plugin estabilizar essa API.

## 4. Trocar provider atual (Mapbox/Google)

Procurar usos atuais no repo:

```bash
# alfaero-mobile
grep -r 'Mapbox\|GoogleMap\|mapbox\|google_maps' lib/

# alfaero-operator
grep -r 'Mapbox\|GoogleMap\|mapbox\|google_maps' lib/
```

Substituir widgets `MapboxMap`/`GoogleMap` por `MaplibreMap`. Adaptar APIs:
- `CameraPosition`, `LatLng`, `Marker` têm equivalentes
- `Polyline`/`Polygon` idem
- Source de markers customs muda — usar `addSymbol` do `MaplibreMapController`

## 5. Remover Mapbox/Google tokens

Depois de migrar:
- Deletar `MAPBOX_ACCESS_TOKEN` do `.env`
- Remover Google Maps API key do `AndroidManifest.xml` e `AppDelegate.swift`
- Cancelar billing Mapbox/Google se não usar em mais lugar

## 6. Smoke test

Após mudança, validar em device físico:
- Mapa abre em <2s em 4G
- Pan/zoom fluido
- Atribuição visível
- Funciona offline (após primeiro carregamento)
- Estilo night legível à noite
