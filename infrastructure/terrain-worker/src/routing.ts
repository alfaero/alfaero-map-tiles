// Rotas do terreno: /terrain/{z}/{x}/{y}.webp e /terrain.json.

export type TerrainRoute =
  | { kind: "tile"; z: number; x: number; y: number }
  | { kind: "tilejson" }
  | { kind: "invalid" };

const TILE = /^\/terrain\/(\d{1,2})\/(\d+)\/(\d+)\.webp$/;

export function parseTerrainPath(path: string): TerrainRoute {
  if (path === "/terrain.json") return { kind: "tilejson" };
  const m = path.match(TILE);
  if (!m) return { kind: "invalid" };
  const z = +m[1], x = +m[2], y = +m[3];
  const n = 2 ** z;
  if (z > 22 || x >= n || y >= n) return { kind: "invalid" };
  return { kind: "tile", z, x, y };
}

/** Arquivos que servem o zoom, na ordem de consulta: o planeta até z9, as
 * regiões (REGION_PATHS, separadas por vírgula) de z10 em diante (spec 007). */
export function archivesFor(
  z: number,
  env: { PLANET_PATH: string; REGION_PATHS: string; REGION_MIN_ZOOM: string }
): string[] {
  if (z < Number(env.REGION_MIN_ZOOM)) return [env.PLANET_PATH];
  return env.REGION_PATHS.split(",").map((p) => p.trim()).filter((p) => p);
}

/** Limites e zooms de um arquivo, como vêm no cabeçalho do PMTiles. */
export interface ArchiveExtent {
  minZoom: number;
  maxZoom: number;
  minLon: number;
  minLat: number;
  maxLon: number;
  maxLat: number;
}

/** O arquivo pode ter o tile: zoom dentro e o tile encosta nos limites. Evita
 * ler o diretório de uma região que nem cobre o lugar. */
export function extentCovers(e: ArchiveExtent, z: number, x: number, y: number): boolean {
  if (z < e.minZoom || z > e.maxZoom) return false;
  const n = 2 ** z;
  const lat = (row: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * row) / n))) * 180) / Math.PI;
  const west = (x / n) * 360 - 180;
  const east = ((x + 1) / n) * 360 - 180;
  const north = lat(y);
  const south = lat(y + 1);
  return east > e.minLon && west < e.maxLon && north > e.minLat && south < e.maxLat;
}

/** Atribuição exigida pela licença do Copernicus e o crédito do Mapterhorn. */
export const ATTRIBUTION =
  'produced using Copernicus WorldDEM-30 &copy; DLR e.V. 2010-2014 and &copy; Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. Packaged by <a href="https://mapterhorn.com">Mapterhorn</a>.';
