variable "cloudflare_api_token" {
  description = "Token com escopo Zone:Edit + R2:Edit + Cache:Purge"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID da Alfaero"
  type        = string
}

variable "cloudflare_zone_id_alfaero" {
  description = "Zone ID de alfaero.com no Cloudflare"
  type        = string
}

variable "tiles_domain" {
  description = "Domínio público dos tiles"
  type        = string
  default     = "tiles.alfaero.com"
}

variable "r2_bucket_name" {
  description = "Nome do bucket R2"
  type        = string
  default     = "alfaero-map-tiles"
}

variable "aws_region" {
  description = "Região AWS pro pipeline semanal"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Perfil AWS local"
  type        = string
  default     = "alfaero"
}

variable "slack_webhook_url" {
  description = "Webhook pra notificações do pipeline"
  type        = string
  sensitive   = true
  default     = ""
}
