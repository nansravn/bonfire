output "function_url" { value = "https://${azurerm_linux_function_app.this.default_hostname}/api/interactions" }
output "function_app_name" { value = azurerm_linux_function_app.this.name }
output "function_principal_id" { value = azurerm_linux_function_app.this.identity[0].principal_id }
output "storage_account_id" { value = azurerm_storage_account.controller.id }
output "storage_account_name" { value = azurerm_storage_account.controller.name }
output "state_table_endpoint" { value = azurerm_storage_account.controller.primary_table_endpoint }
