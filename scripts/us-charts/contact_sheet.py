#!/usr/bin/env python3
"""Monta folhas de contato das miniaturas com o recorte (linha vermelha) para conferência visual.

Uso: python contact_sheet.py <pasta_png> <prefixo_saida> [filtro] [colunas] [largura]
"""
import glob
import os
import sys

from PIL import Image, ImageDraw

src, out = sys.argv[1], sys.argv[2]
flt = sys.argv[3] if len(sys.argv) > 3 else ""
cols = int(sys.argv[4]) if len(sys.argv) > 4 else 3
cw = int(sys.argv[5]) if len(sys.argv) > 5 else 620
files = sorted(f for f in glob.glob(os.path.join(src, "*.png")) if flt in os.path.basename(f) and not os.path.basename(f).startswith(("raw_", "crop_")))
per = cols * 4
for s in range(0, len(files), per):
    chunk = files[s:s + per]
    ims = []
    for f in chunk:
        im = Image.open(f).convert("RGB")
        im = im.resize((cw, int(im.height * cw / im.width)))
        ims.append((os.path.basename(f)[:-4], im))
    rows = [ims[i:i + cols] for i in range(0, len(ims), cols)]
    H = sum(max(i.height for _, i in r) + 22 for r in rows)
    sheet = Image.new("RGB", (cols * (cw + 8), H), "white")
    d = ImageDraw.Draw(sheet)
    y = 0
    for r in rows:
        for c, (n, im) in enumerate(r):
            d.text((c * (cw + 8) + 4, y + 4), n, fill="black")
            sheet.paste(im, (c * (cw + 8), y + 20))
        y += max(i.height for _, i in r) + 22
    sheet.save(f"{out}_{s // per + 1}.png")
    print(f"{out}_{s // per + 1}.png", len(chunk))
