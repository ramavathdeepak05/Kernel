output "data_plane_role_id" {
  value     = vault_approle_auth_backend_role.data_plane.role_id
  sensitive = true
}

output "control_plane_role_id" {
  value     = vault_approle_auth_backend_role.control_plane.role_id
  sensitive = true
}
