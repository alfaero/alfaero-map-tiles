// flutter_map raster — pronto pra copy/paste em alfaero-mobile, alfaero-operator
// ou qualquer projeto Flutter (Windows/Android/iOS/web/macOS/Linux).
//
// Renderiza vector tiles MVT → PNG no servidor (TileServer GL no Hostinger),
// CDN Cloudflare cacheia cada PNG. Cliente baixa raster comum.
//
// Pré-requisitos:
//   flutter_map: ^8.1.1 (já está no projeto)
//   latlong2: ^0.9.1   (já está)
//
// Performance:
//   Cold tile: ~1-2s (TileServer renderiza)
//   Warm tile: ~50-100ms (CF cache hit)
//   Subsequent zoom/pan: ~0ms (browser/Flutter cache)

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

class AlfaeroRasterMap extends StatelessWidget {
  final LatLng initialCenter;
  final double initialZoom;
  final AlfaeroMapVariant variant;
  final MapController? controller;
  final List<Widget> overlayLayers;

  const AlfaeroRasterMap({
    super.key,
    this.initialCenter = const LatLng(-23.5, -46.6),
    this.initialZoom = 10,
    this.variant = AlfaeroMapVariant.day,
    this.controller,
    this.overlayLayers = const [],
  });

  static const String _host = 'https://raster.alfaero.com';

  String get _styleId {
    switch (variant) {
      case AlfaeroMapVariant.day:
        return 'alfaero-day';
      case AlfaeroMapVariant.night:
        return 'alfaero-night';
      case AlfaeroMapVariant.vfr:
        return 'alfaero-vfr';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isRetina = MediaQuery.maybeDevicePixelRatioOf(context) != null &&
        MediaQuery.devicePixelRatioOf(context) > 1.5;

    return FlutterMap(
      mapController: controller,
      options: MapOptions(
        initialCenter: initialCenter,
        initialZoom: initialZoom,
        maxZoom: 18,
        minZoom: 0,
      ),
      children: [
        TileLayer(
          urlTemplate: '$_host/styles/$_styleId/{z}/{x}/{y}${isRetina ? "@2x" : ""}.png',
          userAgentPackageName: 'com.alfaero',
          maxNativeZoom: 14, // pmtiles vai até zoom 14, flutter_map upsample resto
          tileSize: 256,
          // Atribuição obrigatória — OpenStreetMap + OpenMapTiles
          tileProvider: NetworkTileProvider(),
        ),
        // Atribuição visível (collapsed widget)
        const RichAttributionWidget(
          alignment: AttributionAlignment.bottomRight,
          attributions: [
            TextSourceAttribution('© OSM © OpenMapTiles'),
          ],
        ),
        ...overlayLayers,
      ],
    );
  }
}

enum AlfaeroMapVariant { day, night, vfr }

// === Uso ===
//
// Modo simples:
// ```dart
// AlfaeroRasterMap(
//   initialCenter: LatLng(-23.5, -46.6),
//   initialZoom: 10,
//   variant: AlfaeroMapVariant.day,
// )
// ```
//
// Com markers e polylines (overlay sobre o mapa):
// ```dart
// AlfaeroRasterMap(
//   variant: isDark ? AlfaeroMapVariant.night : AlfaeroMapVariant.day,
//   overlayLayers: [
//     MarkerLayer(markers: [
//       Marker(
//         point: LatLng(-23.5, -46.6),
//         child: const Icon(Icons.location_pin, color: Colors.orange, size: 32),
//       ),
//     ]),
//     PolylineLayer(polylines: [
//       Polyline(
//         points: [LatLng(-23.5, -46.6), LatLng(-22.9, -43.2)],
//         color: const Color(0xFFFF6B35),
//         strokeWidth: 3,
//       ),
//     ]),
//   ],
// )
// ```
