# Sprites custom Alfaero

SVGs ficam aqui. Gerar PNG + JSON com [spritezero-cli](https://github.com/mapbox/spritezero-cli):

```bash
npm install -g @mapbox/spritezero-cli
spritezero alfaero ./svgs/
spritezero --retina alfaero@2x ./svgs/
```

Saída (`alfaero.png`, `alfaero.json`, `alfaero@2x.png`, `alfaero@2x.json`) sobe pro R2 via:

```bash
rclone copy . alfaero:alfaero-map-tiles/sprites/alfaero/ \
  --include "alfaero*" \
  --header-upload "Cache-Control: public, max-age=2592000"
```

## Ícones planejados

- airport (icon-airport.svg)
- helipad (icon-helipad.svg)
- navaid-vor, navaid-ndb, navaid-dme
- waypoint (icon-waypoint.svg)
- weather-station (icon-metar.svg)
- alfaero-logo (icon-alfaero.svg)
