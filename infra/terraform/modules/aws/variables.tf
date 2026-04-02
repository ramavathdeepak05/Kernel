# =============================================================================
# AWS Module Variables
# =============================================================================

variable "project" {
  type    = string
  default = "alis"
}

variable "environment" {
  type        = string
  description = "dev | staging | prod"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "region" {
  type    = string
  default = "ap-south-1"   # Mumbai — primary for Indian universities
}

variable "domain" {
  type        = string
  default     = "alis.app"
  description = "Base domain for wildcard DNS (*.alis.app)"
}

variable "create_hosted_zone" {
  type    = bool
  default = false
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

# ---------------------------------------------------------------------------
# EKS
# ---------------------------------------------------------------------------

variable "eks_version" {
  type    = string
  default = "1.29"
}

variable "eks_app_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}

variable "eks_app_min_size" {
  type    = number
  default = 2
}

variable "eks_app_max_size" {
  type    = number
  default = 10
}

variable "eks_app_desired_size" {
  type    = number
  default = 2
}

variable "eks_worker_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}

variable "eks_worker_min_size" {
  type    = number
  default = 2
}

variable "eks_worker_max_size" {
  type    = number
  default = 20
}

variable "eks_worker_desired_size" {
  type    = number
  default = 2
}

# ---------------------------------------------------------------------------
# RDS
# ---------------------------------------------------------------------------

variable "rds_engine_version" {
  type    = string
  default = "15.4"
}

variable "rds_instance_class" {
  type    = string
  default = "db.r6g.large"
}

variable "rds_instance_count" {
  type    = number
  default = 2
}

variable "rds_master_username" {
  type      = string
  default   = "alis_admin"
  sensitive = true
}

variable "rds_master_password" {
  type      = string
  sensitive = true
}

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

variable "redis_node_type" {
  type    = string
  default = "cache.r6g.large"
}

variable "redis_num_cache_clusters" {
  type    = number
  default = 2
}

variable "redis_auth_token" {
  type      = string
  sensitive = true
}

# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

variable "extra_tags" {
  type    = map(string)
  default = {}
}
