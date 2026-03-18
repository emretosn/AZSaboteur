# VM with a system-assigned managed identity.
# The player reaches this VM (e.g. via lateral movement) and queries IMDS
# at 169.254.169.254 to steal a managed identity token.

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
  CLOUD
  )

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "vm-with-identity"
  }
}

# Give the managed identity Reader on the resource group so the stolen
# token is actually useful for enumeration/lateral movement.
resource "azurerm_role_assignment" "reader" {
  scope                = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"
  role_definition_name = "Reader"
  principal_id         = azurerm_linux_virtual_machine.this.identity[0].principal_id
}

data "azurerm_client_config" "current" {}

output "private_ip" {
  description = "Private IP of the VM"
  value       = azurerm_network_interface.this.private_ip_address
}

output "vm_id" {
  description = "VM resource ID"
  value       = azurerm_linux_virtual_machine.this.id
}

output "managed_identity_principal_id" {
  description = "Principal ID of the managed identity"
  value       = azurerm_linux_virtual_machine.this.identity[0].principal_id
}
