#!/usr/bin/env python3
"""Conferência (AC2) dos mbtiles gerados: tiles por zoom contra os arquivos no ar em 21/10/2026,
tamanho, sha256, metadados, tiles 512 px e tiles ilegíveis.

Uso: python3 verify.py <pasta_com_os_mbtiles> [--sample 300]
"""
import hashlib
import io
import os
import random
import sqlite3
import sys

from PIL import Image

# contagem por zoom dos arquivos no ar (research.md 1.1, lido do SQLite do servidor em 21/10/2026)
HOJE = {
    "3447a49e-bcf6-4a02-a033-f726105eb5a0": ("Sectional", 1, [3, 5, 10, 21, 52, 142, 473, 1671, 6283, 24353, 94909], 2666127360),
    "c75884f3-443a-4f1a-aa1a-01f99ad9075f": ("ENR L", 5, [22, 65, 217, 771, 2922, 11405], 229445632),
    "c3fba2b7-575e-4fb9-bf30-8f75a86520f2": ("ENR H", 4, [8, 25, 77, 267, 992, 3778], 82939904),
    "7f17cb4a-88b3-41c7-bf31-67b1f0c48929": ("Havaí/Pacífico", 2, [4, 10, 24, 68, 236, 875], 36229120),
}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    d = sys.argv[1]
    sample = int(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else 300
    for cid, (nome, z0, cont, tam) in HOJE.items():
        p = os.path.join(d, cid + ".mbtiles")
        if not os.path.exists(p):
            print(f"## {nome} ({cid}): AUSENTE")
            continue
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        meta = dict(con.execute("SELECT name, value FROM metadata"))
        rows = dict(con.execute("SELECT zoom_level, COUNT(*) FROM tiles GROUP BY zoom_level"))
        sz = os.path.getsize(p)
        print(f"## {nome} ({cid})")
        print(f"tamanho {sz:,} B (hoje {tam:,} B, {100 * (sz - tam) / tam:+.1f}%)  sha256 {sha256(p)}")
        print("metadata: " + ", ".join(f"{k}={v}" for k, v in sorted(meta.items())))
        print("| zoom | hoje | novo | diferença |")
        print("|---|---|---|---|")
        tot_h = tot_n = 0
        for i, c in enumerate(cont):
            z = z0 + i
            n = rows.get(z, 0)
            tot_h += c
            tot_n += n
            print(f"| {z} | {c} | {n} | {n - c:+d} ({100 * (n - c) / c:+.1f}%) |")
        extra = sorted(set(rows) - set(range(z0, z0 + len(cont))))
        print(f"| total | {tot_h} | {tot_n} | {tot_n - tot_h:+d} ({100 * (tot_n - tot_h) / tot_h:+.1f}%) |")
        if extra:
            print(f"ZOOMS A MAIS: {extra}")
        # amostra: tiles decodificam, 512x512 RGBA
        ids = [r[0] for r in con.execute("SELECT rowid FROM tiles")]
        random.seed(414)
        bad = 0
        for rid in random.sample(ids, min(sample, len(ids))):
            data = con.execute("SELECT tile_data FROM tiles WHERE rowid=?", (rid,)).fetchone()[0]
            try:
                im = Image.open(io.BytesIO(data))
                im.load()
                if im.size != (512, 512) or im.format != "WEBP":
                    bad += 1
            except Exception:
                bad += 1
        print(f"amostra de {min(sample, len(ids))} tiles: {bad} com problema (decodificação, formato ou tamanho != 512)")
        print()


if __name__ == "__main__":
    main()
