variable "subscription_id" { type = string }

variable "location" {
  type    = string
  default = "brazilsouth"
}

variable "admin_ssh_public_key" {
  type        = string
  description = "Contents of the owner's SSH public key."
}

variable "admin_cidr" {
  type        = string
  description = "CIDR allowed to SSH, e.g. 203.0.113.7/32."
}

variable "game" {
  type    = string
  default = "valheim"
}

variable "game_env" {
  type        = map(string)
  default     = {}
  description = "Non-secret adapter environment (for Valheim: SERVER_NAME, WORLD_NAME, SERVER_PUBLIC, optional SERVER_ARGS)."
}

variable "game_password" {
  type      = string
  sensitive = true
}

variable "bonfire_git_ref" {
  type    = string
  default = "main"
}

variable "repo_url" {
  type    = string
  default = "https://github.com/nansravn/bonfire.git"
}

variable "vm_size" {
  type    = string
  default = "Standard_D4as_v5"
}

variable "data_disk_gb" {
  type    = number
  default = 64
}

variable "alert_email" {
  type        = string
  default     = ""
  description = "Receives the budget alert and the nightly-shutdown warning; empty disables both notifications."
}

variable "monthly_budget_usd" {
  type    = number
  default = 120
}
