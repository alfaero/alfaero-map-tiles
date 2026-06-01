# Web integration

Aplica-se a `alfaero-vip-web`, `alfaero-b2b`, `alfaero-backoffice` e qualquer outro web da Alfaero.

## 1. Dependências

```bash
npm install maplibre-gl pmtiles
```

## 2. Inicialização básica

```javascript
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import 'maplibre-gl/dist/maplibre-gl.css';

// Registrar protocol pmtiles:// (uma vez por aplicação)
const protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.alfaero.com/styles/alfaero-day.json',
  center: [-46.6, -23.5],
  zoom: 10,
});

// Atribuição (já vem do style, mas pode customizar):
map.addControl(new maplibregl.AttributionControl({ compact: false }));
map.addControl(new maplibregl.NavigationControl());
```

## 3. Inertia React (alfaero-b2b)

```tsx
import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import 'maplibre-gl/dist/maplibre-gl.css';

// Registrar uma vez (em main.tsx ou app.tsx):
if (!(window as any).__pmtilesRegistered) {
  const protocol = new Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);
  (window as any).__pmtilesRegistered = true;
}

export function AlfaeroMap({ center = [-46.6, -23.5], zoom = 10 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    mapRef.current = new maplibregl.Map({
      container: containerRef.current,
      style: 'https://tiles.alfaero.com/styles/alfaero-day.json',
      center: center as [number, number],
      zoom,
    });
    return () => mapRef.current?.remove();
  }, []);

  return <div ref={containerRef} className="w-full h-[500px]" />;
}
```

## 4. Laravel Blade (alfaero-vip-web)

```blade
<div id="map" style="width:100%;height:500px"></div>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js"></script>
<script>
  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);

  const map = new maplibregl.Map({
    container: 'map',
    style: 'https://tiles.alfaero.com/styles/alfaero-day.json',
    center: [-46.6, -23.5],
    zoom: 10,
  });
</script>
```

## 5. Markers, polylines, layers custom

API igual ao Mapbox GL JS (MapLibre é fork). Maioria do código Mapbox funciona trocando o import.

```js
new maplibregl.Marker({ color: '#FF6B35' })
  .setLngLat([-46.6, -23.5])
  .setPopup(new maplibregl.Popup().setText('Sede'))
  .addTo(map);
```

## 6. Estilo dinâmico (day/night/vfr)

```js
const STYLES = {
  day:   'https://tiles.alfaero.com/styles/alfaero-day.json',
  night: 'https://tiles.alfaero.com/styles/alfaero-night.json',
  vfr:   'https://tiles.alfaero.com/styles/alfaero-vfr.json',
};

document.querySelector('#toggle-night').onclick = () => {
  map.setStyle(STYLES.night);
};
```

## 7. Trocar de Mapbox/Google

Buscar uso atual:

```bash
# em cada repo web:
grep -rn 'mapbox\|MAPBOX\|google.com/maps\|googleapis' resources/ src/ public/
```

Substituir:
- `import mapboxgl from 'mapbox-gl'` → `import maplibregl from 'maplibre-gl'`
- `mapboxgl.accessToken = '...'` → **remover** (não precisa)
- `'mapbox://styles/...'` → `'https://tiles.alfaero.com/styles/alfaero-day.json'`

Google Maps embeds (`<iframe src="google.com/maps/embed...">`): substituir por `<div id="map">` + MapLibre.

## 8. CORS

`tiles.alfaero.com` precisa ter o domínio do consumidor permitido no CORS do R2 (configurado em `docs/operations.md` passo 6). Já inclui `*.alfaero.com` e `localhost:*`.

## 9. Smoke test

- Abrir página em browser
- DevTools → Network → filtrar por `pmtiles`
- Confirmar:
  - `200` no style JSON
  - `206` (Partial Content) nos requests ao .pmtiles
  - Atribuição visível no canto
  - Console sem erros CORS
