# CORS rules pro bucket (necessário pro browser puxar tiles via fetch).
# Aplicado via API (não há resource Terraform pra CORS de R2 ainda — gerenciar via dashboard).
#
# Configuração manual no dashboard:
#   R2 → alfaero-map-tiles → Settings → CORS Policy
#
# JSON:
# [
#   {
#     "AllowedOrigins": [
#       "https://app.alfaero.com",
#       "https://b2b.alfaero.com",
#       "https://alfaerovip.com",
#       "https://*.alfaero.com",
#       "http://localhost:*"
#     ],
#     "AllowedMethods": ["GET", "HEAD"],
#     "AllowedHeaders": ["Range", "If-Modified-Since", "If-None-Match"],
#     "ExposeHeaders": ["Content-Length", "Content-Range", "Content-Type", "ETag"],
#     "MaxAgeSeconds": 3600
#   }
# ]

# Page rule alternativa (se Cache Rules dão problema)
# resource "cloudflare_page_rule" "tiles_cache_fallback" { ... }

# Reserva atribuição: o estilo já injeta. Aqui apenas log de quem acessou.
# Cloudflare Logpush opcional pra debug (não habilitado por default por causa de custo).
