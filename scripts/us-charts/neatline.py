#!/usr/bin/env python3
"""Detecta a área útil (dentro do neatline) de cada GeoTIFF da FAA e grava o recorte.

Roda dentro da imagem alfaero-us-charts (GDAL + OpenCV + Pillow).

Uso:
    python3 neatline.py <saida.geojson> <pasta_png_conferencia> <zip>[::<tif>] ...

Métodos (só com o próprio raster e o georreferenciamento da FAA; nada de recorte de terceiros):

- "sec_flood" (Sectional e insets). O colar da Sectional é papel branco com textos; o mapa é
  sempre colorido (água azul, relevo em tons) e fechado por uma linha preta contínua (neatline).
  1. Máscara "branco" = índice da paleta com R, G e B >= 245, reduzida 2x pelo mínimo (um pixel
     escuro do neatline continua escuro, a linha não abre buraco).
  2. Preenche (4-conectado) o branco a partir da borda da imagem: isso é o colar. Onde o mapa
     chega perto da borda da imagem sem neatline (ex.: leste da Anchorage, com neve branca), uma
     linha-barreira a 2 px da borda impede o preenchimento de correr pela margem e entrar no mapa.
  3. O resto (mapa + neatline + ilhas de texto do colar) passa por abertura morfológica 7x7, que
     solta as marcas de minuto do neatline e textos encostados; fica o maior componente.
  4. Faixas, réguas, textos e caixas do colar encostados no neatline sobrevivem à abertura 7x7 (em
     umas 15 das 57 cartas). Não há regra geométrica segura para separá-los das abas legítimas do
     mapa (a Halifax tem uma aba para o sul; a Kodiak e a Los Angeles têm inset pendurado). Então:
     o que a abertura 61x61 solta do contorno vira candidata, com recorte salvo para conferência
     (CROPS=1), e toda candidata sai, menos as marcadas "manter" no sec_ajustes.csv (carta + um
     ponto da saliência em pixel + motivo: abas legítimas e cantos da carta girada). O ponto acha a
     saliência de novo em outra edição; se não achar, para com erro. A mesma tabela tem retângulos
     "incluir" (pixel) para onde o mapa vai até a borda da imagem com neve branca e o preenchimento
     ainda entra (Seward, Anchorage), e "excluir" para caixas grandes do colar (índice, título,
     avisos) encostadas no neatline, que a abertura 61x61 não solta (Kodiak, Juneau, Cheyenne,
     Twin Cities, Seattle). Cada linha tem a medida das bordas no motivo, para revisar se a FAA
     mudar o leiaute.
  5. O contorno externo desse componente (borda de fora do neatline) é simplificado (0,75 px),
     densificado a cada 32 px no espaço de pixels e convertido para lon/lat pelo
     georreferenciamento do TIF. O neatline fica dentro do recorte: cartas vizinhas se sobrepõem
     pela largura da linha, o que evita fresta transparente na emenda.
- "enr_flood" (ENR L/H/P e insets). O fundo do mapa da ENR também é branco, então a barreira é a
  linha escura (min(R,G,B) < 110), reduzida 2x pelo máximo. Preenche (4-conectado) a partir da borda
  tudo que não é linha escura: colar, painéis de título/legenda e "intentionally left blank" ficam
  preenchidos; o mapa fica fechado pela moldura. Abertura 7x7, maior componente, erosão de 12 px
  (tira a moldura, que riscaria a carta vizinha na sobreposição). Funciona com moldura inclinada e
  com os insets que têm moldura própria (Wilmington-Bimini na L23, Boston-Yarmouth na L34): eles
  saem do mapa principal e entram pelo próprio TIF (ENR_L23_WILM_INSET, ENR_L34_BOST_INSET) por cima.
  Caixas coladas na moldura que não são mapa georreferenciado (a "Guam Area" e a tabela da P01)
  saem pelo enr_exclusions.csv (retângulos em pixel, com a medida das bordas anotada); o script
  confere que a borda continua lá e para com erro se a FAA mudar o leiaute.

Antimeridiano: a longitude é desembrulhada em torno do meridiano central da carta; se passar de
±180, o polígono é cortado em ±180 e vira MultiPolygon com as duas partes em [-180, 180].

Saída: GeoJSON (EPSG:4326) com uma feição por TIF e as propriedades usadas pelo warp/junção.
"""
import io
import json
import math
import os
import sys
import zipfile

