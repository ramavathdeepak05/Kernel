variable "alis_master_key" {
  type        = string
  sensitive   = true
  description = "ALIS master encryption key (AES-256). Must be 32+ characters."
}
