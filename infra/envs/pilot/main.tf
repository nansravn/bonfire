data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "pilot" {
  name     = "rg-bonfire-pilot"
  location = var.location
}

resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  adapter        = jsondecode(file("${path.root}/../../../games/${var.game}/adapter.json"))
  public_address = "${module.network.public_ip_address}:${local.adapter.ports[0].port}"
  # Deterministic so the VM's own cloud-init can carry it (decision P3).
  vm_resource_id = "/subscriptions/${var.subscription_id}/resourceGroups/${azurerm_resource_group.pilot.name}/providers/Microsoft.Compute/virtualMachines/vm-bonfire"

  bonfire_settings = {
    BONFIRE_GAME                    = var.game
    BONFIRE_IDLE_TIMEOUT_MINUTES    = tostring(var.idle_timeout_minutes)
    BONFIRE_IDLE_WARNING_MINUTES    = join(",", [for w in var.idle_warning_minutes : tostring(w)])
    BONFIRE_IDLE_CHECK_INTERVAL     = tostring(var.idle_check_interval)
    BONFIRE_MAX_SESSION_HOURS       = tostring(var.max_session_hours)
    BONFIRE_HEARTBEAT_STALE_MINUTES = tostring(var.heartbeat_stale_minutes)
    BONFIRE_VM_HOURLY_USD           = tostring(var.vm_hourly_usd)
    BONFIRE_FIXED_MONTHLY_USD       = tostring(var.fixed_monthly_usd)
    BONFIRE_PUBLIC_ADDRESS          = local.public_address
    BONFIRE_VM_RESOURCE_ID          = local.vm_resource_id
    BONFIRE_STATE_TABLE_ENDPOINT    = module.controller.state_table_endpoint
    BONFIRE_EVENTS_ENDPOINT         = module.data.endpoint
  }
}

locals {
  function_dist = "${path.root}/../../../dist/function"
  # The zip path carries a content hash: azurerm redeploys only when zip_deploy_file changes.
  function_dist_hash = sha1(join("", [for f in sort(fileset(local.function_dist, "**")) : filesha1("${local.function_dist}/${f}") if !strcontains(f, "__pycache__")]))
}

# scripts/build-function.sh must have run before plan; CI and the README say so.
data "archive_file" "function" {
  type        = "zip"
  source_dir  = local.function_dist
  output_path = "${path.root}/../../../dist/function-${local.function_dist_hash}.zip"
}

module "network" {
  source              = "../../modules/network"
  resource_group_name = azurerm_resource_group.pilot.name
  location            = azurerm_resource_group.pilot.location
  ports               = local.adapter.ports
  admin_cidr          = var.admin_cidr
}

module "backup" {
  source              = "../../modules/backup"
  resource_group_name = azurerm_resource_group.pilot.name
  location            = azurerm_resource_group.pilot.location
  suffix              = random_string.suffix.result
}

module "secrets" {
  source              = "../../modules/secrets"
  resource_group_name = azurerm_resource_group.pilot.name
  location            = azurerm_resource_group.pilot.location
  suffix              = random_string.suffix.result
  tenant_id           = data.azurerm_client_config.current.tenant_id
  deployer_object_id  = data.azurerm_client_config.current.object_id
  game                = var.game
  game_password       = var.game_password
  discord_webhook_url = var.discord_webhook_url
  discord_bot_token   = var.discord_bot_token
}

module "data" {
  source              = "../../modules/data"
  resource_group_name = azurerm_resource_group.pilot.name
  location            = azurerm_resource_group.pilot.location
  suffix              = random_string.suffix.result
}

module "controller" {
  source                     = "../../modules/controller"
  resource_group_name        = azurerm_resource_group.pilot.name
  location                   = azurerm_resource_group.pilot.location
  suffix                     = random_string.suffix.result
  package_zip                = data.archive_file.function.output_path
  host_storage_uses_identity = var.host_storage_uses_identity

  app_settings = merge(local.bonfire_settings, {
    DISCORD_APPLICATION_ID = var.discord_application_id
    DISCORD_PUBLIC_KEY     = var.discord_public_key
    DISCORD_WEBHOOK_URL    = "@Microsoft.KeyVault(SecretUri=${module.secrets.webhook_secret_versionless_id})"
  })
}

module "vm" {
  source               = "../../modules/vm"
  resource_group_name  = azurerm_resource_group.pilot.name
  location             = azurerm_resource_group.pilot.location
  nic_id               = module.network.nic_id
  vm_size              = var.vm_size
  admin_ssh_public_key = var.admin_ssh_public_key
  data_disk_gb         = var.data_disk_gb
  game                 = var.game
  adapter              = local.adapter
  game_env             = var.game_env
  public_address       = local.public_address
  key_vault_name       = module.secrets.key_vault_name
  git_ref              = var.bonfire_git_ref
  repo_url             = var.repo_url

  agent_env = merge(local.bonfire_settings, {
    BONFIRE_BACKUP_ACCOUNT_URL = module.backup.blob_endpoint
  })
}

module "iam" {
  source              = "../../modules/iam"
  vm_id               = module.vm.vm_id
  vm_principal_id     = module.vm.principal_id
  key_vault_id        = module.secrets.key_vault_id
  backup_container_id = module.backup.container_id

  resource_group_name           = azurerm_resource_group.pilot.name
  function_principal_id         = module.controller.function_principal_id
  controller_storage_account_id = module.controller.storage_account_id
  cosmos_account_id             = module.data.account_id
  cosmos_account_name           = module.data.account_name
}

# PRD section 8: cost alert at 80% of the monthly ceiling (section 10).
resource "azurerm_consumption_budget_resource_group" "pilot" {
  count             = var.alert_email != "" ? 1 : 0
  name              = "budget-bonfire-pilot"
  resource_group_id = azurerm_resource_group.pilot.id
  amount            = var.monthly_budget_usd
  time_grain        = "Monthly"

  time_period {
    start_date = "2026-09-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }
}
