// Obstáculos da visão sintética do app (spec 006; formato AOB1 da spec 389 do
// alfaero-mobile) em tiles.alfaero.com/obstacles/{versao}/{z}/{x}/{y}.bin.
// Um PMTiles por base no R2. Tile sem obstáculo devolve 204; versão que não
// existe devolve 404 (sem cache).
import {
  EtagMismatch,
  PMTiles,
  type RangeResponse,
  ResolvedValueCache,
  type Source,
} from "pmtiles";
import { ATTRIBUTION, archiveFor, parseObstaclesPath } from "./routing";

interface Env {
  // biome-ignore lint: config name
  ALLOWED_ORIGINS?: string;
  // biome-ignore lint: config name
  BUCKET: R2Bucket;
  // biome-ignore lint: config name
  CACHE_CONTROL?: string;
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
    const route = parseObstaclesPath(url.pathname);
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
      // 404 de base ausente não fica preso no cache.
      if (status === 200 || status === 204) ctx.waitUntil(cache.put(request.url, r.clone()));
      return withCors(r);
    };

    try {
      const p = new PMTiles(new R2Source(env, archiveFor(route.version)), CACHE);
      const h = await p.getHeader();
      if (route.kind === "tilejson") {
        const json = {
          tilejson: "3.0.0",
          name: "Alfaero obstacles",
          format: "aob1",
          version: route.version,
          tiles: [
            `https://${env.PUBLIC_HOSTNAME || url.hostname}/obstacles/${route.version}/{z}/{x}/{y}.bin`,
          ],
          minzoom: h.minZoom,
          maxzoom: h.maxZoom,
          attribution: ATTRIBUTION,
        };
        return respond(JSON.stringify(json), "application/json", 200);
      }
      if (route.z < h.minZoom || route.z > h.maxZoom) {
        return respond(undefined, null, 204);
      }
      const tile = await p.getZxy(route.z, route.x, route.y);
      if (!tile) return respond(undefined, null, 204);
      return respond(tile.data, "application/octet-stream", 200);
    } catch (e) {
      if (e instanceof KeyNotFoundError) return respond("Archive not found", "text/plain", 404);
      throw e;
    }
  },
};
