locals {
  cloud_init = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    game                 = var.game
    game_env             = var.game_env
    stop_grace_seconds   = var.adapter.stop_grace_seconds
    stop_timeout_seconds = var.adapter.stop_grace_seconds + 60
    public_address       = var.public_address
    key_vault_name       = var.key_vault_name
    git_ref              = var.git_ref
    repo_url             = var.repo_url
  })
}

resource "azurerm_linux_virtual_machine" "this" {
  name                            = "vm-bonfire"
  resource_group_name             = var.resource_group_name
  location                        = var.location
  size                            = var.vm_size
  admin_username                  = "bonfire"
  disable_password_authentication = true
  network_interface_ids           = [var.nic_id]
  custom_data                     = base64encode(local.cloud_init)
  disk_controller_type            = var.disk_controller_type

  admin_ssh_key {
    username   = "bonfire"
    public_key = var.admin_ssh_public_key
  }

  os_disk {
    name                 = "disk-bonfire-os"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_managed_disk" "data" {
  name                 = "disk-bonfire-data"
  resource_group_name  = var.resource_group_name
  location             = var.location
  storage_account_type = "Premium_LRS"
  create_option        = "Empty"
  disk_size_gb         = var.data_disk_gb

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_virtual_machine_data_disk_attachment" "data" {
  managed_disk_id    = azurerm_managed_disk.data.id
  virtual_machine_id = azurerm_linux_virtual_machine.this.id
  lun                = 0
  caching            = "None"
}

# Interim backstop: deallocate every night so a forgotten session costs at most one night.
# Remove once the agent's idle timer (Phase 1) is proven.
resource "azurerm_dev_test_global_vm_shutdown_schedule" "nightly" {
  virtual_machine_id    = azurerm_linux_virtual_machine.this.id
  location              = var.location
  enabled               = true
  daily_recurrence_time = var.shutdown_time
  timezone              = var.shutdown_timezone

  notification_settings {
    enabled         = var.shutdown_notification_email != ""
    time_in_minutes = 30
    email           = var.shutdown_notification_email
  }
}
