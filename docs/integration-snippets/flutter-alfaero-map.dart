// AlfaeroMap — widget Flutter pronto pra usar nos apps Alfaero
// Copia pra: alfaero-mobile/lib/shared/widgets/alfaero_map.dart
//       ou: alfaero-operator/lib/shared/widgets/alfaero_map.dart
//
// Dependências (em pubspec.yaml):
//   maplibre_gl: ^0.21.0
//
// Uso:
//   AlfaeroMap(
//     initialLocation: LatLng(-23.5, -46.6),
//     initialZoom: 10,
//     variant: AlfaeroMapVariant.day,
//   )

import 'package:flutter/material.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

enum AlfaeroMapVariant {
  day,    // estilo claro pra UI geral
  night,  // escuro pra cockpit/noturno
  vfr,    // aeronáutico, terreno destacado
}

class AlfaeroMap extends StatefulWidget {
  final LatLng initialLocation;
  final double initialZoom;
  final AlfaeroMapVariant variant;
  final void Function(MaplibreMapController)? onMapCreated;
  final List<Widget>? overlayControls;
  final bool showAttribution;

  const AlfaeroMap({
    super.key,
    this.initialLocation = const LatLng(-23.5, -46.6),
    this.initialZoom = 10,
    this.variant = AlfaeroMapVariant.day,
    this.onMapCreated,
    this.overlayControls,
    this.showAttribution = true,
  });

  static const String _tilesHost = 'https://tiles.alfaero.com';

  String get _styleUrl {
    switch (variant) {
      case AlfaeroMapVariant.day:
        return '$_tilesHost/styles/alfaero-day.json';
      case AlfaeroMapVariant.night:
        return '$_tilesHost/styles/alfaero-night.json';
      case AlfaeroMapVariant.vfr:
        return '$_tilesHost/styles/alfaero-vfr.json';
    }
  }

  @override
  State<AlfaeroMap> createState() => _AlfaeroMapState();
}

class _AlfaeroMapState extends State<AlfaeroMap> {
  MaplibreMapController? _controller;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        MaplibreMap(
          styleString: widget._styleUrl,
          initialCameraPosition: CameraPosition(
            target: widget.initialLocation,
            zoom: widget.initialZoom,
          ),
          onMapCreated: (c) {
            _controller = c;
            widget.onMapCreated?.call(c);
          },
          // Atribuição obrigatória (OSM + OpenMapTiles) — fica collapsed em "ⓘ"
          attributionButtonPosition: widget.showAttribution
              ? AttributionButtonPosition.BottomRight
              : null,
          // Performance pra mobile
          compassEnabled: true,
          rotateGesturesEnabled: true,
          tiltGesturesEnabled: false, // 2D only por enquanto
        ),
        if (widget.overlayControls != null) ...widget.overlayControls!,
      ],
    );
  }
}

// Helper: pré-aquecer tiles pra rota planejada (uso em alfaero-operator antes de voo)
extension AlfaeroMapPrefetch on MaplibreMapController {
  Future<void> prefetchRoute({
    required List<LatLng> waypoints,
    Duration delayBetween = const Duration(milliseconds: 800),
  }) async {
    for (final wp in waypoints) {
      await animateCamera(
        CameraUpdate.newCameraPosition(
          CameraPosition(target: wp, zoom: 10),
        ),
      );
      await Future.delayed(delayBetween);
    }
  }
}
