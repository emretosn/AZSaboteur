variable "scenario_id" {
  type = string
}

variable "region" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "admin_username" {
  type    = string
  default = "kali"
}

variable "admin_password" {
  type      = string
  sensitive = true
}

variable "vm_size" {
  type    = string
  default = "Standard_B2s_v2"
}

resource "azurerm_public_ip" "this" {
  name                = "pip-kali-${var.scenario_id}"
  location            = var.region
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    role     = "kalibox"
  }
}

resource "azurerm_network_interface" "this" {
  name                = "nic-kali-${var.scenario_id}"
  location            = var.region
  resource_group_name = var.resource_group_name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.subnet_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.this.id
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    role     = "kalibox"
  }
}

resource "azurerm_linux_virtual_machine" "this" {
  name                            = "vm-kali-${var.scenario_id}"
  location                        = var.region
  resource_group_name             = var.resource_group_name
  size                            = var.vm_size
  admin_username                  = var.admin_username
  admin_password                  = var.admin_password
  disable_password_authentication = false
  network_interface_ids           = [azurerm_network_interface.this.id]

  # Install xRDP + xfce4 at boot via cloud-init so the player can RDP in
  custom_data = base64encode(<<-EOF
    #!/bin/bash
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq xrdp xfce4 xfce4-goodies dbus-x11
    echo 'xfce4-session' > /home/${var.admin_username}/.xsession
    chown ${var.admin_username}:${var.admin_username} /home/${var.admin_username}/.xsession
    systemctl enable xrdp
    systemctl restart xrdp
  EOF
  )

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 40
  }

  source_image_reference {
    publisher = "kali-linux"
    offer     = "kali"
    sku       = "kali-2025-2"
    version   = "latest"
  }

  plan {
    name      = "kali-2025-2"
    publisher = "kali-linux"
    product   = "kali"
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    role     = "kalibox"
  }
}

output "public_ip" {
  value = azurerm_public_ip.this.ip_address
}

output "private_ip" {
  value = azurerm_network_interface.this.private_ip_address
}

output "vm_id" {
  value = azurerm_linux_virtual_machine.this.id
}
