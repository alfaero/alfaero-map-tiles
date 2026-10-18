"""Corte da base em tiles z10 autossuficientes (AC3 da spec 389) e saída em MBTiles."""
from __future__ import annotations

import math
import sqlite3

from . import aob
from .model import Base

ZOOM = 10


def tile_of(lat: float, lon: float, z: int = ZOOM) -> tuple[int, int]:
    """Mesma conta do app (terrainTilePixelFor), Web Mercator."""
    n = 1 << z
    lat = max(-85.05112878, min(85.05112878, lat))
    x = (lon + 180) / 360 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return (min(n - 1, max(0, math.floor(x))), min(n - 1, max(0, math.floor(y))))


def _span_tiles(a, b, z):
    """Tiles que o vão toca: pontas e amostras no meio (vão longo, como travessia de rio)."""
    d = max(abs(a.lat - b.lat), abs(a.lon - b.lon))
    steps = max(1, math.ceil(d / 0.05))
    return {tile_of(a.lat + (b.lat - a.lat) * i / steps, a.lon + (b.lon - a.lon) * i / steps, z)
            for i in range(steps + 1)}


def build_tiles(base: Base, base_version: int, z: int = ZOOM) -> dict[tuple[int, int], aob.Tile]:
    owned: dict[tuple[int, int], list[int]] = {}
    for o in base.obstacles.values():
        owned.setdefault(tile_of(o.lat, o.lon, z), []).append(o.id)

    # Vãos únicos por par de ids, com a maior tensão entre as linhas que os repetem.
    spans: dict[tuple[int, int], int] = {}
    for line in base.lines:
        for u, v in zip(line.nodes, line.nodes[1:]):
            if u == v or u not in base.obstacles or v not in base.obstacles:
                continue
            key = (min(u, v), max(u, v))
            spans[key] = max(spans.get(key, 0), line.voltage_kv)
    tile_spans: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for (u, v), kv in spans.items():
        for t in _span_tiles(base.obstacles[u], base.obstacles[v], z):
            tile_spans.setdefault(t, []).append((u, v, kv))

    tiles = {}
    for key in set(owned) | set(tile_spans):
        ids = list(owned.get(key, []))
        own = set(ids)
        for u, v, _ in tile_spans.get(key, []):
            for i in (u, v):
                if i not in own and i not in ids:
                    ids.append(i)
        ids.sort(key=lambda i: (i not in own, i))  # donos primeiro, ordem estável
        index = {i: n for n, i in enumerate(ids)}
        t = aob.Tile(base_version, z, key[0], key[1])
        for i in ids:
            o = base.obstacles[i]
            t.points.append(aob.Point(o.id, o.lat, o.lon, o.final_height_m(), o.type, o.measured,
                                      i not in own, o.heading_deg))
        for u, v, kv in sorted(tile_spans.get(key, [])):
            t.spans.append(aob.Span(index[u], index[v], kv, 0))
        tiles[key] = t
    return tiles


def write_mbtiles(tiles: dict[tuple[int, int], aob.Tile], path: str, base_version: int, attribution: str) -> None:
    """MBTiles (y em TMS) para o `pmtiles convert` do pipeline."""
    db = sqlite3.connect(path)
    db.executescript("""
      DROP TABLE IF EXISTS tiles; DROP TABLE IF EXISTS metadata;
      CREATE TABLE metadata (name TEXT, value TEXT);
      CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);
      CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);
    """)
    db.executemany("INSERT INTO metadata VALUES (?, ?)", [
        ("name", "alfaero-obstacles"),
        ("format", "bin"),
        ("minzoom", str(ZOOM)),
        ("maxzoom", str(ZOOM)),
        ("version", str(base_version)),
        ("attribution", attribution),
        ("description", "Obstaculos AOB1 v1 (spec 389 do alfaero-mobile)"),
    ])
    db.executemany("INSERT INTO tiles VALUES (?, ?, ?, ?)", [
        (t.z, t.x, (1 << t.z) - 1 - t.y, aob.encode(t)) for t in tiles.values()])
    db.commit()
    db.close()
