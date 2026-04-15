packer {
  required_plugins {
    azure = {
      source  = "github.com/hashicorp/azure"
      version = ">= 2.0.0"
    }
  }
}

variable "subscription_id" {
  type        = string
  description = "Azure subscription ID"
}

variable "region" {
  type    = string
  default = "westeurope"
}

variable "vm_size" {
  type    = string
  default = "Standard_D4s_v5"
  description = "VM size for the build (larger = faster install). Only used during image build."
}

variable "image_resource_group" {
  type    = string
  default = "rg-azsaboteur-images"
  description = "Resource group to store the managed image"
}

variable "image_name" {
  type    = string
  default = "kali-azsaboteur"
  description = "Name of the managed image"
}

source "azure-arm" "kali" {
  subscription_id = var.subscription_id
  use_azure_cli_auth = true

  os_type         = "Linux"
  image_publisher = "kali-linux"
  image_offer     = "kali"
  image_sku       = "kali-2025-2"

  plan_info {
    plan_name      = "kali-2025-2"
    plan_product   = "kali"
    plan_publisher = "kali-linux"
  }

  location = var.region
  vm_size  = var.vm_size

  managed_image_name                = var.image_name
  managed_image_resource_group_name = var.image_resource_group

  azure_tags = {
    project = "azsaboteur"
    role    = "kali-golden-image"
  }
}

build {
  sources = ["source.azure-arm.kali"]

  # Install desktop environment, xRDP, and Kali tools
  provisioner "shell" {
    environment_vars = [
      "DEBIAN_FRONTEND=noninteractive",
    ]
    inline = [
      "echo '=== Updating packages ==='",
      "sudo apt-get update -qq",
      "sudo apt-get upgrade -y -qq",

      "echo '=== Installing xRDP and desktop ==='",
      "sudo apt-get install -y -qq xrdp xfce4 xfce4-goodies dbus-x11",

      "echo '=== Installing Kali top 10 tools ==='",
      "sudo apt-get install -y -qq nmap metasploit-framework sqlmap john hydra nikto burpsuite aircrack-ng crackmapexec responder hashcat",

      "echo '=== Configuring xRDP ==='",
      "sudo systemctl enable xrdp",

      "echo '=== Cleaning up ==='",
      "sudo apt-get autoremove -y -qq",
      "sudo apt-get clean",
      "sudo rm -rf /var/lib/apt/lists/*",
    ]
  }

  # Set up xfce4 as the default session for any user that logs in via xRDP
  provisioner "shell" {
    inline = [
      "echo 'xfce4-session' | sudo tee /etc/skel/.xsession",
    ]
  }

  # Ship a small password wordlist for brute-force exercises
  provisioner "shell" {
    inline = [
      "sudo mkdir -p /usr/share/wordlists",
      <<-SCRIPT
      sudo tee /usr/share/wordlists/cloud-common.txt > /dev/null << 'WLIST'
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
      SCRIPT
    ]
  }

  # Generalise the VM so Azure can re-provision it with new credentials
  provisioner "shell" {
    execute_command = "chmod +x {{ .Path }}; {{ .Vars }} sudo -E sh '{{ .Path }}'"
    inline = [
      "/usr/sbin/waagent -force -deprovision+user && export HISTSIZE=0 && sync",
    ]
  }
}
