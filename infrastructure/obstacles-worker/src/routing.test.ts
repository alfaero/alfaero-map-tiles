import assert from "node:assert/strict";
import { ATTRIBUTION, archiveFor, parseObstaclesPath } from "./routing";

assert.deepEqual(parseObstaclesPath("/obstacles/20261018/10/409/527.bin"), {
  kind: "tile",
  version: "20261018",
  z: 10,
  x: 409,
  y: 527,
});
assert.deepEqual(parseObstaclesPath("/obstacles/20261018.json"), { kind: "tilejson", version: "20261018" });
assert.equal(parseObstaclesPath("/obstacles/10/409/527.bin").kind, "invalid", "sem versão");
assert.equal(parseObstaclesPath("/obstacles/2026101/10/409/527.bin").kind, "invalid", "versão curta");
assert.equal(parseObstaclesPath("/obstacles/20261018/10/409/527.webp").kind, "invalid");
assert.equal(parseObstaclesPath("/obstacles/20261018/2/4/0.bin").kind, "invalid", "x fora da grade");
assert.equal(parseObstaclesPath("/obstacles/../terrain/11/1/1.bin").kind, "invalid");

assert.equal(archiveFor("20261018"), "obstacles-sa-z10-20261018.pmtiles");
assert.match(ATTRIBUTION, /ANEEL/);
assert.match(ATTRIBUTION, /NATS/);
assert.match(ATTRIBUTION, /OpenStreetMap/);
console.log("routing ok");
