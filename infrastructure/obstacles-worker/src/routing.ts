// Rotas dos obstáculos: /obstacles/{versao}/{z}/{x}/{y}.bin e /obstacles/{versao}.json.
// A versão (AAAAMMDD) escolhe o arquivo: uma base nova é um caminho novo, então
// o cache pode ser imutável e o app troca de base pelo Remote Config.

export type ObstaclesRoute =
  | { kind: "tile"; version: string; z: number; x: number; y: number }
  | { kind: "tilejson"; version: string }
  | { kind: "invalid" };

const TILE = /^\/obstacles\/(\d{8})\/(\d{1,2})\/(\d+)\/(\d+)\.bin$/;
const TILEJSON = /^\/obstacles\/(\d{8})\.json$/;

export function parseObstaclesPath(path: string): ObstaclesRoute {
  const j = path.match(TILEJSON);
  if (j) return { kind: "tilejson", version: j[1] };
  const m = path.match(TILE);
  if (!m) return { kind: "invalid" };
  const z = +m[2], x = +m[3], y = +m[4];
  const n = 2 ** z;
  if (z > 22 || x >= n || y >= n) return { kind: "invalid" };
  return { kind: "tile", version: m[1], z, x, y };
}

/** Arquivo da base: obstacles-sa-z10-<versao>.pmtiles, gerado pelo obstacles-job. */
export function archiveFor(version: string): string {
  return `obstacles-sa-z10-${version}.pmtiles`;
}

/** ANEEL, NATS (Reino Unido), DFS (Alemanha, CC BY 4.0) e a licença ODbL do OSM (spec 389, AC22;
 * spec 003 do navdata, CA13; spec 005 do navdata, CA15). */
export const ATTRIBUTION =
  'Aerogeradores: ANEEL SIGEL. Reino Unido: NATS (UK AIS). Alemanha: DFS Deutsche Flugsicherung GmbH, <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. Linhas, torres e mastros: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>. Bases sob a Open Database License (ODbL).';
