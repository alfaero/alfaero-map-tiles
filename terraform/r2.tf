# R2 bucket que hospeda os pmtiles + styles + sprites + fonts.
resource "cloudflare_r2_bucket" "tiles" {
  account_id = var.cloudflare_account_id
  name       = var.r2_bucket_name
  location   = "WNAM" # Western North America (closer to BR than EU/APAC; auto-routed via CF)
}

# DNS CNAME tiles.alfaero.com → R2 public domain
# (R2 custom domain é configurado via dashboard ou API; aqui só o DNS).
resource "cloudflare_record" "tiles_cname" {
  zone_id = var.cloudflare_zone_id_alfaero
  name    = "tiles"
  type    = "CNAME"
  content = "${var.r2_bucket_name}.${var.cloudflare_account_id}.r2.cloudflarestorage.com"
  proxied = true
  ttl     = 1
  comment = "Map tiles via R2 (alfaero-map-tiles)"
}

# Cache rules — gerenciadas FORA do Terraform.
#
# Motivo: o zone alfaero.com já tem ruleset http_request_cache_settings em uso
# por outros serviços (ex: maps.alfaero.com), e Cloudflare permite apenas 1
# ruleset por phase + zone. Importar via Terraform falha por incompatibilidade
# do provider v4 com a Rulesets API. Gerenciamento via script API direta em
# infrastructure/cache-rules/.
#
# Rules ativas no zone (ruleset ffbda96c4812447b95fdd2f10a29868a):
#   1. Cache Tiles MapTile (pré-existente, maps.alfaero.com)
#   2. tiles.alfaero.com .pmtiles → TTL 1 ano + respect strong etags
#   3. tiles.alfaero.com /styles/* → TTL 5 min
#   4. tiles.alfaero.com /sprites/, /fonts/ → TTL 30 dias
#
# Pra atualizar:
#   bash infrastructure/cache-rules/apply.sh
#
# Cache Reserve (opcional) → ativar manual no dashboard se quiser:
#   Cloudflare → R2 → alfaero-map-tiles → Settings → Object Lifecycle → Cache Reserve

# Tiered Cache (Smart) — habilitar MANUALMENTE no dashboard:
#   Cloudflare → alfaero.com → Caching → Tiered Cache → Smart Tiered Caching → Enable
# (provider Cloudflare v4 não suporta sem permissão extra Cache Settings, mais simples manual)

output "r2_bucket_name" {
  value = cloudflare_r2_bucket.tiles.name
}

output "tiles_url" {
  value = "https://${var.tiles_domain}"
}
