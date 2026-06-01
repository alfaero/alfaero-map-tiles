// AlfaeroMap — componente React pronto pra usar nos apps web Alfaero
// Copia pra: alfaero-b2b/resources/js/Components/AlfaeroMap.tsx
//       ou: alfaero-backoffice (adapta pra estrutura existente)
//
// Dependências:
//   npm install maplibre-gl pmtiles
//
// Uso:
//   <AlfaeroMap center={[-46.6, -23.5]} zoom={10} variant="day" />

import { useEffect, useRef, useState } from 'react';
import maplibregl, { Map as MaplibreMap, MapOptions } from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import 'maplibre-gl/dist/maplibre-gl.css';

// Registrar protocol pmtiles:// uma vez por aplicação
if (typeof window !== 'undefined' && !(window as any).__pmtilesRegistered) {
  const protocol = new Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);
  (window as any).__pmtilesRegistered = true;
}

const TILES_HOST = 'https://tiles.alfaero.com';

export type AlfaeroMapVariant = 'day' | 'night' | 'vfr';

const STYLE_URLS: Record<AlfaeroMapVariant, string> = {
  day: `${TILES_HOST}/styles/alfaero-day.json`,
  night: `${TILES_HOST}/styles/alfaero-night.json`,
  vfr: `${TILES_HOST}/styles/alfaero-vfr.json`,
};

export interface AlfaeroMapProps {
  center?: [number, number]; // [lng, lat]
  zoom?: number;
  variant?: AlfaeroMapVariant;
  className?: string;
  style?: React.CSSProperties;
  onLoad?: (map: MaplibreMap) => void;
  showNavigation?: boolean;
  showAttribution?: boolean;
}

export function AlfaeroMap({
  center = [-46.6, -23.5],
  zoom = 10,
  variant = 'day',
  className = '',
  style,
  onLoad,
  showNavigation = true,
  showAttribution = true,
}: AlfaeroMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MaplibreMap | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    try {
      const map = new maplibregl.Map({
        container: containerRef.current,
        style: STYLE_URLS[variant],
        center,
        zoom,
      });

      if (showNavigation) {
        map.addControl(new maplibregl.NavigationControl(), 'top-right');
      }
      if (showAttribution) {
        map.addControl(
          new maplibregl.AttributionControl({ compact: true }),
          'bottom-right',
        );
      }

      map.on('load', () => onLoad?.(map));
      map.on('error', (e) => {
        console.error('AlfaeroMap error:', e);
        setError(e.error?.message ?? 'Map load error');
      });

      mapRef.current = map;
      return () => {
        map.remove();
        mapRef.current = null;
      };
    } catch (e: any) {
      setError(e.message);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant]);

  // Atualizar center/zoom sem recriar o mapa
  useEffect(() => {
    mapRef.current?.flyTo({ center, zoom, duration: 1000 });
  }, [center[0], center[1], zoom]);

  if (error) {
    return (
      <div className={`p-4 bg-red-50 text-red-700 rounded ${className}`}>
        Erro ao carregar mapa: {error}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ width: '100%', height: '500px', ...style }}
    />
  );
}

// Hook helper pra acessar a instância do mapa (markers, polylines, etc.)
export function useAlfaeroMap() {
  const mapRef = useRef<MaplibreMap | null>(null);
  return {
    map: mapRef.current,
    setMap: (m: MaplibreMap) => {
      mapRef.current = m;
    },
  };
}
