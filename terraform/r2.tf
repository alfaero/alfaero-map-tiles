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

# Cache rule: .pmtiles imutáveis (TTL 1 ano edge+browser)
resource "cloudflare_ruleset" "tiles_cache" {
  zone_id     = var.cloudflare_zone_id_alfaero
  name        = "alfaero-map-tiles cache rules"
  description = "Cache rules pro subdomínio tiles.alfaero.com"
  kind        = "zone"
  phase       = "http_request_cache_settings"

  rules {
    description = "Long TTL for .pmtiles"
    expression  = "(http.host eq \"${var.tiles_domain}\") and (http.request.uri.path matches \".*\\\\.pmtiles$\")"
    action      = "set_cache_settings"

    action_parameters {
      cache = true

      edge_ttl {
        mode    = "override_origin"
        default = 31536000 # 1 ano
      }

      browser_ttl {
        mode    = "override_origin"
        default = 31536000
      }

      cache_reserve {
        eligible = true
        min_file_size = 1048576 # 1 MB
      }

      respect_strong_etags = true
    }

    enabled = true
  }

  rules {
    description = "Short TTL for styles/* (mutable)"
    expression  = "(http.host eq \"${var.tiles_domain}\") and (starts_with(http.request.uri.path, \"/styles/\"))"
    action      = "set_cache_settings"

    action_parameters {
      cache = true

      edge_ttl {
        mode    = "override_origin"
        default = 300 # 5 min
      }

      browser_ttl {
        mode    = "override_origin"
        default = 300
      }
    }

    enabled = true
  }

  rules {
    description = "Long TTL for sprites/* and fonts/*"
    expression  = "(http.host eq \"${var.tiles_domain}\") and (starts_with(http.request.uri.path, \"/sprites/\") or starts_with(http.request.uri.path, \"/fonts/\"))"
    action      = "set_cache_settings"

    action_parameters {
      cache = true

      edge_ttl {
        mode    = "override_origin"
        default = 2592000 # 30 dias
      }

      browser_ttl {
        mode    = "override_origin"
        default = 2592000
      }
    }

    enabled = true
  }
}

# Tiered Cache (Smart) — POPs menores buscam em POP grande antes do R2
resource "cloudflare_tiered_cache" "smart" {
  zone_id    = var.cloudflare_zone_id_alfaero
  cache_type = "smart"
}

output "r2_bucket_name" {
  value = cloudflare_r2_bucket.tiles.name
}

output "tiles_url" {
  value = "https://${var.tiles_domain}"
}
