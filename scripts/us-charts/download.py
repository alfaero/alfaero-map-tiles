#!/usr/bin/env python3
"""Baixa os GeoTIFF (zip) de uma edição das cartas raster dos EUA da FAA (aeronav).

Uso:
    python download.py <MM-DD-AAAA> <pasta_destino> [--only sec|enr_l|enr_h|enr_p] [--names A,B]

- As URLs seguem o padrão de aeronav.faa.gov (que não bloqueia bots); a página
  faa.gov/.../digital_products responde 403 sem User-Agent de navegador, por isso
  a lista das 53 Sectionals fica fixa aqui (mudou pela última vez quando a FAA
  criou/extinguiu uma carta; conferir a página a cada edição).
- Cada arquivo é conferido contra o Content-Length; arquivo já baixado com o
  mesmo tamanho é pulado (o script pode ser repetido).
"""
import argparse
import os
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (alfaero-us-charts)"}

SECTIONALS = [
    "Albuquerque", "Anchorage", "Atlanta", "Bethel", "Billings", "Brownsville",
    "Cape_Lisburne", "Charlotte", "Cheyenne", "Chicago", "Cincinnati", "Cold_Bay",
    "Dallas-Ft_Worth", "Dawson", "Denver", "Detroit", "Dutch_Harbor", "El_Paso",
    "Fairbanks", "Great_Falls", "Green_Bay", "Halifax", "Hawaiian_Islands", "Houston",
    "Jacksonville", "Juneau", "Kansas_City", "Ketchikan", "Klamath_Falls", "Kodiak",
    "Lake_Huron", "Las_Vegas", "Los_Angeles", "McGrath", "Memphis", "Miami",
    "Montreal", "New_Orleans", "New_York", "Nome", "Omaha", "Phoenix", "Point_Barrow",
    "St_Louis", "Salt_Lake_City", "San_Antonio", "San_Francisco", "Seattle", "Seward",
    "Twin_Cities", "Washington", "Western_Aleutian_Islands", "Wichita",
]


def urls(edition, only=None, names=None):
    out = []
    if only in (None, "sec"):
        for n in SECTIONALS:
            out.append(f"https://aeronav.faa.gov/visual/{edition}/sectional-files/{n}.zip")
    if only in (None, "enr_l"):
        out += [f"https://aeronav.faa.gov/enroute/{edition}/enr_l{i:02d}.zip" for i in range(1, 37)]
    if only in (None, "enr_h"):
        out += [f"https://aeronav.faa.gov/enroute/{edition}/enr_h{i:02d}.zip" for i in range(1, 13)]
    if only in (None, "enr_p"):
        out += [f"https://aeronav.faa.gov/enroute/{edition}/enr_p{i:02d}.zip" for i in range(1, 3)]
    if names:
        out = [u for u in out if u.rsplit("/", 1)[1][:-4] in names]
    return out


def fetch(url, dest_dir, retries=4):
    name = url.rsplit("/", 1)[1]
    dest = os.path.join(dest_dir, name)
    for attempt in range(retries):
        try:
            head = urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=60)
            size = int(head.headers["Content-Length"])
            if os.path.exists(dest) and os.path.getsize(dest) == size:
                return name, size, "já baixado"
            t = time.time()
            tmp = dest + ".part"
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r, open(tmp, "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            got = os.path.getsize(tmp)
            if got != size:
                raise IOError(f"tamanho {got} != Content-Length {size}")
            os.replace(tmp, dest)
            return name, size, f"{size / 1e6 / max(time.time() - t, 0.01):.1f} MB/s"
        except Exception as e:  # rede instável: tenta de novo
            err = e
            time.sleep(5 * (attempt + 1))
    raise SystemExit(f"FALHA {url}: {err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", help="MM-DD-AAAA, ex.: 10-29-2026")
    ap.add_argument("dest")
    ap.add_argument("--only", choices=["sec", "enr_l", "enr_h", "enr_p"])
    ap.add_argument("--names", help="lista separada por vírgula (Hawaiian_Islands,enr_l06)")
    a = ap.parse_args()
    os.makedirs(a.dest, exist_ok=True)
    names = set(a.names.split(",")) if a.names else None
    lst = urls(a.edition, a.only, names)
    total = 0
    for u in lst:
        n, s, info = fetch(u, a.dest)
        total += s
        print(f"{n}\t{s}\t{info}", flush=True)
    print(f"OK {len(lst)} arquivos, {total / 1e9:.2f} GB")


if __name__ == "__main__":
    sys.exit(main())
