# Web VM module — deploys a Linux VM on the lab subnet for hosting a vulnerable web app.
#
# The actual vulnerable application is installed by Ansible (Phase 2).
# Terraform creates the infrastructure: VM, NIC, and private IP.
# The flag is written to /opt/flag.txt via cloud-init as a fallback;
# Ansible may relocate it into the app later.

locals {
  vm_name = "${var.resource_prefix}-vm"
}

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

resource "azurerm_linux_virtual_machine" "this" {
  name                            = local.vm_name
  location                        = var.region
  resource_group_name             = var.resource_group_name
  size                            = "Standard_B2ls_v2"
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
    # Install basic web server as placeholder until Ansible deploys the real app
    apt-get update -qq && apt-get install -y -qq python3 python3-pip
  CLOUD
  )

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "web-ssrf"
  }
}

output "private_ip" {
  description = "Private IP of the web VM"
  value       = azurerm_network_interface.this.private_ip_address
}

output "vm_id" {
  description = "VM resource ID"
  value       = azurerm_linux_virtual_machine.this.id
}
