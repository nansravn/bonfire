variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "suffix" { type = string }
variable "tenant_id" { type = string }
variable "deployer_object_id" {
  type        = string
  description = "Object ID of the principal running terraform; gets Key Vault Secrets Officer."
}
variable "game" { type = string }
variable "game_password" {
  type      = string
  sensitive = true
}
