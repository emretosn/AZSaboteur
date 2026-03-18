# Open NSG — intentionally misconfigured to allow all inbound traffic.
# The player discovers internal services that should not be exposed.

resource "azurerm_network_security_group" "this" {
  name                = "nsg-${var.resource_prefix}"
  location            = var.region
  resource_group_name = var.resource_group_name

  # Intentionally permissive: allow all inbound
  security_rule {
    name                       = "AllowAllInbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "nsg-open"
  }
}

# A VM behind the open NSG that hosts a service with the flag
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
    role     = "nsg-open"
  }
}

output "nsg_id" {
  description = "NSG resource ID"
  value       = azurerm_network_security_group.this.id
}

output "private_ip" {
  description = "Private IP of the VM behind the open NSG"
  value       = azurerm_network_interface.this.private_ip_address
}
