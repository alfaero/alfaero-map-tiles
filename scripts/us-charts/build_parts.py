#!/usr/bin/env python3
"""Reprojeta cada carta (recortada pelo neatline) e gera os tiles dela com gdal2tiles.

Roda dentro da imagem alfaero-us-charts, com:
    /dl      zips da FAA (somente leitura)
    /work    volume Docker (tiles e reprojeções; NÃO usar pasta montada do Windows, é 2,5x mais lento)

Uso:
    python3 build_parts.py --neatlines /scripts/neatlines.geojson --series sec --zoom 1-11 \
        --quality 75 [--charts "Hawaiian Islands SEC,Honolulu Inset SEC"] [--keep-warp]

Para cada feição do GeoJSON (uma por TIF) e cada parte do polígono (duas quando cruza ±180):
  1. Sectional: gdal_translate -expand rgba para VRT ANTES de reprojetar (a paleta reprojetada
     com bilinear mistura índices e estraga as cores). ENR: RGB direto, alfa criado com -dstalpha.
  2. gdalwarp para EPSG:3857 com -cutline da parte (em EPSG:4326), -te calculado da própria parte
     (evita a extensão do mundo inteiro quando a carta cruza o antimeridiano) e -tr fixo:
     resolução da fonte / cos(latitude mais próxima do equador na parte), o que não perde detalhe.
  3. gdal2tiles 512 px WebP (TMS) em /work/parts/<serie>/<ordem>_<carta>_p<i>/.
  4. Apaga a reprojeção (só fica o tile).
Grava /work/parts/<serie>/parts.json com a ordem de prioridade para a junção.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import time

from osgeo import gdal, osr

gdal.UseExceptions()
R = 6378137.0


def merc(lon, lat):
    lat = max(min(lat, 85.0511), -85.0511)
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def run(cmd):
    t = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"ERRO {' '.join(cmd[:3])}...\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")
    return time.time() - t


def slug(s):
    return "".join(c if c.isalnum() else "_" for c in s).strip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--neatlines", required=True)
    ap.add_argument("--series", required=True, choices=["sec", "enr_l", "enr_h", "enr_p"])
    ap.add_argument("--zoom", required=True)
    ap.add_argument("--quality", type=int, default=75)
    ap.add_argument("--charts", default="")
    ap.add_argument("--dl", default="/dl")
    ap.add_argument("--work", default="/work")
    ap.add_argument("--processes", type=int, default=16)
    ap.add_argument("--keep-warp", action="store_true")
    ap.add_argument("--resume", action="store_true", help="pula cartas cujas partes já estão no parts.json")
    ap.add_argument("--tmp", default=None, help="pasta das reprojeções (padrão <work>/tmp; use um tmpfs)")
    a = ap.parse_args()

    feats = [f for f in json.load(open(a.neatlines))["features"] if f["properties"]["series"] == a.series]
    if a.charts:
        want = set(a.charts.split(","))
        feats = [f for f in feats if f["properties"]["chart"] in want]
    # ordem de pintura: carta-mãe (priority 0) antes, inset (1) por cima; depois por nome
    feats.sort(key=lambda f: (f["properties"]["priority"], f["properties"]["chart"]))

    pdir = os.path.join(a.work, "parts", a.series)
    # reprojeções temporárias: num tmpfs (docker run --tmpfs /work/tmp:size=6g). No volume, cada
    # reprojeção apagada deixa blocos novos no disco virtual do Docker (vhdx), que não devolve o
    # espaço ao C: (medido em 21/10/2026: +4,4 GB no C: para 1,3 GB de tiles).
    tmp = a.tmp or os.path.join(a.work, "tmp")
    os.makedirs(pdir, exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    manifest_path = os.path.join(pdir, "parts.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}

    for f in feats:
        p = f["properties"]
        if a.resume and any(v["chart"] == p["chart"] for v in manifest.values()):
            print(f"{p['chart']}	já pronta (--resume)", flush=True)
            continue
        src = f"/vsizip/{a.dl}/{p['zip']}/{p['tif']}"
        ds = gdal.Open(src)
        gt = ds.GetGeoTransform()
        # as ENR vêm com geotransform girado (carta impressa de lado): resolução = módulo do vetor do pixel
        res_src = max(math.hypot(gt[1], gt[4]), math.hypot(gt[2], gt[5]))
        if p["series"] == "sec":
            vrt = os.path.join(tmp, slug(p["chart"]) + ".vrt")
            gdal.Translate(vrt, ds, format="VRT", rgbExpand="rgba")
            warp_src, alpha = vrt, []
        else:
            warp_src, alpha = src, ["-dstalpha"]
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for i, poly in enumerate(polys):
            ring = poly[0]
            cut = os.path.join(tmp, f"{slug(p['chart'])}_p{i}.geojson")
            json.dump({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
                       "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]},
                      open(cut, "w"))
            xs, ys = zip(*[merc(lon, lat) for lon, lat in ring])
            lat_eq = min(abs(lat) for _, lat in ring)
            if min(lat for _, lat in ring) < 0 < max(lat for _, lat in ring):
                lat_eq = 0.0
            tr = res_src / math.cos(math.radians(lat_eq))
            te = [min(xs), min(ys), max(xs), max(ys)]
            warp = os.path.join(tmp, f"{slug(p['chart'])}_p{i}.tif")
            t_w = run(["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:3857", "-r", "bilinear",
                       "-cutline", cut, "-te", *map(str, te), "-tr", str(tr), str(tr), *alpha,
                       "-multi", "-wo", "NUM_THREADS=ALL_CPUS", "-wm", "2048",
                       "-co", "TILED=YES", "-co", "COMPRESS=ZSTD", "-co", "PREDICTOR=2", "-co", "BIGTIFF=IF_SAFER",
                       warp_src, warp])
            part = f"{p['priority']}_{slug(p['chart'])}_p{i}"
            out = os.path.join(pdir, part)
            if os.path.exists(out):
                shutil.rmtree(out)
            t_t = run(["gdal2tiles.py", "-q", "--tilesize=512", "--tiledriver=WEBP", f"--webp-quality={a.quality}",
                       "-r", "bilinear", "-x", "-w", "none", f"--processes={a.processes}", "-z", a.zoom, warp, out])
            n = sum(len(fs) for _, _, fs in os.walk(out))
            print(f"{part}\twarp {t_w:.0f}s\ttiles {t_t:.0f}s\t{n} tiles\ttr {tr:.1f} m", flush=True)
            manifest[part] = {"chart": p["chart"], "priority": p["priority"], "part": i}
            if not a.keep_warp:
                os.remove(warp)
        if p["series"] == "sec":
            os.remove(vrt)
        json.dump(manifest, open(manifest_path, "w"), indent=1)


if __name__ == "__main__":
    main()
