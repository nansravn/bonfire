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
