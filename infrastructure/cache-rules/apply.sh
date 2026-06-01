#!/usr/bin/env bash
# Aplica cache rules do alfaero-map-tiles no zone alfaero.com.
#
# Por que script em vez de Terraform: Cloudflare permite apenas 1 ruleset por
# phase por zone. O zone alfaero.com já tem um ruleset http_request_cache_settings
# em uso (pra outros serviços). Terraform provider v4 não consegue gerenciar
# bem rulesets compartilhados — script garante idempotência mesclando.
#
# Pré-requisitos:
#   - CF_API_TOKEN com permissão Zone:Edit + Cache Rules:Edit
#   - jq, curl

set -euo pipefail

ZONE_ID="${CF_ZONE_ID_ALFAERO:-3f5853709d8cb2a7bbfbde625c307cd5}"
TILES_DOMAIN="${TILES_DOMAIN:-tiles.alfaero.com}"

if [[ -z "${CF_API_TOKEN:-}" ]]; then
    echo "ERROR: CF_API_TOKEN env var required" >&2
    exit 1
fi

# Localiza ruleset http_request_cache_settings do zone
RULESET_ID=$(curl -sS "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets" \
    -H "Authorization: Bearer $CF_API_TOKEN" | \
    jq -r '.result[] | select(.phase == "http_request_cache_settings" and .kind == "zone") | .id')

if [[ -z "$RULESET_ID" ]]; then
    echo "ERROR: no zone-level http_request_cache_settings ruleset found in $ZONE_ID" >&2
    exit 2
fi

echo "Ruleset: $RULESET_ID"

# Lê rules atuais
CURRENT=$(curl -sS "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/$RULESET_ID" \
    -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.rules')

# Filtra fora as rules existentes do alfaero-map-tiles (description começa com "alfaero-map-tiles:")
PRESERVED=$(echo "$CURRENT" | jq '[.[] | select(.description | startswith("alfaero-map-tiles:") | not) | {action, description, enabled, expression, action_parameters}]')

echo "Preserved $(echo "$PRESERVED" | jq 'length') non-map-tiles rules"

# Define nossas rules
read -r -d '' OURS <<EOF || true
[
  {
    "action": "set_cache_settings",
    "description": "alfaero-map-tiles: long TTL for .pmtiles (immutable, versioned)",
    "enabled": true,
    "expression": "(http.host eq \"$TILES_DOMAIN\") and (ends_with(http.request.uri.path, \".pmtiles\"))",
    "action_parameters": {
      "cache": true,
      "edge_ttl": { "mode": "override_origin", "default": 31536000 },
      "browser_ttl": { "mode": "override_origin", "default": 31536000 },
      "respect_strong_etags": true
    }
  },
  {
    "action": "set_cache_settings",
    "description": "alfaero-map-tiles: short TTL for styles/*",
    "enabled": true,
    "expression": "(http.host eq \"$TILES_DOMAIN\") and (starts_with(http.request.uri.path, \"/styles/\"))",
    "action_parameters": {
      "cache": true,
      "edge_ttl": { "mode": "override_origin", "default": 300 },
      "browser_ttl": { "mode": "override_origin", "default": 300 }
    }
  },
  {
    "action": "set_cache_settings",
    "description": "alfaero-map-tiles: long TTL for sprites/* and fonts/*",
    "enabled": true,
    "expression": "(http.host eq \"$TILES_DOMAIN\") and (starts_with(http.request.uri.path, \"/sprites/\") or starts_with(http.request.uri.path, \"/fonts/\"))",
    "action_parameters": {
      "cache": true,
      "edge_ttl": { "mode": "override_origin", "default": 2592000 },
      "browser_ttl": { "mode": "override_origin", "default": 2592000 }
    }
  }
]
EOF

# Mescla preserved + ours
PAYLOAD=$(jq -n --argjson p "$PRESERVED" --argjson o "$OURS" '{rules: ($p + $o)}')

echo "Applying $(echo "$PAYLOAD" | jq '.rules | length') total rules..."

RESPONSE=$(curl -sS -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/$RULESET_ID" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

if echo "$RESPONSE" | jq -e '.success == true' >/dev/null; then
    echo "OK — rules applied"
    echo "$RESPONSE" | jq '.result.rules[] | {description, enabled, expression}'
else
    echo "FAIL:" >&2
    echo "$RESPONSE" | jq '.errors' >&2
    exit 3
fi
