// Troca a versão da base de obstáculos no Remote Config (spec 389 do app, AC8): a chave
// `synthetic_vision_obstacles_url` passa a apontar para .../obstacles/<AAAAMMDD>/{z}/{x}/{y}.bin.
// Só a de produção; a `_homolog` fica como está. Guarda o template anterior em <pasta>.
//
// Uso: node rc_obstacles.mjs <AAAAMMDD> <pasta_backup>          (só mostra)
//      APPLY=1 node rc_obstacles.mjs <AAAAMMDD> <pasta_backup>  (grava)
// Antes de gravar, confere que a base nova responde no worker (TileJSON 200).
// Credencial: segredo alfaero/firebase-admin no Secrets Manager (aws cli da máquina).
import { execFileSync } from "node:child_process";
import { createSign } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";

const KEY = "synthetic_vision_obstacles_url";
const [STAMP, BACKUP_DIR] = process.argv.slice(2);
if (!/^\d{8}$/.test(STAMP ?? "") || !BACKUP_DIR) {
  console.error("uso: node rc_obstacles.mjs <AAAAMMDD> <pasta_backup>");
  process.exit(2);
}

const tilejson = await fetch(`https://tiles.alfaero.com/obstacles/${STAMP}.json`);
console.log(`TileJSON ${STAMP}: HTTP ${tilejson.status}`);
if (!tilejson.ok) throw new Error(`base ${STAMP} não responde no worker; não troca a URL`);

const sa = JSON.parse(
  execFileSync("aws", ["secretsmanager", "get-secret-value", "--secret-id", "alfaero/firebase-admin", "--query", "SecretString", "--output", "text"]).toString(),
);
const now = Math.floor(Date.now() / 1000);
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const head = b64({ alg: "RS256", typ: "JWT", kid: sa.private_key_id });
const claim = b64({ iss: sa.client_email, scope: "https://www.googleapis.com/auth/firebase.remoteconfig", aud: sa.token_uri, iat: now, exp: now + 3600 });
const sig = createSign("RSA-SHA256").update(`${head}.${claim}`).sign(sa.private_key, "base64url");
const tokenRes = await fetch(sa.token_uri, {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion: `${head}.${claim}.${sig}` }),
});
if (!tokenRes.ok) throw new Error(`token ${tokenRes.status}`);
const { access_token: token } = await tokenRes.json();

const url = `https://firebaseremoteconfig.googleapis.com/v1/projects/${sa.project_id}/remoteConfig`;
const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
if (!res.ok) throw new Error(`rc GET ${res.status}`);
const etag = res.headers.get("etag");
const cfg = await res.json();
mkdirSync(BACKUP_DIR, { recursive: true });
writeFileSync(`${BACKUP_DIR}/rc_before_obstacles_${STAMP}_${Date.now()}.json`, JSON.stringify(cfg, null, 1));

const param =
  cfg.parameters?.[KEY] ??
  (cfg.parameterGroups ? Object.values(cfg.parameterGroups).map((g) => g.parameters?.[KEY]).find(Boolean) : undefined);
if (!param) throw new Error(`${KEY} não encontrado`);

let changes = 0;
const patch = (v) => {
  if (!v?.value) return v;
  const next = v.value.replace(/\/obstacles\/\d{8}\//, `/obstacles/${STAMP}/`);
  if (next === v.value && !v.value.includes(`/obstacles/${STAMP}/`)) throw new Error(`URL fora do padrão: ${v.value}`);
  if (next !== v.value) { changes++; console.log(`${v.value} -> ${next}`); }
  return { ...v, value: next };
};
param.defaultValue = patch(param.defaultValue);
for (const [k, v] of Object.entries(param.conditionalValues ?? {})) param.conditionalValues[k] = patch(v);
console.log(`mudanças: ${changes}`);

if (process.env.APPLY === "1" && changes) {
  const put = await fetch(url, {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json; charset=UTF-8", "If-Match": etag },
    body: JSON.stringify(cfg),
  });
  if (!put.ok) throw new Error(`rc PUT ${put.status}: ${(await put.text()).slice(0, 300)}`);
  console.log("gravado");
}
