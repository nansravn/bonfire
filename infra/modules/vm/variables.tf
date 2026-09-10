variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "nic_id" { type = string }
variable "vm_size" { type = string }
variable "disk_controller_type" {
  type        = string
  default     = "NVMe"
  description = "SCSI or NVMe; v6 sizes and newer are NVMe-only."
}
variable "admin_ssh_public_key" { type = string }
variable "data_disk_gb" { type = number }
variable "game" { type = string }
variable "adapter" {
  type        = object({ stop_grace_seconds = number, ready_timeout_minutes = number, ports = list(object({ port = number, proto = string })) })
  description = "Parsed games/<game>/adapter.json."
}
variable "game_env" {
  type        = map(string)
  description = "Non-secret adapter environment written to /etc/bonfire/<game>.env."
}
variable "public_address" { type = string }
variable "key_vault_name" { type = string }
variable "git_ref" { type = string }
variable "repo_url" { type = string }
variable "shutdown_time" {
  type        = string
  default     = "0400"
  description = "Daily auto-deallocate time (HHMM) in shutdown_timezone; a backstop until the agent's idle timer exists."
}
variable "shutdown_timezone" {
  type    = string
  default = "E. South America Standard Time"
}
variable "shutdown_notification_email" {
  type        = string
  default     = ""
  description = "Email warned 30 minutes before the nightly shutdown; empty disables the notification."
}
variable "agent_env" {
  type        = map(string)
  description = "BONFIRE_* settings appended to /etc/bonfire/bonfire.env (docs/contracts/configuration.md)."
}