import cv2
import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
gdal.SetConfigOption("CPL_LOG", "/dev/null")
ogr.UseExceptions()

INSETS = ("Honolulu Inset", "Mariana Islands Inset", "Samoan Islands Inset", "ENR_P01_GUA", "ENR_L23_WILM_INSET", "ENR_L34_BOST_INSET")
EXCLUSIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enr_exclusions.csv")


def series_of(tif):
    t = os.path.basename(tif).upper()
    if t.startswith("ENR_L"):
        return "enr_l"
    if t.startswith("ENR_H"):
        return "enr_h"
    if t.startswith("ENR_P"):
        return "enr_p"
    return "sec"


def read_rgb_sec(ds):
    """Sectional: banda única com paleta -> máscara de branco via LUT."""
    b = ds.GetRasterBand(1)
    ct = b.GetColorTable()
    lut_white = np.zeros(256, np.uint8)
    for i in range(ct.GetCount()):
        r, g, bb, _ = ct.GetColorEntry(i)
        if min(r, g, bb) >= 245:
            lut_white[i] = 1
    idx = b.ReadAsArray()
    return lut_white[idx]


def min_reduce2(m):
    h, w = m.shape
    h2, w2 = h // 2 * 2, w // 2 * 2
    m = m[:h2, :w2]
    return np.minimum(np.minimum(m[0::2, 0::2], m[1::2, 0::2]), np.minimum(m[0::2, 1::2], m[1::2, 1::2]))


