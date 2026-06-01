{{-- AlfaeroMap — snippet Blade pra alfaero-vip-web --}}
{{-- Copia pra: resources/views/components/alfaero-map.blade.php (Laravel) --}}
{{-- Uso: <x-alfaero-map center="-46.6,-23.5" zoom="10" variant="day" /> --}}

@props([
  'center' => '-46.6,-23.5',
  'zoom' => 10,
  'variant' => 'day',
  'height' => '500px',
  'id' => 'alfaero-map-' . uniqid(),
])

@php
  $styleMap = [
    'day' => 'https://tiles.alfaero.com/styles/alfaero-day.json',
    'night' => 'https://tiles.alfaero.com/styles/alfaero-night.json',
    'vfr' => 'https://tiles.alfaero.com/styles/alfaero-vfr.json',
  ];
  $styleUrl = $styleMap[$variant] ?? $styleMap['day'];
  [$lng, $lat] = explode(',', $center);
@endphp

@once
  @push('head')
    <link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
  @endpush
  @push('scripts')
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <script src="https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js"></script>
    <script>
      (function () {
        if (window.__pmtilesRegistered) return;
        const protocol = new pmtiles.Protocol();
        maplibregl.addProtocol('pmtiles', protocol.tile);
        window.__pmtilesRegistered = true;
      })();
    </script>
  @endpush
@endonce

<div id="{{ $id }}" style="width:100%; height:{{ $height }};" {{ $attributes }}></div>

<script>
  (function () {
    const map = new maplibregl.Map({
      container: '{{ $id }}',
      style: '{{ $styleUrl }}',
      center: [{{ (float) $lng }}, {{ (float) $lat }}],
      zoom: {{ (int) $zoom }},
    });
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

    // Expose pra outros scripts da página caso precise (markers, etc.)
    window.alfaeroMaps = window.alfaeroMaps || {};
    window.alfaeroMaps['{{ $id }}'] = map;
  })();
</script>
