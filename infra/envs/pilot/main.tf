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

  shutdown_notification_email = var.alert_email
}

module "iam" {
  source              = "../../modules/iam"
  vm_id               = module.vm.vm_id
  vm_principal_id     = module.vm.principal_id
  key_vault_id        = module.secrets.key_vault_id
  backup_container_id = module.backup.container_id
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
