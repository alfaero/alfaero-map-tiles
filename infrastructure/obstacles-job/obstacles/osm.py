"""Leitura do OSM para a base de obstáculos: PBF filtrado (produção) ou Overpass (amostra).

Os dois caminhos entregam os mesmos elementos a `base_from_elements`, então a
regra é uma só.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from . import aob
from .model import OSM_WAY_ID_BASE, Base, Line, Obstacle, osm_point_type, parse_height_m, parse_voltage_kv

# Filtro do osmium-tool (produção). Vias de linha trazem os nós referenciados.
OSMIUM_FILTERS = [
    "w/power=line",
    "n/power=tower",
    "nw/man_made=mast,tower,communications_tower,chimney",
    "nw/generator:source=wind",
]


@dataclass
class OsmNode:
    id: int
    lat: float
    lon: float
    tags: dict[str, str]


@dataclass
class OsmWay:
    id: int
    refs: list[int]
    tags: dict[str, str]
    center: tuple[float, float] | None = None  # (lat, lon) de via fechada


def base_from_elements(nodes: dict[int, OsmNode], ways: list[OsmWay]) -> Base:
    base = Base()
    # Linhas: todo vértice de power=line vira torre de transmissão (AC1); a
    # torre herda a maior tensão das linhas que passam nela.
    for w in ways:
        if w.tags.get("power") != "line":
            continue
        refs = [r for r in w.refs if r in nodes]
        # Nó repetido seguido (dado sujo) daria vão de ponta igual.
        refs = [r for i, r in enumerate(refs) if i == 0 or r != refs[i - 1]]
        if len(refs) < 2:
            continue
        kv = parse_voltage_kv(w.tags.get("voltage"))
        base.lines.append(Line(w.id, refs, kv))
        for r in refs:
            n = nodes[r]
            o = base.obstacles.get(r)
            if o is None:
                o = Obstacle(r, n.lat, n.lon, aob.TRANSMISSION_TOWER, parse_height_m(n.tags.get("height")))
                base.obstacles[r] = o
            o.voltage_kv = max(o.voltage_kv, kv)
    # Pontos soltos: nós com tipo, e vias fechadas pelo centroide.
    for n in nodes.values():
        if n.id in base.obstacles:
            continue
        typ = osm_point_type(n.tags)
        if typ is None:
            continue
        base.obstacles[n.id] = Obstacle(n.id, n.lat, n.lon, typ, parse_height_m(n.tags.get("height")))
    for w in ways:
        if w.tags.get("power") == "line" or w.center is None:
            continue
        typ = osm_point_type(w.tags)
        if typ is None:
            continue
        oid = OSM_WAY_ID_BASE + w.id
        base.obstacles[oid] = Obstacle(oid, w.center[0], w.center[1], typ, parse_height_m(w.tags.get("height")))
    return base


def overpass_query(south: float, west: float, north: float, east: float) -> str:
    b = f"({south},{west},{north},{east})"
    return f"""[out:json][timeout:180];
(
  way["power"="line"]{b};
  node["power"="tower"]{b};
  node["man_made"~"^(mast|tower|communications_tower|chimney)$"]{b};
  way["man_made"~"^(mast|tower|communications_tower|chimney)$"]{b};
  node["generator:source"="wind"]{b};
  way["generator:source"="wind"]{b};
);
out body center;
>;
out body qt;"""


def elements_from_overpass(data: dict) -> tuple[dict[int, OsmNode], list[OsmWay]]:
    nodes: dict[int, OsmNode] = {}
    ways: list[OsmWay] = []
    for e in data.get("elements", []):
        if e["type"] == "node":
            nodes[e["id"]] = OsmNode(e["id"], e["lat"], e["lon"], e.get("tags", {}))
        elif e["type"] == "way":
            c = e.get("center")
            ways.append(OsmWay(e["id"], e.get("nodes", []), e.get("tags", {}),
                               (c["lat"], c["lon"]) if c else None))
    return nodes, ways


def fetch_overpass(session, bbox, url="https://overpass-api.de/api/interpreter", attempts=5, sleep=time.sleep) -> dict:
    """Amostra pelo Overpass, com retry em 429/5xx e queda de conexão."""
    delay = 5.0
    last = ""
    for i in range(attempts):
        if i:
            sleep(delay)
            delay *= 2
        try:
            r = session.post(url, data={"data": overpass_query(*bbox)}, timeout=240)
        except Exception as e:  # conexão
            last = repr(e)
            continue
        if r.status_code == 200:
            return r.json()
        last = f"HTTP {r.status_code}"
        if r.status_code not in (429, 504) and r.status_code < 500:
            break
    raise RuntimeError(f"Overpass falhou: {last}")


def elements_from_pbf(path: str) -> tuple[dict[int, OsmNode], list[OsmWay]]:
    """PBF já filtrado pelo osmium-tool (OSMIUM_FILTERS), lido com localizações."""
    import osmium

    nodes: dict[int, OsmNode] = {}
    ways: list[OsmWay] = []

    class H(osmium.SimpleHandler):
        def node(self, n):
            nodes[n.id] = OsmNode(n.id, n.location.lat, n.location.lon, {t.k: t.v for t in n.tags})

        def way(self, w):
            refs = [nd.ref for nd in w.nodes]
            center = None
            if w.is_closed() and len(w.nodes) > 2:
                pts = [(nd.location.lat, nd.location.lon) for nd in w.nodes if nd.location.valid()][:-1]
                if pts:
                    center = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            ways.append(OsmWay(w.id, refs, {t.k: t.v for t in w.tags}, center))

    H().apply_file(path, locations=True)
    return nodes, ways


def save_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
