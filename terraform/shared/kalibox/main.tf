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

locals {
  use_custom_image = var.custom_image_id != ""
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

  # Only run cloud-init when using the marketplace image (no pre-built image)
  custom_data = local.use_custom_image ? null : base64encode(<<-EOF
    #cloud-config
    package_update: true
    runcmd:
      - export DEBIAN_FRONTEND=noninteractive
      - apt-get install -y -qq openssh-server xrdp xfce4 xfce4-goodies dbus-x11
      - systemctl enable ssh
      - systemctl start ssh
      - echo 'xfce4-session' > /home/${var.admin_username}/.xsession
      - chown ${var.admin_username}:${var.admin_username} /home/${var.admin_username}/.xsession
      - systemctl enable xrdp
      - systemctl restart xrdp
      - apt-get install -y -qq --fix-broken nmap metasploit-framework sqlmap john hydra nikto burpsuite aircrack-ng crackmapexec responder hashcat || true
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

        WORDLISTS
          /usr/share/wordlists/cloud-common.txt  (passwords)

        Good luck, operator.
        MOTD
      - chown ${var.admin_username}:${var.admin_username} /home/${var.admin_username}/Desktop/README.txt
      - mkdir -p /usr/share/wordlists
      - |
        cat > /usr/share/wordlists/cloud-common.txt << 'WLIST'
        password
        123456
        admin
        letmein
        welcome
        monkey
        master
        dragon
        login
        abc123
        admin123
        root
        toor
        pass
        test
        guest
        access
        iloveyou
        1234567890
        trustno1
        changeme
        P@ssw0rd
        P@ss1234
        Password1
        Password123!
        Welcome2025!
        Admin@1234
        Summer2025!
        Backup123!
        Service1!
        Passw0rd!
        Azure2025!
        Deploy123!
        Qwerty@123
        Winter2024!
        Autumn2025!
        Spring2025!
        Monday01!
        Server2025!
        Database1!
        Network1!
        Cloud123!
        DevOps2025!
        Secure@123
        Company1!
        Support1!
        Helpdesk1!
        Manager1!
        System@123
        Testing123!
        WLIST
      - sed -i 's/^[[:space:]]*//' /usr/share/wordlists/cloud-common.txt
      - sed -i '/^$/d' /usr/share/wordlists/cloud-common.txt
  EOF
  )

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 40
  }

  # Custom image: use source_image_id
  source_image_id = local.use_custom_image ? var.custom_image_id : null

  # Marketplace image: use source_image_reference + plan
  dynamic "source_image_reference" {
    for_each = local.use_custom_image ? [] : [1]
    content {
      publisher = "kali-linux"
      offer     = "kali"
      sku       = "kali-2025-2"
      version   = "latest"
    }
  }

  dynamic "plan" {
    for_each = local.use_custom_image ? [] : [1]
    content {
      name      = "kali-2025-2"
      publisher = "kali-linux"
      product   = "kali"
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
