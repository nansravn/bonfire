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
  sku_name            = "Y1"
}

resource "azurerm_linux_function_app" "this" {
  name                = "func-bonfire-${var.suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  service_plan_id     = azurerm_service_plan.this.id
  https_only          = true

  storage_account_name          = azurerm_storage_account.controller.name
  storage_uses_managed_identity = var.host_storage_uses_identity ? true : null
  storage_account_access_key    = var.host_storage_uses_identity ? null : azurerm_storage_account.controller.primary_access_key

  zip_deploy_file = var.package_zip

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.this.connection_string
    ftps_state                             = "Disabled"

    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = merge(var.app_settings, {
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    ENABLE_ORYX_BUILD              = "true"
  })
}
