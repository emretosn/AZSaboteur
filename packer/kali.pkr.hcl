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
  default = "rg-AZSaboteur-images"
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
      "sudo apt-get install -y -qq xrdp xorgxrdp xfce4 xfce4-goodies dbus-x11",

      "echo '=== Installing Kali top 10 tools ==='",
      "sudo apt-get install -y -qq nmap metasploit-framework sqlmap john hydra nikto burpsuite aircrack-ng crackmapexec responder hashcat firefox-esr",

      "echo '=== Configuring xRDP ==='",
      "sudo ln -sf /lib/systemd/system/xrdp.service /etc/systemd/system/multi-user.target.wants/xrdp.service",

      "echo '=== Cleaning up ==='",
      "sudo apt-get autoremove -y -qq",
      "sudo apt-get clean",
      "sudo rm -rf /var/lib/apt/lists/*",
    ]
  }

  # Set up xfce4 as the default session for xRDP logins
  provisioner "shell" {
    inline = [
      "echo 'xfce4-session' | sudo tee /etc/skel/.xsession",
      "sudo chmod +x /etc/skel/.xsession",
      "echo 'xfce4-session' | sudo tee /etc/xrdp/startwm.sh.bak",
      "sudo sed -i 's|test -x /etc/X11/Xsession.*|exec dbus-launch --exit-with-session xfce4-session|' /etc/xrdp/startwm.sh || true",
      "sudo sed -i '/^exec/d' /etc/xrdp/startwm.sh",
      "echo 'exec dbus-launch --exit-with-session xfce4-session' | sudo tee -a /etc/xrdp/startwm.sh",
    ]
  }

  # Place the lab README on the desktop (in /etc/skel so every user gets it)
  provisioner "shell" {
    inline = [
      "sudo mkdir -p /etc/skel/Desktop",
      <<-SCRIPT
      sudo tee /etc/skel/Desktop/README.txt > /dev/null << 'MOTD'
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

Good luck, operator.
MOTD
      SCRIPT
    ]
  }

  # Generalise the VM so Azure can re-provision it with new credentials.
  # waagent may fail to talk to systemd — that's OK, the deprovision still
  # clears SSH keys, hostname, and user data which is all we need.
  provisioner "shell" {
    execute_command = "chmod +x {{ .Path }}; {{ .Vars }} sudo -E sh '{{ .Path }}'"
    expect_disconnect = true
    inline = [
      "/usr/sbin/waagent -force -deprovision+user; export HISTSIZE=0; sync",
    ]
  }
}
