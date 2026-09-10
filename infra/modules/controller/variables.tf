variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "suffix" { type = string }
variable "package_zip" {
  type        = string
  description = "Path to the zipped dist/function produced by scripts/build-function.sh."
}
variable "app_settings" {
  type        = map(string)
  description = "BONFIRE_* and DISCORD_* settings from docs/contracts/configuration.md."
}
variable "host_storage_uses_identity" {
  type        = bool
  default     = true
  description = "AzureWebJobsStorage through the app's identity; set false to fall back to the account key (spec 5.1)."
}
