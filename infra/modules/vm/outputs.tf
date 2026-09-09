output "vm_id" { value = azurerm_linux_virtual_machine.this.id }
output "vm_name" { value = azurerm_linux_virtual_machine.this.name }
output "principal_id" { value = azurerm_linux_virtual_machine.this.identity[0].principal_id }