def polygon_sec(ds):
    white = min_reduce2(read_rgb_sec(ds))  # 1 = branco
    h, w = white.shape
    # Em várias cartas o mapa vai até perto da borda da imagem, sem neatline, com só uma faixa branca
    # de poucos pixels (leste da Anchorage, com neve branca encostada). Para o preenchimento não
    # correr por essa faixa e entrar no mapa, em todo trecho de 100 px (meia resolução) da borda com
    # tinta de mapa (>= 30% não branco; texto de colar fica bem abaixo) entre 4 e 60 px da borda,
    # traça uma linha-barreira a 2 px da borda; lacunas de até 20 trechos entre trechos com tinta
    # também, e mais 3 trechos em cada ponta (neve branca encostada na borda não tem tinta e
    # deixaria brecha).
    seg = 100
    inked = {}
    for side in ("top", "bottom", "left", "right"):
        n_ = w if side in ("top", "bottom") else h
        lst = []
        for a0 in range(0, n_, seg):
            b0 = min(a0 + seg, n_)
            band = {"top": white[4:60, a0:b0], "bottom": white[h - 60:h - 4, a0:b0],
                    "left": white[a0:b0, 4:60], "right": white[a0:b0, w - 60:w - 4]}[side]
            lst.append(1.0 - float(band.mean()) >= 0.30)
        # fecha lacunas de até 20 trechos entre trechos com tinta: neve branca encostada na borda
        idx = [k for k, v in enumerate(lst) if v]
        for k0, k1 in zip(idx, idx[1:]):
            if 1 < k1 - k0 <= 21:
                for k in range(k0 + 1, k1):
                    lst[k] = True
        # estica cada trecho de barreira 3 trechos para cada lado (neve sem tinta na ponta)
        base = list(lst)
        for k, v in enumerate(base):
            if v:
                for j in range(max(0, k - 3), min(len(lst), k + 4)):
                    lst[j] = True
        inked[side] = lst
    for side, lst in inked.items():
        for k, a0 in enumerate(range(0, len(lst) * seg, seg)):
            if not lst[k]:
                continue
            b0 = a0 + seg
            if side == "top":
                white[2, a0:b0] = 0
            elif side == "bottom":
                white[h - 3, a0:b0] = 0
            elif side == "left":
                white[a0:b0, 2] = 0
            else:
                white[a0:b0, w - 3] = 0
    # moldura branca de 1 px para o preenchimento começar de fora
    pad = np.ones((h + 2, w + 2), np.uint8)
    pad[1:-1, 1:-1] = white
    mask = np.zeros((h + 4, w + 4), np.uint8)
    # floodFill sobre a imagem binária: pinta de 2 o branco ligado à borda (4-conectado)
    cv2.floodFill(pad, mask, (0, 0), 2, loDiff=0, upDiff=0, flags=4)
    inside = (pad[1:-1, 1:-1] != 2).astype(np.uint8)
    del pad, mask, white
    for x0, y0, x1, y1 in sec_ajustes_for(ds, "incluir"):
        inside[y0 // 2:y1 // 2, x0 // 2:x1 // 2] = 1
    for x0, y0, x1, y1 in sec_ajustes_for(ds, "excluir"):
        inside[y0 // 2:(y1 + 1) // 2, x0 // 2:(x1 + 1) // 2] = 0
    if inside.mean() > 0.97:
        raise RuntimeError(f"{ds.GetDescription()}: preenchimento do colar falhou (área {inside.mean():.3f}); revisar barreiras")
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    inside = cv2.morphologyEx(inside, cv2.MORPH_OPEN, k)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inside, connectivity=8)
    if n < 2:
        raise RuntimeError("nenhuma região de mapa")
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    comp = (lab == big).astype(np.uint8)
    del lab, inside
    # saliências: o que a abertura 61x61 solta do contorno (textos, réguas e caixas do colar
    # encostados no neatline, mas também cantos e abas legítimas). Viram candidatas; só sai o que
    # está marcado "manter" no sec_ajustes.csv (conferido a olho nos recortes de check/).
    o61 = cv2.morphologyEx(comp, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (61, 61)))
    resid = comp & (1 - o61)
    del o61
    nr, labr, str_, cen = cv2.connectedComponentsWithStats(resid, connectivity=8)
    cands = []
    for i in range(1, nr):
        if str_[i, cv2.CC_STAT_AREA] >= 300:
            x, y, w_, h_ = (int(v) for v in str_[i, :4])
            cands.append({"id": i, "x": int(cen[i][0] * 2), "y": int(cen[i][1] * 2), "bbox": [x * 2, y * 2, (x + w_) * 2, (y + h_) * 2],
                          "area_px": int(str_[i, cv2.CC_STAT_AREA] * 4)})
    keep_labels = set()
    for kx, ky in sec_ajustes_for(ds, "manter"):
        kx2, ky2 = kx // 2, ky // 2
        win = labr[max(ky2 - 40, 0):ky2 + 41, max(kx2 - 40, 0):kx2 + 41]
        vals = win[win > 0]
        if len(vals) == 0:
            raise RuntimeError(f"{ds.GetDescription()}: 'manter' em ({kx},{ky}) não acha saliência; revisar sec_ajustes.csv")
        keep_labels.add(int(np.bincount(vals).argmax()))
    removed = []
    for c in cands:
        if c["id"] in keep_labels:
            c["kept"] = True
            continue
        comp[labr == c["id"]] = 0
        removed.append((c["x"], c["y"]))
    if removed:
        n3, lab3, st3, _ = cv2.connectedComponentsWithStats(comp, connectivity=8)
        comp = (lab3 == 1 + int(np.argmax(st3[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
        del lab3
    del labr, resid
    polygon_sec.last = {"cands": cands, "comp": comp}
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    area = cv2.contourArea(c)
    hull = cv2.contourArea(cv2.convexHull(c))
    ap = cv2.approxPolyDP(c, 0.75, True).reshape(-1, 2).astype(np.float64)
    ap = (ap + 0.5) * 2.0  # volta à resolução cheia (centro do pixel reduzido)
    stats_out = {
        "protrusions_removed": len(removed),
        "protrusion_candidates": len(cands),
        "area_frac": round(area * 4 / (ds.RasterXSize * ds.RasterYSize), 4),
        "hull_ratio": round(area / hull, 4),
        "vertices": int(len(ap)),
    }
    return ap, stats_out


def max_reduce2(m):
    h, w = m.shape
    m = m[:h // 2 * 2, :w // 2 * 2]
    return np.maximum(np.maximum(m[0::2, 0::2], m[1::2, 0::2]), np.maximum(m[0::2, 1::2], m[1::2, 1::2]))


def polygon_enr(ds):
    """ENR: preenche a partir da borda tudo que não é linha escura; o que sobra fechado pela moldura é o mapa."""
    bands = [ds.GetRasterBand(i + 1).ReadAsArray() for i in range(3)]
    lum = np.minimum(np.minimum(bands[0], bands[1]), bands[2])
    del bands
    dark = max_reduce2((lum < 110).astype(np.uint8))  # reduzido 2x pelo máximo: linha fina continua fechada
    del lum
    h, w = dark.shape
    pad = np.zeros((h + 2, w + 2), np.uint8)
    pad[1:-1, 1:-1] = dark
    mask = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(pad, mask, (0, 0), 2, loDiff=0, upDiff=0, flags=4)
    inside = (pad[1:-1, 1:-1] != 2).astype(np.uint8)
    del pad, mask
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    inside = cv2.morphologyEx(inside, cv2.MORPH_OPEN, k)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inside, connectivity=8)
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    comp = (lab == big).astype(np.uint8)
    del lab, inside
    # tira a própria moldura (cerca de 8 px): em sobreposição com a carta vizinha ela riscaria o mapa
    comp = cv2.erode(comp, cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13)))
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    area = cv2.contourArea(c)
    hull = cv2.contourArea(cv2.convexHull(c))
    ap = (cv2.approxPolyDP(c, 0.75, True).reshape(-1, 2).astype(np.float64) + 0.5) * 2.0
    ex = exclusions_for(ds, dark)
    if ex:
        ap = subtract_rects(ap, ex)
    x0, y0 = ap.min(axis=0)
    x1, y1 = ap.max(axis=0)
    margins = {"left": round(float(x0)), "top": round(float(y0)), "right": round(float(ds.RasterXSize - x1)),
               "bottom": round(float(ds.RasterYSize - y1))}
    return ap, {"margins_px": margins, "hull_ratio": round(area / hull, 4), "vertices": int(len(ap)),
                "area_frac": round(float(cv2.contourArea(ap.astype(np.float32)) / (ds.RasterXSize * ds.RasterYSize)), 4)}


def exclusions_for(ds, dark2):
    """Retângulos a excluir (pixel cheio) do enr_exclusions.csv, conferindo as bordas internas."""
    import csv
    tif = os.path.basename(ds.GetDescription())
    out = []
    if not os.path.exists(EXCLUSIONS):
        return out
    for r in csv.DictReader(open(EXCLUSIONS, encoding="utf-8")):
        if r["tif"] != tif:
            continue
        x0, y0, x1, y1 = (int(r[k]) for k in ("x0", "y0", "x1", "y1"))
        # confere: linha escura logo dentro da borda de cima (y0) e da direita (x1) da caixa
        ya, xa = (y0 + 5) // 2, (x1 - 5) // 2
        top = dark2[max(ya - 6, 0):ya + 6, x0 // 2 + 20:x1 // 2 - 20].mean(axis=1).max()
        right = dark2[y0 // 2 + 20:y1 // 2 - 20, max(xa - 6, 0):xa + 6].mean(axis=0).max()
        if top < 0.5 or right < 0.5:
            raise RuntimeError(f"{tif}: borda da exclusão não encontrada (cima {top:.2f}, direita {right:.2f}); revisar enr_exclusions.csv")
        out.append((x0, y0, x1, y1))
    return out


SEC_AJUSTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sec_ajustes.csv")


def sec_ajustes_for(ds, tipo):
    import csv
    tif = os.path.basename(ds.GetDescription())
    if not os.path.exists(SEC_AJUSTES):
        return []
    out = []
    for r in csv.DictReader(open(SEC_AJUSTES, encoding="utf-8")):
        if r["tif"] == tif and r["tipo"] == tipo:
            out.append(tuple(int(r[k]) for k in (("x", "y") if tipo == "manter" else ("x", "y", "x1", "y1"))))
    return out


def save_crops(ds, crop_dir, name):
    """Recorte de cada saliência candidata, com o contorno final em vermelho e a id no nome."""
    info = getattr(polygon_sec, "last", None)
    if not info:
        return
    os.makedirs(crop_dir, exist_ok=True)
    comp = info["comp"]
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    for c in info["cands"]:
        x0, y0, x1, y1 = c["bbox"]
        pad = 300
        X0, Y0 = max(x0 - pad, 0), max(y0 - pad, 0)
        X1, Y1 = min(x1 + pad, ds.RasterXSize), min(y1 + pad, ds.RasterYSize)
        f = max(1, int(max(X1 - X0, Y1 - Y0) / 500) + 1)
        arr = gdal.Translate("", ds, format="MEM", srcWin=[X0, Y0, X1 - X0, Y1 - Y0], width=(X1 - X0) // f,
                             height=(Y1 - Y0) // f, rgbExpand="rgb", resampleAlg="average").ReadAsArray()
        img = np.ascontiguousarray(np.transpose(arr, (1, 2, 0))[:, :, ::-1])
        for cc in cs:
            pts = ((cc.reshape(-1, 2) * 2 - [X0, Y0]) / f).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], True, (0, 0, 255), 1)
        cx, cy = (c["x"] - X0) // f, (c["y"] - Y0) // f
        cv2.circle(img, (cx, cy), 6, (255, 0, 255), 2)
        cv2.imwrite(os.path.join(crop_dir, f"{name}__{c['x']}_{c['y']}.png"), img)


def subtract_rects(ring, rects):
    def poly(pts):
        rr = ogr.Geometry(ogr.wkbLinearRing)
        for x, y in list(pts) + [pts[0]]:
            rr.AddPoint_2D(float(x), float(y))
        g = ogr.Geometry(ogr.wkbPolygon)
        g.AddGeometry(rr)
        return g
    g = poly([tuple(p) for p in ring])
    for x0, y0, x1, y1 in rects:
        g = g.Difference(poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))
    if g.GetGeometryType() != ogr.wkbPolygon:
        raise RuntimeError("exclusão partiu o recorte em pedaços")
    r = g.GetGeometryRef(0)
    return np.array([[r.GetX(i), r.GetY(i)] for i in range(r.GetPointCount() - 1)], np.float64)


def densify(ring, step):
    out = []
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, int(math.ceil(d / step)))
        for j in range(k):
            t = j / k
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def to_lonlat(ds, ring_px):
    gt = ds.GetGeoTransform()
    src = osr.SpatialReference(wkt=ds.GetProjection())
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(src, dst)
    lon0 = src.GetProjParm(osr.SRS_PP_CENTRAL_MERIDIAN, 0.0)
    pts = []
    for px, py in ring_px:
        X = gt[0] + px * gt[1] + py * gt[2]
        Y = gt[3] + px * gt[4] + py * gt[5]
        lon, lat, _ = tr.TransformPoint(X, Y)
        lon = lon0 + ((lon - lon0 + 180.0) % 360.0) - 180.0  # desembrulha em torno do meridiano central
        pts.append((lon, lat))
    return pts, lon0


def split_antimeridian(pts):
    """Recebe anel com lon desembrulhada; devolve lista de anéis em [-180, 180]."""
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in pts + [pts[0]]:
        ring.AddPoint_2D(x, y)
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)
    if not poly.IsValid():
        poly = poly.MakeValid()
    parts = []
    for shift, (a, b) in ((0.0, (-180.0, 180.0)), (-360.0, (180.0, 540.0)), (360.0, (-540.0, -180.0))):
        box = ogr.CreateGeometryFromWkt(f"POLYGON(({a} -90,{b} -90,{b} 90,{a} 90,{a} -90))")
        inter = poly.Intersection(box)
        if inter is None or inter.IsEmpty() or inter.GetArea() < 1e-9:
            continue
        geoms = [inter] if inter.GetGeometryType() == ogr.wkbPolygon else [inter.GetGeometryRef(i) for i in range(inter.GetGeometryCount())]
        for g in geoms:
            if g.GetGeometryType() != ogr.wkbPolygon or g.GetArea() < 1e-9:
                continue
            r = g.GetGeometryRef(0)
            parts.append([[round(r.GetX(i) + shift, 7), round(r.GetY(i), 7)] for i in range(r.GetPointCount())])
    return parts


