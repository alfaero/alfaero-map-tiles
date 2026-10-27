// Patch cirúrgico do Remote Config `map_downloads` (specs 414 e 008): só o `map_online_url` das 4
// cartas dos EUA ganha `?v=<edição>`; `map_version` não muda (subir a versão tiraria a carta
// offline do piloto até baixar de novo). Guarda o template anterior em <pasta>.
//
// Uso: node rc_patch.mjs <AAAAMMDD> <pasta_backup>          (só mostra)
//      APPLY=1 node rc_patch.mjs <AAAAMMDD> <pasta_backup>  (grava)
// Credencial: segredo alfaero/firebase-admin no Secrets Manager (aws cli da máquina).
import { execFileSync } from "node:child_process";
import { createSign } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";

const [EDITION, BACKUP_DIR] = process.argv.slice(2);
if (!/^\d{8}$/.test(EDITION ?? "") || !BACKUP_DIR) {
  console.error("uso: node rc_patch.mjs <AAAAMMDD> <pasta_backup>");
  process.exit(2);
}
const IDS = [
  "3447a49e-bcf6-4a02-a033-f726105eb5a0",
  "c75884f3-443a-4f1a-aa1a-01f99ad9075f",
  "c3fba2b7-575e-4fb9-bf30-8f75a86520f2",
  "7f17cb4a-88b3-41c7-bf31-67b1f0c48929",
];

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
writeFileSync(`${BACKUP_DIR}/rc_before_${EDITION}_${Date.now()}.json`, JSON.stringify(cfg, null, 1));

const param =
  cfg.parameters?.map_downloads ??
  (cfg.parameterGroups ? Object.values(cfg.parameterGroups).map((g) => g.parameters?.map_downloads).find(Boolean) : undefined);
if (!param) throw new Error("map_downloads não encontrado");

let changes = 0;
let found = 0;
function patchValue(v) {
  const data = JSON.parse(v.value);
  for (const region of Array.isArray(data) ? data : []) {
    for (const it of region.items ?? []) {
      if (!IDS.includes(it.id)) continue;
      found++;
      const before = it.map_online_url;
      it.map_online_url = `${String(before).replace(/\?v=[^&]*$/, "")}?v=${EDITION}`;
      if (before !== it.map_online_url) {
        changes++;
        console.log(`${it.name}: ${before} -> ${it.map_online_url} (map_version ${it.map_version})`);
      }
    }
  }
  return { value: JSON.stringify(data) };
}
param.defaultValue = patchValue(param.defaultValue);
for (const [k, v] of Object.entries(param.conditionalValues ?? {})) {
  if (v.value) param.conditionalValues[k] = patchValue(v);
}
console.log(`cartas encontradas: ${found}, mudanças: ${changes}`);
if (found < 4) throw new Error(`só ${found} das 4 cartas no map_downloads`);

if (process.env.APPLY === "1" && changes) {
  const put = await fetch(url, {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json; charset=UTF-8", "If-Match": etag },
    body: JSON.stringify(cfg),
  });
  if (!put.ok) throw new Error(`rc PUT ${put.status}: ${(await put.text()).slice(0, 300)}`);
  console.log("gravado");
}
