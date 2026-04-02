# =============================================================================
# ALIS SaaS — Production Environment (AWS + multi-region ready)
#
# Production runs on AWS ap-south-1 (Mumbai) as the primary region.
# Multi-region failover (uae-north, eu-west) uses the same module
# with region-specific overrides.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  backend "s3" {
    bucket         = "alis-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "alis-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

provider "vault" {
  address = var.vault_addr
}

# ---------------------------------------------------------------------------
# Core infrastructure
# ---------------------------------------------------------------------------

module "aws" {
  source = "../../modules/aws"

  project     = "alis"
  environment = "prod"
  region      = var.aws_region
  domain      = var.domain

  # Production-grade sizing
  eks_app_instance_types    = ["m6i.large"]
  eks_app_min_size          = 3
  eks_app_max_size          = 20
  eks_app_desired_size      = 3
  eks_worker_instance_types = ["m6i.large"]
  eks_worker_min_size       = 3
  eks_worker_max_size       = 50
  eks_worker_desired_size   = 3

  rds_instance_class  = "db.r6g.xlarge"
  rds_instance_count  = 3        # writer + 2 readers
  rds_master_password = var.rds_master_password

  redis_node_type          = "cache.r6g.large"
  redis_num_cache_clusters = 3   # primary + 2 replicas
  redis_auth_token         = var.redis_auth_token

  create_hosted_zone = true

  extra_tags = {
    CostCenter = "alis-prod"
    Compliance = "SOC2"
  }
}

# ---------------------------------------------------------------------------
# Vault configuration
# ---------------------------------------------------------------------------

module "vault" {
  source = "../../modules/shared"

  alis_master_key = var.alis_master_key
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "domain" {
  type    = string
  default = "alis.app"
}

variable "vault_addr" {
  type    = string
  default = "https://vault.alis.app:8200"
}

variable "rds_master_password" {
  type      = string
  sensitive = true
}

variable "redis_auth_token" {
  type      = string
  sensitive = true
}

variable "alis_master_key" {
  type      = string
  sensitive = true
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "eks_cluster_name" {
  value = module.aws.eks_cluster_name
}

output "eks_cluster_endpoint" {
  value = module.aws.eks_cluster_endpoint
}

output "rds_cluster_endpoint" {
  value = module.aws.rds_cluster_endpoint
}

output "rds_reader_endpoint" {
  value = module.aws.rds_reader_endpoint
}

output "redis_primary_endpoint" {
  value = module.aws.redis_primary_endpoint
}

output "s3_system_bucket" {
  value = module.aws.s3_system_bucket
}

output "database_url" {
  value     = module.aws.database_url
  sensitive = true
}

output "redis_url" {
  value     = module.aws.redis_url
  sensitive = true
}
