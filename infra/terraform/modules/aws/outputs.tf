# =============================================================================
# AWS Module Outputs
# =============================================================================

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnet_ids" {
  value = module.vpc.private_subnets
}

output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "eks_cluster_ca_cert" {
  value     = module.eks.cluster_certificate_authority_data
  sensitive = true
}

output "rds_cluster_endpoint" {
  value = aws_rds_cluster.alis.endpoint
}

output "rds_reader_endpoint" {
  value = aws_rds_cluster.alis.reader_endpoint
}

output "redis_primary_endpoint" {
  value = aws_elasticache_replication_group.alis.primary_endpoint_address
}

output "s3_system_bucket" {
  value = aws_s3_bucket.system.id
}

output "kms_key_arn" {
  value = aws_kms_key.alis.arn
}

output "database_url" {
  value     = "postgresql://${var.rds_master_username}:${var.rds_master_password}@${aws_rds_cluster.alis.endpoint}:5432/alis_control"
  sensitive = true
}

output "redis_url" {
  value     = "rediss://:${var.redis_auth_token}@${aws_elasticache_replication_group.alis.primary_endpoint_address}:6379/0"
  sensitive = true
}
