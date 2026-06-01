# Fonts (glyphs PBF)

MapLibre precisa de glyphs no formato PBF (256 caracteres por arquivo, range `0-255`, `256-511`, etc.).

## Gerar com fontnik

```bash
npm install -g @mapbox/glyph-pbf-composite fontnik
node -e "
  const fontnik = require('fontnik');
  const fs = require('fs');
  const font = fs.readFileSync('NotoSans-Regular.ttf');
  for (let s = 0; s < 65536; s += 256) {
    fontnik.range({font, start: s, end: s + 255}, (err, data) => {
      if (!err) fs.writeFileSync(\`Noto Sans Regular/\${s}-\${s+255}.pbf\`, data);
    });
  }
"
```

Mais simples: baixar bundle pré-gerado do [openmaptiles/fonts](https://github.com/openmaptiles/fonts).

```bash
git clone --depth 1 https://github.com/openmaptiles/fonts.git /tmp/omt-fonts
cd /tmp/omt-fonts
node generate.js
# saídas em _output/
rclone copy _output/ alfaero:alfaero-map-tiles/fonts/ \
  --header-upload "Cache-Control: public, max-age=2592000"
```

## Stacks usados nos styles Alfaero

- `Noto Sans Regular`
- `Noto Sans Bold`
- `Noto Sans Italic`

Cobertura suficiente pra portugues, inglês, latin extended.

## Tamanho

~150 MB total no R2. Imutável, cache 1 ano.
