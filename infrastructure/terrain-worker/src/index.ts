// Terreno Terrarium (Copernicus GLO-30 via Mapterhorn) em
// tiles.alfaero.com/terrain/{z}/{x}/{y}.webp, para a visão sintética do app
// (spec 005). Dois arquivos PMTiles no R2: o planeta até z9 e a América do Sul
// de z10 em diante. Tile sem dado devolve 204: o app trata como "sem dado",
// nunca como 0 m.
import {
  EtagMismatch,
  PMTiles,
  type RangeResponse,
  ResolvedValueCache,
  type Source,
  TileType,
} from "pmtiles";
import { ATTRIBUTION, archiveFor, parseTerrainPath } from "./routing";

interface Env {
  // biome-ignore lint: config name
  ALLOWED_ORIGINS?: string;
  // biome-ignore lint: config name
  BUCKET: R2Bucket;
  // biome-ignore lint: config name
  CACHE_CONTROL?: string;
  // biome-ignore lint: config name
  PLANET_PATH: string;
  // biome-ignore lint: config name
  REGION_PATH: string;
  // biome-ignore lint: config name
  REGION_MIN_ZOOM: string;
  // biome-ignore lint: config name
  PUBLIC_HOSTNAME?: string;
}

class KeyNotFoundError extends Error {}

const CACHE = new ResolvedValueCache(25, undefined);

class R2Source implements Source {
  constructor(
    private env: Env,
    private key: string
  ) {}

  getKey() {
    return this.key;
  }

  async getBytes(
    offset: number,
    length: number,
    _signal?: AbortSignal,
    etag?: string
  ): Promise<RangeResponse> {
    const resp = await this.env.BUCKET.get(this.key, {
      range: { offset, length },
      onlyIf: { etagMatches: etag },
    });
    if (!resp) throw new KeyNotFoundError("Archive not found");
    const o = resp as R2ObjectBody;
    if (!o.body) throw new EtagMismatch();
    return { data: await o.arrayBuffer(), etag: o.etag };
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response(undefined, { status: 405 });
    }
    const url = new URL(request.url);
    const route = parseTerrainPath(url.pathname);
    if (route.kind === "invalid") return new Response("Invalid URL", { status: 404 });

    const origin = env.ALLOWED_ORIGINS?.split(",").find(
      (o) => o === "*" || o === request.headers.get("Origin")
    );
    const withCors = (r: Response) => {
      const h = new Headers(r.headers);
      if (origin) h.set("Access-Control-Allow-Origin", origin);
      h.set("Vary", "Origin");
      return new Response(r.body, { headers: h, status: r.status });
    };

    const cache = caches.default;
    const cached = await cache.match(request.url);
    if (cached) return withCors(cached);

    const respond = (body: ArrayBuffer | string | undefined, type: string | null, status: number) => {
      const h = new Headers();
      if (type) h.set("Content-Type", type);
      h.set("Cache-Control", env.CACHE_CONTROL || "public, max-age=86400");
      const r = new Response(body, { headers: h, status });
      // 404 de arquivo ausente não fica preso no cache.
      if (status === 200 || status === 204) ctx.waitUntil(cache.put(request.url, r.clone()));
      return withCors(r);
    };

    try {
      if (route.kind === "tilejson") {
        const p = new PMTiles(new R2Source(env, env.PLANET_PATH), CACHE);
        const h = await p.getHeader();
        const json = {
          tilejson: "3.0.0",
          name: "Alfaero terrain (Copernicus GLO-30)",
          encoding: "terrarium",
          tiles: [`https://${env.PUBLIC_HOSTNAME || url.hostname}/terrain/{z}/{x}/{y}.webp`],
          minzoom: h.minZoom,
          maxzoom: 11,
          tileSize: 512,
          attribution: ATTRIBUTION,
        };
        return respond(JSON.stringify(json), "application/json", 200);
      }

      const p = new PMTiles(new R2Source(env, archiveFor(route.z, env)), CACHE);
      const h = await p.getHeader();
      if (h.tileType !== TileType.Webp) {
        return respond("Archive is not WebP", "text/plain", 500);
      }
      if (route.z < h.minZoom || route.z > h.maxZoom) {
        return respond(undefined, null, 204);
      }
      const tile = await p.getZxy(route.z, route.x, route.y);
      if (!tile) return respond(undefined, null, 204);
      return respond(tile.data, "image/webp", 200);
    } catch (e) {
      if (e instanceof KeyNotFoundError) return respond("Archive not found", "text/plain", 404);
      throw e;
    }
  },
};
