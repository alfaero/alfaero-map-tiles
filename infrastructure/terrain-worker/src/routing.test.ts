import assert from "node:assert/strict";
import { ATTRIBUTION, archiveFor, parseTerrainPath } from "./routing";

const env = { PLANET_PATH: "p.pmtiles", REGION_PATH: "sa.pmtiles", REGION_MIN_ZOOM: "10" };

assert.deepEqual(parseTerrainPath("/terrain/11/769/1154.webp"), { kind: "tile", z: 11, x: 769, y: 1154 });
assert.deepEqual(parseTerrainPath("/terrain.json"), { kind: "tilejson" });
assert.equal(parseTerrainPath("/terrain/11/769/1154.png").kind, "invalid");
assert.equal(parseTerrainPath("/terrain/2/4/0.webp").kind, "invalid", "x fora da grade");
assert.equal(parseTerrainPath("/tiles/11/769/1154.webp").kind, "invalid");

assert.equal(archiveFor(9, env), "p.pmtiles");
assert.equal(archiveFor(10, env), "sa.pmtiles");
assert.equal(archiveFor(11, env), "sa.pmtiles");
assert.equal(archiveFor(0, env), "p.pmtiles");

assert.match(ATTRIBUTION, /Copernicus WorldDEM-30/);
assert.match(ATTRIBUTION, /Mapterhorn/);
console.log("routing ok");
