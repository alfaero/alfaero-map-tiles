"""Obstáculos oficiais da Alemanha: ED Obstacles Area 1 da DFS (AIXM 5.1.1), licença CC BY 4.0.

Spec 005 do alfaero-navdata-pipeline, onda D. Download pela API REST documentada da DFS
(aip.dfs.de/datasets): o nome do arquivo muda a cada AIRAC e vem do metadado, junto com o
SHA-512. Área 1 = obstáculos com 100 m ou mais sobre o solo, com altura medida.

Diferença para a NATS: a DFS agrupa por estrutura. Um parque eólico é uma VerticalStructure com
uma VerticalStructurePart por aerogerador, cada parte com posição, altura e tipo próprios. Cada
parte vira um obstáculo.

Baixar e conferir (na VPS, antes do build):
  python -m obstacles.dfs --download dfs-obstacles.xml
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

from . import aob
from .model import DFS_ID_BASE

METADATA_URL = "https://aip.dfs.de/datasets/rest/"
DATASET_NAME = "ED Obstacles Area 1"
AIXM = "{http://www.aixm.aero/schema/5.1.1}"
GML = "{http://www.opengis.net/gml/3.2}"
FT_TO_M = 0.3048
UA = {"User-Agent": "alfaero-obstacles-job/1 (tiles.alfaero.com)"}

_TYPES = {
    "WINDMILL": aob.WIND_TURBINE,
    "TRANSMISSION_LINE": aob.TRANSMISSION_TOWER,
    "TOWER": aob.TELECOM_TOWER,
    "ANTENNA": aob.TELECOM_TOWER,
    "POLE": aob.MAST,
    "STACK": aob.CHIMNEY,
    "COOLING_TOWER": aob.CHIMNEY,
}
_SKIP = {"AREA1"}  # o polígono da própria Área 1, não é obstáculo


class DfsError(RuntimeError):
    pass


def dfs_type(raw: str | None) -> int | None:
    t = (raw or "").strip().upper()
    if t in _SKIP:
        return None
    return _TYPES.get(t, aob.GENERIC)


def _height_m(el) -> float | None:
    if el is None or el.text is None or not el.text.strip():
        return None
    v = float(el.text)
    uom = (el.get("uom") or "FT").upper()
    return v * FT_TO_M if uom in ("FT", "[FT_I]") else v


def _stable_id(structure: str, part: str) -> int:
    """Id estável por parte: identificador da estrutura + designador da parte."""
    key = f"{structure}#{part}".encode()
    return DFS_ID_BASE + int.from_bytes(hashlib.sha1(key).digest()[:6], "big")


def parse_obstacles(source) -> tuple[list[dict], dict]:
    """Lê o XML em fluxo. Item por parte: id, name, lat, lon, type, height_m. Retorna (itens, contagens)."""
    items: list[dict] = []
    stats = {"structures": 0, "parts": 0, "skipped": 0, "no_height": 0, "no_position": 0}
    uuid = None
    for event, el in ET.iterparse(source, events=("end",)):
        if el.tag == f"{GML}identifier":
            uuid = (el.text or "").strip() or uuid
            continue
        if el.tag != f"{AIXM}VerticalStructureTimeSlice":
            continue
        stats["structures"] += 1
        name = (el.findtext(f"{AIXM}name") or "").strip()
        structure_type = el.findtext(f"{AIXM}type")
        structure_key = uuid or name
        if dfs_type(structure_type) is None:
            stats["skipped"] += 1
            el.clear()
            continue
        for idx, part in enumerate(el.findall(f"{AIXM}part/{AIXM}VerticalStructurePart")):
            stats["parts"] += 1
            typ = dfs_type(part.findtext(f"{AIXM}type") or structure_type)
            if typ is None:
                stats["skipped"] += 1
                continue
            h = _height_m(part.find(f"{AIXM}verticalExtent"))
            pos = part.find(f"{AIXM}horizontalProjection_location/{AIXM}ElevatedPoint/{GML}pos")
            if h is None:
                stats["no_height"] += 1
                continue
            if pos is None or not (pos.text or "").strip():
                stats["no_position"] += 1
                continue
            lat, lon = (float(v) for v in pos.text.split()[:2])
            designator = (part.findtext(f"{AIXM}designator") or "").strip() or str(idx)
            items.append({
                "id": _stable_id(structure_key, designator),
                "name": f"{name} {designator}".strip(),
                "lat": lat,
                "lon": lon,
                "type": typ,
                "height_m": h,
            })
        el.clear()
        uuid = None
    return items, stats


def release_of(meta: dict, amdt: int = 0) -> dict:
    """Release AIXM do dataset de obstáculos no AMDT pedido (0 = ciclo vigente)."""
    for a in meta.get("Amdts", []):
        if a.get("Amdt") != amdt:
            continue
        stack = [a.get("Metadata", {})]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if node.get("type") == "leaf" and node.get("name") == DATASET_NAME:
                    for r in node.get("releases", []):
                        if r.get("type") == "AIXM 5.1" and r.get("filename"):
                            ck = r.get("checksum") or {}
                            return {
                                "filename": r["filename"],
                                "sha512": (ck.get("value") or "").lower() if ck.get("type") == "sha512" else "",
                                "effective": a.get("AmdtNumeric"),
                            }
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    raise DfsError(f"{DATASET_NAME} (AIXM 5.1) ausente do AMDT {amdt} no metadado")


def file_url(amdt: int, filename: str) -> str:
    return f"{METADATA_URL}{amdt}/" + "/".join(urllib.parse.quote(p) for p in filename.split("/"))


def verify(data: bytes, sha512: str) -> None:
    if not sha512:
        raise DfsError("metadado sem SHA-512 para o arquivo de obstáculos")
    actual = hashlib.sha512(data).hexdigest()
    if actual != sha512:
        raise DfsError(f"SHA-512 não confere: declarado {sha512}, calculado {actual}")


def _get(url: str):
    import requests

    r = None
    for attempt in range(5):
        try:
            r = requests.get(url, timeout=300, headers=UA)
            if r.status_code < 500 and r.status_code != 429:
                break
        except requests.RequestException as e:
            print(f"dfs: tentativa {attempt + 1}: {e}")
        time.sleep(10 * (attempt + 1))
    if r is None or r.status_code != 200:
        raise DfsError(f"{url} HTTP {getattr(r, 'status_code', 'sem resposta')}")
    return r


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--download", required=True, help="caminho do XML conferido")
    a = p.parse_args(argv)
    try:
        meta = json.loads(_get(METADATA_URL).content)
        rel = release_of(meta, 0)
        data = _get(file_url(0, rel["filename"])).content
        verify(data, rel["sha512"])
    except DfsError as e:
        print(f"dfs: {e}")
        return 2
    with open(a.download, "wb") as f:
        f.write(data)
    print(f"dfs: {rel['filename']} ({rel['effective']}) {len(data)} bytes conferidos em {a.download}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
