resource "azurerm_storage_account" "backup" {
  name                            = "stbonfirebak${var.suffix}"
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
}

resource "azurerm_storage_container" "backups" {
  name                  = "backups"
  storage_account_id    = azurerm_storage_account.backup.id
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "retention" {
  storage_account_id = azurerm_storage_account.backup.id

  rule {
    name    = "delete-backups-after-7-days"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["backups/"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 7
      }
    }
  }
}
