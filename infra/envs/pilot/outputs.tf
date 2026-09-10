output "public_address" { value = local.public_address }
output "vm_id" { value = module.vm.vm_id }
output "vm_name" { value = module.vm.vm_name }
output "resource_group" { value = azurerm_resource_group.pilot.name }
output "key_vault_name" { value = module.secrets.key_vault_name }
output "backup_storage_account" { value = module.backup.storage_account_name }
