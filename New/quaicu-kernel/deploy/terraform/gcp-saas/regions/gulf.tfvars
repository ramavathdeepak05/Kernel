# Gulf residency zone (KSA/UAE data-sovereignty regimes).
# Apply: terraform apply -var-file=regions/gulf.tfvars  (plus your secret -var / *.auto.tfvars)
region       = "me-central1" # Doha. Alt: me-central2 (Dammam, KSA), me-west1 (Tel Aviv).
service_name = "quaicu-kernel-gulf"

# Verify Cloud SQL + Serverless VPC Access availability in the chosen Gulf region before committing —
# regional service coverage varies. See docs/operations/DATA_RESIDENCY.md.
# enable_private_egress = true
# vpc_connector         = "projects/PROJECT/locations/me-central1/connectors/quaicu-gulf"

# project_id / image / db_password / *_dsn / pepper / jwt / edge_secret come from your secret tfvars.
