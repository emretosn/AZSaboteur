# Web VM module — deploys a Linux VM on the lab subnet for hosting a vulnerable web app.
#
# The VM has a system-assigned managed identity that the player can steal
# via SSRF to the IMDS endpoint.  The actual vulnerable application is
# installed by Ansible (Phase 2).

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

data "azurerm_client_config" "current" {}

resource "azurerm_linux_virtual_machine" "this" {
  name                            = local.vm_name
  location                        = var.region
  resource_group_name             = var.resource_group_name
  size                            = "Standard_B2ls_v2"
  admin_username                  = var.credentials["step_${var.step_index}_username"]
  admin_password                  = var.credentials["step_${var.step_index}_password"]
  disable_password_authentication = false
  network_interface_ids           = [azurerm_network_interface.this.id]

  identity {
    type = "SystemAssigned"
  }

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

# Give the managed identity Reader on the RG so the stolen token is
# useful for enumeration and lateral movement.
resource "azurerm_role_assignment" "reader" {
  scope                = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"
  role_definition_name = "Reader"
  principal_id         = azurerm_linux_virtual_machine.this.identity[0].principal_id
}

output "private_ip" {
  description = "Private IP of the web VM"
  value       = azurerm_network_interface.this.private_ip_address
}

output "vm_id" {
  description = "VM resource ID"
  value       = azurerm_linux_virtual_machine.this.id
}

output "managed_identity_principal_id" {
  description = "Principal ID of the VM managed identity (stolen via SSRF/IMDS)"
  value       = azurerm_linux_virtual_machine.this.identity[0].principal_id
}
