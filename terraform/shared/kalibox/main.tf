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

variable "custom_image_id" {
  type        = string
  default     = ""
  description = "Resource ID of a pre-built Kali image. When set, skips cloud-init provisioning and marketplace plan."
}

variable "use_ubuntu_fallback" {
  type        = bool
  default     = false
  description = "Use Ubuntu instead of Kali marketplace image. Enables automatic fallback when marketplace purchase fails."
}

locals {
  use_custom_image = var.custom_image_id != ""
  # Three mutually exclusive image modes
  use_kali_marketplace = !local.use_custom_image && !var.use_ubuntu_fallback
  use_ubuntu_fallback  = !local.use_custom_image && var.use_ubuntu_fallback
  # Custom images built from the Kali marketplace still need the plan block
  needs_kali_plan = local.use_kali_marketplace || local.use_custom_image
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

  # Cloud-init runs when NOT using a pre-built Kali golden image (i.e. marketplace or Ubuntu fallback)
  custom_data = local.use_custom_image ? null : base64encode(<<-EOF
    #cloud-config
    package_update: true
    runcmd:
      - export DEBIAN_FRONTEND=noninteractive
      - apt-get install -y -qq openssh-server xrdp xorgxrdp xfce4 xfce4-goodies dbus-x11
      - systemctl enable ssh
      - systemctl start ssh
      - echo 'xfce4-session' > /home/${var.admin_username}/.xsession
      - chown ${var.admin_username}:${var.admin_username} /home/${var.admin_username}/.xsession
      - chmod +x /home/${var.admin_username}/.xsession
      - sed -i '/^exec/d' /etc/xrdp/startwm.sh
      - echo 'exec dbus-launch --exit-with-session xfce4-session' >> /etc/xrdp/startwm.sh
      - systemctl enable xrdp
      - systemctl restart xrdp
      - apt-get install -y -qq --fix-broken nmap metasploit-framework sqlmap john hydra nikto burpsuite aircrack-ng crackmapexec responder hashcat git || true
      - git clone --depth 1 https://github.com/danielmiessler/SecLists.git /usr/share/seclists || true
      - mkdir -p /home/${var.admin_username}/Desktop
      - |
        cat > /home/${var.admin_username}/Desktop/README.txt << 'MOTD'
        === AZSaboteur - Attack Lab ===

        You are on the attack machine inside an Azure virtual network.

        NETWORK LAYOUT
          Your machine : 10.13.37.0/28  (kali subnet)
          Target range : 10.13.37.16/28 (lab subnet)

        START HERE
          1. Scan the target range:  nmap -sV 10.13.37.16/28
          2. Find exposed services and weak credentials
          3. Exploit the chain - each step leads to the next
          4. Capture flags (format: AZS_F{xxxxxxxxxxxx})

        TOOLS AVAILABLE
          nmap, hydra, john, hashcat, sqlmap, nikto, crackmapexec,
          metasploit, burpsuite, responder, aircrack-ng

        TIPS
          Look for exposed web services, view page source for leaked credentials.
          Use discovered creds to SSH into targets and pivot through the chain.

        WORDLISTS (via SecLists)
          /usr/share/seclists/

        Good luck, operator.
        MOTD
      - chown ${var.admin_username}:${var.admin_username} /home/${var.admin_username}/Desktop/README.txt
  EOF
  )

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 40
  }

  # Custom image: use source_image_id
  source_image_id = local.use_custom_image ? var.custom_image_id : null

  # Marketplace Kali image: used when no custom image and no Ubuntu fallback
  dynamic "source_image_reference" {
    for_each = local.use_kali_marketplace ? [1] : []
    content {
      publisher = "kali-linux"
      offer     = "kali"
      sku       = "kali-2025-2"
      version   = "latest"
    }
  }

  dynamic "plan" {
    for_each = local.needs_kali_plan ? [1] : []
    content {
      name      = "kali-2025-2"
      publisher = "kali-linux"
      product   = "kali"
    }
  }

  # Ubuntu fallback image: used when Kali marketplace purchase fails
  dynamic "source_image_reference" {
    for_each = local.use_ubuntu_fallback ? [1] : []
    content {
      publisher = "Canonical"
      offer     = "0001-com-ubuntu-server-jammy"
      sku       = "22_04-lts-gen2"
      version   = "latest"
    }
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
