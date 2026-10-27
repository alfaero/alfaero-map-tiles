#!/usr/bin/env python3
"""Publicação de uma edição das cartas raster dos EUA (spec 008, AC5).

Mesmo caminho da publicação manual da edição 2026-10-29 (22/10/2026, spec 414):
cópia das cartas em uso -> envio como .new com sha256 -> mv + reinício com volta automática ->
purga do nginx -> S3 + CloudFront -> Remote Config `?v=` -> conferência de fora.
Cada passo lança `PublishError` com o nome da etapa; o chamador avisa por e-mail.
"""
import hashlib
import os
import sqlite3
import subprocess
import urllib.request

from check import CHARTS

HOST = "root@2.25.136.129"
SSH_KEY = os.path.expanduser("~/.ssh/alfaero_hostinger")
MBTILES_DIR = "/opt/alfaero-tileserver/mbtiles"
SERVER_BACKUP = "/opt/us-charts"
BUCKET = "alfaero"
S3_BACKUP = "backup/us-charts"
DISTRIBUTION = "E2N82UK4937317"
HERE = os.path.dirname(os.path.abspath(__file__))


class PublishError(RuntimeError):
    def __init__(self, step, detail):
        super().__init__(f"{step}: {detail}")
        self.step = step


def _run(step, cmd, timeout=3600, input_text=None):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_text,
                       env={**os.environ, "MSYS_NO_PATHCONV": "1", "AWS_PAGER": ""})
    if r.returncode != 0:
        raise PublishError(step, (r.stderr or r.stdout).strip()[-800:])
    return r.stdout


def _ssh(step, script, timeout=900):
    return _run(step, ["ssh", "-i", SSH_KEY, "-o", "BatchMode=yes", HOST, "bash -s"],
                timeout=timeout, input_text=script)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def backup_current(prev_edition):
    """Cópia das cartas em uso antes de trocar (S3 não guarda versões)."""
    for chart in CHARTS:
        _run("backup S3", ["aws", "s3", "cp", "--only-show-errors", f"s3://{BUCKET}/{chart}.mbtiles",
                           f"s3://{BUCKET}/{S3_BACKUP}/{prev_edition}/{chart}.mbtiles"])
    ids = " ".join(CHARTS)
    _ssh("backup servidor", f"""set -e
mkdir -p {SERVER_BACKUP}/{prev_edition}
for id in {ids}; do cp -p {MBTILES_DIR}/$id.mbtiles {SERVER_BACKUP}/{prev_edition}/; done
""")


def upload_new(out_dir):
    """Envia como .new (o arquivo em uso não é tocado) e confere o sha256 no servidor."""
    local = {}
    for chart in CHARTS:
        p = os.path.join(out_dir, chart + ".mbtiles")
        local[chart] = sha256(p)
        _run("envio", ["scp", "-q", "-i", SSH_KEY, "-o", "BatchMode=yes", p,
                       f"{HOST}:{MBTILES_DIR}/{chart}.mbtiles.new"], timeout=7200)
    out = _ssh("sha256 no servidor", f"cd {MBTILES_DIR} && sha256sum " + " ".join(f"{c}.mbtiles.new" for c in CHARTS))
    remote = {line.split()[1].replace(".mbtiles.new", ""): line.split()[0] for line in out.strip().splitlines()}
    bad = [CHARTS[c] for c in CHARTS if remote.get(c) != local[c]]
    if bad:
        raise PublishError("sha256 no servidor", f"diferente em {', '.join(bad)}")


def swap_and_check(prev_edition):
    """mv atômico + reinício; sem servidor saudável e tiles 200, volta as anteriores."""
    ids = " ".join(CHARTS)
    out = _ssh("troca no servidor", f"""set -u
cd {MBTILES_DIR}
for id in {ids}; do mv -f $id.mbtiles.new $id.mbtiles; done
docker restart alfaero-tileserver >/dev/null
ok=0
for i in $(seq 1 30); do
  st=$(docker inspect -f "{{{{.State.Health.Status}}}}" alfaero-tileserver 2>/dev/null)
  c1=$(curl -s -o /dev/null -w "%{{http_code}}" http://127.0.0.1:8006/data/3447a49e-bcf6-4a02-a033-f726105eb5a0/9/149/193.webp)
  c2=$(curl -s -o /dev/null -w "%{{http_code}}" http://127.0.0.1:8006/data/c75884f3-443a-4f1a-aa1a-01f99ad9075f/7/37/48.webp)
  if [ "$st" = healthy ] && [ "$c1" = 200 ] && [ "$c2" = 200 ]; then ok=1; break; fi
  sleep 4
done
if [ $ok != 1 ]; then
  for id in {ids}; do cp -p {SERVER_BACKUP}/{prev_edition}/$id.mbtiles $id.mbtiles; done
  docker restart alfaero-tileserver >/dev/null
  echo "ROLLBACK health=$st sectional=$c1 enrl=$c2"
else
  echo "OK"
fi
""")
    if "ROLLBACK" in out:
        raise PublishError("troca no servidor", f"servidor não ficou saudável; edição anterior restaurada ({out.strip()})")


