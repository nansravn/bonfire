terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# Cosmos DB serverless for events (ADR 0005). Data-plane access is RBAC only.
resource "azurerm_cosmosdb_account" "this" {
  name                          = "cosmos-bonfire-${var.suffix}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  offer_type                    = "Standard"
  kind                          = "GlobalDocumentDB"
  local_authentication_disabled = true

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  capabilities {
    name = "EnableServerless"
  }
}

resource "azurerm_cosmosdb_sql_database" "bonfire" {
  name                = "bonfire"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.this.name
}

resource "azurerm_cosmosdb_sql_container" "events" {
  name                = "events"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.this.name
  database_name       = azurerm_cosmosdb_sql_database.bonfire.name
  partition_key_paths = ["/month"]
  default_ttl         = 7776000
}
