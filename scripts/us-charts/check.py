#!/usr/bin/env python3
"""Conferência automática de uma edição gerada contra a publicada (spec 008, AC3).

Diferente do verify.py (relatório para gente ler), aqui o resultado é uma decisão: lista de
problemas vazia = pode publicar.
"""
import io
import os
import random
import sqlite3

CHARTS = {
    "3447a49e-bcf6-4a02-a033-f726105eb5a0": "Sectional",
    "c75884f3-443a-4f1a-aa1a-01f99ad9075f": "ENR L",
    "c3fba2b7-575e-4fb9-bf30-8f75a86520f2": "ENR H",
    "7f17cb4a-88b3-41c7-bf31-67b1f0c48929": "Havaí/Pacífico",
}

TOTAL_TOLERANCE = 0.05   # total de tiles
ZOOM_TOLERANCE = 0.15    # cada zoom com mais de ZOOM_MIN_TILES
ZOOM_MIN_TILES = 100
SIZE_TOLERANCE = 0.30


def summarize(path: str, sample: int = 200) -> dict:
    """Contagem por zoom, tamanho, metadados e amostra de tiles de um mbtiles."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        meta = dict(con.execute("SELECT name, value FROM metadata"))
        zooms = {int(z): n for z, n in con.execute("SELECT zoom_level, COUNT(*) FROM tiles GROUP BY zoom_level")}
        ids = [r[0] for r in con.execute("SELECT rowid FROM tiles")]
        random.seed(8)
        bad = 0
        try:
            from PIL import Image
        except ImportError:  # sem Pillow a amostra não é conferida, e isso vira problema
            return {"meta": meta, "zooms": zooms, "size": os.path.getsize(path), "bad": -1}
        for rid in random.sample(ids, min(sample, len(ids))):
            data = con.execute("SELECT tile_data FROM tiles WHERE rowid=?", (rid,)).fetchone()[0]
            try:
                im = Image.open(io.BytesIO(data))
                im.load()
                if im.size != (512, 512) or im.format != "WEBP":
                    bad += 1
            except Exception:
                bad += 1
        return {"meta": meta, "zooms": zooms, "size": os.path.getsize(path), "bad": bad}
    finally:
        con.close()


def compare(chart: str, new: dict, prev: dict, edition: str) -> list:
    """Problemas de uma carta nova contra a anterior. `prev` = {zooms, size}."""
    name = CHARTS.get(chart, chart)
    out = []
    if new["meta"].get("faa_edition") != edition:
        out.append(f"{name}: faa_edition {new['meta'].get('faa_edition')} != {edition}")
    pz = {int(k): v for k, v in prev["zooms"].items()}
    nz = new["zooms"]
    if sorted(pz) != sorted(nz):
        out.append(f"{name}: zooms {sorted(nz)} != {sorted(pz)}")
    pt, nt = sum(pz.values()), sum(nz.values())
    if pt and abs(nt - pt) / pt > TOTAL_TOLERANCE:
        out.append(f"{name}: total de tiles {nt} contra {pt} ({100 * (nt - pt) / pt:+.1f}%)")
    for z, c in pz.items():
        if c > ZOOM_MIN_TILES:
            n = nz.get(z, 0)
            if abs(n - c) / c > ZOOM_TOLERANCE:
                out.append(f"{name}: zoom {z} com {n} tiles contra {c} ({100 * (n - c) / c:+.1f}%)")
    if prev.get("size") and abs(new["size"] - prev["size"]) / prev["size"] > SIZE_TOLERANCE:
        out.append(f"{name}: tamanho {new['size']} contra {prev['size']}")
    if new["bad"] != 0:
        out.append(f"{name}: amostra com {new['bad']} tiles ruins (ou sem Pillow)")
    return out


def check_edition(out_dir: str, published: dict, edition: str) -> tuple:
    """(problemas, resumos) da edição em `out_dir` contra `published[chart]`."""
    problems, summaries = [], {}
    for chart in CHARTS:
        path = os.path.join(out_dir, chart + ".mbtiles")
        if not os.path.exists(path):
            problems.append(f"{CHARTS[chart]}: arquivo ausente")
            continue
        s = summarize(path)
        summaries[chart] = {"zooms": s["zooms"], "size": s["size"]}
        prev = published.get(chart)
        if prev:
            problems += compare(chart, s, prev, edition)
        else:
            problems.append(f"{CHARTS[chart]}: sem edição anterior para comparar")
    return problems, summaries
