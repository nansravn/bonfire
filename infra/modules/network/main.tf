resource "azurerm_virtual_network" "this" {
  name                = "vnet-bonfire"
  resource_group_name = var.resource_group_name
  location            = var.location
  address_space       = ["10.20.0.0/24"]
}

resource "azurerm_subnet" "game" {
  name                 = "snet-game"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.20.0.0/26"]
}

resource "azurerm_public_ip" "this" {
  name                = "pip-bonfire"
  resource_group_name = var.resource_group_name
  location            = var.location
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_security_group" "game" {
  name                = "nsg-bonfire-game"
  resource_group_name = var.resource_group_name
  location            = var.location
}

resource "azurerm_network_security_rule" "game" {
  for_each                    = { for i, p in var.ports : "${p.proto}-${p.port}" => merge(p, { priority = 100 + i }) }
  name                        = "allow-${each.key}"
  priority                    = each.value.priority
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = title(each.value.proto)
  source_port_range           = "*"
  destination_port_range      = tostring(each.value.port)
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.game.name
}

resource "azurerm_network_security_rule" "ssh" {
  name                        = "allow-ssh-admin"
  priority                    = 200
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = var.admin_cidr
  destination_address_prefix  = "*"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.game.name
}

resource "azurerm_subnet_network_security_group_association" "game" {
  subnet_id                 = azurerm_subnet.game.id
  network_security_group_id = azurerm_network_security_group.game.id
}

resource "azurerm_network_interface" "this" {
  name                = "nic-bonfire"
  resource_group_name = var.resource_group_name
  location            = var.location

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.game.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.this.id
  }
}
