terraform {
  required_providers {
    time = {
      source = "hashicorp/time"
    }
  }
}

resource "azurerm_key_vault" "this" {
  name                       = "kv-bonfire-${var.suffix}"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  tenant_id                  = var.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
}

resource "azurerm_role_assignment" "deployer_secrets_officer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.deployer_object_id
}

# RBAC propagation is not immediate; writing the secret right after the
# assignment fails with 403 on a fresh vault (decision P6).
resource "time_sleep" "rbac_propagation" {
  depends_on      = [azurerm_role_assignment.deployer_secrets_officer]
  create_duration = "60s"
}

resource "azurerm_key_vault_secret" "game_password" {
  name         = "${var.game}-server-password"
  value        = var.game_password
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac_propagation]
}

resource "azurerm_key_vault_secret" "discord_webhook_url" {
  name         = "discord-webhook-url"
  value        = var.discord_webhook_url
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac_propagation]
}

# Stored for scripts/register-commands.py and Phase 1.5; no Function setting references it yet.
resource "azurerm_key_vault_secret" "discord_bot_token" {
  name         = "discord-bot-token"
  value        = var.discord_bot_token
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac_propagation]
}
