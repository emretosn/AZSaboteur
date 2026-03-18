# Exposed management port — VM with SSH directly accessible from the lab subnet.
# The player uses discovered credentials to log in via SSH.

resource "azurerm_network_interface" "this" {
  name                = "nic-${var.resource_prefix}"
  location            = var.region
  resource_group_name = var.resource_group_name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.lab_subnet_id
    private_ip_address_allocation = "Dynamic"
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
  }
}

# NSG allowing SSH from the lab subnet
resource "azurerm_network_security_group" "this" {
  name                = "nsg-${var.resource_prefix}"
  location            = var.region
  resource_group_name = var.resource_group_name

  security_rule {
    name                       = "AllowSSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "10.13.37.0/24"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowRDP"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = "10.13.37.0/24"
    destination_address_prefix = "*"
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
  }
}

resource "azurerm_network_interface_security_group_association" "this" {
  network_interface_id      = azurerm_network_interface.this.id
  network_security_group_id = azurerm_network_security_group.this.id
}

resource "azurerm_linux_virtual_machine" "this" {
  name                            = "${var.resource_prefix}-vm"
  location                        = var.region
  resource_group_name             = var.resource_group_name
  size                            = "Standard_B1s"
  admin_username                  = var.credentials["step_${var.step_index}_username"]
  admin_password                  = var.credentials["step_${var.step_index}_password"]
  disable_password_authentication = false
  network_interface_ids           = [azurerm_network_interface.this.id]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  custom_data = base64encode(<<-CLOUD
    #!/bin/bash
    mkdir -p /opt/azsaboteur
    echo '${var.flag}' > /opt/azsaboteur/flag.txt
    chmod 600 /opt/azsaboteur/flag.txt
  CLOUD
  )

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "mgmt-exposed"
  }
}

output "private_ip" {
  description = "Private IP of the VM"
  value       = azurerm_network_interface.this.private_ip_address
}

output "vm_id" {
  description = "VM resource ID"
  value       = azurerm_linux_virtual_machine.this.id
}
