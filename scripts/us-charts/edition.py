#!/usr/bin/env python3
"""Datas das edições das cartas raster dos EUA (spec 008).

A FAA troca Sectional e cartas de rota a cada 56 dias, todas no mesmo ciclo. A âncora é a edição
2026-10-29; a vigência começa às 09:01Z da data e vale até a edição seguinte.
"""
from datetime import date, datetime, timedelta, timezone

ANCHOR = date(2026, 10, 29)
CYCLE = timedelta(days=56)
EFFECTIVE_TIME = (9, 1)  # 09:01Z


def edition_after(d: date) -> date:
    """Primeira edição estritamente depois de `d`."""
    if d < ANCHOR:
        steps = 0
        while ANCHOR - CYCLE * (steps + 1) > d:
            steps += 1
        return ANCHOR - CYCLE * steps
    n = (d - ANCHOR) // CYCLE + 1
    return ANCHOR + CYCLE * n


def is_edition(d: date) -> bool:
    return (d - ANCHOR).days % CYCLE.days == 0


def effective_utc(edition: date) -> datetime:
    h, m = EFFECTIVE_TIME
    return datetime(edition.year, edition.month, edition.day, h, m, tzinfo=timezone.utc)


def valid_until(edition: date) -> date:
    return edition + CYCLE


def faa_folder(edition: date) -> str:
    """Pasta da edição em aeronav.faa.gov (`MM-DD-AAAA`)."""
    return edition.strftime("%m-%d-%Y")


def parse(s: str) -> date:
    return date.fromisoformat(s)
