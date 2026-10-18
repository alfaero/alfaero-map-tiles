"""Aerogeradores da ANEEL SIGEL pela API REST do ArcGIS (spec 006, item 1).

Página no máximo do serviço, retry com espera dobrando em conexão, 429 e 5xx,
teto de páginas e conferência da contagem do servidor contra o que veio.
"""
from __future__ import annotations

import math
import time

SERVICE = "https://sigel.aneel.gov.br/arcgis/rest/services/PORTAL/Parques_E%C3%B3licos/MapServer"
TURBINES = 0
INTERFERENCE = 1  # região de interferência: DIRECAO_PREDO por parque


class AneelError(RuntimeError):
    pass


def _get(session, url, params, attempts, sleep):
    delay = 2.0
    last = ""
    for i in range(attempts):
        if i:
            sleep(delay)
            delay *= 2
        try:
            r = session.get(url, params=params, timeout=120)
        except Exception as e:  # conexão caiu ou estourou o tempo
            last = repr(e)
            continue
        if r.status_code == 200:
            j = r.json()
            if "error" in j:  # o ArcGIS devolve erro com HTTP 200
                last = str(j["error"])
                continue
            return j
        last = f"HTTP {r.status_code}"
        if r.status_code not in (425, 429) and r.status_code < 500:
            break
    raise AneelError(f"{url}: {last}")


def _query_all(session, layer, fields, geometry, attempts, sleep, max_pages=None):
    url = f"{SERVICE}/{layer}/query"
    meta = _get(session, f"{SERVICE}/{layer}", {"f": "json"}, attempts, sleep)
    page = int(meta.get("maxRecordCount") or 1000)
    total = _get(session, url, {"where": "1=1", "returnCountOnly": "true", "f": "json"}, attempts, sleep)["count"]
    cap = max_pages if max_pages is not None else math.ceil(total / page) + 5
    out = []
    for n in range(cap):
        j = _get(session, url, {
            "where": "1=1",
            "outFields": fields,
            "returnGeometry": "true" if geometry else "false",
            "outSR": 4326,
            "orderByFields": "OBJECTID",
            "resultOffset": n * page,
            "resultRecordCount": page,
            "f": "json",
        }, attempts, sleep)
        feats = j.get("features", [])
        out.extend(feats)
        if len(feats) < page and not j.get("exceededTransferLimit"):
            break
    else:
        raise AneelError(f"camada {layer}: teto de {cap} páginas atingido")
    if len(out) != total:
        raise AneelError(f"camada {layer}: servidor diz {total}, vieram {len(out)}")
    return out


def fetch_turbines(session, attempts=5, sleep=time.sleep, max_pages=None) -> list[dict]:
    """Lista no formato de `merge_aneel`: id, lat, lon, height_m, status, heading_deg."""
    headings = {}
    for f in _query_all(session, INTERFERENCE, "NOME_EOL,DIRECAO_PREDO", False, attempts, sleep, max_pages):
        a = f["attributes"]
        if a.get("NOME_EOL") and a.get("DIRECAO_PREDO") is not None:
            headings[a["NOME_EOL"].strip().lower()] = float(a["DIRECAO_PREDO"])
    out = []
    for f in _query_all(session, TURBINES, "OBJECTID,ALT_TOTAL,OPERACAO,NOME_EOL", True, attempts, sleep, max_pages):
        a, g = f["attributes"], f.get("geometry")
        if not g:
            continue
        h = a.get("ALT_TOTAL")
        out.append({
            "id": a["OBJECTID"],
            "lat": g["y"],
            "lon": g["x"],
            "height_m": float(h) if h and h > 0 else None,
            "status": a.get("OPERACAO"),
            "heading_deg": headings.get((a.get("NOME_EOL") or "").strip().lower()),
        })
    return out
