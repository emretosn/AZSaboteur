variable "scenario_id" {
  type = string
}

variable "region" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "vnet_address_space" {
  type    = list(string)
  default = ["10.13.37.0/24"]
}

resource "azurerm_virtual_network" "this" {
  name                = "vnet-${var.scenario_id}"
  location            = var.region
  resource_group_name = var.resource_group_name
  address_space       = var.vnet_address_space

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
  }
}

# Kali box subnet — player's attack machine sits here
resource "azurerm_subnet" "kali" {
  name                 = "snet-kali"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.13.37.0/28"]
}

# Lab subnet — vulnerable target VMs/services live here
resource "azurerm_subnet" "lab" {
  name                 = "snet-lab"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.13.37.16/28"]
}

# NSG for the Kali subnet — allow RDP inbound from the internet
resource "azurerm_network_security_group" "kali" {
  name                = "nsg-kali-${var.scenario_id}"
  location            = var.region
  resource_group_name = var.resource_group_name

  security_rule {
    name                       = "AllowRDP"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
  }
}

resource "azurerm_subnet_network_security_group_association" "kali" {
  subnet_id                 = azurerm_subnet.kali.id
  network_security_group_id = azurerm_network_security_group.kali.id
}

# NSG for the lab subnet — no inbound from internet, only from kali subnet
resource "azurerm_network_security_group" "lab" {
  name                = "nsg-lab-${var.scenario_id}"
  location            = var.region
  resource_group_name = var.resource_group_name

  security_rule {
    name                       = "AllowFromKali"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "10.13.37.0/28"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "DenyInternetInbound"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
  }
}

resource "azurerm_subnet_network_security_group_association" "lab" {
  subnet_id                 = azurerm_subnet.lab.id
  network_security_group_id = azurerm_network_security_group.lab.id
}

output "vnet_id" {
  value = azurerm_virtual_network.this.id
}

output "vnet_name" {
  value = azurerm_virtual_network.this.name
}

output "kali_subnet_id" {
  value = azurerm_subnet.kali.id
}

output "lab_subnet_id" {
  value = azurerm_subnet.lab.id
}
