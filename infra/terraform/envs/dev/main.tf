# =============================================================================
# ALIS SaaS — Dev Environment (AWS)
#
# Usage:
#   cd infra/terraform/envs/dev
#   terraform init
#   terraform plan -var-file=terraform.tfvars
#   terraform apply -var-file=terraform.tfvars
# =============================================================================

terraform {
  required_version = ">= 1.5"

  backend "s3" {
    bucket         = "alis-terraform-state"
    key            = "dev/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "alis-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

module "aws" {
  source = "../../modules/aws"

  project     = "alis"
  environment = "dev"
  region      = var.aws_region

  # Smaller instances for dev
  eks_app_instance_types    = ["t3.small"]
  eks_app_min_size          = 1
  eks_app_max_size          = 3
  eks_app_desired_size      = 1
  eks_worker_instance_types = ["t3.small"]
  eks_worker_min_size       = 1
  eks_worker_max_size       = 5
  eks_worker_desired_size   = 1

  rds_instance_class = "db.t4g.medium"
  rds_instance_count = 1
  rds_master_password = var.rds_master_password

  redis_node_type          = "cache.t4g.micro"
  redis_num_cache_clusters = 1
  redis_auth_token         = var.redis_auth_token
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "rds_master_password" {
  type      = string
  sensitive = true
}

variable "redis_auth_token" {
  type      = string
  sensitive = true
}

output "eks_cluster_name" {
  value = module.aws.eks_cluster_name
}

output "rds_endpoint" {
  value = module.aws.rds_cluster_endpoint
}

output "redis_endpoint" {
  value = module.aws.redis_primary_endpoint
}
