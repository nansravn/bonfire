output "key_vault_id" { value = azurerm_key_vault.this.id }
output "key_vault_name" { value = azurerm_key_vault.this.name }
output "secret_name" { value = azurerm_key_vault_secret.game_password.name }