def lonlat_to_px(ds, pts):
    gt = ds.GetGeoTransform()
    inv = gdal.InvGeoTransform(gt)
    src = osr.SpatialReference(wkt=ds.GetProjection())
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ll = osr.SpatialReference()
    ll.ImportFromEPSG(4326)
    ll.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(ll, src)
    out = []
    for lon, lat in pts:
        X, Y, _ = tr.TransformPoint(lon, lat)
        out.append((inv[0] + X * inv[1] + Y * inv[2], inv[3] + X * inv[4] + Y * inv[5]))
    return out


def thumb(ds, rings_px, png, sec):
    f = 16
    w, h = ds.RasterXSize // f, ds.RasterYSize // f
    if sec:
        arr = gdal.Translate("", ds, format="MEM", width=w, height=h, rgbExpand="rgb", resampleAlg="average").ReadAsArray()
    else:
        arr = gdal.Translate("", ds, format="MEM", width=w, height=h, resampleAlg="average").ReadAsArray()[:3]
    img = np.ascontiguousarray(np.transpose(arr, (1, 2, 0))[:, :, ::-1])
    for ring_px in rings_px:
        pts = (np.array(ring_px) / f).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(img, [pts], True, (0, 0, 255), 2)
    cv2.imwrite(png, img)


def process(zip_path, tif):
    path = f"/vsizip/{zip_path}/{tif}"
    ds = gdal.Open(path)
    ser = series_of(tif)
    if ser == "sec":
        ring, st = polygon_sec(ds)
        method = "sec_flood"
    else:
        ring, st = polygon_enr(ds)
        method = "enr_flood"
    dens = densify([tuple(p) for p in ring], 32.0)
    pts, lon0 = to_lonlat(ds, dens)
    parts = split_antimeridian(pts)
    name = os.path.splitext(tif)[0]
    is_inset = any(name.startswith(i) for i in INSETS)
    props = {
        "chart": name,
        "zip": os.path.basename(zip_path),
        "tif": tif,
        "series": ser,
        "method": method,
        "priority": 1 if is_inset else 0,
        "lon0": lon0,
        "parts": len(parts),
        **st,
    }
    geom = {"type": "Polygon", "coordinates": [parts[0]]} if len(parts) == 1 else {
        "type": "MultiPolygon", "coordinates": [[p] for p in parts]}
    rings_px = [lonlat_to_px(ds, p) for p in parts]  # o recorte final, para a miniatura de conferência
    return {"type": "Feature", "properties": props, "geometry": geom}, ds, rings_px


