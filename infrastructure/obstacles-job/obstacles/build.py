"""Monta a base de obstáculos (spec 006).

Produção (na VPS, depois do osmium tags-filter):
  python -m obstacles.build --osm-pbf filtered.pbf --stamp 20261105 --mbtiles out.mbtiles
Amostra (Overpass, bbox sul,oeste,norte,leste):
  python -m obstacles.build --overpass -5.6,-36.2,-5.0,-35.6 --stamp 20261018 --tiles-dir amostra/rn
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

from . import aneel, dfs, nats, osm, tiling
from .model import drop_low_measured, merge_aneel, merge_nats

ATTRIBUTION = "ANEEL SIGEL; NATS (UK AIS); DFS Deutsche Flugsicherung GmbH (CC BY 4.0); (c) OpenStreetMap contributors; ODbL"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--osm-pbf")
    src.add_argument("--overpass", help="sul,oeste,norte,leste")
    p.add_argument("--stamp", type=int, required=True, help="AAAAMMDD da base")
    p.add_argument("--aneel-json", help="usa a coleta guardada em vez de baixar")
    p.add_argument("--save-aneel-json")
    p.add_argument("--nats-xml", help="obstáculos oficiais do Reino Unido (python -m obstacles.nats --download)")
    p.add_argument("--dfs-xml", help="obstáculos oficiais da Alemanha (python -m obstacles.dfs --download)")
    p.add_argument("--mbtiles")
    p.add_argument("--tiles-dir", help="grava {z}/{x}/{y}.bin (amostra e teste)")
    a = p.parse_args(argv)

    session = requests.Session()
    session.headers["User-Agent"] = "alfaero-obstacles-job/1 (tiles.alfaero.com)"

    bbox = None
    if a.overpass:
        bbox = tuple(float(v) for v in a.overpass.split(","))
        nodes, ways = osm.elements_from_overpass(osm.fetch_overpass(session, bbox))
    else:
        nodes, ways = osm.elements_from_pbf(a.osm_pbf)
    base = osm.base_from_elements(nodes, ways)
    print(f"osm: {len(nodes)} nos, {len(ways)} vias, {len(base.obstacles)} obstaculos, {len(base.lines)} linhas")

    if a.aneel_json:
        with open(a.aneel_json, encoding="utf-8") as f:
            turbines = json.load(f)
    else:
        turbines = aneel.fetch_turbines(session)
    if a.save_aneel_json:
        with open(a.save_aneel_json, "w", encoding="utf-8") as f:
            json.dump(turbines, f)
    print(f"aneel: {len(turbines)} aerogeradores")
    if bbox:
        s, w, n, e = bbox
        turbines = [t for t in turbines if s <= t["lat"] <= n and w <= t["lon"] <= e]
    # A1: o log diz quantos entraram e por que os outros ficaram fora.
    print("aneel juncao:", merge_aneel(base, turbines))
    if a.nats_xml:
        items, read = nats.parse_obstacles(a.nats_xml)
        if bbox:
            s, w, n, e = bbox
            items = [i for i in items if s <= i["lat"] <= n and w <= i["lon"] <= e]
        print(f"nats: {len(items)} obstaculos ({read})")
        print("nats juncao:", merge_nats(base, items))
    if a.dfs_xml:
        items, read = dfs.parse_obstacles(a.dfs_xml)
        if bbox:
            s, w, n, e = bbox
            items = [i for i in items if s <= i["lat"] <= n and w <= i["lon"] <= e]
        print(f"dfs: {len(items)} obstaculos ({read})")
        # Mesma regra da NATS: altura medida oficial vence o par compatível do OSM a menos de 60 m.
        print("dfs juncao:", merge_nats(base, items))
    print("baixos descartados:", drop_low_measured(base))

    tiles = tiling.build_tiles(base, a.stamp)
    print(f"tiles: {len(tiles)}, pontos {sum(len(t.points) for t in tiles.values())}, "
          f"vaos {sum(len(t.spans) for t in tiles.values())}")
    if a.mbtiles:
        tiling.write_mbtiles(tiles, a.mbtiles, a.stamp, ATTRIBUTION)
    if a.tiles_dir:
        from .aob import encode
        for t in tiles.values():
            d = os.path.join(a.tiles_dir, str(t.z), str(t.x))
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"{t.y}.bin"), "wb") as f:
                f.write(encode(t))
    return 0


if __name__ == "__main__":
    sys.exit(main())
