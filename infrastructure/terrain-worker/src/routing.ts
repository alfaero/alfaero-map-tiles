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

/** Arquivo que serve o zoom: o planeta até z9, a região de z10 em diante. */
export function archiveFor(
  z: number,
  env: { PLANET_PATH: string; REGION_PATH: string; REGION_MIN_ZOOM: string }
): string {
  return z >= Number(env.REGION_MIN_ZOOM) ? env.REGION_PATH : env.PLANET_PATH;
}

/** Atribuição exigida pela licença do Copernicus e o crédito do Mapterhorn. */
export const ATTRIBUTION =
  'produced using Copernicus WorldDEM-30 &copy; DLR e.V. 2010-2014 and &copy; Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. Packaged by <a href="https://mapterhorn.com">Mapterhorn</a>.';
