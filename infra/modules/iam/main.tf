# The VM may deallocate itself and nothing else (ADR 0004).
resource "azurerm_role_definition" "self_deallocate" {
  name        = "Bonfire VM Self-Deallocate"
  scope       = var.vm_id
  description = "Deallocate and read the one Bonfire game VM."

  permissions {
    actions = [
      "Microsoft.Compute/virtualMachines/read",
      "Microsoft.Compute/virtualMachines/instanceView/read",
      "Microsoft.Compute/virtualMachines/deallocate/action",
    ]
  }

  assignable_scopes = [var.vm_id]
}

resource "azurerm_role_assignment" "vm_self_deallocate" {
  scope                            = var.vm_id
  role_definition_id               = azurerm_role_definition.self_deallocate.role_definition_resource_id
  principal_id                     = var.vm_principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "vm_reads_secrets" {
  scope                            = var.key_vault_id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = var.vm_principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "vm_writes_backups" {
  scope                            = var.backup_container_id
  role_definition_name             = "Storage Blob Data Contributor"
  principal_id                     = var.vm_principal_id
  skip_service_principal_aad_check = true
}

# The Function may read, start and deallocate the one VM (ADR 0004, spec 5.3).
resource "azurerm_role_definition" "vm_control" {
  name        = "Bonfire VM Control"
  scope       = var.vm_id
  description = "Read, start and deallocate the one Bonfire game VM."

  permissions {
    actions = [
      "Microsoft.Compute/virtualMachines/read",
      "Microsoft.Compute/virtualMachines/instanceView/read",
      "Microsoft.Compute/virtualMachines/start/action",
      "Microsoft.Compute/virtualMachines/deallocate/action",
    ]
  }

  assignable_scopes = [var.vm_id]
}

resource "azurerm_role_assignment" "function_vm_control" {
  scope                            = var.vm_id
  role_definition_id               = azurerm_role_definition.vm_control.role_definition_resource_id
  principal_id                     = var.function_principal_id
  skip_service_principal_aad_check = true
}

# Host storage (blob lease, queue trigger) and the state table, through the Function's identity.
resource "azurerm_role_assignment" "function_storage" {
  for_each = toset(["Storage Blob Data Owner", "Storage Queue Data Contributor", "Storage Table Data Contributor"])

  scope                            = var.controller_storage_account_id
  role_definition_name             = each.value
  principal_id                     = var.function_principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "function_reads_secrets" {
  scope                            = var.key_vault_id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = var.function_principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "vm_state_table" {
  scope                            = var.controller_storage_account_id
  role_definition_name             = "Storage Table Data Contributor"
  principal_id                     = var.vm_principal_id
  skip_service_principal_aad_check = true
}

# Cosmos data-plane RBAC: the built-in Data Contributor role definition id ends in ...0002.
locals {
  cosmos_data_contributor = "${var.cosmos_account_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
}

resource "azurerm_cosmosdb_sql_role_assignment" "function_events" {
  resource_group_name = var.resource_group_name
  account_name        = var.cosmos_account_name
  role_definition_id  = local.cosmos_data_contributor
  principal_id        = var.function_principal_id
  scope               = var.cosmos_account_id
}

resource "azurerm_cosmosdb_sql_role_assignment" "vm_events" {
  resource_group_name = var.resource_group_name
  account_name        = var.cosmos_account_name
  role_definition_id  = local.cosmos_data_contributor
  principal_id        = var.vm_principal_id
  scope               = var.cosmos_account_id
}