def purge_cache():
    ids = " ".join(CHARTS)
    _ssh("purga do nginx", f"for id in {ids}; do /opt/alfaero-tileserver/purge-raster-cache.sh --prefix /data/$id; done")


def upload_s3(out_dir):
    for chart in CHARTS:
        _run("S3", ["aws", "s3", "cp", "--only-show-errors", os.path.join(out_dir, chart + ".mbtiles"),
                    f"s3://{BUCKET}/{chart}.mbtiles"], timeout=7200)
    _run("CloudFront", ["aws", "cloudfront", "create-invalidation", "--distribution-id", DISTRIBUTION,
                        "--paths", *[f"/{c}.mbtiles" for c in CHARTS]])


def patch_remote_config(edition_compact, backup_dir):
    """Simula primeiro (falha se faltar alguma das 4 cartas) e só então grava."""
    cmd = ["node", os.path.join(HERE, "rc_patch.mjs"), edition_compact, backup_dir]
    _run("Remote Config (simulação)", cmd, timeout=300)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env={**os.environ, "APPLY": "1"})
    if r.returncode != 0:
        raise PublishError("Remote Config", (r.stderr or r.stdout).strip()[-800:])


def external_check(out_dir, edition_compact):
    """Tile novo pela Cloudflare com o `?v=` igual ao gerado (Sectional 9/149/193)."""
    chart = "3447a49e-bcf6-4a02-a033-f726105eb5a0"
    z, x, y = 9, 149, 193
    con = sqlite3.connect(f"file:{os.path.join(out_dir, chart + '.mbtiles')}?mode=ro", uri=True)
    row = con.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                      (z, x, (1 << z) - 1 - y)).fetchone()
    con.close()
    url = f"https://raster.alfaero.com/data/{chart}/{z}/{x}/{y}.webp?v={edition_compact}"
    body = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    if not row or hashlib.sha256(body).digest() != hashlib.sha256(row[0]).digest():
        raise PublishError("conferência de fora", f"tile de {url} diferente do gerado")


def cleanup_backups(keep_edition):
    """Fica só a cópia da edição anterior (a de `keep_edition`), no S3 e no servidor."""
    out = _run("limpeza", ["aws", "s3", "ls", f"s3://{BUCKET}/{S3_BACKUP}/"])
    for line in out.splitlines():
        name = line.strip().split()[-1].rstrip("/") if line.strip() else ""
        if name and name != keep_edition:
            _run("limpeza", ["aws", "s3", "rm", "--recursive", "--only-show-errors", f"s3://{BUCKET}/{S3_BACKUP}/{name}/"])
    _ssh("limpeza", f"cd {SERVER_BACKUP} && for d in */; do d=${{d%/}}; [ \"$d\" != \"{keep_edition}\" ] && rm -rf \"$d\"; done; true")


def publish(out_dir, edition, prev_edition, backup_dir, log=print):
    compact = edition.replace("-", "")
    steps = [
        ("cópia das cartas em uso", lambda: backup_current(prev_edition)),
        ("envio ao servidor", lambda: upload_new(out_dir)),
        ("troca no servidor", lambda: swap_and_check(prev_edition)),
        ("purga do nginx", purge_cache),
        ("S3 e CloudFront", lambda: upload_s3(out_dir)),
        ("Remote Config", lambda: patch_remote_config(compact, backup_dir)),
        ("conferência de fora", lambda: external_check(out_dir, compact)),
        ("limpeza das cópias antigas", lambda: cleanup_backups(prev_edition)),
    ]
    for name, fn in steps:
        log(f"publicação: {name}")
        fn()
