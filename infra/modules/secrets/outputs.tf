output "key_vault_id" { value = azurerm_key_vault.this.id }
output "key_vault_name" { value = azurerm_key_vault.this.name }
output "secret_name" { value = azurerm_key_vault_secret.game_password.name }
output "webhook_secret_versionless_id" { value = azurerm_key_vault_secret.discord_webhook_url.versionless_id }
