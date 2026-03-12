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
  default = "Standard_B2ms"
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

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "kali-linux"
    offer     = "kali"
    sku       = "kali-2025-1"
    version   = "latest"
  }

  plan {
    name      = "kali-2025-1"
    publisher = "kali-linux"
    product   = "kali"
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    role     = "kalibox"
  }
}

# Install xRDP + xfce4 so the player can RDP in with a desktop
resource "azurerm_virtual_machine_extension" "xrdp" {
  name                 = "install-xrdp"
  virtual_machine_id   = azurerm_linux_virtual_machine.this.id
  publisher            = "Microsoft.Azure.Extensions"
  type                 = "CustomScript"
  type_handler_version = "2.1"

  settings = jsonencode({
    commandToExecute = join(" && ", [
      "export DEBIAN_FRONTEND=noninteractive",
      "apt-get update -qq",
      "apt-get install -y -qq xrdp xfce4 xfce4-goodies dbus-x11",
      "systemctl enable xrdp",
      "systemctl start xrdp",
      "echo 'xfce4-session' > /home/${var.admin_username}/.xsession",
      "chown ${var.admin_username}:${var.admin_username} /home/${var.admin_username}/.xsession",
      "sed -i 's/^port=3389/port=3389/' /etc/xrdp/xrdp.ini",
      "systemctl restart xrdp",
    ])
  })

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
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
