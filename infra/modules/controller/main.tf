terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

resource "azurerm_storage_account" "controller" {
  name                            = "stbonfirectl${var.suffix}"
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
}

resource "azurerm_storage_table" "state" {
  name               = "state"
  storage_account_id = azurerm_storage_account.controller.id
}

resource "azurerm_storage_queue" "interactions" {
  name               = "interactions"
  storage_account_id = azurerm_storage_account.controller.id
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-bonfire"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "this" {
  name                = "appi-bonfire"
  resource_group_name = var.resource_group_name
  location            = var.location
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.this.id
  sampling_percentage = 20
}

resource "azurerm_service_plan" "this" {
  name                = "asp-bonfire"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "FC1"
}

# Flex deployment package lives here; storage_container_endpoint below points at it.
resource "azurerm_storage_container" "deployments" {
  name                  = "deployments"
  storage_account_id    = azurerm_storage_account.controller.id
  container_access_type = "private"
}

resource "azurerm_function_app_flex_consumption" "this" {
  name                = "func-bonfire-${var.suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  service_plan_id     = azurerm_service_plan.this.id
  https_only          = true

  runtime_name    = "python"
  runtime_version = "3.12"

  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.controller.primary_blob_endpoint}${azurerm_storage_container.deployments.name}"
  storage_authentication_type = var.host_storage_uses_identity ? "SystemAssignedIdentity" : "StorageAccountConnectionString"
  storage_access_key          = var.host_storage_uses_identity ? null : azurerm_storage_account.controller.primary_access_key

  zip_deploy_file = var.package_zip

  instance_memory_in_mb  = 2048
  maximum_instance_count = 40

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.this.connection_string
  }

  # Flex does not populate AzureWebJobsStorage for the queue/table bindings on its own
  # (only DEPLOYMENT_STORAGE_CONNECTION_STRING, for the package container above); the
  # provider's own merge helper favors explicit user settings over its enumerated ones
  # ("explicit user settings take priority over enumerated, e.g. specifying KeyVault for
  # AzureWebJobsStorage" - internal/services/appservice/helpers/function_app_schema.go),
  # so set it here for the interactions queue trigger/output and the state table.
  app_settings = merge(var.app_settings, var.host_storage_uses_identity ? {
    AzureWebJobsStorage__accountName = azurerm_storage_account.controller.name
    } : {
    AzureWebJobsStorage = azurerm_storage_account.controller.primary_connection_string
  })
}
