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
  default = "Standard_D4as_v6"
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

# Tunables (docs/contracts/configuration.md). Validation mirrors the contract's table.
variable "idle_timeout_minutes" {
  type    = number
  default = 45
  validation {
    condition     = var.idle_timeout_minutes > var.idle_check_interval
    error_message = "idle_timeout_minutes must be greater than idle_check_interval."
  }
}
variable "idle_warning_minutes" {
  type    = list(number)
  default = [15, 5]
  validation {
    condition = alltrue([
      for i in range(length(var.idle_warning_minutes)) :
      var.idle_warning_minutes[i] < var.idle_timeout_minutes && var.idle_warning_minutes[i] > var.idle_check_interval
      && (i == 0 || var.idle_warning_minutes[i] < var.idle_warning_minutes[i - 1])
    ])
    error_message = "idle_warning_minutes must be strictly descending, each below idle_timeout_minutes and above idle_check_interval."
  }
}
variable "idle_check_interval" {
  type    = number
  default = 1
  validation {
    condition     = var.idle_check_interval >= 1
    error_message = "idle_check_interval must be at least 1."
  }
}
variable "max_session_hours" {
  type    = number
  default = 12
  validation {
    condition     = var.max_session_hours >= 2
    error_message = "max_session_hours must be at least 2."
  }
}
variable "heartbeat_stale_minutes" {
  type    = number
  default = 20
  validation {
    condition     = var.heartbeat_stale_minutes >= 3 * var.idle_check_interval && var.heartbeat_stale_minutes > 15
    error_message = "heartbeat_stale_minutes must be at least 3 x idle_check_interval and greater than 15."
  }
}
variable "vm_hourly_usd" {
  type    = number
  default = 0.30
  validation {
    condition     = var.vm_hourly_usd > 0
    error_message = "vm_hourly_usd must be greater than 0."
  }
}
variable "fixed_monthly_usd" {
  type    = number
  default = 18
  validation {
    condition     = var.fixed_monthly_usd >= 0
    error_message = "fixed_monthly_usd must be at least 0."
  }
}

# Discord (docs/contracts/discord.md). IDs and the public key are not secrets.
variable "discord_application_id" { type = string }
variable "discord_public_key" { type = string }
variable "discord_guild_id" { type = string }
variable "discord_bot_token" {
  type      = string
  sensitive = true
}
variable "discord_webhook_url" {
  type      = string
  sensitive = true
}
variable "host_storage_uses_identity" {
  type    = bool
  default = true
}
