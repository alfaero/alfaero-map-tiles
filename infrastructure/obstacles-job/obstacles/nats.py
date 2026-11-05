"""Obstáculos oficiais do Reino Unido: UK ICAO Obstacle Dataset Area 1 da NATS (AIXM 5.1).

Spec 003 do alfaero-navdata-pipeline, onda C. Sem login desde a AIC W003/2026; um zip por
ciclo AIRAC com o XML e o .sha256 dele. Área 1 = obstáculos com 100 m ou mais sobre o solo,
todos com altura medida (verticalExtent).

Baixar e conferir (na VPS, antes do build):
  python -m obstacles.nats --download nats-obstacles.xml [--date AAAAMMDD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

from . import aob
from .model import NATS_ID_BASE

BASE_URL = "https://nats-uk.ead-it.com/cms-nats/export/sites/default/en/Publications/digital-datasets"
AIXM = "{http://www.aixm.aero/schema/5.1}"
GML = "{http://www.opengis.net/gml/3.2}"
FT_TO_M = 0.3048

# Âncora AIRAC: ciclo 2001 efetivo em 2020-01-02; ciclos de 28 dias.
_AIRAC_ANCHOR = dt.date(2020, 1, 2)

_TYPES = {
    "WINDMILL": aob.WIND_TURBINE,
    "TRANSMISSION_LINE": aob.TRANSMISSION_TOWER,  # a NATS dá um ponto por vão (o mais alto)
    "TOWER": aob.TELECOM_TOWER,
    "STACK": aob.CHIMNEY,
    "COOLING_TOWER": aob.CHIMNEY,
}
_SKIP = {"AREA1"}  # o polígono da própria Área 1, não é obstáculo


class NatsError(RuntimeError):
    pass


def nats_type(raw: str | None) -> int | None:
    t = (raw or "").strip().upper()
    if t in _SKIP:
        return None
    return _TYPES.get(t, aob.GENERIC)


def airac_effective(day: dt.date) -> str:
    """AAAAMMDD do início do ciclo AIRAC que contém o dia."""
    k = (day - _AIRAC_ANCHOR).days // 28
    return (_AIRAC_ANCHOR + dt.timedelta(days=28 * k)).strftime("%Y%m%d")


def obstacles_url(date8: str) -> str:
    return f"{BASE_URL}/UK_ICAO_Obstacle_Dataset_Area_1/EG_OBS_DS_AREA1_FULL_{date8}_XML.zip"


def xml_from_zip(data: bytes) -> bytes:
    """XML do zip, conferido pelo .sha256 irmão. Sem .sha256 ou divergente: erro."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        xml_name = next((n for n in names if re.search(r"EG_OBS_DS_AREA1_FULL_\d{8}\.xml$", n)), None)
        if not xml_name:
            raise NatsError(f"XML de obstáculos não encontrado no zip: {names}")
        sha_name = xml_name[:-4] + ".sha256"
        if sha_name not in names:
            raise NatsError(f"{sha_name} ausente no zip")
        xml = z.read(xml_name)
        declared = z.read(sha_name).decode("utf-8", "replace").strip().split()[0].lower()
    actual = hashlib.sha256(xml).hexdigest()
    if declared != actual:
        raise NatsError(f"SHA-256 de {xml_name} não confere: declarado {declared}, calculado {actual}")
    return xml


def _stable_id(name: str) -> int:
    return NATS_ID_BASE + int.from_bytes(hashlib.sha1(name.encode()).digest()[:6], "big")


def _height_m(el) -> float | None:
    if el is None or el.text is None or not el.text.strip():
        return None
    v = float(el.text)
    uom = (el.get("uom") or "FT").upper()
    return v * FT_TO_M if uom in ("FT", "[FT_I]") else v


def parse_obstacles(source) -> tuple[list[dict], dict]:
    """Lê o XML em fluxo. Item: id, name, lat, lon, type, height_m. Retorna (itens, contagens)."""
    items: list[dict] = []
    stats = {"read": 0, "skipped": 0, "no_height": 0, "no_position": 0}
    for _, el in ET.iterparse(source, events=("end",)):
        if el.tag != f"{AIXM}VerticalStructureTimeSlice":
            continue
        stats["read"] += 1
        name = (el.findtext(f"{AIXM}name") or "").strip()
        typ = nats_type(el.findtext(f"{AIXM}type"))
        part = el.find(f"{AIXM}part/{AIXM}VerticalStructurePart")
        if typ is None:
            stats["skipped"] += 1
        elif part is None:
            stats["no_position"] += 1
        else:
            h = _height_m(part.find(f"{AIXM}verticalExtent"))
            pos = part.find(f"{AIXM}horizontalProjection_location/{AIXM}ElevatedPoint/{GML}pos")
            if h is None:
                stats["no_height"] += 1
            elif pos is None or not (pos.text or "").strip():
                stats["no_position"] += 1
            else:
                lat, lon = (float(v) for v in pos.text.split()[:2])
                items.append({"id": _stable_id(name), "name": name, "lat": lat, "lon": lon, "type": typ, "height_m": h})
        el.clear()
    return items, stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--download", required=True, help="caminho do XML conferido")
    p.add_argument("--date", help="AAAAMMDD do ciclo (padrão: ciclo vigente hoje)")
    a = p.parse_args(argv)
    import requests

    date8 = a.date or airac_effective(dt.datetime.now(dt.timezone.utc).date())
    url = obstacles_url(date8)
    r = None
    for attempt in range(5):
        try:
            r = requests.get(url, timeout=120, headers={"User-Agent": "alfaero-obstacles-job/1 (tiles.alfaero.com)"})
            if r.status_code < 500 and r.status_code != 429:
                break
        except requests.RequestException as e:
            print(f"nats: tentativa {attempt + 1}: {e}")
        import time
        time.sleep(10 * (attempt + 1))
    if r is None or r.status_code != 200:
        print(f"nats: {url} HTTP {getattr(r, 'status_code', 'sem resposta')}")
        return 2
    xml = xml_from_zip(r.content)
    with open(a.download, "wb") as f:
        f.write(xml)
    print(f"nats: {date8} {len(xml)} bytes conferidos em {a.download}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
