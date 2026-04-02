# =============================================================================
# ALIS SaaS — AWS Module
#
# Provisions the complete AWS infrastructure for one ALIS region:
#   - VPC (3 AZs, public/private subnets, NAT Gateway)
#   - EKS Cluster (managed node groups)
#   - RDS PostgreSQL (Multi-AZ, encrypted)
#   - ElastiCache Redis (cluster mode)
#   - S3 bucket (system-level — per-tenant buckets created by BucketProvisioner)
#   - Route53 hosted zone + wildcard DNS
#   - KMS key for envelope encryption
# =============================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.project}-${var.environment}"
  cidr = var.vpc_cidr

  azs             = var.availability_zones
  private_subnets = var.private_subnet_cidrs
  public_subnets  = var.public_subnet_cidrs

  enable_nat_gateway   = true
  single_nat_gateway   = var.environment != "prod"   # save cost in non-prod
  enable_dns_hostnames = true
  enable_dns_support   = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }

  tags = local.tags
}

# ---------------------------------------------------------------------------
# KMS — Envelope encryption key
# ---------------------------------------------------------------------------

resource "aws_kms_key" "alis" {
  description             = "ALIS ${var.environment} envelope encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = local.tags
}

resource "aws_kms_alias" "alis" {
  name          = "alias/${var.project}-${var.environment}"
  target_key_id = aws_kms_key.alis.key_id
}

# ---------------------------------------------------------------------------
# EKS Cluster
# ---------------------------------------------------------------------------

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "${var.project}-${var.environment}"
  cluster_version = var.eks_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access = var.environment != "prod"

  eks_managed_node_groups = {
    app = {
      name           = "app"
      instance_types = var.eks_app_instance_types
      min_size       = var.eks_app_min_size
      max_size       = var.eks_app_max_size
      desired_size   = var.eks_app_desired_size

      labels = {
        role = "app"
      }
    }

    worker = {
      name           = "worker"
      instance_types = var.eks_worker_instance_types
      min_size       = var.eks_worker_min_size
      max_size       = var.eks_worker_max_size
      desired_size   = var.eks_worker_desired_size

      labels = {
        role = "worker"
      }

      taints = [{
        key    = "workload"
        value  = "celery"
        effect = "NO_SCHEDULE"
      }]
    }
  }

  # Encryption
  cluster_encryption_config = {
    provider_key_arn = aws_kms_key.alis.arn
    resources        = ["secrets"]
  }

  tags = local.tags
}

# ---------------------------------------------------------------------------
# RDS PostgreSQL
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "alis" {
  name       = "${var.project}-${var.environment}"
  subnet_ids = module.vpc.private_subnets
  tags       = local.tags
}

resource "aws_security_group" "rds" {
  name_prefix = "${var.project}-rds-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
    description     = "PostgreSQL from EKS"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_rds_cluster" "alis" {
  cluster_identifier = "${var.project}-${var.environment}"
  engine             = "aurora-postgresql"
  engine_version     = var.rds_engine_version
  database_name      = "alis_control"
  master_username    = var.rds_master_username
  master_password    = var.rds_master_password

  db_subnet_group_name   = aws_db_subnet_group.alis.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  storage_encrypted = true
  kms_key_id        = aws_kms_key.alis.arn

  backup_retention_period = var.environment == "prod" ? 30 : 7
  preferred_backup_window = "03:00-04:00"

  deletion_protection = var.environment == "prod"

  tags = local.tags
}

resource "aws_rds_cluster_instance" "alis" {
  count = var.rds_instance_count

  identifier         = "${var.project}-${var.environment}-${count.index}"
  cluster_identifier = aws_rds_cluster.alis.id
  instance_class     = var.rds_instance_class
  engine             = aws_rds_cluster.alis.engine
  engine_version     = aws_rds_cluster.alis.engine_version

  tags = local.tags
}

# ---------------------------------------------------------------------------
# ElastiCache Redis
# ---------------------------------------------------------------------------

resource "aws_security_group" "redis" {
  name_prefix = "${var.project}-redis-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
    description     = "Redis from EKS"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_elasticache_subnet_group" "alis" {
  name       = "${var.project}-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "alis" {
  replication_group_id = "${var.project}-${var.environment}"
  description          = "ALIS ${var.environment} Redis"

  node_type            = var.redis_node_type
  num_cache_clusters   = var.redis_num_cache_clusters

  subnet_group_name  = aws_elasticache_subnet_group.alis.name
  security_group_ids = [aws_security_group.redis.id]

  engine_version    = "7.0"
  port              = 6379
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = var.redis_auth_token

  automatic_failover_enabled = var.redis_num_cache_clusters > 1

  tags = local.tags
}

# ---------------------------------------------------------------------------
# S3 — System bucket
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "system" {
  bucket = "${var.project}-${var.environment}-system"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "system" {
  bucket = aws_s3_bucket.system.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "system" {
  bucket = aws_s3_bucket.system.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.alis.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "system" {
  bucket                  = aws_s3_bucket.system.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# Route53 — Wildcard DNS
# ---------------------------------------------------------------------------

resource "aws_route53_zone" "alis" {
  count = var.create_hosted_zone ? 1 : 0
  name  = var.domain
  tags  = local.tags
}

# ---------------------------------------------------------------------------
# Locals
# ---------------------------------------------------------------------------

locals {
  tags = merge(var.extra_tags, {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}
