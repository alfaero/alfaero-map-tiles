terraform {
  required_version = ">= 1.6"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  backend "s3" {
    # Configure via -backend-config ou backend.hcl
    # bucket   = "alfaero-terraform-state"
    # key      = "map-tiles/terraform.tfstate"
    # region   = "us-east-1"
    # encrypt  = true
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
  default_tags {
    tags = {
      Project   = "alfaero-map-tiles"
      ManagedBy = "terraform"
      Repo      = "alfaero/alfaero-map-tiles"
    }
  }
}
