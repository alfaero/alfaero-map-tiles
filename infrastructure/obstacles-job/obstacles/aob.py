"""Formato AOB1 v1 dos tiles de obstáculos (spec 389 do alfaero-mobile, plan.md).

Espelho do decoder do app (lib/src/services/obstacles/obstacle_tile.dart). Os
testes deste pacote conferem a ida e volta; a amostra é conferida também pelo
decoder do app (A2 da spec 006).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b"AOB1"
VERSION = 1
NO_HEADING = 0xFFFF

# Índice = byte do formato. Nunca reordenar (igual ao enum ObstacleType do app).
GENERIC, WIND_TURBINE, TRANSMISSION_TOWER, TELECOM_TOWER, MAST, CHIMNEY = range(6)

_HEADER = struct.Struct("<4sHHIB3xIIII")  # 32 bytes
_POINT = struct.Struct("<QiiHBBHH")  # 24 bytes
_SPAN = struct.Struct("<IIHBx")  # 12 bytes


@dataclass
class Point:
    id: int
    lat: float
    lon: float
    height_m: float
    type: int
    measured: bool
    outside_tile: bool = False
    heading_deg: float | None = None


@dataclass
class Span:
    a: int
    b: int
    voltage_kv: int = 0
    cables: int = 0


@dataclass
class Tile:
    base_version: int
    z: int
    x: int
    y: int
    points: list[Point] = field(default_factory=list)
    spans: list[Span] = field(default_factory=list)


def encode(t: Tile) -> bytes:
    out = bytearray(_HEADER.pack(MAGIC, VERSION, 0, t.base_version, t.z, t.x, t.y,
                                 len(t.points), len(t.spans)))
    for p in t.points:
        heading = NO_HEADING if p.heading_deg is None else round((p.heading_deg % 360) * 10) % 3600
        flags = (1 if p.measured else 0) | (2 if p.outside_tile else 0)
        out += _POINT.pack(p.id, round(p.lat * 1e7), round(p.lon * 1e7),
                           max(0, min(0xFFFE, round(p.height_m * 10))), p.type, flags, heading, 0)
    for s in t.spans:
        out += _SPAN.pack(s.a, s.b, min(s.voltage_kv, 0xFFFF), min(s.cables, 0xFF))
    return bytes(out)


def decode(b: bytes) -> Tile:
    if len(b) < _HEADER.size:
        raise ValueError("tile curto")
    magic, version, _, base, z, x, y, n_points, n_spans = _HEADER.unpack_from(b, 0)
    if magic != MAGIC or version != VERSION:
        raise ValueError("magic ou versão inválidos")
    if len(b) != _HEADER.size + n_points * _POINT.size + n_spans * _SPAN.size:
        raise ValueError("tamanho não fecha com os contadores")
    t = Tile(base, z, x, y)
    o = _HEADER.size
    for _ in range(n_points):
        pid, lat, lon, h, typ, flags, heading, _r = _POINT.unpack_from(b, o)
        if typ > CHIMNEY:
            raise ValueError(f"tipo desconhecido {typ}")
        t.points.append(Point(pid, lat / 1e7, lon / 1e7, h / 10, typ, bool(flags & 1),
                              bool(flags & 2), None if heading == NO_HEADING else heading / 10))
        o += _POINT.size
    for _ in range(n_spans):
        a, c, kv, cables = _SPAN.unpack_from(b, o)
        if a >= n_points or c >= n_points or a == c:
            raise ValueError(f"vão inválido {a} {c}")
        t.spans.append(Span(a, c, kv, cables))
        o += _SPAN.size
    return t
