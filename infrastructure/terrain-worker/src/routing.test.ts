import assert from "node:assert/strict";
import { ATTRIBUTION, archivesFor, extentCovers, parseTerrainPath } from "./routing";

const env = { PLANET_PATH: "p.pmtiles", REGION_PATHS: "sa.pmtiles, na.pmtiles", REGION_MIN_ZOOM: "10" };

assert.deepEqual(parseTerrainPath("/terrain/11/769/1154.webp"), { kind: "tile", z: 11, x: 769, y: 1154 });
assert.deepEqual(parseTerrainPath("/terrain.json"), { kind: "tilejson" });
assert.equal(parseTerrainPath("/terrain/11/769/1154.png").kind, "invalid");
assert.equal(parseTerrainPath("/terrain/2/4/0.webp").kind, "invalid", "x fora da grade");
assert.equal(parseTerrainPath("/tiles/11/769/1154.webp").kind, "invalid");

assert.deepEqual(archivesFor(9, env), ["p.pmtiles"]);
assert.deepEqual(archivesFor(0, env), ["p.pmtiles"]);
assert.deepEqual(archivesFor(10, env), ["sa.pmtiles", "na.pmtiles"], "regiões na ordem da lista");
assert.deepEqual(archivesFor(11, { ...env, REGION_PATHS: "sa.pmtiles" }), ["sa.pmtiles"]);

// Limites dos recortes (spec 005 e 007).
const sa = { minZoom: 0, maxZoom: 11, minLon: -82, minLat: -56, maxLon: -34, maxLat: 13 };
const na = { minZoom: 10, maxZoom: 11, minLon: -170, minLat: 7, maxLon: -52, maxLat: 72 };
// Agulhas Negras (11/769/1154): só na América do Sul.
assert.equal(extentCovers(sa, 11, 769, 1154), true);
assert.equal(extentCovers(na, 11, 769, 1154), false);
// Denver (11/430/777): só na América do Norte.
assert.equal(extentCovers(sa, 11, 430, 777), false);
assert.equal(extentCovers(na, 11, 430, 777), true);
// Caribe perto de Caracas (z10, 10.5N 66.9W): nas duas; vence a primeira da lista.
const n10 = 2 ** 10;
const cx = Math.floor(((-66.9 + 180) / 360) * n10);
const cy = Math.floor(((1 - Math.asinh(Math.tan((10.5 * Math.PI) / 180)) / Math.PI) / 2) * n10);
assert.equal(extentCovers(sa, 10, cx, cy), true);
assert.equal(extentCovers(na, 10, cx, cy), true);
// Zoom fora do arquivo: a América do Norte só tem z10 e z11.
assert.equal(extentCovers(na, 9, 107, 194), false);
assert.equal(extentCovers(na, 12, 860, 1554), false);
// Europa (11/1024/700): em nenhuma das duas, segue 204.
assert.equal(extentCovers(sa, 11, 1024, 700), false);
assert.equal(extentCovers(na, 11, 1024, 700), false);

assert.match(ATTRIBUTION, /Copernicus WorldDEM-30/);
assert.match(ATTRIBUTION, /Mapterhorn/);
console.log("routing ok");