def items_from_args(args):
    out = []
    for a in args:
        if "::" in a:
            z, t = a.split("::", 1)
            out.append((z, t))
        else:
            for n in zipfile.ZipFile(a).namelist():
                if n.lower().endswith(".tif"):
                    out.append((a, n))
    return out


def main():
    out_geojson, png_dir = sys.argv[1], sys.argv[2]
    os.makedirs(png_dir, exist_ok=True)
    feats = []
    if os.path.exists(out_geojson):  # acrescenta/atualiza
        feats = json.load(open(out_geojson))["features"]
    for z, t in items_from_args(sys.argv[3:]):
        f, ds, ring = process(z, t)
        feats = [x for x in feats if x["properties"]["tif"] != t] + [f]
        thumb(ds, ring, os.path.join(png_dir, f["properties"]["chart"].replace(" ", "_") + ".png"), f["properties"]["series"] == "sec")
        if os.environ.get("CROPS") and f["properties"]["series"] == "sec":
            save_crops(ds, os.path.join(png_dir, "crops"), f["properties"]["chart"].replace(" ", "_"))
        polygon_sec.last = None
        p = f["properties"]
        print(json.dumps({k: p[k] for k in p if k not in ("zip",)}, ensure_ascii=False), flush=True)
        json.dump({"type": "FeatureCollection", "features": sorted(feats, key=lambda x: x["properties"]["tif"])},
                  open(out_geojson, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
