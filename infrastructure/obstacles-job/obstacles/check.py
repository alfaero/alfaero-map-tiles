"""Confere o MBTiles gerado antes de subir (A1 e A2 da spec 006).

  python -m obstacles.check out.mbtiles --min-turbines 15000

Todo tile decodifica, o z/x/y gravado no tile bate com a chave, cada ponto dono
cai no próprio tile e nenhum id se repete dentro do tile. Sai com erro se algo
falhar ou se vierem menos aerogeradores do que o mínimo (coleta pela metade).
"""
from __future__ import annotations

import argparse
import collections
import sqlite3
import sys

from . import aob
from .model import NATS_ID_BASE
from .tiling import tile_of


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("mbtiles")
    p.add_argument("--min-turbines", type=int, default=0)
    p.add_argument("--min-nats", type=int, default=0, help="mínimo de obstáculos oficiais da NATS (Reino Unido)")
    a = p.parse_args(argv)
    db = sqlite3.connect(a.mbtiles)
    counts = collections.Counter()
    measured = collections.Counter()
    errors = 0
    n = 0
    nats_points = 0
    for z, x, tms_y, data in db.execute("SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles"):
        n += 1
        y = (1 << z) - 1 - tms_y
        try:
            t = aob.decode(data)
        except ValueError as e:
            print(f"tile {z}/{x}/{y} ilegivel: {e}")
            errors += 1
            continue
        if (t.z, t.x, t.y) != (z, x, y):
            print(f"tile {z}/{x}/{y} diz ser {t.z}/{t.x}/{t.y}")
            errors += 1
        if len({pt.id for pt in t.points}) != len(t.points):
            print(f"tile {z}/{x}/{y} com id repetido")
            errors += 1
        for pt in t.points:
            if pt.outside_tile:
                continue
            if tile_of(pt.lat, pt.lon, z) != (x, y):
                print(f"tile {z}/{x}/{y}: ponto {pt.id} fora do proprio tile")
                errors += 1
            counts[pt.type] += 1
            measured[pt.type] += pt.measured
            nats_points += pt.id >= NATS_ID_BASE
    print(f"tiles {n}, por tipo {dict(counts)}, medidos {dict(measured)}, nats {nats_points}, erros {errors}")
    if counts[aob.WIND_TURBINE] < a.min_turbines:
        print(f"aerogeradores {counts[aob.WIND_TURBINE]} abaixo do minimo {a.min_turbines}")
        return 1
    if nats_points < a.min_nats:
        print(f"obstaculos da NATS {nats_points} abaixo do minimo {a.min_nats}")
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
