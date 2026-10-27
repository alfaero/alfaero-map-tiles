#!/usr/bin/env python3
"""Monta um PNG de conferência a partir de um mbtiles: os tiles em volta de um ponto, num zoom,
sobre fundo xadrez (faixa transparente aparece como xadrez) e com a grade dos tiles em cinza.

Uso:
    python3 render_check.py <arquivo.mbtiles> <z> <lon> <lat> <saida.png> [raio_tiles=1] [lado_px=1536]
"""
import io
import math
import sqlite3
import sys

from PIL import Image, ImageDraw


def tile_xy(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    la = math.radians(lat)
    y = int((1.0 - math.log(math.tan(la) + 1 / math.cos(la)) / math.pi) / 2.0 * n)
    return x % n, y


def main():
    path, z, lon, lat, out = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    r = int(sys.argv[6]) if len(sys.argv) > 6 else 1
    side = int(sys.argv[7]) if len(sys.argv) > 7 else 1536
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cx, cy = tile_xy(lon, lat, z)
    n = 2 * r + 1
    canvas = Image.new("RGBA", (512 * n, 512 * n))
    d = ImageDraw.Draw(canvas)
    for i in range(0, 512 * n, 16):  # xadrez
        for j in range(0, 512 * n, 16):
            if (i // 16 + j // 16) % 2 == 0:
                d.rectangle([i, j, i + 15, j + 15], fill=(200, 200, 200, 255))
            else:
                d.rectangle([i, j, i + 15, j + 15], fill=(255, 255, 255, 255))
    found = 0
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            x, y = (cx + dx) % (2 ** z), cy + dy
            row = con.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                              (z, x, 2 ** z - 1 - y)).fetchone()
            if row:
                found += 1
                t = Image.open(io.BytesIO(row[0])).convert("RGBA")
                canvas.alpha_composite(t, ((dx + r) * 512, (dy + r) * 512))
    d = ImageDraw.Draw(canvas)
    for k in range(1, n):
        d.line([(k * 512, 0), (k * 512, 512 * n)], fill=(120, 120, 120, 255), width=1)
        d.line([(0, k * 512), (512 * n, k * 512)], fill=(120, 120, 120, 255), width=1)
    canvas = canvas.convert("RGB")
    if canvas.width > side:
        canvas = canvas.resize((side, side), Image.LANCZOS)
    canvas.save(out)
    print(f"{out}: z{z} centro {cx}/{cy} (xyz), {found} de {n * n} tiles")


if __name__ == "__main__":
    main()
