"""Base intermediária de obstáculos, alturas (AC2 da spec 389) e junção ANEEL + OSM."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

from . import aob

MIN_MEASURED_HEIGHT_M = 15.0

# Ids estáveis entre tiles e entre execuções: nó do OSM como está; centroide de
# via do OSM e aerogerador da ANEEL em faixas próprias.
OSM_WAY_ID_BASE = 1 << 59
ANEEL_ID_BASE = 1 << 60


@dataclass
class Obstacle:
    id: int
    lat: float
    lon: float
    type: int
    height_m: float | None = None  # medida; None = estimar
    heading_deg: float | None = None
    voltage_kv: int = 0  # torre: maior tensão das linhas que passam nela

    @property
    def measured(self) -> bool:
        return self.height_m is not None

    def final_height_m(self) -> float:
        return self.height_m if self.height_m is not None else estimated_height_m(self.type, self.voltage_kv)


@dataclass
class Line:
    id: int
    nodes: list[int]
    voltage_kv: int = 0


@dataclass
class Base:
    obstacles: dict[int, Obstacle] = field(default_factory=dict)
    lines: list[Line] = field(default_factory=list)


def estimated_height_m(typ: int, voltage_kv: int = 0) -> float:
    """Espelho de estimatedObstacleHeightM do app (obstacle_heights.dart)."""
    if typ == aob.TRANSMISSION_TOWER:
        if voltage_kv >= 500:
            return 50
        if voltage_kv >= 345:
            return 40
        if voltage_kv >= 230:
            return 35
        if voltage_kv >= 138:
            return 28
        return 22
    return {aob.WIND_TURBINE: 150, aob.TELECOM_TOWER: 45, aob.MAST: 30, aob.CHIMNEY: 40}.get(typ, 30)


_NUMBER = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*(m|ft|')?\s*$", re.I)


def parse_height_m(raw: str | None) -> float | None:
    """`height` do OSM: '45', '45 m', '45.5', '150 ft'. Outra coisa = sem altura."""
    if not raw:
        return None
    m = _NUMBER.match(raw)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    if (m.group(2) or "").lower() in ("ft", "'"):
        v *= 0.3048
    return v if 0 < v < 1000 else None


def parse_voltage_kv(raw: str | None) -> int:
    """`voltage` do OSM em volts, às vezes vários separados por ';'. Maior em kV."""
    best = 0
    for part in (raw or "").split(";"):
        part = part.strip()
        if part.isdigit():
            best = max(best, int(part) // 1000)
    return best


def osm_point_type(tags: dict[str, str]) -> int | None:
    """Tipo de um nó ou via do OSM que não é vértice de linha (AC1)."""
    mm = tags.get("man_made")
    if tags.get("generator:source") == "wind" or tags.get("generator:method") == "wind_turbine":
        return aob.WIND_TURBINE
    if mm == "communications_tower":
        return aob.TELECOM_TOWER
    if mm == "tower":
        return aob.TELECOM_TOWER if tags.get("tower:type") == "communication" else aob.GENERIC
    if mm == "mast":
        return aob.MAST
    if mm == "chimney":
        return aob.CHIMNEY
    if tags.get("power") == "tower":
        return aob.TRANSMISSION_TOWER
    return None


def _fold(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()


_BUILT = {"sim", "operacao", "1", "construcao"}
_UNCONFIRMED = {"nao", ""}


def aneel_status(raw: str | None) -> str:
    """'built' entra; 'unconfirmed' só com aerogerador do OSM perto; 'skip' fica fora (AC2a)."""
    v = _fold(raw)
    if v in _BUILT:
        return "built"
    if v in _UNCONFIRMED:
        return "unconfirmed"
    return "skip"


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    k = math.pi / 180
    x = (lon2 - lon1) * k * math.cos((lat1 + lat2) / 2 * k)
    y = (lat2 - lat1) * k
    return math.hypot(x, y) * 6371008.8


class _Grid:
    """Busca por vizinho em células de ~0,001 grau (cerca de 110 m)."""

    def __init__(self, cell: float = 0.001):
        self.cell = cell
        self.cells: dict[tuple[int, int], list[Obstacle]] = {}

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return (math.floor(lat / self.cell), math.floor(lon / self.cell))

    def add(self, o: Obstacle) -> None:
        self.cells.setdefault(self._key(o.lat, o.lon), []).append(o)

    def near(self, lat: float, lon: float, radius_m: float) -> list[Obstacle]:
        ky, kx = self._key(lat, lon)
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for o in self.cells.get((ky + dy, kx + dx), []):
                    if distance_m(lat, lon, o.lat, o.lon) <= radius_m:
                        out.append(o)
        return out


def merge_aneel(base: Base, turbines: list[dict], match_radius_m: float = 60) -> dict[str, int]:
    """Junta os aerogeradores da ANEEL na base do OSM (A1 da spec 006).

    Cada item de `turbines`: id, lat, lon, height_m, status (texto cru de
    OPERACAO), heading_deg. O da ANEEL fica (altura medida) e apaga o do OSM a
    menos de `match_radius_m`; 'Não' e vazio só entram com esse par.
    """
    grid = _Grid()
    for o in base.obstacles.values():
        if o.type == aob.WIND_TURBINE:
            grid.add(o)
    stats = {"built": 0, "confirmed": 0, "unconfirmed_dropped": 0, "skip": 0, "low": 0}
    for t in turbines:
        status = aneel_status(t.get("status"))
        if status == "skip":
            stats["skip"] += 1
            continue
        h = t.get("height_m")
        if h is not None and h < MIN_MEASURED_HEIGHT_M:
            stats["low"] += 1
            continue
        twins = grid.near(t["lat"], t["lon"], match_radius_m)
        if status == "unconfirmed" and not twins:
            stats["unconfirmed_dropped"] += 1
            continue
        for twin in twins:
            base.obstacles.pop(twin.id, None)
        stats["built" if status == "built" else "confirmed"] += 1
        oid = ANEEL_ID_BASE + int(t["id"])
        base.obstacles[oid] = Obstacle(oid, t["lat"], t["lon"], aob.WIND_TURBINE, h, t.get("heading_deg"))
    return stats


def drop_low_measured(base: Base) -> int:
    """Altura medida abaixo de 15 m fica fora (AC2), exceto vértice de linha:
    sem ele o fio perderia a ponta."""
    on_lines = {n for line in base.lines for n in line.nodes}
    low = [o.id for o in base.obstacles.values()
           if o.height_m is not None and o.height_m < MIN_MEASURED_HEIGHT_M and o.id not in on_lines]
    for oid in low:
        del base.obstacles[oid]
    return len(low)
