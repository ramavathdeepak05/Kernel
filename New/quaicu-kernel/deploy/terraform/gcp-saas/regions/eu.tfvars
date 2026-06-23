# EU residency zone (GDPR — keep personal data in the EEA, no US egress).
# Apply: terraform apply -var-file=regions/eu.tfvars  (plus your secret -var / *.auto.tfvars)
region       = "europe-west1" # Belgium. Alt: europe-west3 (Frankfurt), europe-west4 (Netherlands).
service_name = "quaicu-kernel-eu"

# For a true no-US-egress posture, enable the private path and supply a VPC connector in this region.
# See docs/operations/ZERO_EGRESS_VALIDATION.md. Default off here so a first apply is simple.
# enable_private_egress = true
# vpc_connector         = "projects/PROJECT/locations/europe-west1/connectors/quaicu-eu"

# project_id / image / db_password / *_dsn / pepper / jwt / edge_secret come from your secret tfvars.
