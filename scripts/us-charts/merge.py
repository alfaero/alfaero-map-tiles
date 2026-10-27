#!/usr/bin/env python3
"""Junta as partes geradas pelo build_parts.py num mbtiles (base: docs/chart-pipeline/merge_g2t.py).

Uso:
    python3 merge.py --series sec --out /work/out/<id>.mbtiles --quality 75 \
        --meta '{"description": "Sectional Chart Tiles", "version": "1.0"}' \
        --edition 2026-10-29 --valid-until 2026-12-24

- O gdal2tiles usa a grade global TMS, então (z, x, y) batem entre as partes.
- Tile que vem de uma parte só: bytes do gdal2tiles sem recomprimir.
- Tile em sobreposição: alpha_composite na ordem do parts.json (priority 0 = carta-mãe embaixo,
  1 = inset por cima; dentro da mesma prioridade, ordem alfabética) e WebP na mesma qualidade.
- mbtiles no formato do TileServer de hoje: tabelas metadata/tiles, tile_row em TMS.
"""
import argparse
import io
import json
import os
import re
import sqlite3
from collections import defaultdict

from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--work", default="/work")
    ap.add_argument("--out", required=True)
    ap.add_argument("--quality", type=int, default=75)
    ap.add_argument("--meta", default="{}")
    ap.add_argument("--edition", required=True)
    ap.add_argument("--valid-until", required=True)
    a = ap.parse_args()

    pdir = os.path.join(a.work, "parts", a.series)
    manifest = json.load(open(os.path.join(pdir, "parts.json")))
    order = sorted(manifest, key=lambda k: (manifest[k]["priority"], manifest[k]["chart"], manifest[k]["part"]))
    rank = {k: i for i, k in enumerate(order)}

    index = defaultdict(list)
    yp = re.compile(r"^(\d+)\.webp$")
    for part in order:
        cdir = os.path.join(pdir, part)
        for zdir in os.listdir(cdir):
            zp = os.path.join(cdir, zdir)
            if not (zdir.isdigit() and os.path.isdir(zp)):
                continue
            for xdir in os.listdir(zp):
                xp = os.path.join(zp, xdir)
                for yf in os.listdir(xp):
                    m = yp.match(yf)
                    if m:
                        index[(int(zdir), int(xdir), int(m.group(1)))].append((rank[part], os.path.join(xp, yf)))
    multi = sum(1 for v in index.values() if len(v) > 1)
    print(f"tiles únicos: {len(index)}  sobrepostos (alpha_composite): {multi}", flush=True)

    tmp_out = a.out + ".tmp"
    if os.path.exists(tmp_out):
        os.remove(tmp_out)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    con = sqlite3.connect(tmp_out, isolation_level=None)
    con.executescript("""
    PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
    CREATE TABLE metadata (name text, value text);
    CREATE UNIQUE INDEX name ON metadata (name);
    CREATE TABLE tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);
    CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);
    """)
    con.execute("BEGIN")
    minz, maxz = 99, 0
    for (z, x, y), files in sorted(index.items()):
        files.sort()
        if len(files) == 1:
            with open(files[0][1], "rb") as fh:
                data = fh.read()
        else:
            base = None
            for _, fp in files:
                im = Image.open(fp).convert("RGBA")
                base = im if base is None else Image.alpha_composite(base, im)
            b = io.BytesIO()
            base.save(b, format="WEBP", quality=a.quality, method=4)
            data = b.getvalue()
        con.execute("INSERT INTO tiles VALUES(?,?,?,?)", (z, x, y, data))
        minz, maxz = min(minz, z), max(maxz, z)
    con.execute("COMMIT")

    # bounds a partir dos tiles do zoom máximo
    import math

    def lon(x, z):
        return x / 2 ** z * 360 - 180

    def lat(ytms, z):
        y = 2 ** z - 1 - ytms  # TMS -> XYZ (borda de cima do tile)
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))

    xs = [k for k in index if k[0] == maxz]
    w = min(lon(x, maxz) for _, x, _ in xs)
    e = max(lon(x + 1, maxz) for _, x, _ in xs)
    s = min(lat(y - 1, maxz) for _, _, y in xs)
    n = max(lat(y, maxz) for _, _, y in xs)
    meta = {"format": "webp", "type": "overlay", "minzoom": str(minz), "maxzoom": str(maxz),
            "bounds": f"{max(w, -180):.6f},{s:.6f},{min(e, 180):.6f},{n:.6f}"}
    meta.update(json.loads(a.meta))
    meta["faa_edition"] = a.edition
    meta["valid_until"] = a.valid_until
    con.executemany("INSERT INTO metadata VALUES(?,?)", list(meta.items()))
    con.execute("VACUUM")
    total, sz = con.execute("SELECT COUNT(*), SUM(length(tile_data)) FROM tiles").fetchone()
    print(f"OK tiles={total} payload={sz / 1e6:.1f} MB zoom={minz}..{maxz}")
    for z, c, avg in con.execute("SELECT zoom_level, COUNT(*), CAST(AVG(length(tile_data)) AS INT) FROM tiles GROUP BY zoom_level ORDER BY zoom_level"):
        print(f"  z{z}: {c} tiles, média {avg} B")
    print("metadata:", json.dumps(meta, ensure_ascii=False))
    con.close()
    os.replace(tmp_out, a.out)


if __name__ == "__main__":
    main()
