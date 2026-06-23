# India residency zone (DPDP — localize personal data in India; aligns with the RBI/SEBI policy pack).
# Apply: terraform apply -var-file=regions/india.tfvars  (plus your secret -var / *.auto.tfvars)
region       = "asia-south1" # Mumbai. Alt: asia-south2 (Delhi).
service_name = "quaicu-kernel-in"

# RBI payment-data localization + DPDP favour keeping the durable stores in-region and egress private.
# enable_private_egress = true
# vpc_connector         = "projects/PROJECT/locations/asia-south1/connectors/quaicu-in"

# project_id / image / db_password / *_dsn / pepper / jwt / edge_secret come from your secret tfvars.
